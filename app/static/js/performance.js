const $=(s)=>document.querySelector(s);
async function api(p){const r=await fetch(p);if(!r.ok)throw new Error(r.status);return r.json();}
const CODE={reloaded:'b-reloaded',planned:'b-planned',unassigned:'b-unassigned',fronthaul:'b-fronthaul',na:'b-na'};
async function loadPerf(){
  const d=await api('/api/performance');
  const cmp=d.avg_cycle_hours==null?'—':`${d.avg_cycle_hours}h vs ${d.plan_cycle_hours}h plan`;
  $('#perfCards').innerHTML=`
    <div class="kpi"><div class="kpi-v">${d.trucks}</div><div class="kpi-l">Trucks tracked</div></div>
    <div class="kpi"><div class="kpi-v">${d.completed_trips}</div><div class="kpi-l">Completed trips</div></div>
    <div class="kpi"><div class="kpi-v">${d.cycles}</div><div class="kpi-l">Cycles detected</div></div>
    <div class="kpi"><div class="kpi-v">${d.avg_cycle_hours==null?'—':d.avg_cycle_hours+'h'}</div><div class="kpi-l">Avg cycle (${cmp})</div></div>`;
  $('#perfHaul').innerHTML='<div class="legend">'+Object.entries(d.by_haul||{}).map(([k,v])=>`<span class="leg-item"><b>${k}</b>: ${v}</span>`).join('')+'</div>';
}
async function loadStatus(){
  const {rows,count}=await api('/api/status');
  $('#statusNote').textContent=`${count} trucks · ETA (raw)=distance÷speed · ETA (criteria) adds window waits`;
  const tb=$('#statusTable tbody');tb.innerHTML='';
  rows.forEach(r=>{const tr=document.createElement('tr');
    tr.innerHTML=`<td>${r.plate}</td><td>${r.haul}</td><td>${r.direction}</td><td>${r.next}</td>
      <td>${r.rem_km??''}</td><td>${r.eta_raw}</td><td>${r.eta_criteria}</td><td>${r.last_seen}</td>
      <td><span class="badge ${CODE[r.status_code]||''}" title="${r.status_detail}">${r.status}</span></td>`;
    tb.appendChild(tr);});
}
$('#stRefresh').addEventListener('click',loadStatus);
loadPerf();loadStatus();
