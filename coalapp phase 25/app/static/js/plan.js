const $=(s)=>document.querySelector(s);
async function api(p,o){const r=await fetch(p,o);if(!r.ok)throw new Error(r.status);return r.json();}
async function table(){
  const d=await api('/api/plan_rows');$('#planCount').textContent=`${d.count} rows`;
  const tb=$('#planTable tbody');tb.innerHTML='';
  d.rows.forEach(r=>{const tr=document.createElement('tr');
    tr.innerHTML=`<td>${r.plate}</td><td>${r.load_start}</td><td>${r.port_arrive}</td>`;tb.appendChild(tr);});
}
$('#planFile').addEventListener('change',async e=>{
  const f=e.target.files[0];if(!f)return;const fd=new FormData();fd.append('file',f);
  $('#planMsg').textContent='Uploading '+f.name+'…';
  try{const r=await api('/api/upload/plan',{method:'POST',body:fd});
    $('#planMsg').textContent=`${f.name}: ${r.added} rows.`;table();}
  catch(err){$('#planMsg').textContent='Failed: '+err.message;}e.target.value='';
});
table();
