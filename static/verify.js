const qcExport = $('qc-export');
let qcIds = '';
let qcUrl;
window.updateVerificationExports = jobs => {
  const complete = jobs.filter(job => job.status === 'complete');
  const ids = complete.map(job => job.id).join(',');
  if (ids === qcIds) return;
  const selected = qcExport.value;
  qcIds = ids;
  qcExport.replaceChildren(new Option('Choose a local file', ''));
  for (const job of complete) qcExport.add(new Option(job.filename, job.id));
  qcExport.value = selected;
  $('qc-file-label').hidden = Boolean(qcExport.value);
};
qcExport.addEventListener('change', () => { $('qc-file-label').hidden = Boolean(qcExport.value); });
$('qc-form').addEventListener('submit', async event => {
  event.preventDefault();
  const job = qcExport.value;
  const file = $('qc-file').files[0];
  const reference = $('qc-reference').files[0];
  const status = $('qc-status');
  $('qc-details').hidden = true;
  $('qc-summary').textContent = '';
  $('qc-run').disabled = true;
  try {
    if (!job && !file) throw new Error('Choose an export or local video.');
    const upload = async f => {
      const uploaded = await uploadFile(f, 'video', percent => {status.textContent = 'Uploading ' + f.name + ' · ' + percent + '%';});
      return uploaded.id;
    };
    const request = job ? {job_id:job} : {source_id:await upload(file)};
    request.loop = $('qc-loop').checked;
    if (reference) request.reference_id = await upload(reference);
    status.textContent = 'Decoding ' + (job ? qcExport.selectedOptions[0].text : file.name) + '…';
    const response = await fetch('/api/verify', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(request)});
    const report = await response.json();
    if (!response.ok) throw new Error(report.error);
    status.textContent = 'Verification · ' + report.status;
    const lines = [...report.errors, ...report.review];
    const scan = report.scan;
    if (scan) lines.push(scan.decoded_frames + ' frames decoded · ' + scan.consecutive_identical + ' identical neighbours · ' + scan.near_freezes + ' freeze events');
    if (scan?.cadence) lines.push(scan.cadence.timestamps + ' picture timestamps checked · maximum cadence error '
      + scan.cadence.max_error_ticks.toFixed(2) + ' ticks at time base ' + scan.cadence.time_base);
    for (const stream of report.inventory?.streams || []) {
      lines.push('Track ' + stream.index + ' · ' + [stream.codec_type, stream.codec_name, stream.profile, stream.pix_fmt,
        stream.width ? stream.width + ' × ' + stream.height : null, stream.avg_frame_rate && stream.codec_type === 'video' ? stream.avg_frame_rate + ' fps' : null,
        stream.field_order, stream.channel_layout, stream.tags?.timecode].filter(Boolean).join(' · '));
    }
    if (report.loop_boundary) lines.push('Loop join · mean RGB difference ' + report.loop_boundary.picture.seam_mean.toFixed(2) + ' codes · ' + report.loop_boundary.audio.length + ' audio tracks checked');
    if (report.comparison) lines.push(report.comparison.frames + ' frames compared against the reference.');
    $('qc-summary').textContent = lines.join('\n');
    const json = JSON.stringify(report, null, 2);
    $('qc-json').textContent = json;
    if (qcUrl) URL.revokeObjectURL(qcUrl);
    qcUrl = URL.createObjectURL(new Blob([json], {type:'application/json'}));
    $('qc-download').href = qcUrl;
    $('qc-details').hidden = false;
  } catch (exc) {
    status.textContent = exc.message;
  } finally {
    $('qc-run').disabled = false;
  }
});

const matrixControls = $('matrix-controls');
async function matrixStatus() {
  if (!matrixControls.open || $('verification-panel').hidden) return;
  try {
    const response = await fetch('/api/matrix');
    if (!response.ok) throw new Error('Could not read profile results.');
    const run = await response.json();
    $('matrix-start').disabled = run.state === 'running';
    $('matrix-status').textContent = [run.state, run.tested + ' tested', run.failed + ' failed',
      run.review + ' for review', run.unsupported + ' unsupported', run.latest].filter(Boolean).join(' · ');
    $('matrix-report').hidden = !run.tested && run.state !== 'failed';
  } catch (exc) { $('matrix-status').textContent = exc.message; }
}
function updateMatrixControls() {
  const fixed = $('matrix-suite').value !== 'profiles';
  for(const id of ['matrix-resolution','matrix-duration']) $(id).closest('label').hidden = fixed;
}
$('matrix-suite').addEventListener('change', updateMatrixControls);
updateMatrixControls();
matrixControls.addEventListener('toggle', matrixStatus);
$('matrix-start').addEventListener('click', async () => {
  $('matrix-start').disabled = true;
  try {
    const response = await fetch('/api/matrix', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify($('matrix-suite').value === 'profiles'
        ? {resolution:$('matrix-resolution').value, duration:Number($('matrix-duration').value) || null}
        : {suite:$('matrix-suite').value})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    await matrixStatus();
  } catch (exc) {
    $('matrix-status').textContent = exc.message;
    $('matrix-start').disabled = false;
  }
});
setInterval(matrixStatus, 3000);
