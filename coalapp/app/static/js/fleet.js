const $ = (s) => document.querySelector(s);

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
  return r.json();
}

const STATUS_CLASS = { online: 'b-reloaded', maintenance: 'b-planned',
                       breakdown: 'b-unassigned', deactivated: 'b-na' };

async function loadFleet() {
  const list = await api('/api/fleet');
  $('#fleetCount').textContent = `${list.length} trucks`;
  const tb = $('#fleetTable tbody');
  tb.innerHTML = '';
  list.forEach((t) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${t.plate}</td>
      <td><span class="badge ${STATUS_CLASS[t.status] || ''}">${t.status}</span></td>
      <td>${t.phone || ''}</td><td>${t.gps_provider || ''}</td>
      <td>${t.eff_from || ''}</td><td>${t.eff_to || ''}</td>
      <td class="rowbtns">
        <button class="edit">Edit</button>
        <button class="del">Delete</button>
      </td>`;
    tr.querySelector('.edit').onclick = () => fillForm(t);
    tr.querySelector('.del').onclick = () => delTruck(t.plate);
    tb.appendChild(tr);
  });
}

function fillForm(t) {
  $('#f_plate').value = t.plate;
  $('#f_status').value = t.status || 'online';
  $('#f_phone').value = t.phone || '';
  $('#f_gps').value = t.gps_provider || '';
  $('#f_from').value = t.eff_from || '';
  $('#f_to').value = t.eff_to || '';
  $('#f_plate').focus();
}

function clearForm() {
  ['f_plate', 'f_phone', 'f_gps', 'f_from', 'f_to'].forEach((id) => ($('#' + id).value = ''));
  $('#f_status').value = 'online';
}

async function save() {
  const plate = $('#f_plate').value.trim();
  if (!plate) { $('#fleetMsg').textContent = 'Plate is required.'; return; }
  try {
    await api('/api/fleet', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plate, status: $('#f_status').value, phone: $('#f_phone').value.trim(),
        gps_provider: $('#f_gps').value.trim(),
        eff_from: $('#f_from').value, eff_to: $('#f_to').value,
      }),
    });
    $('#fleetMsg').textContent = `Saved ${plate}.`;
    clearForm();
    loadFleet();
  } catch (e) { $('#fleetMsg').textContent = 'Save failed: ' + e.message; }
}

async function delTruck(plate) {
  if (!confirm(`Remove ${plate}?`)) return;
  await api('/api/fleet/' + encodeURIComponent(plate), { method: 'DELETE' });
  loadFleet();
}

$('#saveBtn').addEventListener('click', save);
loadFleet();
