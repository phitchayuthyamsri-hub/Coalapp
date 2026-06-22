const $=(s)=>document.querySelector(s);
async function api(p,o){const r=await fetch(p,o);if(!r.ok)throw new Error(r.status);return r.json();}
async function table(){
  const d=await api('/api/gps_summary');
  $('#gpsTotals').textContent=`${d.plates} plates · ${d.total_pings} pings`;
  const tb=$('#gpsTable tbody');tb.innerHTML='';
  d.rows.forEach(r=>{const tr=document.createElement('tr');
    tr.innerHTML=`<td>${r.plate}</td><td>${r.pings}</td><td>${r.first}</td><td>${r.last}</td>`;tb.appendChild(tr);});
}
$('#gpsFile').addEventListener('change',async e=>{
  const f=e.target.files[0];if(!f)return;
  const fd=new FormData();fd.append('file',f);
  const rep=$('#gpsReplace').checked?'?replace=1':'';
  $('#gpsMsg').textContent='Uploading '+f.name+'…';
  try{const r=await api('/api/upload/gps'+rep,{method:'POST',body:fd});
    $('#gpsMsg').textContent=`${f.name}: ${r.added} pings loaded.`;table();}
  catch(err){$('#gpsMsg').textContent='Failed: '+err.message;}
  e.target.value='';
});
table();
