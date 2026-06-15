const $ = (s) => document.querySelector(s);

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

const ROLE_COLOR = {
  xppl: '#34c759', loading: '#00c7be', border: '#5ac8fa', ql49: '#ffd60a',
  ql49b: '#ff9f0a', ql49p: '#ff9f0a', port: '#0a84ff', detour: '#bf5af2', '': '#6b7280',
};
const ROLE_LABEL = {
  xppl: 'Mine', loading: 'Loading', border: 'Border', ql49: 'QL49',
  ql49b: 'QL49(b)', ql49p: 'QL49(p)', port: 'Port', detour: 'Detour', '': 'Other',
};

function fmtDur(m) {
  if (m < 60) return m + 'm';
  const h = Math.floor(m / 60), mm = m % 60;
  return mm ? `${h}h${mm}m` : `${h}h`;
}

function buildLegend() {
  const used = ['xppl', 'loading', 'border', 'ql49', 'ql49b', 'port', 'detour'];
  $('#tl_legend').innerHTML = used.map((r) =>
    `<span class="leg-item"><span class="dot" style="background:${ROLE_COLOR[r]}"></span>${ROLE_LABEL[r]}</span>`
  ).join('');
}

async function load() {
  const fr = $('#tl_from').value, to = $('#tl_to').value, plate = $('#tl_plate').value.trim();
  let url = '/api/visits?1=1';
  if (fr) url += '&from=' + fr;
  if (to) url += '&to=' + to;
  if (plate && plate.toLowerCase() !== 'all') url += '&plate=' + encodeURIComponent(plate);

  const data = await api(url);
  const body = $('#tl_body');
  body.innerHTML = '';
  if (!data.visits.length) { $('#tl_note').textContent = 'No visits in range.'; return; }

  const min = new Date(data.min).getTime();
  const max = new Date(data.max).getTime();
  const span = Math.max(1, max - min);
  $('#tl_note').textContent =
    `${data.visits.length} visits · ${new Date(min).toLocaleString()} → ${new Date(max).toLocaleString()}`;

  const byPlate = {};
  data.visits.forEach((v) => { (byPlate[v.plate] ||= []).push(v); });

  Object.keys(byPlate).sort().forEach((plate) => {
    const row = document.createElement('div');
    row.className = 'tl-row';
    const label = document.createElement('div');
    label.className = 'tl-label';
    label.textContent = plate;
    const track = document.createElement('div');
    track.className = 'tl-track';
    byPlate[plate].forEach((v) => {
      const e = new Date(v.enter).getTime(), x = new Date(v.exit).getTime();
      const seg = document.createElement('div');
      seg.className = 'tl-seg';
      seg.style.left = ((e - min) / span * 100) + '%';
      seg.style.width = Math.max(0.4, (x - e) / span * 100) + '%';
      seg.style.background = ROLE_COLOR[v.role] || ROLE_COLOR[''];
      seg.title = `${v.anchor_name}\n${new Date(v.enter).toLocaleString()} → ${new Date(v.exit).toLocaleString()}\n${fmtDur(v.dur_min)}${v.open ? ' (open)' : ''}`;
      track.appendChild(seg);
    });
    row.appendChild(label);
    row.appendChild(track);
    body.appendChild(row);
  });
}

buildLegend();
$('#tl_load').addEventListener('click', load);
load();
