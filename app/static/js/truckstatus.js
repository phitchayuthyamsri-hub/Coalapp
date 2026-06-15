const $=(s)=>document.querySelector(s);
async function api(p){const r=await fetch(p);if(!r.ok)throw new Error(r.status);return r.json();}
async function load(){
  const d=await api('/api/truckstatus');
  const th=$('#tsTable thead');th.innerHTML='';
  const tb=$('#tsTable tbody');tb.innerHTML='';
  const hr=document.createElement('tr');
  hr.innerHTML='<th class="rowhead">Plate</th>'+d.dates.map(dt=>`<th>${dt.slice(5)}</th>`).join('');
  th.appendChild(hr);
  d.plates.forEach(p=>{const tr=document.createElement('tr');
    tr.innerHTML=`<td class="rowhead">${p}</td>`+d.dates.map(dt=>{
      const v=d.cells[p][dt];return `<td class="${v?'has':'empty'}">${v||''}</td>`;}).join('');
    tb.appendChild(tr);});
  if(!d.plates.length) tb.innerHTML='<tr><td class="muted">No cycles yet — upload GPS.</td></tr>';
}
$('#tsRefresh').addEventListener('click',load);load();
