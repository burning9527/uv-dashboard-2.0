/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 应用入口（统一筛选器版）
   ═══════════════════════════════════════════════════════════════ */

let currentMainTab = 'dashboard';
let currentSubTab = 'matrix';
let _lastRunTime = '';

// ── 全局筛选栏「更多筛选」展开/收起 ──
function toggleMoreFilters() {
  const sec = document.getElementById('gf-secondary');
  const btn = document.getElementById('gf-more-btn');
  if (!sec || !btn) return;
  const collapsed = sec.classList.contains('gf-collapsed');
  sec.classList.toggle('gf-collapsed', !collapsed);
  btn.innerHTML = collapsed ? '收起筛选 <span class="mf-arrow">▴</span>' : '更多筛选 <span class="mf-arrow">▾</span>';
}

// ── 主Tab切换 ──
function switchMainTab(tab) {
  currentMainTab = tab;
  document.querySelectorAll('.main-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tab));
  document.querySelectorAll('[id^="tab-"]').forEach(el => el.classList.toggle('active', el.id === `tab-${tab}`));
  if (tab === 'dashboard') loadDashboard();
  if (tab === 'detail') switchSubTab(currentSubTab);
  if (tab === 'monitor') loadMonitor();
}
function refreshAll() {
  if (typeof UVFilters !== 'undefined' && UVFilters._clearPendingRefresh) UVFilters._clearPendingRefresh();
  switchMainTab(currentMainTab);
}

function _updateRunTimeRelative() {
  const el = document.getElementById('run-time'); if (!el) return;
  const rel = UVConfig.relativeTime(_lastRunTime);
  el.textContent = rel ? `更新于 ${rel}` : (_lastRunTime || '');
  el.title = _lastRunTime || '';
}
function openCalibrate() { switchMainTab('calibrate'); document.getElementById('zone-enrollment')?.scrollIntoView({behavior:'smooth',block:'center'}); }

// ── 子Tab切换 ──
function switchSubTab(tab) {
  currentSubTab = tab;
  document.querySelectorAll('#tab-detail .sub-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.subtab === tab));
  document.querySelectorAll('#tab-detail .tab-content').forEach(el => { if (el.id.startsWith('sub-')) el.classList.toggle('active', el.id === `sub-${tab}`); });
  if (tab === 'matrix') UVMatrix.render();
  if (tab === 'schedule') loadSchedule();
  if (tab === 'student') UVStudent.loadFilters();
  if (tab === 'teacher') UVTeacher.load();
  if (tab === 'advisor') UVAdvisor.load();
}

// ── 加载看板 ──
async function loadDashboard() {
  const params = UVFilters.buildParams();
  const [stats, trends, acquisition, channel] = await Promise.all([
    UVApi.getStats(params),
    UVApi.getTrends(params),
    UVApi.getAcquisitionTrends(params),
    UVApi.getChannelAcquisition(UVFilters.buildParams({ channelLevel: UVTrends.channelLevel || 'l1' })),
  ]);
  if (stats) {
    if (stats.period_config) UVConfig.applyPeriodConfig(stats.period_config);
    if (stats.filter_config) UVConfig.applyFilterConfig(stats.filter_config);
    UVStats.render(stats);
    _lastRunTime = stats.run_time || ''; _updateRunTimeRelative();
    const badge = document.getElementById('run-pin-badge');
    if (badge) { if (stats.is_pinned) { badge.style.display=''; badge.textContent='📌 已回溯至历史基线'; badge.className='pin-badge pinned'; } else { badge.style.display='none'; } }
    UVTrends.statsData = stats; UVTrends.trendData = trends; UVTrends.acquisitionData = acquisition; UVTrends.channelData = channel;
    if (stats.by_advisor) { const map = {}; stats.by_advisor.forEach(a => { if (a.teaching_point) map[a.name] = a.teaching_point; }); if (Object.keys(map).length) UVTrends.advisorPtMap = map; }
    UVTrends.renderRankings(stats); UVTrends.renderInsightCharts(stats);
  }
  if (trends) UVTrends.renderCharts(trends);
  if (acquisition) UVTrends.renderAcquisitionChart(acquisition);
  if (channel) UVTrends.renderChannelChart(channel);
}

// ── 加载排班 ──
let scheduleDataCache = null;
async function loadSchedule() {
  const params = UVFilters.buildParams();
  const data = await UVApi.getClasses(params);
  if (!data) return;
  scheduleDataCache = data;
  UVFilters.scheduleOptions = {
    teachingPoints: data.teaching_points || [], teachers: data.teachers || [], subjects: data.subjects || [],
    classTypes: data.class_types || [], courseTypes: data.course_types || [], classModes: data.class_modes || [],
    ptClassCounts: data.filtered_pt_class_counts || data.pt_class_counts || {},
  };
  renderClassCards(data);
}

function renderClassCards(data) {
  const container = document.getElementById('schedule-content');
  const classes = data.classes || [];
  if (!classes.length) { container.innerHTML = UVConfig.renderEmpty({msg:'暂无排班数据',icon:'🗓️',sub:'调整筛选条件后重试'}); return; }
  const C = UVConfig.COLORS, sc = UVConfig.SUBJECT_PILL_CLASS, activeSeason = UVFilters.currentSeason();
  container.onclick = (e) => {
    const card = e.target.closest('.schedule-class-card'); if (!card) return;
    const tag = e.target.closest('.student-tag.clickable');
    if (tag) { e.stopPropagation(); const uid=tag.dataset.uid, season=card.dataset.season||activeSeason||''; if(uid) UVModal.openStudentDetail(uid,season); return; }
    const moreBtn = e.target.closest('.student-tag.more'); if (moreBtn) { e.stopPropagation(); toggleClassStudents(moreBtn); return; }
    const classId = card.dataset.classId; if (classId) UVModal.openClassDetail(classId);
  };
  let html = '<div class="class-grid">';
  classes.forEach(c => {
    const students = c.students||[], total = c.total||students.length, renewed = c.renewed_count||0, rate = c.renewal_rate||0;
    const rateColor = rate>=50?C.success:(rate>=25?C.warning:C.danger);
    const subjPillCls = sc[c.subject]||'', subjShort = UVConfig.SUBJECT_SHORT[c.subject]||c.subject, subjColor = UVConfig.SUBJECT_COLOR[c.subject]||C.textTertiary;
    const periodLabel = UVConfig.displayPeriod(c.period||'',activeSeason), periodColor = UVConfig.periodColor(c.period||'');
    const seasonVal = c.season||'';
    const periodBadge = seasonVal ? UVConfig.seasonPeriodBadge(c.period||'',seasonVal) : `<span class="cls-period-pill" style="background:${periodColor};color:#fff">${periodLabel}</span>`;
    const typeColor = UVConfig.classTypeColor(c.class_type||''), ptColor = UVConfig.teachingPointColor(c.teaching_point||'');
    const maxShow = 5; let tagsHtml = '';
    if (students.length > 0) {
      const shown = students.slice(0,maxShow), hidden = students.slice(maxShow);
      tagsHtml = '<div class="student-tags">';
      shown.forEach(s => { const isR=UVConfig.isContinueFall(s.continue_fall); tagsHtml+=`<span class="${isR?'student-tag renewed clickable':'student-tag clickable'}" data-uid="${s.uid}" title="${s.name}${isR?' (已续)':''}">${s.name}</span>`; });
      if (hidden.length) { tagsHtml+=`<span class="student-tag more">+${hidden.length}人</span><span style="display:none" class="hidden-tags">${hidden.map(s=>{const isR=UVConfig.isContinueFall(s.continue_fall);return`<span class="${isR?'student-tag renewed clickable':'student-tag clickable'}" data-uid="${s.uid}" title="${s.name}${isR?' (已续)':''}">${s.name}</span>`}).join('')}</span>`; }
      tagsHtml += '</div>';
    }
    const courseTypePill=UVConfig.courseTypePill(c.course_type), classModePill=UVConfig.classModePill(c.class_mode);
    const classTypePill=UVConfig.classTypePill(c.class_type)||`<span class="cls-type-pill" style="background:${typeColor.bg};border:1px solid ${typeColor.border};color:${typeColor.text}">-</span>`;
    html += `<div class="schedule-class-card ${subjPillCls}" data-class-id="${c.class_id||''}" data-season="${c.season||''}">
      <div class="cls-card-main"><div class="cls-card-hd"><div class="cls-card-title-block">
        <div class="cls-title-row"><span class="cls-subject-pill" style="background:${subjColor};color:#fff">${subjShort}</span><strong class="cls-teacher">${c.teacher||'-'}</strong><span class="cls-id">${c.class_id||''}</span></div>
        <div class="cls-info-row"><span class="cls-pt-pill" style="background:${ptColor.bg};border:1px solid ${ptColor.border};color:${ptColor.text}">${c.teaching_point||'-'}</span>${classModePill}</div>
        <div class="cls-meta-row"><span class="cls-meta-inline">${c.time_slot||'-'} · ${c.room||'-'}</span></div>
      </div><div class="cls-card-tags">${periodBadge}<div class="cls-card-type-wrap">${classTypePill}</div></div></div></div>
      <div class="cls-card-stats" data-course-type="${UVConfig._esc(c.course_type||'')}">${courseTypePill?`<div class="cls-stats-notch">${courseTypePill}</div>`:''}
        <div class="cls-stats-body"><div class="cls-stat"><span class="cls-stat-value">${total}</span><span class="cls-stat-label">在读</span></div><div class="cls-stat-divider"></div>
        <div class="cls-stat"><span class="cls-stat-value renew-num">${renewed}</span><span class="cls-stat-label">续报</span></div><div class="cls-stat-divider"></div>
        <div class="cls-stat"><span class="cls-stat-value" style="color:${rateColor}">${rate}%</span><span class="cls-stat-label">续报率</span><div class="cls-mini-bar"><div class="cls-mini-fill" style="width:${rate}%;background:${rateColor}"></div></div></div></div></div>
      ${tagsHtml}</div>`;
  });
  html += '</div>'; container.innerHTML = html;
}

function toggleClassStudents(el) {
  const hidden = el.nextElementSibling; if (!hidden) return;
  if (hidden.style.display==='none'||hidden.style.display==='') { hidden.style.display='inline'; el.textContent='收起'; }
  else { hidden.style.display='none'; el.textContent='+'+hidden.querySelectorAll('.student-tag').length+'人'; }
}

// ── 监控 ──
async function loadMonitor() {
  const runs = await UVApi.getRuns(); if (!runs) return;
  const container = document.getElementById('monitor-runs-table');
  if (!runs.length) { container.innerHTML=UVConfig.renderEmpty({msg:'暂无校准记录',icon:'📋'}); return; }
  let html = `<div style="font-size:12px;color:var(--text-muted);margin-bottom:10px">共 ${runs.length} 次校准</div>`;
  html += '<table class="data-table"><thead><tr><th>时间</th><th>学员总数</th><th>在读</th><th>新增</th><th>退费</th><th>变动</th><th>类型</th><th>招生明细</th><th>原台帐</th><th>当前</th><th>操作</th></tr></thead><tbody>';
  runs.forEach(r => {
    const enroll=(r.enrollment_file||'').length>24?(r.enrollment_file||'').slice(0,24)+'…':(r.enrollment_file||'');
    const ledger=(r.old_ledger_file||'').length>24?(r.old_ledger_file||'').slice(0,24)+'…':(r.old_ledger_file||'');
    const rid=escHtml(r.run_id);
    let currentCell='<span class="muted-dot">—</span>';
    if (r.is_current) currentCell=r.is_pinned?'<span class="cur-badge pinned">📌 已固定</span>':'<span class="cur-badge">● 当前</span>';
    let actionBtns=`<a href="#" class="link-btn" onclick="viewRunDetail('${rid}');return false">详情</a>`;
    if (r.is_current&&r.is_pinned) actionBtns+=` <a href="#" class="link-btn warn" onclick="pinRunAction('',true);return false">返回最新</a>`;
    else if (!r.is_current) actionBtns+=` <a href="#" class="link-btn primary" onclick="pinRunAction('${rid}',false);return false">设为当前基线</a>`;
    html += `<tr class="${r.is_current?'row-current':''}"><td>${escHtml(r.run_time||'-')}</td><td><strong>${r.total_students||0}</strong></td><td style="color:var(--c-success)">${r.active_students||0}</td><td style="color:var(--c-warning)">${r.new_students||0}</td><td style="color:var(--c-danger)">${r.refund_students||0}</td><td>${r.changes_count||0}</td><td>${sourceBadge(r.source)}</td><td style="font-size:12px;color:var(--text-muted);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(r.enrollment_file||'')}">${escHtml(enroll)}</td><td style="font-size:12px;color:var(--text-muted);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(r.old_ledger_file||'')}">${escHtml(ledger)}</td><td>${currentCell}</td><td>${actionBtns}</td></tr>`;
  });
  html += '</tbody></table>'; container.innerHTML = html;
}

async function viewRunDetail(runId) { try { const [data,runsData]=await Promise.all([UVApi.getRunDetail(runId),UVApi.getRuns()]); const run=(data&&data.run)||{},changes=(data&&data.changes)||[]; const rid=escHtml(runId),runMeta=(runsData||[]).find(r=>r.run_id===runId)||{}; const isCurrent=!!runMeta.is_current,isPinned=!!runMeta.is_pinned; let stats={}; try{stats=run.stats_json?JSON.parse(run.stats_json):{};}catch(e){stats={};} let html='<div class="modal-overlay open" id="run-detail-modal" onclick="closeRunDetail()"><div class="modal-content" onclick="event.stopPropagation()"><span class="modal-close" onclick="closeRunDetail()">✕</span>'; html+=`<div class="panel-title">校准变动概览 · ${escHtml(run.run_time||'')}</div>`; html+='<div class="run-ov">'; const kpis=[{l:'学员总数',v:run.total_students||0,c:'k-neu'},{l:'在读学员',v:run.active_students||0,c:'k-ok'},{l:'新增学员',v:stats.new_students!=null?stats.new_students:(run.new_students||0),c:'k-add'},{l:'新增退费学员',v:stats.new_refund_students!=null?stats.new_refund_students:(run.refund_students||0),c:'k-del'},{l:'新增退费单科',v:stats.new_refund_details!=null?stats.new_refund_details:'-',c:'k-del'},{l:'变动学员',v:run.changes_count||0,c:'k-chg'}]; html+='<div class="run-ov-kpis">'; kpis.forEach(k=>{html+=`<div class="run-ov-kpi ${k.c}"><div class="v">${k.v}</div><div class="l">${k.l}</div></div>`;}); html+='</div>'; const bd=stats.change_breakdown||{},bdEntries=Object.entries(bd).sort((a,b)=>b[1]-a[1]); if(bdEntries.length){html+='<div class="run-ov-sec-title"><span class="dot"></span>变动类型统计</div><div class="run-ov-list">';bdEntries.forEach(([t,c])=>{html+=`<div class="run-ov-row"><span class="tag ${changeTagClass(t)}">${escHtml(t)}</span><span class="cnt">${c}</span></div>`;});html+='</div>';}else{html+='<div class="cal-empty">本次校准无变动</div>'; } html+='</div>'; let studentChanges=[];try{studentChanges=run.student_changes_json?JSON.parse(run.student_changes_json):[];}catch(e){studentChanges=[];} html+=renderStudentChangeOverview(studentChanges,{showEmpty:true}); html+='<div class="modal-footer">'; if(isCurrent&&isPinned)html+=`<button class="btn btn-sm tf-btn-reset" onclick="pinRunAction('',true);closeRunDetail();return false">返回最新</button>`; else if(!isCurrent)html+=`<button class="btn btn-primary btn-sm" onclick="pinRunAction('${rid}',false);closeRunDetail();return false">设为当前基线</button>`; else html+='<span class="muted-dot">当前最新基线</span>'; html+='</div></div></div>'; const existing=document.getElementById('run-detail-modal');if(existing)existing.remove();document.body.insertAdjacentHTML('beforeend',html); }catch(err){console.error('viewRunDetail error:',err);} }
function changeTagClass(label) { const s=String(label||''); if(s.includes('新增学员'))return'tag-green';if(s.includes('退费'))return'tag-red';if(s.includes('调班')||s.includes('调期'))return'tag-orange';if(s.includes('续秋')||s.includes('续报'))return'tag-blue';if(s.includes('报科'))return'tag-teal';return'tag-grey'; }
function closeRunDetail() { const m=document.getElementById('run-detail-modal');if(m)m.remove(); }
async function pinRunAction(runId,clearOnly) { const res=await UVApi.pinRun(clearOnly?'':runId); if(!res||!res.success){showToast('操作失败','error');return;} showToast(clearOnly?'已返回最新校准':'已设为当前基线','success'); loadMonitor();loadDashboard(); }
function escHtml(s) { return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function sourceBadge(source) { const map={full:{t:'全量',c:'badge-full'},calibration:{t:'校准',c:'badge-cal'},merged:{t:'合并',c:'badge-merged'}}; const m=map[source]||{t:source||'—',c:'badge-muted'}; return `<span class="badge ${m.c}">${m.t}</span>`; }

// ── 文件上传 ──
function onFileChange(input) { const zone=input.closest('.upload-zone'),fileEl=zone?.querySelector('.uz-file'); if(input.files.length>0){if(fileEl)fileEl.textContent=input.files[0].name;if(zone)zone.classList.add('has-file');}else{if(fileEl)fileEl.textContent='';if(zone)zone.classList.remove('has-file');} }
async function handleCalibrate() { const enrollment=document.getElementById('cal-enrollment').files[0],ledger=document.getElementById('cal-ledger').files[0],fall=document.getElementById('cal-fall').files[0],container=document.getElementById('calibrate-result'); if(!enrollment||!ledger){container.innerHTML='<p class="calibrate-error">请上传招生明细和原台帐文件</p>';return;} container.innerHTML='<div class="cal-loading"><span class="spin"></span> 校准中…</div>'; const formData=new FormData(); formData.append('enrollment',enrollment);formData.append('ledger',ledger);if(fall)formData.append('fall_orders',fall); try{const data=await UVApi.calibrate(formData);if(data&&data.success){container.innerHTML=renderCalibrateDashboard(data);loadMonitor();}else{container.innerHTML=`<p class="calibrate-error">校准失败：${data&&data.error?data.error:'未知错误'}</p>`;}}catch(err){container.innerHTML=`<p class="calibrate-error">请求失败：${err.message}</p>`;} }
function onFullFilesChange(input) { const zone=input.closest('.upload-zone'),fileEl=zone?.querySelector('.uz-file'); if(input.files.length>0){const names=Array.from(input.files).map(f=>f.name);if(fileEl)fileEl.textContent=names.length<=2?names.join('、'):`${names.length} 个文件已选`;if(zone)zone.classList.add('has-file');}else{if(fileEl)fileEl.textContent='';if(zone)zone.classList.remove('has-file');} }
async function handleFullUpload() { const input=document.getElementById('full-files'),files=input&&input.files?Array.from(input.files):[],container=document.getElementById('full-upload-result'); if(!files.length){container.innerHTML='<p class="calibrate-error">请选择至少一个文件</p>';return;} container.innerHTML='<div class="cal-loading"><span class="spin"></span> 上传并合并中…</div>'; const formData=new FormData();files.forEach(f=>formData.append('files',f)); try{const data=await UVApi.uploadFull(formData);if(data&&data.success){container.innerHTML=renderFullUploadResult(data);loadMonitor();refreshAll();}else{container.innerHTML=`<p class="calibrate-error">上传失败：${data&&data.error?data.error:'未知错误'}</p>`;}}catch(err){container.innerHTML=`<p class="calibrate-error">请求失败：${err.message}</p>`;} }
function renderFullUploadResult(data) { const rb=data.rebuild||{},srcMap={full:'全量',calibration:'校准',merged:'合并'},srcLabel=srcMap[rb.source]||rb.source||'—',kept=data.kept_from_old_base||0; let mergeInfo='';if(rb.source==='merged')mergeInfo=`<div class="cal-note">已合并：全量 ${rb.base_students||0} + 校准 ${rb.overlay_students||0} → ${rb.students||0} 人</div>`;else if(rb.source==='full')mergeInfo='<div class="cal-note">无校准数据，已采用全量快照</div>'; let keptInfo='';if(kept>0)keptInfo=`<div class="cal-note" style="color:var(--c-success-text)">✅ 已保留旧基线中其他分校 ${kept} 人（未被覆盖）</div>`; return `<div class="cal-dash"><div class="cal-stat-grid"><div class="cal-stat-card t-total"><div class="v">${data.students||0}</div><div class="l">写入学员</div></div><div class="cal-stat-card t-active"><div class="v">${data.active||0}</div><div class="l">在读</div></div><div class="cal-stat-card t-refund"><div class="v">${data.refund||0}</div><div class="l">退费</div></div><div class="cal-stat-card t-fall"><div class="v">${srcLabel}</div><div class="l">当前生效类型</div></div></div>${mergeInfo}${keptInfo}<div class="cal-note muted">Run: ${escHtml(data.run_id||'')} · 基线: ${escHtml(rb.current_run_id||'')}</div></div>`; }
async function handleRebuild() { try{const data=await UVApi.rebuild();if(data&&data.success){showToast('已重新合并','success');loadMonitor();refreshAll();}else{showToast('合并失败：'+(data&&data.error?data.error:'未知错误'),'error');}}catch(err){showToast('合并失败：'+err.message,'error');} }

// ── 校准结果渲染 ──
function renderCalibrateDashboard(data) {
  const s=data.stats||{},studentChanges=data.student_changes||[];
  function isFallVal(v){return v==='是'||v==='T'||v==='AC'||v==='AL';}
  let fallUv=0,fallPv=0;
  (data.changed_list||[]).forEach(sc=>{const details=sc.details||[];let hasFall=false;details.forEach(d=>{if(d.type&&d.type.includes('续秋变化')&&isFallVal(d.new)&&!isFallVal(d.old)){fallPv++;if(!hasFall){hasFall=true;fallUv++;}}});});
  let html='<div class="cal-dash"><div class="cal-stat-grid">';
  [{cls:'t-total',v:s.total_students,l:'学员总数'},{cls:'t-active',v:s.active_students,l:'在读'},{cls:'t-new',v:s.new_students,l:'新增学员'},{cls:'t-refund',v:s.new_refund_students||0,l:'新增退费(UV)',sub:(s.new_refund_details||0)+' 单科'},{cls:'t-fall',v:fallUv,l:'新增续费(UV)',sub:fallPv+' 单科'},{cls:'t-change',v:s.changes_count,l:'变动学员'}].forEach(c=>{html+=`<div class="cal-stat-card ${c.cls}"><div class="v">${c.v==null?'-':c.v}</div><div class="l">${c.l}</div>${c.sub?`<div class="sub">${c.sub}</div>`:''}</div>`;});
  html+='</div>';
  const bd=s.change_breakdown||{},btns=Object.entries(bd).sort((a,b)=>b[1]-a[1]);
  if(btns.length){html+='<div class="cal-pills">';btns.forEach(([t,n])=>{const isNew=t.includes('新增学员'),isRefund=t.includes('退费'),isFall=t.includes('续秋');let bg,cl;if(isNew||isFall){bg='var(--c-success-bg)';cl='var(--c-success-text)';}else if(isRefund){bg='var(--c-danger-bg)';cl='var(--c-danger-text)';}else{bg='var(--c-warning-bg)';cl='var(--c-warning-text)';}html+=`<span class="cal-pill" style="background:${bg};color:${cl}">${escHtml(t)} ${n}</span>`;});html+='</div>';}
  html+=renderStudentChangeOverview(studentChanges,{showEmpty:true});
  const anomalies=data.anomalies||[];
  if(anomalies.length){html+='<div class="cal-anomaly"><div class="cal-anomaly-title">⚠️ 异常数据修正</div>';anomalies.forEach(a=>{html+=`<div class="cal-anomaly-item"><span class="nm">${escHtml(a.name||'')}</span><span class="uid">${escHtml(a.uid||'')}</span><div>${escHtml(a.desc||'')}</div></div>`;});html+='</div>';}
  if(!studentChanges.length&&!anomalies.length)html+='<div class="cal-empty">本次校准无变动</div>';
  html+=`<div class="cal-downloads"><a href="${data.files.ledger}" class="btn btn-primary" download>📥 下载校准台帐</a><a href="${data.files.report}" class="btn btn-outline" download>📥 下载校准报告</a></div></div>`;
  return html;
}
function formatStudentChanges(sc) { const details=sc.details||[];if(!details.length)return`<div style="color:var(--text-tertiary);font-size:12px">${escHtml(sc.summary||'无明细')}</div>`;const bySubject={};details.forEach(d=>{const subj=d.subject||(d.type?d.type.split('-')[1]:'');if(!subj)return;if(!bySubject[subj])bySubject[subj]=[];bySubject[subj].push(d);});const subjOrder=['雪球思维','悦读创作','双语素养'];const lines=[];subjOrder.forEach(subj=>{const items=bySubject[subj];if(!items)return;const refund=items.find(it=>it.type&&it.type.includes('退费'));if(refund){lines.push(`<div class="cal-ch-line"><span class="cal-ch-subj">${escHtml(subj)}</span><span class="refund">退费(${escHtml(refund.new||refund.type.split('-')[1]||'退费')})</span><span class="cal-ch-attr">期次 ${escHtml(refund.period||'-')} · 老师 ${escHtml(refund.teacher||'-')}</span></div>`);return;}const added=items.find(it=>it.type&&it.type.includes('新增报科'));if(added){lines.push(`<div class="cal-ch-line"><span class="cal-ch-subj">${escHtml(subj)}</span><span class="new">新增报科</span><span class="cal-ch-attr">期次 ${escHtml(added.period||'-')} · 老师 ${escHtml(added.teacher||'-')}</span></div>`);return;}const cf=items.find(it=>it.type&&it.type.includes('续秋变化'));if(cf){lines.push(`<div class="cal-ch-line"><span class="cal-ch-subj">${escHtml(subj)}</span><span class="fall">续秋 ${escHtml(cf.old||'-')}→${escHtml(cf.new||'-')}</span></div>`);return;}const periodItem=items.find(it=>it.field==='period'),teacherItem=items.find(it=>it.field==='teacher');const attrs=[];if(periodItem&&periodItem.old&&periodItem.new&&periodItem.old!==periodItem.new)attrs.push(`期次 ${escHtml(periodItem.old)}→${escHtml(periodItem.new)}`);if(teacherItem&&teacherItem.old&&teacherItem.new&&teacherItem.old!==teacherItem.new)attrs.push(`主讲 ${escHtml(teacherItem.old)}→${escHtml(teacherItem.new)}`);lines.push(`<div class="cal-ch-line"><span class="cal-ch-subj">${escHtml(subj)}</span><span class="transfer">调班</span>${attrs.length?`<span class="cal-ch-attr">${attrs.join(' · ')}</span>`:''}</div>`);});return`<div class="cal-ch-lines">${lines.join('')}</div>`; }
function renderStudentChangeOverview(studentChanges,opts) { opts=opts||{};if(!studentChanges||!studentChanges.length){if(!opts.showEmpty)return'';return'<div class="cal-empty">本次校准无学员变动</div>';}const newList=studentChanges.filter(sc=>sc.change_type==='新增学员'),changedList=studentChanges.filter(sc=>sc.change_type!=='新增学员');let html='<div class="cal-section"><div class="cal-section-title">变动概览</div>';if(newList.length){html+=`<div class="cal-section" style="margin-bottom:12px"><div class="cal-cat-title"><span class="dot" style="background:var(--c-success)"></span>新增学员(${newList.length}人)</div><div class="cal-change-grid">`;newList.forEach(sc=>{html+=`<div class="cal-change-card hd-new"><div class="cal-cc-head"><span class="cal-cc-name">${escHtml(sc.name||'')}</span><span class="cal-cc-meta">${escHtml(sc.uid||'')}</span><span class="cal-cc-meta">${escHtml(sc.teaching_point||'')}</span></div>${formatStudentChanges(sc)}</div>`;});html+='</div></div>';}const refundChanges=changedList.filter(sc=>sc.summary&&sc.summary.includes('退费'));if(refundChanges.length){html+=`<div class="cal-section" style="margin-bottom:12px"><div class="cal-cat-title"><span class="dot" style="background:var(--c-danger)"></span>新增退费(${refundChanges.length}人)</div><div class="cal-change-grid">`;refundChanges.forEach(sc=>{html+=`<div class="cal-change-card hd-refund"><div class="cal-cc-head"><span class="cal-cc-name">${escHtml(sc.name||'')}</span><span class="cal-cc-meta">${escHtml(sc.uid||'')}</span><span class="cal-cc-meta">${escHtml(sc.teaching_point||'')}</span></div>${formatStudentChanges(sc)}</div>`;});html+='</div></div>';}const fallChanges=changedList.filter(sc=>(sc.details||[]).some(d=>d.type&&d.type.includes('续秋变化')));if(fallChanges.length){html+=`<div class="cal-section" style="margin-bottom:12px"><div class="cal-cat-title"><span class="dot" style="background:var(--c-success)"></span>新增续费(${fallChanges.length}人)</div><div class="cal-change-grid">`;fallChanges.forEach(sc=>{html+=`<div class="cal-change-card hd-fall"><div class="cal-cc-head"><span class="cal-cc-name">${escHtml(sc.name||'')}</span><span class="cal-cc-meta">${escHtml(sc.uid||'')}</span><span class="cal-cc-meta">${escHtml(sc.teaching_point||'')}</span></div>${formatStudentChanges(sc)}</div>`;});html+='</div></div>';}const transferChanges=changedList.filter(sc=>{if(sc.summary&&(sc.summary.includes('退费')||sc.summary.includes('续秋')))return false;return(sc.details||[]).some(d=>d.type&&(d.type.includes('调班')||d.type.includes('新增报科')));});if(transferChanges.length){html+=`<div class="cal-section" style="margin-bottom:12px"><div class="cal-cat-title"><span class="dot" style="background:var(--c-warning)"></span>调班(${transferChanges.length}人)</div><div class="cal-change-grid">`;transferChanges.forEach(sc=>{html+=`<div class="cal-change-card hd-info"><div class="cal-cc-head"><span class="cal-cc-name">${escHtml(sc.name||'')}</span><span class="cal-cc-meta">${escHtml(sc.uid||'')}</span><span class="cal-cc-meta">${escHtml(sc.teaching_point||'')}</span></div>${formatStudentChanges(sc)}</div>`;});html+='</div></div>';}html+='</div>';return html; }

// ══════════════════════════════════════════════
// 初始化
// ══════════════════════════════════════════════
async function initApp() {
  await UVFilters.init();
  loadDashboard();
  // 学员搜索按钮接线
  const searchBtn = document.getElementById('student-search-btn');
  if (searchBtn) searchBtn.addEventListener('click', () => {
    const kw = document.getElementById('student-keyword')?.value || '';
    UVFilters.state.keyword = kw;
    UVStudent.search();
  });
  window.addEventListener('error', e => { if(typeof showToast==='function') showToast('页面异常：'+(e.message||'未知错误'),'error'); });
  window.addEventListener('unhandledrejection', e => { if(typeof showToast==='function') showToast('请求异常：'+((e.reason&&e.reason.message)||'未知错误'),'error'); });
  setInterval(_updateRunTimeRelative, 60000);
}
document.addEventListener('DOMContentLoaded', initApp);
