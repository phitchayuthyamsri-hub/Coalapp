const $ = (s) => document.querySelector(s);

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
  return r.json();
}

let map, routeLayers = {}, drawer = null;
const LEG_COLOR = {
  mine_border: '#ff9f0a', border_ql49b: '#ffd60a', ql49b_ql49p: '#30d158',
  ql49p_port: '#0a84ff', port_mine: '#bf5af2', port_mine_ql49: '#ff453a',
};

function msg(t) { $('#routeMsg').textContent = t; }

async function drawAnchors() {
  try {
    const anchors = await api('/api/anchors');
    anchors.forEach((a) => {
      if (a.polygon && a.polygon.length) {
        L.polygon(a.polygon, { color: a.color, weight: 1, fillOpacity: 0.1, interactive: false })
          .bindTooltip(a.name).addTo(map);
      }
    });
  } catch (e) { /* map still works */ }
}

function clearLayer(key) {
  if (routeLayers[key]) { map.removeLayer(routeLayers[key]); delete routeLayers[key]; }
}

function showRoute(leg) {
  clearLayer(leg.leg_key);
  if (leg.points && leg.points.length > 1) {
    routeLayers[leg.leg_key] = L.polyline(leg.points,
      { color: LEG_COLOR[leg.leg_key] || '#4ea1ff', weight: 4 })
      .bindTooltip(leg.label).addTo(map);
  }
}

async function loadRoutes() {
  const legs = await api('/api/routes');
  const tb = $('#legTable tbody');
  tb.innerHTML = '';
  legs.forEach((leg) => {
    showRoute(leg);
    const n = leg.points ? leg.points.length : 0;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="dot" style="background:${LEG_COLOR[leg.leg_key] || '#4ea1ff'}"></span>${leg.label}</td>
      <td>${n || '<span class="muted">none</span>'}</td>
      <td><input type="number" min="1" value="${leg.speed}" data-leg="${leg.leg_key}" class="spd"></td>
      <td class="rowbtns">
        <button class="draw">Draw</button>
        <button class="del">Clear</button>
      </td>`;
    tr.querySelector('.draw').onclick = () => startDraw(leg.leg_key);
    tr.querySelector('.del').onclick = () => clearRoute(leg.leg_key);
    tr.querySelector('.spd').onchange = (e) => saveSpeed(leg.leg_key, e.target.value);
    tb.appendChild(tr);
  });
}

function startDraw(key) {
  if (drawer) drawer.disable();
  msg(`Drawing ${key} — click along the road, double-click to finish.`);
  drawer = new L.Draw.Polyline(map, {
    shapeOptions: { color: LEG_COLOR[key] || '#4ea1ff', weight: 4 },
  });
  drawer._coalLeg = key;
  drawer.enable();
}

async function savePoints(key, points) {
  try {
    await api('/api/routes/' + key, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ points }),
    });
    msg(`Saved ${key} (${points.length} points).`);
    loadRoutes();
  } catch (e) { msg('Save failed: ' + e.message); }
}

async function clearRoute(key) {
  await api('/api/routes/' + key, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ points: null }),
  });
  clearLayer(key);
  msg(`Cleared ${key}.`);
  loadRoutes();
}

async function saveSpeed(key, val) {
  await api('/api/routes/' + key, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ speed: Number(val) }),
  });
  msg(`Speed for ${key} set to ${val} km/h.`);
}

function init() {
  map = L.map('map').setView([16.1, 107.1], 8);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxZoom: 18, attribution: '© OpenStreetMap' }).addTo(map);
  map.on(L.Draw.Event.CREATED, (e) => {
    const key = drawer ? drawer._coalLeg : null;
    const pts = e.layer.getLatLngs().map((ll) => [ll.lat, ll.lng]);
    drawer = null;
    if (key) savePoints(key, pts);
  });
  drawAnchors();
  loadRoutes();
}
init();
