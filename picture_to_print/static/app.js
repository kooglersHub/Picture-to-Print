const $ = id => document.getElementById(id);
let currentJob = null;
let busy = false;
let previewUrl = null;
let allJobs = [];
let selectedJob = null;
let capabilities = null;
const toolNames = {meshlib:'MeshLib',blender:'Blender'};
const labels = {queued:'In der Warteschlange',generating:'3D-Modell entsteht',repairing:'Wird aufbereitet',ready:'Bereit zur Prüfung',failed:'Prüfung nötig',interrupted:'Unterbrochen'};
const messages = {queued:'Dein Auftrag ist gespeichert und startet automatisch.',generating:'Dein Motiv wird freigestellt und als 3D-Geometrie rekonstruiert. Der erste Start kann länger dauern.',repairing:'Wir schließen die Oberfläche, entfernen Innengeometrie und prüfen die Druckdateien.',ready:'Deine Dateien sind bereit. Prüfe die Figur und anschließend die Schichten in deinem Slicer.'};
async function api(path, options={}) {
  const response = await fetch(path,options);
  if (response.status===401) { showSession(false); throw new Error('Bitte erneut mit deinem Token anmelden.'); }
  if (!response.ok) { const value = await response.json().catch(()=>({})); throw new Error(typeof value.detail==='string' ? value.detail : 'Die Anfrage konnte nicht verarbeitet werden.'); }
  return response.json();
}
function showSession(authenticated) { $('login').hidden=authenticated; $('atelier').hidden=!authenticated; $('logout').hidden=!authenticated; }
async function login(token) {
  const response=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});
  if(!response.ok) throw new Error((await response.json()).detail || 'Anmeldung fehlgeschlagen');
  $('token').value=''; showSession(true); await loadCapabilities(); await refreshJobs();
}
async function loadCapabilities(){
  const health=await api('/api/health');capabilities=health.repair_tools||{};
  for(const id of ['backend','compare-backend']){
    for(const option of $(id).options){
      option.disabled=capabilities[option.value]===false;
      option.textContent=toolNames[option.value]+(option.disabled?' · nicht verfügbar':option.value==='meshlib'?' · Standard':' · Voxel-Remesh');
    }
    if($(id).selectedOptions[0]?.disabled){const available=[...$(id).options].find(option=>!option.disabled);if(available)$(id).value=available.value;}
  }
}
$('login-form').addEventListener('submit',async event=>{event.preventDefault();$('login-error').textContent='';try{await login($('token').value.trim());}catch(error){$('login-error').textContent=error.message;}});
$('logout').addEventListener('click',async()=>{await fetch('/auth/logout',{method:'POST'});currentJob=null;$('history-list').replaceChildren();showSession(false);});
$('file').addEventListener('change',()=>{
  const file=$('file').files[0]; if(!file)return;
  $('file-name').textContent=file.name;
  if(previewUrl)URL.revokeObjectURL(previewUrl);
  const image=/^image\//.test(file.type);
  $('photo-preview').hidden=!image;$('drop-copy').hidden=image;
  if(image){previewUrl=URL.createObjectURL(file);$('photo-preview').src=previewUrl;}
  $('create').firstChild.textContent=image?'Figur erstellen ':'Modell aufbereiten ';
});
for(const event of ['dragenter','dragover'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.add('drag');});
for(const event of ['dragleave','drop'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.remove('drag');});
$('dropzone').addEventListener('drop',event=>{if(event.dataTransfer.files.length){$('file').files=event.dataTransfer.files;$('file').dispatchEvent(new Event('change'));}});
$('job-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;busy=true;$('create').disabled=true;$('form-error').textContent='';
  try{const job=await api('/api/jobs',{method:'POST',body:new FormData(event.currentTarget)});currentJob=job.id;renderJob(job);await refreshJobs();}
  catch(error){$('form-error').textContent=error.message;}finally{busy=false;$('create').disabled=false;}
});
function metric(value,label){const box=document.createElement('div');box.className='metric';const number=document.createElement('b');number.textContent=value;box.append(number,document.createTextNode(label));return box;}
function renderJob(job){
  if(selectedJob?.id!==job.id){const alternate=job.settings.backend==='meshlib'?'blender':'meshlib';$('compare-backend').value=capabilities?.[alternate]===false?job.settings.backend:alternate;}
  selectedJob=job;
  currentJob=job.id;$('empty-state').hidden=true;$('job-state').hidden=false;
  $('job-name').textContent=job.name;$('status').textContent=labels[job.status]||job.status;
  $('job-message').textContent=job.error||messages[job.status]||'Du kannst die Druckaufbereitung erneut starten.';
  const stages=['queued','generating','repairing','ready'];const index=stages.indexOf(job.status);
  document.querySelectorAll('.timeline li').forEach(item=>item.classList.toggle('active',stages.indexOf(item.dataset.stage)<=index));
  const ready=job.status==='ready';$('viewer').hidden=!ready;$('downloads').hidden=!ready;$('review').hidden=!ready;
  renderComparison(job);
  $('metrics').replaceChildren();$('retry').hidden=!job.can_retry_repair||!['ready','failed','interrupted'].includes(job.status);
  if(ready){
    const source=job.artifacts['preview.glb'];if($('viewer').getAttribute('src')!==source)$('viewer').setAttribute('src',source);
    $('zip-link').href=job.artifacts['result.zip'];$('three-mf-link').href=job.artifacts['model.3mf'];$('stl-link').href=job.artifacts['model.stl'];$('report-link').href=job.artifacts['manifest.json'];
    $('metrics').append(metric(job.geometry.boundary_edges,'offene Kanten'),metric(job.geometry.components,'getrennte Teile'),metric(Math.max(...job.geometry.dimensions_mm).toFixed(1)+' mm','längste Seite'));
    let text='Prüfe Wandstärken, Stützen und die Schichten im Slicer. Die Geometrieprüfung ersetzt keine Druckfreigabe.';
    if(job.geometry.components>1)text=`Das Modell enthält ${job.geometry.components} getrennte Teile. Prüfe lose Fragmente und die Verbindung der Teile. `+text;
    if(job.review_reasons?.includes('large_surface_change'))text+=' Die Reparatur hat die Oberfläche deutlicher verändert; vergleiche sie mit deinem Motiv.';
    $('review-text').textContent=text;
  }
}
$('retry').addEventListener('click',async()=>{
  if(!currentJob)return;$('retry').disabled=true;
  const data=new FormData();data.set('size_mm',$('size').value);data.set('voxel_mm',$('voxel').value);data.set('backend',$('backend').value);
  try{renderJob(await api(`/api/jobs/${currentJob}/retry`,{method:'POST',body:data}));await refreshJobs();}
  catch(error){$('job-message').textContent=error.message;}finally{$('retry').disabled=false;}
});
function renderComparison(job){
  $('comparison').hidden=!job.can_retry_repair;
  if(!job.can_retry_repair)return;
  const settings=job.settings;
  $('comparison-settings').textContent=`Ausgewählt: ${toolNames[settings.backend]||settings.backend} · ${settings.size_mm} mm · ${settings.voxel_mm} mm Voxel`;
  const candidates=allJobs.filter(other=>{
    const sameRaw=job.raw_sha256&&other.raw_sha256===job.raw_sha256;
    const directlyRelated=other.id===job.id||other.source_job_id===job.id||job.source_job_id===other.id;
    return (sameRaw||directlyRelated)&&other.settings.size_mm===settings.size_mm&&other.settings.voxel_mm===settings.voxel_mm;
  });
  const rows=candidates.length?candidates:[job];$('comparison-rows').replaceChildren();
  for(const item of rows){
    const row=document.createElement('tr');
    const values=[toolNames[item.settings.backend]||item.settings.backend,labels[item.status],item.repair_seconds==null?'—':item.repair_seconds.toFixed(1)+' s',item.geometry?.boundary_edges??'—',item.geometry?.components??'—',item.surface_deviation?.sampled_p95_mm==null?'—':item.surface_deviation.sampled_p95_mm.toFixed(3)+' mm'];
    for(const value of values){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}
    const cell=document.createElement('td');const button=document.createElement('button');button.className='quiet';button.textContent=item.id===job.id?'Ausgewählt':'Ansehen';button.disabled=item.id===job.id;button.addEventListener('click',()=>{renderJob(item);$('job-state').scrollIntoView({behavior:'smooth',block:'start'});});cell.append(button);row.append(cell);$('comparison-rows').append(row);
  }
  $('compare-start').disabled=!['ready','failed','interrupted'].includes(job.status);
}
$('compare-start').addEventListener('click',async()=>{
  if(!selectedJob)return;
  const original=selectedJob;$('compare-start').disabled=true;$('compare-error').textContent='';
  const data=new FormData();data.set('size_mm',original.settings.size_mm);data.set('voxel_mm',original.settings.voxel_mm);data.set('backend',$('compare-backend').value);
  try{const job=await api(`/api/jobs/${original.id}/retry`,{method:'POST',body:data});renderJob(job);await refreshJobs();}
  catch(error){$('compare-error').textContent=error.message;}finally{$('compare-start').disabled=!selectedJob||!['ready','failed','interrupted'].includes(selectedJob.status);}
});
async function refreshJobs(){
  const jobs=await api('/api/jobs');allJobs=jobs;$('history-list').replaceChildren();
  for(const job of jobs){const row=document.createElement('button');row.className='history-row';const date=document.createElement('span');date.textContent=new Date(job.created_at).toLocaleDateString('de-DE');const name=document.createElement('b');name.textContent=job.name;const status=document.createElement('span');status.textContent=(toolNames[job.settings.backend]||job.settings.backend)+' · '+(labels[job.status]||job.status);row.append(date,name,status);row.addEventListener('click',()=>renderJob(job));$('history-list').append(row);}
  const selected=jobs.find(job=>job.id===currentJob)||(!currentJob&&jobs[0]);if(selected)renderJob(selected);
  $('connection').textContent='Privat verbunden · '+jobs.length+' Auftrag'+(jobs.length===1?'':'e');
}
async function initialize(){
  const fragment=new URLSearchParams(location.hash.slice(1));const token=fragment.get('token');
  if(token){history.replaceState(null,'',location.pathname);try{await login(token);return;}catch(error){$('login-error').textContent=error.message;}}
  try{const session=await fetch('/auth/session').then(r=>r.json());showSession(session.authenticated);if(session.authenticated){await loadCapabilities();await refreshJobs();}}catch{showSession(false);$('login-error').textContent='Die Verbindung konnte nicht hergestellt werden.';}
}
initialize();setInterval(()=>{if(!$('atelier').hidden)refreshJobs().catch(error=>{$('connection').textContent=error.message;});},5000);
