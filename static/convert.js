const conversionForm=$('convert-settings');
let sourceAsset=null, conversionPlan=null, conversionValid=false, conversionUploading=false, conversionPosting=false, planSequence=0, planTimer=null, videoXHR=null;

function switchTool(which){
  for(const name of ['generator','converter']){const on=name===which;$(`${name}-tab`).setAttribute('aria-selected',String(on));$(`${name}-tab`).tabIndex=on?0:-1;$(`${name}-panel`).hidden=!on;}
  if(which==='converter')schedulePlan();else update();
}
for(const which of ['generator','converter']){
  $(`${which}-tab`).addEventListener('click',()=>switchTool(which));
  $(`${which}-tab`).addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const next=event.key==='Home'?'generator':event.key==='End'?'converter':which==='generator'?'converter':'generator';switchTool(next);$(`${next}-tab`).focus();}});
}

function uploadFile(file,kind,onProgress,receiveXHR){
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();receiveXHR?.(xhr);xhr.open('POST','/api/upload/'+kind);xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('X-Filename',encodeURIComponent(file.name));
    xhr.upload.onprogress=e=>{if(e.lengthComputable)onProgress(Math.floor(e.loaded/e.total*100));};
    xhr.onload=()=>{try{const item=JSON.parse(xhr.responseText);if(xhr.status>=400)throw new Error(item.error||'Upload failed');resolve(item);}catch(exc){reject(exc);}};
    xhr.onerror=()=>reject(new Error('Upload connection failed.'));xhr.onabort=()=>reject(new Error('Upload cancelled.'));xhr.send(file);
  });
}
$('logo-file').addEventListener('change',async()=>{
  const file=$('logo-file').files[0];if(!file)return;if(file.size>25*1024**2){error('Logo limit is 25 MB.');return;}
  uploadingLogo=true;$('logo-file').disabled=true;update();
  try{logoAsset=await uploadFile(file,'logo',p=>{$('logo-status').textContent='Uploading logo · '+p+'%';});$('logo-thumbnail').src='/logo/'+logoAsset.id;$('logo-loaded').hidden=false;$('logo-status').textContent=logoAsset.name+' · '+logoAsset.width+'×'+logoAsset.height;error('');}
  catch(exc){error(exc.message);$('logo-status').textContent='Upload failed. Choose another image.';}
  finally{uploadingLogo=false;$('logo-file').disabled=false;update();schedulePlan();}
});
$('remove-logo').addEventListener('click',()=>{logoAsset=null;$('logo-file').value='';$('logo-loaded').hidden=true;$('logo-status').textContent='Overlay removed. The local upload copy remains in uploads/.';update();schedulePlan();});
for(const name of ['logo_position','logo_width','logo_margin','logo_opacity'])form.elements[name].addEventListener('input',schedulePlan);

$('video-file').addEventListener('change',async()=>{
  const file=$('video-file').files[0];if(!file)return;if(file.size>20*1024**3){error('Video limit is 20 GB.');return;}
  conversionUploading=true;sourceAsset=null;conversionValid=false;$('source-details').hidden=true;$('video-file').disabled=true;$('upload-progress').hidden=false;$('cancel-upload').hidden=false;refreshConvertButton();
  try{sourceAsset=await uploadFile(file,'video',p=>{$('upload-progress').value=p;$('video-upload-status').textContent=p===100?'Inspecting video…':'Uploading locally · '+p+'%';},xhr=>videoXHR=xhr);
    const v=sourceAsset.video;$('video-upload-status').textContent='Source ready · '+(sourceAsset.bytes/1048576).toFixed(1)+' MB';
    $('source-details').textContent=sourceAsset.name+'\n'+v.width+' × '+v.height+' · '+v.codec_name+' · '+v.pix_fmt+'\n'+v.avg_frame_rate+' fps · '+sourceAsset.duration.toFixed(2)+' seconds\n'+sourceAsset.audio.length+' audio track(s) · '+(v.color_primaries||'untagged colour')+' / '+(v.color_transfer||'untagged transfer');$('source-details').hidden=false;error('');
  }catch(exc){error(exc.message);$('video-upload-status').textContent=exc.message;}
  finally{conversionUploading=false;$('video-file').disabled=false;$('upload-progress').hidden=true;$('cancel-upload').hidden=true;videoXHR=null;schedulePlan();}
});
$('cancel-upload').addEventListener('click',()=>videoXHR?.abort());
function conversionSettings(){const s=Object.fromEntries(new FormData(conversionForm));delete s.use_logo;for(const key of ['width','height','start','length','proxy_crf'])s[key]=Number(s[key]);s.source_id=sourceAsset?.id||'';return {...s,...logoSettings(),logo_id:conversionForm.elements.use_logo.checked?(logoAsset?.id||''):''};}
function refreshConvertButton(){$('convert-button').disabled=!healthy||!sourceAsset||!conversionValid||conversionUploading||uploadingLogo||conversionPosting||!!activeId;}
function schedulePlan(){
  clearTimeout(planTimer);planSequence++;conversionValid=false;refreshConvertButton();
  if(!$('converter-panel').hidden)$('footer-format').textContent='LOCAL VIDEO CONVERTER';
  const s=conversionSettings();$('custom-size').hidden=s.resolution!=='custom';$('proxy-options').hidden=!s.profile.startsWith('hevc');
  $('convert-profile-note').textContent=s.profile==='dnxhd_hq'?'DNxHD HQ requires 1920×1080 at 23.98, 24, 25, 29.97 or 30p. Use DNxHR for UHD or other sizes.':s.profile.startsWith('hevc')?'Compact inter-frame proxies. CRF 28 is a starting point; lower values improve quality.':'Editing-friendly intra-frame video in a MOV container. The selected profile determines bit depth and chroma.';
  $('conversion-logo-note').textContent=logoAsset?'Available logo: '+logoAsset.name:'Upload a logo in the generator tab first.';
  if(!sourceAsset){$('conversion-plan').textContent='Upload a video to prepare a conversion.';$('conversion-error').textContent='';return;}
  if(conversionForm.elements.use_logo.checked&&!logoAsset){$('conversion-error').textContent='Upload a logo or turn off Use uploaded logo.';return;}
  const seq=planSequence;planTimer=setTimeout(()=>loadPlan(seq,s),300);
}
async function loadPlan(seq,s){
  try{const response=await fetch('/api/conversion-plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(s)});const p=await response.json();if(seq!==planSequence)return;if(!response.ok)throw new Error(p.error);conversionPlan=p;conversionValid=true;$('conversion-error').textContent='';$('conversion-plan').textContent=p.label+'\n'+p.width+' × '+p.height+' · '+p.fps+' fps\n'+p.duration.toFixed(2)+' seconds · '+p.container.toUpperCase()+'\n'+p.pix_fmt+(p.hdr?'\nHDR transfer retained; no tone mapping.':'')+(s.logo_id?'\nLogo overlay enabled.':'');}
  catch(exc){if(seq===planSequence){conversionValid=false;$('conversion-error').textContent=exc.message;}}
  finally{refreshConvertButton();}
}
conversionForm.addEventListener('input',schedulePlan);conversionForm.addEventListener('change',schedulePlan);
conversionForm.addEventListener('submit',async event=>{event.preventDefault();if(!conversionValid||activeId||conversionPosting)return;conversionPosting=true;refreshConvertButton();error('');try{const response=await fetch('/api/convert',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(conversionSettings())});const result=await response.json();if(!response.ok)throw new Error(result.error);activeId=result.id;await poll();}catch(exc){error(exc.message);}finally{conversionPosting=false;refreshConvertButton();}});
$('cancel-convert').addEventListener('click',()=>$('cancel').click());
window.updateConverterStatus=(data,active)=>{
  refreshConvertButton();$('convert-progress').hidden=!active;$('convert-button').firstChild.textContent=active?'Processing video… ':'Convert video ';
    if(active){const percentage=Math.floor(active.progress*100);$('convert-progress-bar').value=percentage;$('convert-progress-text').textContent=(active.kind==='conversion'?'Converting':'Generating pattern')+' · '+percentage+'%';}
    if(!$('converter-panel').hidden&&conversionValid&&conversionPlan)$('footer-format').textContent=conversionPlan.label+' · '+conversionPlan.container.toUpperCase();
};
schedulePlan();
