// Actual GPS Report — dashboard client (talks to the Flask JSON API)
const $ = (s) => document.querySelector(s);

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
  return r.json();
}

// ── Uploads ──────────────────────────────────────────────
document.querySelectorAll('.uploads input[type=file]').forEach((inp) => {
  inp.addEventListener('change', async () => {
    const file = inp.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    $('#uploadMsg').textContent = `Uploading ${file.name}…`;
    try {
      const res = await api(inp.dataset.ep, { method: 'POST', body: fd });
      $('#uploadMsg').textContent = `${file.name}: ${res.added} rows loaded.`;
      loadStatus();
    } catch (e) {
      $('#uploadMsg').textContent = `Upload failed: ${e.message}`;
    }
    inp.value = '';
  });
});

// ── Status table ─────────────────────────────────────────
async function loadStatus() {
  try {
    const { rows, count } = await api('/api/status');
    $('#statusNote').textContent =
      `${count} trucks · ETA (raw) = distance ÷ speed · ETA (criteria) adds operating-window waits`;
    const tb = $('#statusTable tbody');
    tb.innerHTML = '';
    rows.forEach((r) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${r.plate}</td><td>${r.haul}</td><td>${r.direction}</td>
        <td>${r.next}</td><td>${r.rem_km ?? ''}</td>
        <td>${r.eta_raw}</td><td>${r.eta_criteria}</td>
        <td>${r.last_seen}</td>
        <td><span class="badge b-${r.status_code}" title="${r.status_detail}">${r.status}</span></td>`;
      tb.appendChild(tr);
    });
  } catch (e) {
    $('#statusNote').textContent = 'Could not load status: ' + e.message;
  }
}
$('#refreshBtn').addEventListener('click', loadStatus);

// ── Map ──────────────────────────────────────────────────
async function loadMap() {
  const map = L.map('map').setView([16.1, 107.1], 8);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxZoom: 18, attribution: '© OpenStreetMap' }).addTo(map);
  try {
    const anchors = await api('/api/anchors');
    anchors.forEach((a) => {
      if (a.polygon && a.polygon.length) {
        L.polygon(a.polygon, { color: a.color, weight: 2, fillOpacity: 0.15 })
          .bindTooltip(a.name).addTo(map);
      }
    });
    const routes = await api('/api/routes');
    routes.forEach((r) => {
      if (r.points && r.points.length > 1) {
        L.polyline(r.points, { color: '#4ea1ff', weight: 3 })
          .bindTooltip(r.label).addTo(map);
      }
    });
  } catch (e) { /* map still usable */ }
}

loadStatus();
loadMap();
