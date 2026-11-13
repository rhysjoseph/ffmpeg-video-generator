const $ = id => document.getElementById(id);
const form = $('settings');
const names = {smptehdbars:'HD SMPTE Bars',smptebars:'SMPTE Bars',pal75bars:'PAL 75%',pal100bars:'PAL 100%',scroll:'Moving Colour Bars',lipsync:'Lip Sync',sweep:'Side Sweep'};
const resolutions = {'3840x2160':'UHD 4K','2560x1440':'QHD','1920x1080':'Full HD','1280x720':'HD'};
const colours = {bt709:'BT.709 · SDR',bt2020:'BT.2020 · SDR',bt601_pal:'BT.601 PAL',bt601_ntsc:'BT.601 NTSC'};
const codecName = s => deliveryProfiles[s.delivery_profile]?.label || (s.codec==='hevc'||(s.codec==='auto'&&s.bit_depth===12)?'HEVC':'H.264');
const chromaName = value => value.split('').join(':');
const notes = {smptehdbars:'SMPTE HD colour bars, based on RP 219-2002.',smptebars:'Classic SMPTE bars, based on EG 1-1990. Converted to BT.709.',pal75bars:'EBU PAL colour bars at 75% levels. Converted to BT.709.',pal100bars:'EBU PAL colour bars at 100% levels. Converted to BT.709.',scroll:'HD colour bars scroll horizontally, completing a cycle every 8 seconds.',lipsync:'A white flash and 1 kHz beep repeat together every ~1 second. Silence mutes the beep.',sweep:'A narrow white vertical bar sweeps left to right every 2 seconds.'};
let activeId = null, healthy = false, previewUrl = null, previewBusy = false, previewSettings = '', lastJobs = '', posting = false, availableFormats = null, formatOK = true;
let logoAsset=null, uploadingLogo=false;
let deliveryProfiles={}, profilesLoaded=false, customEncoding=null, selectedProfile='custom';
const encodingFields=['bit_depth','chroma','video_range','codec','quality','preset'];
function logoSettings(){return {logo_id:logoAsset?.id||'',logo_position:form.elements.logo_position.value,...Object.fromEntries(['logo_width','logo_margin','logo_opacity'].map(k=>[k,Number(form.elements[k].value)]))};}
function settings(){const data=Object.fromEntries(new FormData(form));const output=form.elements.output_format.value;delete data.output_format;data.delivery_profile=deliveryProfiles[output]?output:'custom';data.container=deliveryProfiles[output]?.container||output;for(const key of encodingFields)data[key]=form.elements[key].value;data.duration=Number(data.duration);data.bit_depth=Number(data.bit_depth);data.timecode=form.elements.timecode.checked;data.freeze_box=form.elements.freeze_box.checked;data.field_order=form.elements.field_order.value;data.box_speed=form.elements.box_speed.value;return {...data,...logoSettings()};}
function error(message){$('error').textContent=message||'';$('error').hidden=!message;}
function update(){
  const profile=deliveryProfiles[form.elements.output_format.value];
  if(profile){
    if(selectedProfile==='custom')customEncoding=Object.fromEntries(encodingFields.map(key=>[key,form.elements[key].value]));
    form.elements.bit_depth.value=String(profile.bit_depth);form.elements.chroma.value=profile.chroma;form.elements.video_range.value='tv';form.elements.codec.value='auto';
  }else if(selectedProfile!=='custom'&&customEncoding){for(const key of encodingFields)form.elements[key].value=customEncoding[key];}
  selectedProfile=profile?form.elements.output_format.value:'custom';
  for(const key of encodingFields)form.elements[key].disabled=!!profile;
  form.elements.codec.querySelector('option[value="auto"]').textContent=profile?profile.label:'Auto · match bit depth';
  const twelve=form.elements.bit_depth.value==='12';
  form.elements.codec.querySelector('option[value="h264"]').disabled=twelve;
  if(twelve&&form.elements.codec.value==='h264')form.elements.codec.value='auto';
  const s=settings(), drop=['29.97p','59.94p','59.94i'].includes(s.rate), interlaced=s.rate.endsWith('i');
  form.elements.field_order.disabled=!interlaced;form.elements.box_speed.disabled=!s.freeze_box;
  $('pattern-note').textContent=notes[s.pattern].replace('Converted to BT.709.','Converted to the selected colour profile.');
  $('timecode-note').textContent=drop?'Drop-frame · starts at 00:00:00;00':'Non-drop · starts at 00:00:00:00 (DF does not apply at this rate)';
  $('rate-note').textContent=interlaced?(s.rate==='50i'?'25 frames / 50 fields per second.':'29.97 frames / 59.94 fields per second.')+' True interlace · top field first.':['23.98p','29.97p','59.94p'].includes(s.rate)?({'23.98p':'24000/1001','29.97p':'30000/1001','59.94p':'60000/1001'}[s.rate])+' progressive frames per second.':s.rate.slice(0,-1)+' progressive frames per second.';
  if(interlaced && s.resolution!=='1920x1080') $('rate-note').textContent+=' This resolution/interlace combination is nonstandard for broadcast delivery.';
  if(s.field_order==='bff')$('rate-note').textContent=$('rate-note').textContent.replace('top field first','bottom field first');
  const pixel='yuv'+s.chroma+'p'+(s.bit_depth>8?s.bit_depth+'le':'');
  const encoder=profile?.encoder||(codecName(s)==='HEVC'?'hevc':'h264');
  const badInterlace=interlaced&&(encoder==='hevc'||encoder==='dnxhd');
  formatOK=!badInterlace&&(!availableFormats||availableFormats[encoder]?.includes(pixel));
  $('encoding-note').textContent=badInterlace?'This profile requires a progressive frame rate. Choose ProRes or H.264 for interlaced output.':formatOK?(profile?codecName(s)+' · '+pixel+' encoder input. The selected profile controls compression; quality and speed settings do not apply.':codecName(s)+' · '+pixel+'. '+(twelve?'12-bit requires HEVC. ':'')+((s.bit_depth>8||s.chroma!=='420')?'Higher-depth and 4:2:2/4:4:4 playback requires a compatible player or NLE.':'H.264 8-bit 4:2:0 offers the broadest playback support.')):'Your FFmpeg cannot encode this combination. Choose another codec or format.';
  $('encoding-note').classList.toggle('problem',!formatOK);
  $('delivery-note').textContent=profile?profile.label+' in MOV with 24-bit PCM audio. '+(s.delivery_profile.startsWith('prores')?'ProRes supports progressive and interlaced output.':'DNxHR requires progressive output.')+(s.delivery_profile==='prores_4444'||s.delivery_profile==='prores_xq'?' 4444 uses 10-bit encoder input and decodes as 12-bit; the generated picture is opaque.':''):'Choose a container for custom encoding, or an editing profile to set codec, bit depth and chroma automatically.';
  const scale=2**(s.bit_depth-8);
  $('colour-note').textContent=colours[s.colour]+' · '+(s.video_range==='tv'?'Nominal Y '+(16*scale)+'–'+(235*scale)+', C '+(16*scale)+'–'+(240*scale):'Full scale 0–'+(2**s.bit_depth-1))+'. The picture is converted, with matching colour metadata.'+(s.colour==='bt2020'?' SDR transfer; no PQ or HLG.':'');
  $('audio-note').textContent=codecName(s)+' video · '+(s.container==='mov'?'24-bit PCM audio':'AAC audio')+' · 48 kHz '+(s.audio==='four_pairs'?'in four separate stereo tracks (1–2, 3–4, 5–6, 7–8).':'stereo.')+(s.container!=='mov'?' AAC may slightly change decoded peak levels.':'');
  $('summary-pattern').textContent=names[s.pattern];$('summary-video').textContent=resolutions[s.resolution]+' / '+s.rate;
  $('summary-audio').textContent=(s.audio==='four_pairs'?'8 channels':'2 channels')+' / '+(s.level==='silence'?'Silence':s.level.replace('-','−')+' dBFS');
  $('summary-delivery').textContent=(s.container==='ts'?'MPEG-TS':s.container.toUpperCase())+' / '+s.duration+' seconds';
  $('summary-signal').textContent=s.bit_depth+'-bit / '+chromaName(s.chroma)+' / '+(s.video_range==='tv'?'Limited':'Full');
  $('summary-colour').textContent=colours[s.colour];
  $('summary-encoding').textContent=profile?codecName(s):codecName(s)+' / '+s.quality+' / '+s.preset;
  if(!$('generator-panel').hidden)$('footer-format').textContent=codecName(s)+' · '+s.bit_depth+'-bit '+chromaName(s.chroma)+' · '+colours[s.colour];
  $('generate').disabled=!healthy||!formatOK||!!activeId||posting||uploadingLogo;
  if(!previewBusy)$('preview-button').disabled=!formatOK;
  if(previewSettings!==JSON.stringify(s)) $('preview-note').textContent='Settings changed. Refresh the frame to update the preview.';
}
form.addEventListener('input',update);form.addEventListener('change',update);
async function preview(){
  if(previewBusy)return;previewBusy=true;$('preview-button').disabled=true;$('preview-button').textContent='Rendering…';
  const s=settings();
  try{const response=await fetch('/api/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(s)});
    if(!response.ok)throw new Error((await response.json()).error);
    const url=URL.createObjectURL(await response.blob());if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=url;
    $('preview').src=url;$('preview').hidden=false;$('preview-empty').hidden=true;
    $('preview-format').textContent=s.resolution.replace('x',' × ');$('preview-rate').textContent=s.rate;
    $('preview-colour').textContent=colours[s.colour];
    previewSettings=JSON.stringify(s);$('preview-note').textContent='8-bit SDR display preview of the selected output. Motion and full bit depth are in the exported file.';update();
  }catch(exc){error('Preview: '+exc.message);$('preview-empty').textContent='Preview unavailable';}
  finally{previewBusy=false;$('preview-button').disabled=!formatOK;$('preview-button').textContent='Refresh frame ↻';}
}
$('preview-button').addEventListener('click',preview);
form.addEventListener('submit',async event=>{event.preventDefault();if(activeId||posting||!formatOK)return;posting=true;$('generate').disabled=true;error('');
  try{const response=await fetch('/api/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings())});const result=await response.json();if(!response.ok)throw new Error(result.error);activeId=result.id;await poll();}
  catch(exc){error(exc.message);}finally{posting=false;update();}
});
$('cancel').addEventListener('click',async()=>{if(!activeId)return;$('cancel').disabled=true;try{const response=await fetch('/api/cancel/'+activeId,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(!response.ok)throw new Error('Could not cancel render.');await poll();}catch(exc){error(exc.message);}finally{$('cancel').disabled=false;}});
function showJobs(jobs){
  const serialized=JSON.stringify(jobs.map(j=>({id:j.id,status:j.status,error:j.error,bytes:j.bytes})));if(serialized===lastJobs)return;lastJobs=serialized;
  const completed=jobs.filter(j=>j.status==='complete');$('export-count').textContent=completed.length+' '+(completed.length===1?'file':'files');
  $('jobs').replaceChildren();if(!jobs.length){const div=document.createElement('div');div.className='empty';div.textContent='Your finished test files will appear here.';$('jobs').append(div);return;}
  for(const job of jobs.slice(0,8)){
    const row=document.createElement('div');row.className='job';const top=document.createElement('div');top.className='job-top';const title=document.createElement('span');title.className='job-title';title.textContent=job.kind==='conversion'?job.conversion.label:names[job.settings.pattern];top.append(title);
    if(job.status==='complete'){const link=document.createElement('a');link.href='/download/'+job.id;link.download=job.filename;link.textContent='Download ↓';top.append(link);}else{const status=document.createElement('span');status.className='subtle';status.textContent=job.status;top.append(status);}
    const detail=document.createElement('small');detail.textContent=(job.kind==='conversion'?job.conversion.width+'×'+job.conversion.height+' · '+job.conversion.fps+' fps · '+job.conversion.duration.toFixed(2)+'s · '+job.conversion.container.toUpperCase():job.settings.resolution+' · '+job.settings.rate+' · '+job.settings.duration+'s · '+job.settings.container.toUpperCase())+(job.bytes?' · '+(job.bytes/1048576).toFixed(1)+' MB':'');row.append(top,detail);
    const signal=document.createElement('small');const saved={bit_depth:8,chroma:'420',colour:'bt709',codec:'auto',...job.settings};signal.textContent=job.kind==='conversion'?job.conversion.name:codecName(saved)+' · '+saved.bit_depth+'-bit '+chromaName(saved.chroma)+' · '+colours[saved.colour];row.append(signal);
    if(job.error){const reason=document.createElement('small');reason.className='job-error';reason.textContent=job.error;row.append(reason);}$('jobs').append(row);
  }
  $('convert-jobs').replaceChildren(...[...$('jobs').children].map(node=>node.cloneNode(true)));
}
async function poll(){
  try{const response=await fetch('/api/status');if(!response.ok)throw new Error('Server returned '+response.status);const data=await response.json();healthy=data.health.ready;
    $('health').textContent=healthy?'● FFMPEG CONNECTED':'● FFMPEG UNAVAILABLE';$('health').title=data.health.version||data.health.error;if(!healthy)error(data.health.error);
    availableFormats=data.health.encoder_formats||null;
    if(!profilesLoaded&&data.generation_profiles){
      deliveryProfiles=data.generation_profiles;
      for(const [key,p] of Object.entries(deliveryProfiles)){
        const option=document.createElement('option');option.value=key;option.textContent=p.label+' · MOV';option.disabled=!!availableFormats&&!availableFormats[p.encoder]?.includes(p.pixel_format);if(option.disabled)option.textContent+=' · unavailable';
        $(key.startsWith('prores')?'prores-profiles':'dnxhr-profiles').append(option);
      }
      profilesLoaded=true;
    }
    const active=data.jobs.find(j=>j.status==='rendering');activeId=active?active.id:null;update();
    $('generate').firstChild.textContent=active?'Generating video… ':'Generate video ';$('render-progress').hidden=!active;
    if(active){const percent=Math.floor(active.progress*100);$('progress').value=percent;$('progress-text').textContent=percent>=99?'Finalising file…':'Rendering · '+percent+'%';}
    showJobs(data.jobs);$('output-path').textContent='Saved to '+data.output_dir;
    window.updateConverterStatus?.(data,active);
  }catch(exc){healthy=false;$('health').textContent='● SERVER OFFLINE';$('generate').disabled=true;error('Cannot reach the local server. Start it with Start.command. '+exc.message);}
}
update();poll().then(()=>{if(healthy)preview();});setInterval(poll,1500);
