const $ = (s) => document.querySelector(s);
async function api(p, o) { const r = await fetch(p, o); if (!r.ok) throw new Error(r.status); return r.json(); }

// ── Sub-tab switching ────────────────────────────────────
let mapInited = false, tlLoaded = false;
document.querySelectorAll('.subtab').forEach((b) => {
  b.addEventListener('click', () => {
    document.querySelectorAll('.subtab').forEach((x) => x.classList.remove('active'));
    b.classList.add('active');
    const tab = b.dataset.tab;
    document.querySelectorAll('.subpanel').forEach((p) => {
      p.style.display = p.dataset.panel === tab ? '' : 'none';
    });
    if (tab === 'route') { initMap(); setTimeout(() => map.invalidateSize(), 50); }
    if (tab === 'timeline' && !tlLoaded) { tlLoaded = true; loadTimeline(); }
  });
});

// ── Sequence table ───────────────────────────────────────
async function loadSequences() {
  const d = await api('/api/sequences');
  $('#seqCount').textContent = `${d.count} cycles`;
  const tb = $('#seqTable tbody'); tb.innerHTML = '';
  d.rows.forEach((r) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${r.plate}</td><td>${r.cycle_date}</td><td>${r.xppl_in}</td>
      <td>${r.loading_in}</td><td>${r.lalay_out_in}</td><td>${r.ql49_out_in}</td>
      <td>${r.chan_may_in}</td><td>${r.ql49_back_in}</td><td>${r.lalay_back_in}</td>
      <td>${r.xppl_r}</td><td>${r.backhaul_type}</td>
      <td>${r.complete ? '✓' : ''}</td>`;
    tb.appendChild(tr);
  });
}

// ── Route drawing ────────────────────────────────────────
let map, routeLayers = {}, drawer = null;
const LEG_COLOR = { mine_border:'#ff9f0a', border_ql49b:'#ffd60a', ql49b_ql49p:'#30d158',
  ql49p_port:'#0a84ff', port_mine:'#bf5af2', port_mine_ql49:'#ff453a' };
function msg(t){ $('#routeMsg').textContent = t; }
function initMap() {
  if (mapInited) return;
  mapInited = true;
  map = L.map('map').setView([16.1, 107.1], 8);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom:18, attribution:'© OpenStreetMap' }).addTo(map);
  map.on(L.Draw.Event.CREATED, (e) => {
    const key = drawer ? drawer._leg : null;
    const pts = e.layer.getLatLngs().map((ll) => [ll.lat, ll.lng]);
    drawer = null;
    if (key) savePoints(key, pts);
  });
  api('/api/anchors').then((as) => as.forEach((a) => {
    if (a.polygon && a.polygon.length)
      L.polygon(a.polygon, { color:a.color, weight:1, fillOpacity:0.1, interactive:false }).bindTooltip(a.name).addTo(map);
  }));
  loadRoutes();
}
function clearLayer(k){ if (routeLayers[k]) { map.removeLayer(routeLayers[k]); delete routeLayers[k]; } }
function showRoute(leg) {
  clearLayer(leg.leg_key);
  if (leg.points && leg.points.length > 1)
    routeLayers[leg.leg_key] = L.polyline(leg.points, { color: LEG_COLOR[leg.leg_key]||'#4ea1ff', weight:4 }).bindTooltip(leg.label).addTo(map);
}
async function loadRoutes() {
  const legs = await api('/api/routes');
  const tb = $('#legTable tbody'); tb.innerHTML = '';
  legs.forEach((leg) => {
    showRoute(leg);
    const n = leg.points ? leg.points.length : 0;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><span class="dot" style="background:${LEG_COLOR[leg.leg_key]||'#4ea1ff'}"></span>${leg.label}</td>
      <td>${n||'<span class="muted">none</span>'}</td>
      <td><input type="number" min="1" value="${leg.speed}" class="spd"></td>
      <td class="rowbtns"><button class="draw">Draw</button><button class="del">Clear</button></td>`;
    tr.querySelector('.draw').onclick = () => startDraw(leg.leg_key);
    tr.querySelector('.del').onclick = () => clearRoute(leg.leg_key);
    tr.querySelector('.spd').onchange = (e) => saveSpeed(leg.leg_key, e.target.value);
    tb.appendChild(tr);
  });
}
function startDraw(key) {
  if (drawer) drawer.disable();
  msg(`Drawing ${key} — click along the road, double-click to finish.`);
  drawer = new L.Draw.Polyline(map, { shapeOptions: { color: LEG_COLOR[key]||'#4ea1ff', weight:4 } });
  drawer._leg = key; drawer.enable();
}
async function savePoints(key, points) {
  await api('/api/routes/'+key, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({points}) });
  msg(`Saved ${key} (${points.length} points).`); loadRoutes();
}
async function clearRoute(key) {
  await api('/api/routes/'+key, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({points:null}) });
  clearLayer(key); msg(`Cleared ${key}.`); loadRoutes();
}
async function saveSpeed(key, val) {
  await api('/api/routes/'+key, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({speed:Number(val)}) });
  msg(`Speed for ${key} set to ${val}.`);
}

// ── Timeline ─────────────────────────────────────────────
const ROLE_COLOR = { xppl:'#34c759', loading:'#00c7be', border:'#5ac8fa', ql49:'#ffd60a',
  ql49b:'#ff9f0a', ql49p:'#ff9f0a', port:'#0a84ff', detour:'#bf5af2', '':'#6b7280' };
const ROLE_LABEL = { xppl:'Mine', loading:'Loading', border:'Border', ql49:'QL49',
  ql49b:'QL49(b)', ql49p:'QL49(p)', port:'Port', detour:'Detour', '':'Other' };
function fmtDur(m){ if (m<60) return m+'m'; const h=Math.floor(m/60),mm=m%60; return mm?`${h}h${mm}m`:`${h}h`; }
function buildLegend() {
  $('#tl_legend').innerHTML = ['xppl','loading','border','ql49','ql49b','port','detour']
    .map((r) => `<span class="leg-item"><span class="dot" style="background:${ROLE_COLOR[r]}"></span>${ROLE_LABEL[r]}</span>`).join('');
}
async function loadTimeline() {
  const fr=$('#tl_from').value, to=$('#tl_to').value, plate=$('#tl_plate').value.trim();
  let url='/api/visits?1=1';
  if (fr) url+='&from='+fr; if (to) url+='&to='+to;
  if (plate && plate.toLowerCase()!=='all') url+='&plate='+encodeURIComponent(plate);
  const data = await api(url);
  const body=$('#tl_body'); body.innerHTML='';
  if (!data.visits.length) { $('#tl_note').textContent='No visits in range.'; return; }
  const min=new Date(data.min).getTime(), max=new Date(data.max).getTime(), span=Math.max(1,max-min);
  $('#tl_note').textContent=`${data.visits.length} visits · ${new Date(min).toLocaleString()} → ${new Date(max).toLocaleString()}`;
  const byPlate={}; data.visits.forEach((v)=>{(byPlate[v.plate]||=[]).push(v);});
  Object.keys(byPlate).sort().forEach((plate)=>{
    const row=document.createElement('div'); row.className='tl-row';
    const label=document.createElement('div'); label.className='tl-label'; label.textContent=plate;
    const track=document.createElement('div'); track.className='tl-track';
    byPlate[plate].forEach((v)=>{
      const e=new Date(v.enter).getTime(), x=new Date(v.exit).getTime();
      const seg=document.createElement('div'); seg.className='tl-seg';
      seg.style.left=((e-min)/span*100)+'%';
      seg.style.width=Math.max(0.4,(x-e)/span*100)+'%';
      seg.style.background=ROLE_COLOR[v.role]||ROLE_COLOR[''];
      seg.title=`${v.anchor_name}\n${new Date(v.enter).toLocaleString()} → ${new Date(v.exit).toLocaleString()}\n${fmtDur(v.dur_min)}${v.open?' (open)':''}`;
      track.appendChild(seg);
    });
    row.appendChild(label); row.appendChild(track); body.appendChild(row);
  });
}
$('#tl_load').addEventListener('click', loadTimeline);

buildLegend();
loadSequences();
