'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => Number(value || 0).toLocaleString('en-US');
const tokens = value => value >= 1e6 ? `${(value / 1e6).toFixed(2)}M` : value >= 1e3 ? `${(value / 1e3).toFixed(1)}K` : number(value);
const taskName = value => ({stack_bowls:'叠碗',classify_objects:'物体分类',organize_table:'桌面整理',fold_clothes:'折衣',make_kong:'麻将',build_tower:'搭塔',imitate_sorting_sequence:'顺序模仿',pack_objects_into_box:'物品装箱',put_bottles_into_dustbin:'瓶子入桶'}[value] || value);
const cameraName = value => ({cam_high:'全景相机',cam_left_wrist:'左腕相机',cam_right_wrist:'右腕相机'}[value] || value);
const statuses = {running:'运行中',completed:'已完成',error:'异常结束',budget:'预算截断',incomplete:'未完整结束',unknown:'待核验'};
const badge = status => `<span class="badge ${esc(status)}"><i></i>${esc(statuses[status] || status)}</span>`;
const date = value => value ? new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}) : '—';
const state = {records:[], batches:[], line:'all', detail:null, active:null, traceTab:'calls', archive:false, selectedMedia:null, busy:false, noteDirty:false, activeCallId:null, evidencePhase:'after', pinCall:false, clipCall:null};
let toastTimer;
function toast(text) { $('toast').textContent=text; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,3000); }
async function api(path, options={}) {
  const response = await fetch(path, {...options, signal:AbortSignal.timeout(35000), headers:{'Content-Type':'application/json',...(options.headers||{})}});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function route() { const p=new URLSearchParams(location.hash.slice(1)); return {id:p.get('run'),call:p.get('call')}; }
function download(data, name) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const a=document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function resultLabel(row) {
  if (!row.valid_score) return '<span class="score-missing">—</span><div class="scope">尚无有效判分</div>';
  const label=row.native_success ? '成功' : '未成功';
  return `<span>${label}</span><div class="scope">原生分数 ${row.native_score == null ? '缺失' : esc(row.native_score)}</div>`;
}
function filtered() {
  const term=$('search').value.trim().toLowerCase(), status=$('status-filter').value;
  return state.records.filter(r=>(!state.archive||r.status!=='running')&&(state.line==='all'||r.line===state.line)&&(status==='all'||r.status===status)&&(!term||[r.name,r.id,r.task,r.model,r.harness].join(' ').toLowerCase().includes(term)));
}
function renderTable() {
  const rows=filtered();
  $('records-body').innerHTML=rows.length ? rows.map(r=>`<tr tabindex="0" data-id="${esc(r.id)}" aria-label="查看 ${esc(r.name)}"><td><div class="run-cell"><div class="run-icon ${r.line==='B'?'b':''}">⌘</div><div><div class="run-title">${esc(taskName(r.task))}<span class="scope"> · ${r.scope==='published'?'冻结评测':'开发验证'}</span></div><div class="run-subtitle" title="${esc(r.id)}">${esc(r.name)}</div></div></div></td><td><span class="harness-label ${r.line==='B'?'b':''}"><b>${esc(r.line)}</b>${esc(r.harness)}</span></td><td>${badge(r.status)}</td><td><div class="step-value">${number(r.steps)}<span>/ ${number(r.budget)}</span></div><div class="mini-track"><i style="width:${Math.min(100,100*r.steps/(r.budget||1))}%"></i></div></td><td>${tokens(r.tokens)}</td><td>${resultLabel(r)}</td><td class="arrow-cell">↗</td></tr>`).join('') : '<tr><td colspan="7" class="empty-state">没有符合条件的记录，试试其他筛选或登记新的实验目录。</td></tr>';
  $('visible-count').textContent=`显示 ${rows.length} 条，共 ${state.records.length} 条评测记录`;
  $('record-count').textContent=state.records.length;
  document.querySelectorAll('#records-body tr[data-id]').forEach(row=>{ row.onclick=()=>openRun(row.dataset.id); row.onkeydown=e=>{if(e.key==='Enter')openRun(row.dataset.id);}; });
}
function renderOverview() {
  const rows=state.records, live=rows.filter(r=>r.status==='running');
  $('metric-running').textContent=live.length.toString().padStart(2,'0');
  $('metric-total').textContent=rows.length.toString().padStart(2,'0');
  $('metric-steps').textContent=number(rows.reduce((a,r)=>a+r.steps,0));
  $('metric-scored').textContent=rows.filter(r=>r.valid_score).length.toString().padStart(2,'0');
  $('nav-count').textContent=live.length;
  const r=live[0]; $('spotlight').hidden=!r;
  if(r) {
    $('live-name').textContent=`${taskName(r.task)} / ${r.line} 线${r.scope==='published'?'配对评测':'开发运行'}`;
    $('live-subtitle').textContent=`${r.harness}  ·  ${r.model}`;
    $('live-progress').textContent=`${number(r.steps)} / ${number(r.budget)} 控制步`;
    $('live-percent').textContent=`${(100*r.steps/(r.budget||1)).toFixed(1)}%`;
    $('live-progress-bar').style.width=`${Math.min(100,100*r.steps/(r.budget||1))}%`;
    $('live-meta').innerHTML=`<span>${number(r.decisions)} 次有效执行</span><span>${tokens(r.tokens)} tokens</span><span>${esc(date(r.started_at))} 启动</span>`;
    if(r.images[0]) {if($('live-image').getAttribute('src')!==r.images[0].url)$('live-image').src=r.images[0].url; $('live-image').hidden=false;} else $('live-image').hidden=true;
    $('live-open').onclick=()=>openRun(r.id);
  }
  const batchLabels={preflight:'协议与资产校验',waiting_development_run:'等待开发运行收尾',development_run_finished:'开发运行已结束',waiting_resources:'等待显存与端口',running:'正在评测',case_finished:'当前案例已结束',finished:'本批执行结束',halt_incomplete:'结果未完成，队列已停',halt_controller_error:'控制器异常，队列已停',halt_infrastructure:'基础设施异常，队列已停',halt_missing_summary:'结果不完整，队列已停',halt_launcher_error:'启动异常，队列已停',halted_error:'队列异常',halted_model_unavailable:'模型服务不可用',interrupted:'队列已中断',halted_development_infrastructure:'开发运行基础设施异常，队列已停',halted_development_controller:'开发运行控制器异常，队列已停'};
  $('batch-banner').hidden=!state.batches.length;
  $('batch-banner').innerHTML=state.batches.map(b=>`<div class="batch-row"><div class="batch-symbol">↗</div><div><strong>网页任务配对评测 <span>${b.planned_tasks??10} 任务 · ${b.planned_cases??50} 案例</span></strong><p>${esc(batchLabels[b.status]||b.status)}${b.status==='waiting_development_run'?` · 叠碗当前 ${b.after_run_step??'—'} 步`:''}${b.current_case?` · ${esc(b.current_case)}${b.current_step==null?'':` · STEP ${b.current_step}`}`:''}</p></div><div class="batch-counts"><strong>${b.attempted_cases??0}<small> / ${b.planned_cases??50} 已尝试</small></strong><span>${b.complete_cases??0} 有效原生结果 · ${b.review_cases??0} 待核验</span></div></div>`).join('');
  renderTable();
}
function mediaButtons(row) {
  const images=row.images||[], videos=row.videos||[];
  const entries=[...images.map(i=>({key:i.camera,label:cameraName(i.camera),url:i.url,type:'image'})),...videos.filter(v=>v.available).map((v,i)=>({key:`video-${i}`,label:v.name,url:v.url,type:'video'}))];
  if(!entries.length){$('viewer').innerHTML='<div class="viewer-empty">暂无可展示的图像或视频<br>等待实验产生第一帧观测</div>'; $('camera-tabs').innerHTML=''; return;}
  let selected=entries.find(e=>e.key===state.selectedMedia)||entries.find(e=>row.status!=='running'&&e.type==='video')||entries[0];
  state.selectedMedia=selected.key;
  $('camera-tabs').innerHTML=entries.map(e=>`<button data-media="${esc(e.key)}" class="${e.key===selected.key?'selected':''}">${esc(e.label)}</button>`).join('');
  const old=$('viewer').firstElementChild;
  if(!old||old.dataset.mediaType!==selected.type||old.getAttribute('src')!==selected.url) {
    if(selected.type==='video') $('viewer').innerHTML=`<video src="${esc(selected.url)}" controls playsinline preload="metadata" data-media-type="video"></video>`;
    else $('viewer').innerHTML=`<img src="${esc(selected.url)}" alt="${esc(selected.label)}最新观测" data-media-type="image">`;
  }
  $('viewer-state').textContent=selected.type==='video'?'实验录像 · 支持拖动回放':'最新观测 · 随运行刷新';
  document.querySelectorAll('[data-media]').forEach(b=>b.onclick=()=>{state.selectedMedia=b.dataset.media;state.clipCall=null;mediaButtons(row);});
  const video=$('viewer').querySelector('video');if(video)bindVideo(video);
  $('video-links').innerHTML=videos.length?videos.map(v=>v.available?`<div>↗ <a href="${esc(v.url)}" target="_blank" rel="noopener">打开${esc(v.name)}</a> <small>${(v.bytes/1048576).toFixed(1)} MB</small></div>`:`<div>◌ ${esc(v.name)}仍在写入 <small>封装完成后自动开放播放</small></div>`).join(''):'<small>当前实验尚未生成视频文件。</small>';
}
function targetSummary(call) {
  const targets=call.targets||{};
  if(!targets.left&&!targets.right)return '<div class="target-unavailable">未记录结构化目标，完整参数见下方。</div>';
  const vector=value=>Array.isArray(value)?value.map(v=>typeof v==='number'?v.toFixed(4):String(v)).join(', '):'未记录';
  return `<div class="target-summary"><div class="target-heading">${call.status==='rejected'?'请求目标 · 未执行':'目标位置 XYZ · m'}<span>环境坐标 · 姿态 w,x,y,z</span></div>${['left','right'].map(arm=>{
    const t=targets[arm]||{};
    return `<div class="arm-target"><span class="arm-name">${arm==='left'?'左臂':'右臂'}</span><div><code>[${esc(vector(t.position))}]</code><small>q [${esc(vector(t.quaternion_wxyz))}]</small></div><span class="gripper ${t.gripper_closed===true?'closed':''}">${t.gripper_closed===true?'夹爪闭合':t.gripper_closed===false?'夹爪张开':'夹爪未记录'}</span></div>`;
  }).join('')}<div class="target-note">目标参数与夹爪指令不代表实际到位或抓取成功。</div></div>`;
}
function highlightCall(id, follow=false) {
  document.querySelectorAll('[data-call-id]').forEach(el=>el.classList.toggle('selected-call',el.dataset.callId===id));
  if(follow&&state.traceTab==='calls'){
    const list=$('trace-list'),el=list.querySelector(`[data-call-id="${CSS.escape(id)}"]`);
    if(el&&(el.offsetTop<list.scrollTop||el.offsetTop+Math.min(el.offsetHeight,180)>list.scrollTop+list.clientHeight))
      list.scrollTo({top:Math.max(0,el.offsetTop-18),behavior:'smooth'});
  }
}
function renderEvidence() {
  const call=state.detail?.calls.find(c=>c.id===state.activeCallId);
  if(!call){delete $('evidence-images').dataset.signature;$('evidence-call-label').textContent='选择右侧工具调用';$('evidence-images').innerHTML='<p class="empty-state">点击右侧调用，查看该次动作对应的相机图像。</p>';$('evidence-caption').textContent='';$('evidence-step').textContent='';return;}
  if(call.status!=='executed')state.evidencePhase='before';
  const phase=state.evidencePhase, observation=call.observations?.[phase];
  $('evidence-call-label').textContent=`${call.tool} · STEP ${call.step_start} → ${call.step_end??'待核验'}`;
  document.querySelectorAll('[data-phase]').forEach(b=>{b.classList.toggle('selected',b.dataset.phase===phase);b.disabled=b.dataset.phase==='after'&&call.status!=='executed';});
  $('evidence-step').textContent=observation?`STEP ${observation.step_id}`:'该步图像未保存';
  const images=observation?.images||[];
  const signature=call.id+'|'+phase+'|'+images.map(i=>i.url).join('|');
  if($('evidence-images').dataset.signature!==signature){
    $('evidence-images').dataset.signature=signature;
    $('evidence-images').innerHTML=images.length?images.map(i=>`<a class="evidence-image" href="${esc(i.url)}" target="_blank" rel="noopener" title="打开原始图像"><img src="${esc(i.url)}" alt="${esc(cameraName(i.camera))} STEP ${observation.step_id}" loading="lazy"><span>${esc(cameraName(i.camera))}<b>↗</b></span></a>`).join(''):'<p class="empty-state">该控制步没有保存对应图像，未用其他时刻的画面替代。</p>';
  }
  $('evidence-caption').textContent=call.status==='rejected'?'本次输入被拒绝，未执行物理动作、未产生动作后图像；此处显示调用时已有观测。':call.status==='uncertain'?'执行结果待核验，只展示已保存的动作前观测。':`${phase==='before'?'动作前':'动作后'}三相机观测。点击缩略图打开原图；图像按执行步对应，不按墙钟推理时间对应。`;
}
function selectCall(id,{play=false,seek=true}={}) {
  const call=state.detail?.calls.find(c=>c.id===id);if(!call)return;
  state.activeCallId=id;state.pinCall=true;state.evidencePhase=call.status==='executed'?'after':'before';
  highlightCall(id);renderEvidence();
  const videos=state.detail.videos.filter(v=>v.available);
  const videoIndex=videos.findIndex(v=>v.sync_available);
  if(seek&&videoIndex>=0){
    state.selectedMedia=`video-${videoIndex}`;mediaButtons(state.detail);
    const video=$('viewer').querySelector('video');video.pause();
    const go=()=>{
      const time=EvalTraceSync.timeForCall(call,state.detail.control_dt);
      if(time==null)return;
      video.currentTime=Math.max(0,Math.min(time,Math.max(0,video.duration-0.001)));
      $('playback-position').textContent=call.status==='executed'?`选中 ${call.tool} · STEP ${call.step_start} → ${call.step_end}`:'输入拒绝 / 执行待核验 · 无可归属的动作片段';
      if(play&&call.status==='executed'){state.clipCall=call;state.pinCall=false;video.play().catch(()=>{});}
    };
    if(video.readyState>=1)go();else video.addEventListener('loadedmetadata',go,{once:true});
  } else {
    const video=$('viewer').querySelector('video');if(video)video.pause();
    $('playback-position').textContent='录像尚不可联动 · 已显示本次调用对应图像';
  }
}
function syncPlayback(video,seconds=video.currentTime) {
  const available=state.detail?.videos.filter(v=>v.available)||[];
  const index=Number((state.selectedMedia||'').replace('video-',''));
  if(!available[index]?.sync_available){$('playback-position').textContent='此录像未声明控制步映射，未自动关联调用';return;}
  const dt=state.detail.control_dt;
  if(state.clipCall&&video.currentTime>=(state.clipCall.step_end+1)*dt-0.001){
    const call=state.clipCall;state.clipCall=null;video.pause();state.pinCall=true;video.currentTime=call.step_end*dt;
    $('playback-position').textContent=`动作回放结束 · STEP ${call.step_end}`;return;
  }
  if(video.paused&&state.pinCall)return;
  const frame=Math.floor(seconds/dt+1e-6);
  const call=EvalTraceSync.callAtTime(state.detail.calls,seconds,dt);
  $('playback-position').textContent=call?`FRAME ${frame} · ${call.tool} · STEP ${call.step_start} → ${call.step_end}`:frame===0?'FRAME 0 · 初始观测，尚无执行动作':`FRAME ${frame} · 没有可确认的调用归属`;
  if(!$('sync-follow').checked)return;
  if(call&&state.activeCallId!==call.id){state.activeCallId=call.id;state.evidencePhase='after';highlightCall(call.id,true);renderEvidence();}
  else if(!call){state.activeCallId=null;highlightCall(null);renderEvidence();}
}
function bindVideo(video) {
  if(video.dataset.syncBound)return;video.dataset.syncBound='true';
  let generation=0;
  const start=()=>{
    const current=++generation;
    const tick=(_time,metadata)=>{if(current!==generation||!video.isConnected||video.paused)return;syncPlayback(video,metadata?.mediaTime??video.currentTime);if(video.paused)return;if(video.requestVideoFrameCallback)video.requestVideoFrameCallback(tick);else requestAnimationFrame(tick);};
    tick();
  };
  video.addEventListener('play',()=>{state.pinCall=false;start();});
  video.addEventListener('pause',()=>{generation++;});
  video.addEventListener('timeupdate',()=>syncPlayback(video));
  video.addEventListener('seeked',()=>syncPlayback(video));
  video.addEventListener('pointerdown',()=>{state.clipCall=null;state.pinCall=false;});
  video.addEventListener('keydown',()=>{state.clipCall=null;state.pinCall=false;});
}
function renderTrace(row) {
  const list=$('trace-list'), scroll=list.scrollTop;
  const open=new Set([...list.querySelectorAll('details[open]')].map(d=>d.dataset.id));
  const filter=$('call-filter').value;
  $('call-count').textContent=`${row.calls.length} 次调用`;
  $('call-filter').hidden=state.traceTab!=='calls';
  if(state.traceTab==='calls') {
    const calls=row.calls.filter(c=>filter==='all'||c.status===filter).slice().reverse();
    list.innerHTML=calls.length?calls.map(c=>`<article tabindex="0" aria-label="查看 ${esc(c.tool)} STEP ${c.step_start} 的录像与图像" class="call ${esc(c.status)} ${c.id===state.activeCallId?'selected-call':''}" data-call-id="${esc(c.id)}"><div class="call-header"><code>${esc(c.tool)}</code><span>STEP ${c.step_start??'—'} → ${c.step_end??'—'} <a class="call-permalink" href="#run=${encodeURIComponent(row.id)}&amp;call=${encodeURIComponent(c.id)}" title="此调用的独立链接">↗</a></span></div><p>${esc(c.reason||'机器人控制调用')}</p>${targetSummary(c)}<div class="call-meta"><span>${c.status==='executed'?'已执行':c.status==='rejected'?'输入拒绝 · 未执行':'执行待核验'}</span><span>${c.executed_steps==null?'—':number(c.executed_steps)} 物理步</span><button class="seek-button" data-select-call="${esc(c.id)}">对应图像 ↗</button>${c.status==='executed'?`<button class="seek-button" data-play-call="${esc(c.id)}">回放此动作 ▷</button>`:''}</div><details data-id="${esc(c.id)}" ${open.has(c.id)?'open':''}><summary>参数与调用详情</summary><pre>${esc(JSON.stringify(c.arguments,null,2))}</pre></details></article>`).join(''):'<div class="empty-state">暂无此类工具调用。</div>';
    list.querySelectorAll('[data-select-call]').forEach(b=>b.onclick=()=>selectCall(b.dataset.selectCall));
    list.querySelectorAll('[data-play-call]').forEach(b=>b.onclick=()=>selectCall(b.dataset.playCall,{play:true}));
    list.querySelectorAll('[data-call-id]').forEach(el=>{
      el.onclick=event=>{if(!event.target.closest('button,a,details'))selectCall(el.dataset.callId);};
      el.onkeydown=event=>{if(event.target===el&&(event.key==='Enter'||event.key===' ')){event.preventDefault();selectCall(el.dataset.callId);}};
    });
  } else {
    const events=row.events.slice().reverse();
    list.innerHTML=events.length?'<div class="subtle" style="padding:15px 0 0">此处包含模型自述，不代表物理执行或原生成功。</div>'+events.map(e=>`<article class="event"><div class="event-head"><b>${esc(({agentMessage:'Agent 消息',commandExecution:'命令执行',imageView:'图像查看',assistant:'Agent 消息',tool:'工具反馈'})[e.type]||e.type)}</b><span>${e.step==null?'':`STEP ${e.step}`}${e.exit_code==null?'':` · EXIT ${e.exit_code}`}</span></div>${e.type==='commandExecution'?`<pre>${esc(e.text)}</pre>`:`<p>${esc(e.text||'图像查看完成')}</p>`}</article>`).join(''):'<div class="empty-state">当前运行未保存可展示的 Agent 活动。</div>';
  }
  list.scrollTop=scroll;
}
function renderDetail(row, initial=false) {
  $('detail-name').textContent=row.name;
  $('detail-eyebrow').textContent=`${row.line} LINE / ${row.scope==='published'?'PUBLISHED EVALUATION':'DEVELOPMENT RUN'}`;
  $('detail-model').textContent=`${taskName(row.task)} · ${row.harness} · ${row.model}`;
  $('detail-status').innerHTML=badge(row.status);
  $('detail-stats').innerHTML=`<div class="detail-stat"><span>已执行控制步 / 本轮预算</span><strong>${number(row.steps)}<small>/ ${number(row.budget)}</small></strong></div><div class="detail-stat"><span>已确认有效执行</span><strong>${number(row.decisions)}<small>次</small></strong></div><div class="detail-stat"><span>累计模型 Tokens</span><strong>${tokens(row.tokens)}</strong></div><div class="detail-stat"><span>原生任务结果</span><strong style="font-size:17px">${row.valid_score?(row.native_success?'成功':'未成功'):'尚无有效判分'}</strong></div>`;
  const fields=[['运行 ID',row.id],['任务',row.task],['Harness',row.harness],['模型',row.model],['实验类型',row.scope==='published'?'网页冻结案例':'开发链路验证'],['启动时间',date(row.started_at)],['最新产物',date(row.updated_at)],['提示协议',row.prompt_protocol||'未记录'],['预览长边',row.image_max_edge?row.image_max_edge+' px':'未记录'],['上下文上限',row.context_window?number(row.context_window)+' tokens':'未记录'],['原生步数上限',number(row.native_horizon)],['连续工具闭环',row.tool_loop_observed?'已观察到连续动作与执行回执':'待核验（其他 harness 以原始轨迹为准）'],['本轮有效预算',`${number(row.budget)}${row.budget_guard?' · 外部守护收尾':''}`],['启动快照预算',number(row.original_budget)],['原始状态',row.raw_status],['原生分数',row.native_score==null?'缺失，未补零':row.native_score],['案例 ID',row.case_id||'独立开发任务'],['产物目录',`artifacts/${row.relative_path}`]];
  if(row.error)fields.push(['异常信息',row.error]);
  $('provenance').innerHTML=fields.map(([k,v])=>`<div class="provenance-row"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('');
  if(initial||!state.noteDirty)$('notes').value=row.notes||'';
  mediaButtons(row);renderTrace(row);renderEvidence();
}
async function openRun(id,callId=null) {
  $('viewer').querySelector('video')?.pause();state.detail=null;
  state.active=id;state.selectedMedia=null;state.noteDirty=false;state.activeCallId=null;state.clipCall=null;state.pinCall=false;
  $('overview').hidden=true;$('detail').hidden=false;$('breadcrumb').textContent='运行详情';
  $('detail-name').textContent='读取运行记录…';
  history.replaceState(null,'',`#run=${encodeURIComponent(id)}${callId?'&call='+encodeURIComponent(callId):''}`);
  window.scrollTo({top:0});
  try {const row=await api(`/api/run/${encodeURIComponent(id)}`);if(state.active!==id)return;state.detail=row;if(callId){state.traceTab='calls';$('call-filter').value='all';document.querySelectorAll('#trace-tabs button').forEach(b=>b.classList.toggle('selected',b.dataset.tab==='calls'));}renderDetail(row,true);if(callId){selectCall(callId);const call=document.querySelector(`[data-call-id="${CSS.escape(callId)}"]`);if(call){call.querySelector('details').open=true;call.scrollIntoView({behavior:'smooth',block:'center'});}}}
  catch(error){showError(`读取详情失败：${error.message}`);}
}
function overview() {
  $('viewer').querySelector('video')?.pause();
  state.active=null;state.detail=null;state.noteDirty=false;$('overview').hidden=false;$('detail').hidden=true;$('breadcrumb').textContent='评测总览';
  history.replaceState(null,'',location.pathname);renderTable();
}
function showError(message) {$('error-banner').textContent=message;$('error-banner').hidden=false;$('sync-state').textContent='连接中断 · 保留上次数据';}
async function refresh(manual=false) {
  if(state.busy)return;state.busy=true;
  try {
    const data=await api('/api/records');state.records=data.records;state.batches=data.batches||[];
    $('host-name').textContent=data.host;$('update-label').textContent=`最新读取 ${date(data.updated_at)} · ${data.read_errors.length?`${data.read_errors.length} 条记录读取异常`:'直接读取实验产物'}`;
    $('error-banner').hidden=true;$('sync-state').innerHTML='<i class="live-dot"></i>实时读取';
    renderOverview();
    if(state.active) {
      const row=await api(`/api/run/${encodeURIComponent(state.active)}`);state.detail=row;renderDetail(row);
    }
    if(data.read_errors.length){$('error-banner').textContent=`部分记录读取异常：${data.read_errors.map(e=>e.id).join('、')}。其他记录仍可查看。`;$('error-banner').hidden=false;}
    if(manual)toast('已读取最新评测产物');
  }catch(error){showError(`数据读取失败：${error.message}。页面保留上次结果，稍后自动重试。`);}finally{state.busy=false;}
}
$('refresh').onclick=()=>refresh(true);
$('search').oninput=renderTable;$('status-filter').onchange=renderTable;
document.querySelectorAll('#line-tabs button').forEach(b=>b.onclick=()=>{state.line=b.dataset.line;document.querySelectorAll('#line-tabs button').forEach(x=>x.classList.toggle('selected',x===b));renderTable();});
function nav(id,status='all'){state.archive=id==='nav-archive';overview();$('status-filter').value=status;document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active',b.id===id));renderTable();if(id!=='nav-overview')$('records-body').scrollIntoView({behavior:'smooth',block:'center'});}
$('nav-overview').onclick=()=>nav('nav-overview');$('nav-running').onclick=()=>nav('nav-running','running');$('nav-archive').onclick=()=>{nav('nav-archive');$('search').value='';renderTable();};
$('back-button').onclick=overview;
$('export-index').onclick=()=>download({schema:'agent_action.evaluation_observatory.v1',exported_at:new Date().toISOString(),records:filtered()},'evaluation-records.json');
$('export-run').onclick=()=>state.detail&&download(state.detail,`${state.detail.id.replaceAll('/','-')}.json`);
$('notes').oninput=()=>{state.noteDirty=true;$('notes-status').textContent='有未保存的修改';};
$('save-notes').onclick=async()=>{if(!state.active)return;try{await api(`/api/notes/${encodeURIComponent(state.active)}`,{method:'POST',body:JSON.stringify({notes:$('notes').value})});state.noteDirty=false;$('notes-status').textContent='已保存到实验目录';toast('实验备注已保存');}catch(e){toast(`保存失败：${e.message}`);}};
document.querySelectorAll('[data-phase]').forEach(b=>b.onclick=()=>{state.evidencePhase=b.dataset.phase;renderEvidence();});
$('call-filter').onchange=()=>state.detail&&renderTrace(state.detail);
document.querySelectorAll('#trace-tabs button').forEach(b=>b.onclick=()=>{state.traceTab=b.dataset.tab;document.querySelectorAll('#trace-tabs button').forEach(x=>x.classList.toggle('selected',x===b));if(state.detail)renderTrace(state.detail);});
$('register-button').onclick=()=>$('register-dialog').showModal();$('close-register').onclick=()=>$('register-dialog').close();
$('register-form').onsubmit=async event=>{event.preventDefault();$('register-error').textContent='';const body=Object.fromEntries(new FormData(event.target));try{const result=await api('/api/register',{method:'POST',body:JSON.stringify(body)});$('register-dialog').close();event.target.reset();await refresh();openRun(result.id);toast('已登记评测目录');}catch(e){$('register-error').textContent=e.message;}};
window.addEventListener('hashchange',()=>{const r=route();if(r.id)openRun(r.id,r.call);else overview();});
refresh().then(()=>{const r=route();if(r.id)openRun(r.id,r.call);});
setInterval(()=>{if(!document.hidden)refresh();},15000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
