const $=(s)=>document.querySelector(s);
async function api(p,o){const r=await fetch(p,o);if(!r.ok)throw new Error(r.status);return r.json();}
const ROLES=['','xppl','loading','border','ql49','ql49b','ql49p','port','detour'];
let map;
async function load(){
  const anchors=await api('/api/anchors');
  const tb=$('#anchorTable tbody');tb.innerHTML='';
  anchors.forEach(a=>{
    const tr=document.createElement('tr');
    const opts=ROLES.map(r=>`<option value="${r}"${r===a.role?' selected':''}>${r||'—'}</option>`).join('');
    tr.innerHTML=`<td><span class="dot" style="background:${a.color}"></span>${a.name}</td>
      <td><select data-id="${a.id}" class="rolesel">${opts}</select></td>
      <td><input type="number" min="0" value="${a.min_dwell_min}" data-id="${a.id}" class="dwell" style="width:70px"></td>`;
    tb.appendChild(tr);
    if(a.polygon&&a.polygon.length)
      L.polygon(a.polygon,{color:a.color,weight:1,fillOpacity:0.12,interactive:false}).bindTooltip(a.name).addTo(map);
  });
  document.querySelectorAll('.rolesel').forEach(s=>s.onchange=e=>save(e.target.dataset.id,{role:e.target.value}));
  document.querySelectorAll('.dwell').forEach(s=>s.onchange=e=>save(e.target.dataset.id,{min_dwell_min:Number(e.target.value)}));
}
async function save(id,body){
  await api('/api/anchors/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  $('#paramMsg').textContent='Saved.';
}
function init(){
  map=L.map('map').setView([16.1,107.1],8);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(map);
  load();
}
init();
