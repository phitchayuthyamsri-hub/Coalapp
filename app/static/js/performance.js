const $=(s)=>document.querySelector(s);
async function api(p){const r=await fetch(p);if(!r.ok)throw new Error(r.status);return r.json();}
async function load(){
  const d=await api('/api/performance');
  const cycleCmp=d.avg_cycle_hours==null?'—':`${d.avg_cycle_hours}h vs ${d.plan_cycle_hours}h plan`;
  $('#perfCards').innerHTML=`
    <div class="kpi"><div class="kpi-v">${d.trucks}</div><div class="kpi-l">Trucks tracked</div></div>
    <div class="kpi"><div class="kpi-v">${d.completed_trips}</div><div class="kpi-l">Completed trips</div></div>
    <div class="kpi"><div class="kpi-v">${d.cycles}</div><div class="kpi-l">Cycles detected</div></div>
    <div class="kpi"><div class="kpi-v">${d.avg_cycle_hours==null?'—':d.avg_cycle_hours+'h'}</div><div class="kpi-l">Avg cycle (${cycleCmp})</div></div>`;
  const haul=Object.entries(d.by_haul||{}).map(([k,v])=>`<span class="leg-item"><b>${k}</b>: ${v}</span>`).join('');
  $('#perfHaul').innerHTML=`<div class="legend">${haul}</div>`;
}
load();
