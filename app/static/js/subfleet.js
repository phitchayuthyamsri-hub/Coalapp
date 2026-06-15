const $=(s)=>document.querySelector(s);
async function api(p){const r=await fetch(p);if(!r.ok)throw new Error(r.status);return r.json();}
const GPS={'Returning':'b-planned','At mine':'b-reloaded','Not returning':'b-unassigned','No GPS':'b-na'};
async function load(){
  const d=await api('/api/subfleet');
  $('#sfNote').textContent=`${d.count} subcontractor trucks`;
  const tb=$('#sfTable tbody');tb.innerHTML='';
  d.rows.forEach(r=>{
    const dl=r.delta==null?'':(r.delta>0?'+':'')+r.delta;
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${r.plate}</td><td>${r.declared_haul}</td><td>${r.status}</td><td>${r.location}</td>
      <td>${r.claimed_arrive_mine}</td><td>${r.est_arrive_mine}</td><td>${dl}</td>
      <td><span class="badge ${GPS[r.gps_check]||''}">${r.gps_check}</span></td>`;
    tb.appendChild(tr);
  });
}
$('#sfRefresh').addEventListener('click',load);load();
