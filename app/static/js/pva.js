const $=(s)=>document.querySelector(s);
async function api(p){const r=await fetch(p);if(!r.ok)throw new Error(r.status);return r.json();}
const CODE={reloaded:'b-reloaded',planned:'b-planned',unassigned:'b-unassigned',fronthaul:'b-fronthaul',na:'b-na'};
async function load(){
  const d=await api('/api/pva');
  $('#pvaCards').innerHTML=`
    <div class="kpi"><div class="kpi-v">${d.ontime_pct==null?'—':d.ontime_pct+'%'}</div><div class="kpi-l">Port on-time (±1h)</div></div>
    <div class="kpi"><div class="kpi-v">${d.scored}</div><div class="kpi-l">Cycles scored</div></div>
    <div class="kpi"><div class="kpi-v">${d.total}</div><div class="kpi-l">Plan rows</div></div>`;
  const tb=$('#pvaTable tbody');tb.innerHTML='';
  d.rows.forEach(r=>{
    const tr=document.createElement('tr');
    const dl=r.port_delta==null?'':(r.port_delta>0?'+':'')+r.port_delta;
    tr.innerHTML=`<td>${r.plate}</td><td>${r.plan_load}</td><td>${r.actual_load}</td>
      <td>${r.plan_port}</td><td>${r.actual_port}</td><td>${dl}</td>
      <td><span class="badge ${CODE[r.code]||''}">${r.status}</span></td>`;
    tb.appendChild(tr);
  });
}
$('#pvaRefresh').addEventListener('click',load);load();
