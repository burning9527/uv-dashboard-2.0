/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 分享卡片
   数据逻辑完全复刻 1.0（/api/share-card 的 KPI/分教学点/分学科/
   老师排行/班级/顾问双维度），卡片 UI 迭代为 2.0 高级风格。
   ═══════════════════════════════════════════════════════════════ */

// 期次 / 学科 选项
const SHARE_PERIODS = ['全部', ...(window.UVConfig ? UVConfig.PERIODS : ['零期', '一期', '二期', '三期'])];
const SHARE_SUBJECTS = ['全部', '雪球思维', '悦读创作', '双语素养', '雪球科学'];
let sharePointsList = ['全部'];
let shareTeachersList = ['全部'];
let shareAdvisorsList = ['全部'];
let shareState = { period: '全部', point: '全部', subject: '全部', teacher: '全部', advisor: '全部' };
let shareMetrics = { active: true, uv: true, rate: true, fall_active: false, refund: false, class_count: true, subject: true };
let shareAdvisorMode = 'uv'; // 'uv' or 'pv' for advisor conversion ranking

async function openShareCard() {
  const overlay = document.getElementById('shareOverlay');
  overlay.style.display = 'flex';
  // 重置为全部分校初始态，随后 updateShareCard 会根据当前全局分校（顶部全局栏）收窄
  sharePointsList = ['全部'];
  shareTeachersList = ['全部'];
  shareAdvisorsList = ['全部'];
  shareState = { period: '全部', point: '全部', subject: '全部', teacher: '全部', advisor: '全部' };
  renderShareFilters();
  await updateShareCard();
}

function renderShareFilters() {
  const chipHTML = (items, key) => items.map(v => {
    const active = shareState[key] === v;
    return `<span class="share-chip${active ? ' active' : ''}" onclick="setShareFilter('${key}','${v.replace(/'/g, "\\'")}')">${v}</span>`;
  }).join('');

  const metricItems = [
    ['active', '在读PV'], ['uv', '在读UV'], ['rate', 'PV续报率'], ['fall_active', '秋季在读PV'],
    ['refund', '退费PV'], ['class_count', '班级数'], ['subject', '分学科']
  ];
  const metricHTML = metricItems.map(([k, label]) => {
    const active = shareMetrics[k];
    return `<span class="share-chip${active ? ' active' : ''}" onclick="toggleShareMetric('${k}')">${active ? '✓ ' : ''}${label}</span>`;
  }).join('');

  document.getElementById('shareFilters').innerHTML = `
    <div class="share-group"><div class="share-label">期次</div><div class="share-chips">${chipHTML(SHARE_PERIODS, 'period')}</div></div>
    <div class="share-group"><div class="share-label">教学点</div><div class="share-chips">${chipHTML(sharePointsList, 'point')}</div></div>
    <div class="share-group"><div class="share-label">学科</div><div class="share-chips">${chipHTML(SHARE_SUBJECTS, 'subject')}</div></div>
    <div class="share-group"><div class="share-label">老师</div><div class="share-chips share-chips-wrap">${chipHTML(shareTeachersList, 'teacher')}</div></div>
    <div class="share-group"><div class="share-label">顾问</div><div class="share-chips share-chips-wrap">${chipHTML(shareAdvisorsList, 'advisor')}</div></div>
    <div class="share-group"><div class="share-label">卡片指标</div><div class="share-chips share-chips-wrap">${metricHTML}</div></div>
  `;
}

function setShareFilter(key, val) {
  shareState[key] = val;
  renderShareFilters();
  updateShareCard();
}

function toggleShareMetric(key) {
  shareMetrics[key] = !shareMetrics[key];
  renderShareFilters();
  updateShareCard();
}

function setShareAdvisorMode(mode) {
  shareAdvisorMode = mode;
  updateShareCard();
}

async function updateShareCard() {
  const params = {};
  if (shareState.period !== '全部') params.period = shareState.period;
  if (shareState.point !== '全部') params.teaching_point = shareState.point;
  const subjMap = { '雪球思维': '雪球思维', '悦读创作': '悦读创作', '双语素养': '双语素养', '雪球科学': '雪球科学' };
  if (shareState.subject !== '全部') params.subject = subjMap[shareState.subject] || shareState.subject;
  if (shareState.teacher !== '全部') params.teacher = shareState.teacher;
  if (shareState.advisor !== '全部') params.advisor = shareState.advisor;
  // 全局筛选联动（顶部全局栏）——支持多选分校及其他全局维度
  const _toParam = (set) => (set && set.size) ? Array.from(set).join(',') : '';
  const gb = _toParam(UVFilters.state.branch); if (gb) params.branch = gb;
  const gy = _toParam(UVFilters.state.year); if (gy) params.year = gy;
  const gs = _toParam(UVFilters.state.season); if (gs) params.season = gs;
  const gct = _toParam(UVFilters.state.course_type); if (gct) params.course_type = gct;
  const gcm = _toParam(UVFilters.state.class_mode); if (gcm) params.class_mode = gcm;
  const gg = _toParam(UVFilters.state.grade); if (gg) params.grade = gg;

  document.getElementById('shareCardPreview').innerHTML = '<div class="share-loading">加载中…</div>';

  try {
    const data = await UVApi.getShareCard(params);
    if (!data) throw new Error('no data');
    if (data.available_teachers && data.available_teachers.length > 0) {
      shareTeachersList = ['全部', ...data.available_teachers];
    }
    if (data.available_points && data.available_points.length > 0) {
      sharePointsList = ['全部', ...data.available_points];
    }
    if (data.available_advisors && data.available_advisors.length > 0) {
      shareAdvisorsList = ['全部', ...data.available_advisors];
    }
    renderShareFilters();
    renderShareCard(data);
  } catch (e) {
    document.getElementById('shareCardPreview').innerHTML = '<div class="share-loading" style="color:#e8453c">加载失败</div>';
  }
}

function rateColor(rate) {
  if (rate >= 60) return '#1D9E75';
  if (rate >= 50) return '#3B6FE0';
  if (rate >= 45) return '#639922';
  return '#BA7517';
}

// ── 2.0 设计令牌（用于内联卡片，保证 html2canvas 可捕获）──
const SC = {
  primary: '#1F2733',
  secondary: '#5B6478',
  muted: '#9AA0B4',
  border: '#ECEEF4',
  accent: '#4F6BED',
  blue: '#3B6FE0',
  green: '#16A34A',
  orange: '#E8943B',
  red: '#E8505B',
  teal: '#0D9488',
};

// 指标配色（主色 + 极浅底色）
const METRIC_STYLE = {
  '在读PV': { c: SC.blue, t: '#EAF1FF' },
  '在读UV': { c: SC.green, t: '#E7F8EF' },
  'PV续报率': { c: SC.accent, t: '#EEF1FE' },
  '秋季在读PV': { c: SC.teal, t: '#E2F5F3' },
  '退费PV': { c: SC.red, t: '#FDEBEC' },
  '班级数': { c: SC.orange, t: '#FDF1E3' },
};

function renderShareCard(data) {
  const k = data.kpi;
  const f = data.filters;
  const dateStr = (data.run_time || '').substring(0, 10);

  // ── KPI 区 ──
  const kpiItems = [];
  if (shareMetrics.active) kpiItems.push({ label: '在读PV', value: k.active_pv, color: SC.blue });
  if (shareMetrics.uv) kpiItems.push({ label: '在读UV', value: k.uv, color: SC.green });
  if (shareMetrics.rate) kpiItems.push({ label: 'PV续报率', value: k.renewal_rate + '%', color: rateColor(k.renewal_rate) });
  if (shareMetrics.fall_active) kpiItems.push({ label: '秋季在读PV', value: k.renewal_pv, color: SC.teal });
  if (shareMetrics.refund) kpiItems.push({ label: '退费PV', value: k.refund_pv, color: SC.red });
  if (shareMetrics.class_count) kpiItems.push({ label: '班级数', value: k.class_count, color: SC.orange });

  const kpiHTML = kpiItems.length > 0 ? `
    <div style="display:grid;grid-template-columns:repeat(${Math.min(kpiItems.length, 5)},1fr);gap:10px;margin-bottom:20px">
      ${kpiItems.map(it => {
        const ms = METRIC_STYLE[it.label] || { c: '#888', t: '#F2F3F7' };
        return `
        <div style="background:${ms.t};border-radius:12px;padding:12px 12px 11px 14px;border-left:3px solid ${ms.c}">
          <div style="font-size:11px;color:${SC.secondary};margin-bottom:6px">${it.label}</div>
          <div style="font-size:23px;font-weight:700;color:${it.color};line-height:1">${it.value}</div>
        </div>`;
      }).join('')}
    </div>
  ` : '';

  // ── 分教学点表格 ──
  let pointHTML = '';
  if (data.by_point.length > 0) {
    const thStyle = 'text-align:center;padding:9px 6px;font-weight:600;color:' + SC.secondary + ';font-size:12px;white-space:nowrap';
    const tdStyle = 'text-align:center;padding:9px 6px;color:' + SC.primary + ';font-size:13px;white-space:nowrap';
    pointHTML = `
      ${sectionTitle('分教学点')}
      <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
        <thead><tr style="background:#F6F8FD">
          <th style="${thStyle};text-align:left;padding-left:12px;border-radius:6px 0 0 6px">教学点</th>
          <th style="${thStyle}">在读PV</th>
          <th style="${thStyle}">在读UV</th>
          <th style="${thStyle}">班级数</th>
          <th style="${thStyle}">续费PV</th>
          <th style="${thStyle}">续费UV</th>
          <th style="${thStyle}">PV续报率</th>
          <th style="${thStyle};border-radius:0 6px 6px 0">UV续报率</th>
        </tr></thead>
        <tbody>
          ${data.by_point.map(p => `
            <tr style="border-bottom:1px solid ${SC.border}">
              <td style="${tdStyle};text-align:left;padding-left:12px;font-weight:600">${p.name}</td>
              <td style="${tdStyle}">${p.active}</td>
              <td style="${tdStyle}">${p.uv}</td>
              <td style="${tdStyle}">${p.class_count}</td>
              <td style="${tdStyle}">${p.renewed}</td>
              <td style="${tdStyle}">${p.renewed_uv}</td>
              <td style="${tdStyle};font-weight:700;color:${rateColor(p.renewal_rate)}">${p.renewal_rate}%</td>
              <td style="${tdStyle};font-weight:700;color:${rateColor(p.renewal_uv_rate)}">${p.renewal_uv_rate}%</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  // ── 分学科 ──
  let subjectHTML = '';
  if (shareMetrics.subject && data.by_subject.length > 0) {
    subjectHTML = `
      ${sectionTitle('分学科')}
      <div style="display:grid;grid-template-columns:repeat(${Math.min(data.by_subject.length, 3)},1fr);gap:10px;margin-bottom:20px">
        ${data.by_subject.map(s => `
          <div style="background:#F6F8FD;border-radius:12px;padding:12px 14px;border-left:3px solid ${s.color}">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
              <span style="width:8px;height:8px;border-radius:50%;background:${s.color}"></span>
              <span style="font-size:12px;color:${SC.secondary}">${s.name}</span>
            </div>
            <div style="font-size:23px;font-weight:700;color:${rateColor(s.renewal_rate)};line-height:1">${s.renewal_rate}%</div>
            <div style="font-size:11px;color:${SC.muted};margin-top:6px">续费 ${s.renewed} / 在读 ${s.active}</div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // ── 老师排行（选具体老师时隐藏）──
  let teacherHTML = '';
  const showTeacherSection = shareState.teacher === '全部';
  if (showTeacherSection && data.by_teacher.length > 0) {
    const thC = 'text-align:center;padding:8px 6px;font-weight:600;color:' + SC.secondary + ';font-size:12px;white-space:nowrap';
    const tdC = 'text-align:center;padding:9px 6px;color:' + SC.primary + ';font-size:13px;white-space:nowrap';
    teacherHTML = `
      ${sectionTitle('老师续报率排行')}
      <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
        <thead><tr style="background:#F6F8FD">
          <th style="${thC};text-align:left;padding-left:12px">姓名</th>
          <th style="${thC}">在读</th>
          <th style="${thC}">已续报</th>
          <th style="${thC}">续报率</th>
          <th style="${thC};width:34%">进度</th>
        </tr></thead>
        <tbody>
          ${data.by_teacher.map(t => `
            <tr style="border-bottom:1px solid ${SC.border}">
              <td style="${tdC};text-align:left;padding-left:12px;font-weight:600">${t.name}</td>
              <td style="${tdC}">${t.active}</td>
              <td style="${tdC}">${t.renewed}</td>
              <td style="${tdC};font-weight:700;color:${rateColor(t.renewal_rate)}">${t.renewal_rate}%</td>
              <td style="${tdC}">
                <div style="background:${SC.border};border-radius:5px;height:7px;overflow:hidden">
                  <div style="width:${Math.round(t.renewal_rate)}%;height:100%;background:${rateColor(t.renewal_rate)};border-radius:5px"></div>
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  // ── 顾问转化排行（选具体顾问时隐藏）──
  let advisorHTML = '';
  const showAdvisorSection = shareState.advisor === '全部';
  if (showAdvisorSection && data.by_advisor && data.by_advisor.length > 0) {
    const ap = data.advisor_current_period || '当期';
    const usePV = shareAdvisorMode === 'pv';
    const thA = 'text-align:center;padding:8px 6px;font-weight:600;color:' + SC.secondary + ';font-size:12px;white-space:nowrap';
    const tdA = 'text-align:center;padding:9px 6px;color:' + SC.primary + ';font-size:13px;white-space:nowrap';
    const modeLabel = usePV ? 'PV' : 'UV';
    const advisorRows = data.by_advisor.map(a => {
      const active = usePV ? a.pv_active : a.active;
      const pre = usePV ? a.pv_pre_renewed : a.pre_renewed;
      const should = usePV ? a.pv_should_renew : a.should_renew;
      const newRen = usePV ? a.pv_new_renewed : a.new_renewed;
      const totalRen = usePV ? (a.pv_total_renewed ?? (a.pv_pre_renewed + a.pv_new_renewed)) : (a.total_renewed ?? (a.pre_renewed + a.new_renewed));
      const rate = usePV ? a.pv_renewal_rate : a.renewal_rate;
      return { name: a.name, active, pre, should, newRen, totalRen, rate };
    }).sort((a, b) => b.newRen - a.newRen);
    advisorHTML = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        ${sectionTitleInner('顾问转化排行（' + ap + '）')}
        <span style="font-size:10px;color:${SC.muted};background:#F6F8FD;padding:2px 8px;border-radius:5px">应续 = 在读 − 课前续</span>
        <span style="display:inline-flex;border-radius:7px;overflow:hidden;border:1px solid ${SC.border};margin-left:auto">
          <span onclick="setShareAdvisorMode('uv')" style="font-size:10px;font-weight:600;padding:3px 11px;cursor:pointer;${usePV ? 'color:' + SC.muted + ';background:#fff' : 'color:#fff;background:' + SC.accent}">UV</span>
          <span onclick="setShareAdvisorMode('pv')" style="font-size:10px;font-weight:600;padding:3px 11px;cursor:pointer;${!usePV ? 'color:' + SC.muted + ';background:#fff' : 'color:#fff;background:' + SC.accent}">PV</span>
        </span>
      </div>
      <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
        <thead><tr style="background:#F6F8FD">
          <th style="${thA};text-align:left;padding-left:12px">顾问</th>
          <th style="${thA}">在读${modeLabel}</th>
          <th style="${thA}">应续</th>
          <th style="${thA}">当期转化</th>
          <th style="${thA}">已转化</th>
          <th style="${thA}">转化率</th>
          <th style="${thA};width:24%">进度</th>
        </tr></thead>
        <tbody>
          ${advisorRows.map(a => `
            <tr style="border-bottom:1px solid ${SC.border}">
              <td style="${tdA};text-align:left;padding-left:12px;font-weight:600">${a.name}</td>
              <td style="${tdA}">${a.active}</td>
              <td style="${tdA};font-weight:600">${a.should}</td>
              <td style="${tdA};font-weight:700;color:${rateColor(a.rate)}">${a.newRen}</td>
              <td style="${tdA};color:${SC.secondary}">${a.totalRen}</td>
              <td style="${tdA};font-weight:700;color:${rateColor(a.rate)}">${a.rate}%</td>
              <td style="${tdA}">
                <div style="background:${SC.border};border-radius:5px;height:7px;overflow:hidden">
                  <div style="width:${Math.min(Math.round(a.rate), 100)}%;height:100%;background:${rateColor(a.rate)};border-radius:5px"></div>
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  // ── 班级续报详情（仅选了具体老师时显示）──
  let classHTML = '';
  if (data.by_class && data.by_class.length > 0) {
    const thC = 'text-align:center;padding:8px 6px;font-weight:600;color:' + SC.secondary + ';font-size:12px;white-space:nowrap';
    const tdC = 'text-align:center;padding:9px 6px;color:' + SC.primary + ';font-size:13px;white-space:nowrap';
    classHTML = `
      ${sectionTitle('班级续报详情')}
      <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
        <thead><tr style="background:#F6F8FD">
          <th style="${thC};text-align:left;padding-left:12px">班级编号</th>
          <th style="${thC}">学科</th>
          <th style="${thC}">期次</th>
          <th style="${thC}">在读PV</th>
          <th style="${thC}">在读UV</th>
          <th style="${thC}">续费PV</th>
          <th style="${thC}">续费UV</th>
          <th style="${thC}">PV续报率</th>
          <th style="${thC}">UV续报率</th>
        </tr></thead>
        <tbody>
          ${data.by_class.map(c => `
            <tr style="border-bottom:1px solid ${SC.border}">
              <td style="${tdC};text-align:left;padding-left:12px;font-weight:600">${c.class_id}</td>
              <td style="${tdC}">${c.subject}</td>
              <td style="${tdC}">${c.period}</td>
              <td style="${tdC}">${c.active}</td>
              <td style="${tdC}">${c.uv}</td>
              <td style="${tdC}">${c.renewed}</td>
              <td style="${tdC}">${c.renewed_uv}</td>
              <td style="${tdC};font-weight:700;color:${rateColor(c.renewal_rate)}">${c.renewal_rate}%</td>
              <td style="${tdC};font-weight:700;color:${rateColor(c.renewal_uv_rate)}">${c.renewal_uv_rate}%</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  const titleParts = [];
  if (f.period !== '全部') titleParts.push(f.period);
  titleParts.push('数据概览');
  const title = '26暑新初一 · ' + titleParts.join('');

  const subtitleParts = [];
  if (f.teaching_point !== '全部') subtitleParts.push(f.teaching_point); else subtitleParts.push('全教学点');
  if (f.subject !== '全部') subtitleParts.push(f.subject); else subtitleParts.push('全学科');
  if (f.teacher !== '全部') subtitleParts.push(f.teacher); else subtitleParts.push('全老师');
  if (f.advisor !== '全部') subtitleParts.push(f.advisor); else subtitleParts.push('全顾问');

  document.getElementById('shareCardPreview').innerHTML = `
    <div id="shareCardCapture">
      <div class="sc-card">
        <div class="sc-head">
          <div>
            <div class="sc-title">${title}</div>
            <div class="sc-sub">${subtitleParts.join(' · ')}</div>
          </div>
          <div class="sc-date">${dateStr}</div>
        </div>
        ${kpiHTML}
        ${pointHTML}
        ${subjectHTML}
        ${classHTML}
        ${teacherHTML}
        ${advisorHTML}
        <div class="sc-foot">数据来源：UV台帐校准系统 · 2.0</div>
      </div>
    </div>
  `;
}

// 区块标题（带品牌色左侧竖条）
function sectionTitle(text) {
  return `<div class="sc-section">${text}</div>`;
}
function sectionTitleInner(text) {
  return `<span class="sc-section" style="margin:0">${text}</span>`;
}

async function downloadShareCard() {
  const el = document.getElementById('shareCardCapture');
  if (!el) return;
  const btn = document.getElementById('shareDownloadBtn');
  const orig = btn.textContent;
  btn.textContent = '生成中…';
  btn.disabled = true;
  try {
    const canvas = await html2canvas(el, { scale: 2, backgroundColor: null, useCORS: true, logging: false });
    const link = document.createElement('a');
    link.download = '分享卡片_' + new Date().toISOString().slice(0, 10) + '.png';
    link.href = canvas.toDataURL('image/png');
    link.click();
  } catch (e) {
    alert('生成图片失败：' + e.message);
  } finally {
    btn.textContent = orig;
    btn.disabled = false;
  }
}

function closeShareCard() {
  document.getElementById('shareOverlay').style.display = 'none';
}
