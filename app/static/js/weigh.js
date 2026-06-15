const $=(s)=>document.querySelector(s);
async function api(p,o){const r=await fetch(p,o);if(!r.ok)throw new Error(r.status);return r.json();}
async function table(){
  const d=await api('/api/load_rows');$('#weighCount').textContent=`${d.count} tickets`;
  const tb=$('#weighTable tbody');tb.innerHTML='';
  d.rows.forEach(r=>{const tr=document.createElement('tr');
    tr.innerHTML=`<td>${r.plate}</td><td>${r.load_in}</td><td>${r.net?Number(r.net).toLocaleString():''}</td><td>${r.ticket||''}</td>`;tb.appendChild(tr);});
}
$('#weighFile').addEventListener('change',async e=>{
  const f=e.target.files[0];if(!f)return;const fd=new FormData();fd.append('file',f);
  $('#weighMsg').textContent='Uploading '+f.name+'…';
  try{const r=await api('/api/upload/load',{method:'POST',body:fd});
    $('#weighMsg').textContent=`${f.name}: ${r.added} tickets.`;table();}
  catch(err){$('#weighMsg').textContent='Failed: '+err.message;}e.target.value='';
});
table();
