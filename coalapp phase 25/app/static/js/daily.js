const $=(s)=>document.querySelector(s);
async function api(p){const r=await fetch(p);if(!r.ok)throw new Error(r.status);return r.json();}
async function load(){
  const d=await api('/api/daily');
  const max=Math.max(1,...d.series.map(s=>s.port_arrivals));
  $('#dailyChart').innerHTML=d.series.map(s=>`
    <div class="bar-col" title="${s.date}: ${s.port_arrivals} port arrivals">
      <div class="bar" style="height:${s.port_arrivals/max*100}%"></div>
      <div class="bar-x">${s.date.slice(5)}</div>
    </div>`).join('')||'<span class="muted">No data yet.</span>';
  const tb=$('#dailyTable tbody');tb.innerHTML='';
  d.series.forEach(s=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${s.date}</td><td>${s.port_arrivals}</td><td>${s.loads}</td><td>${s.tonnes||''}</td>`;
    tb.appendChild(tr);
  });
}
load();
