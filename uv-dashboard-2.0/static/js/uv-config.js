/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 前端配置常量
   与后端 config/__init__.py + CSS :root 变量保持同步
   ═══════════════════════════════════════════════════════════════ */

const UVConfig = {
  // ── 统一色板 (与 CSS :root 变量一一对应) ──
  COLORS: {
    primary: '#4F6BED',
    primaryHover: '#3B55C7',
    primaryLight: '#EEF2FF',

    // 学科色
    math: '#378ADD',
    chinese: '#639922',
    english: '#BA7517',

    // 状态色
    success: '#16A34A',
    successBg: '#DCFCE7',
    warning: '#CA8A04',
    warningBg: '#FEF3C7',
    danger: '#DC2626',
    dangerBg: '#FEE2E2',

    // 强调色
    accentBlue: '#378ADD',
    accentGreen: '#16A34A',
    accentRed: '#E8505B',
    accentOrange: '#E8943B',
    accentPurple: '#8B5CF6',

    // 中性色
    textPrimary: '#1A1A2E',
    textSecondary: '#2D3142',
    textTertiary: '#6C7293',
    textMuted: '#999999',
    bgSubtle: '#F8F9FB',
    bgHover: '#F0F4FF',
    borderLight: '#E8E9F0',
  },

  // ── 期次（默认值，初始化时从后端 period_config 覆盖）──
  PERIODS: ['零期', '一期', '二期', '三期'],
  PERIOD_ORDER: { '零期': 0, '一期': 1, '二期': 2, '三期': 3 },
  PERIOD_SCHEDULE: {
    '零期': { start: '6/29', end: '7/10', note: '7/4-5休息' },
    '一期': { start: '7/13', end: '7/24', note: '7/18-19休息' },
    '二期': { start: '7/27', end: '8/7',  note: '8/1-2休息' },
    '三期': { start: '8/10', end: '8/21',  note: '8/15-16休息' },
  },
  currentPeriod() { return this._currentPeriod || '零期'; },
  _currentPeriod: null,

  // 从后端 period_config 更新期次配置
  applyPeriodConfig(pc) {
    if (!pc) return;
    const order = pc.order || [];
    if (order.length) this.PERIODS = order;
    // 重建 PERIOD_ORDER
    this.PERIOD_ORDER = {};
    order.forEach((p, i) => { this.PERIOD_ORDER[p] = i; });
    if (pc.schedule) this.PERIOD_SCHEDULE = pc.schedule;
    if (pc.current) this._currentPeriod = pc.current;
  },

  // ── 学科（语数英物四科；物理=雪球科学，teal 系）──
  SUBJECTS: ['雪球思维', '悦读创作', '双语素养', '雪球科学'],
  SUBJECT_SHORT: { '雪球思维': '数', '悦读创作': '语', '双语素养': '英', '雪球科学': '物' },
  SUBJECT_LABEL: { '雪球思维': '数学', '悦读创作': '语文', '双语素养': '英语', '雪球科学': '物理' },
  SUBJECT_COLOR: { '雪球思维': '#378ADD', '悦读创作': '#639922', '双语素养': '#BA7517', '雪球科学': '#2BB6A3' },
  SUBJECT_PILL_CLASS: { '雪球思维': 'sx', '悦读创作': 'yd', '双语素养': 'sy', '雪球科学': 'wk' },
  SUBJECT_TINT: {
    '雪球思维': { bg: '#EAF2FC', border: '#C5DCF7', text: '#2E6FC0' },
    '悦读创作': { bg: '#EEF5E6', border: '#CFE2B8', text: '#4F7A18' },
    '双语素养': { bg: '#F8F0E0', border: '#ECD6B0', text: '#9A6212' },
    '雪球科学': { bg: '#E3F6F2', border: '#B6E7DE', text: '#1E8377' },
  },

  // ── 顾问标签（全称映射 + 动态映射支持）──
  ADVISOR_POINT_TAG: {
    '陈亮延': '天成大厦', '王达04': '天成大厦', '沈思浩': '天成大厦', '龙倩敏': '天成大厦',
    '戎凯01': '同创汇', '王丽': '同创汇', '苏丽婷': '同创汇',
    '杨林33': '新宝利大厦', '林志豪01': '新宝利大厦', '张敏烨': '新宝利大厦',
  },
  POINT_COLOR: { '天成大厦': '#f5a623', '同创汇': '#1d9e75', '新宝利大厦': '#378add' },
  POINT_COLOR_SHARE: { '天成大厦': '#f5a623', '同创汇': '#1d9e75', '新宝利大厦': '#8c92a3' },
  DEFAULT_POINT_COLOR: '#6B7280',
  DEFAULT_POINT_COLOR_SHARE: '#8C92A3',

  // ── 期次色块（冷色实心白字渐变序列，按值固定区分，不跟随学科色）──
  PERIOD_COLORS: {
    '零期': '#4F46E5',
    '一期': '#0EA5E9',
    '二期': '#0D9488',
    '三期': '#059669',
    '四期': '#7C3AED',
  },
  PERIOD_FALLBACK: '#475569',

  // 学季简写（期次为"无"的长学期显示为学季简称）
  SEASON_SHORT: { '暑假': '暑', '寒假': '寒', '春季': '春', '秋季': '秋' },

  // 期次展示："无" 按所在学季显示为 春/秋/暑/寒
  displayPeriod(period, season) {
    if ((period || '').trim() === '无') {
      return this.SEASON_SHORT[season] || (season ? season.replace('季', '') : '无');
    }
    return period || '-';
  },

  // ── 学季×期次 高级徽章（寒暑不同标记 + 春秋不同标记）──
  // 设计语言：左段"学季标记"用季节专属高级渐变（暑假=暖琥珀 / 寒假=冷靛蓝 / 春季=翠绿 / 秋季=秋金），
  //          右段"期次"用深色字；长学期(期次="无")整颗徽章为学季渐变仅显学季(春/秋/暑/寒)。
  SEASON_COLORS: {
    '暑假': { key: '暑', grad: 'linear-gradient(135deg,#FB923C,#F97316)', text: '#9A3412', tint: '#FFF7ED', border: '#FED7AA' },
    '寒假': { key: '寒', grad: 'linear-gradient(135deg,#6366F1,#4338CA)', text: '#3730A3', tint: '#EEF2FF', border: '#C7D2FE' },
    '春季': { key: '春', grad: 'linear-gradient(135deg,#34D399,#059669)', text: '#065F46', tint: '#ECFDF5', border: '#A7F3D0' },
    '秋季': { key: '秋', grad: 'linear-gradient(135deg,#FBBF24,#D97706)', text: '#92400E', tint: '#FFFBEB', border: '#FDE68A' },
  },
  SEASON_FALLBACK: { key: '', grad: 'linear-gradient(135deg,#64748B,#475569)', text: '#334155', tint: '#F1F5F9', border: '#E2E8F0' },
  seasonInfo(season) {
    return this.SEASON_COLORS[season] || this.SEASON_FALLBACK;
  },
  // 返回 {seasonKey, seasonShort, periodLabel, isLong, label}
  //   isLong=true 表示长学期(期次="无")，徽章只显学季(春/秋/暑/寒)
  seasonPeriod(period, season) {
    const info = this.seasonInfo(season);
    const p = (period || '').trim();
    const isLong = (p === '' || p === '无');
    const periodLabel = isLong ? '' : p;
    const label = (info.key ? info.key : (season ? season.replace('季', '') : '')) + periodLabel;
    return { seasonKey: info.key, seasonShort: info.key || (season || ''), periodLabel, isLong, label };
  },
  // 生成"学季×期次"高级徽章 HTML（统一入口）
  seasonPeriodBadge(period, season) {
    const sp = this.seasonPeriod(period, season);
    const info = this.seasonInfo(season);
    if (sp.isLong) {
      return `<span class="cls-period-badge season-${sp.seasonKey || 'x'} long" style="background:${info.grad};color:#fff">`
           + `<span class="cpb-season">${sp.seasonShort}</span></span>`;
    }
    return `<span class="cls-period-badge season-${sp.seasonKey || 'x'}" style="background:${info.tint};border:1px solid ${info.border}">`
         + `<span class="cpb-season" style="background:${info.grad};color:#fff">${sp.seasonShort}</span>`
         + `<span class="cpb-period" style="color:${info.text}">${sp.periodLabel}</span></span>`;
  },

  // ── 班型阶梯（依次进阶：源能→启航→潜能→启能→超能）──
  // 设计语言：随等级上升，色彩由淡底描边 → 实心渐变 → 高光金质，形成清晰的高级感与阶梯感。
  //   Lv1 源能 石墨淡底 / Lv2 启航 天青淡底 / Lv3 潜能 琥珀实心渐变
  //   Lv4 启能 靛紫实心渐变（顶配感）/ Lv5 超能 流光金质渐变（王者档，带高光）
  CLASS_TYPE_ORDER: ['源能班', '启航班', '潜能班', '启能班', '超能班'],
  CLASS_TYPE_COLORS: {
    '源能班': { level: 1, bg: '#F1F5F9', border: '#DDE5EE', text: '#516074' },
    '启航班': { level: 2, bg: '#E4F1FB', border: '#C3E0F5', text: '#2074B8' },
    '潜能班': { level: 3, bg: 'linear-gradient(135deg, #FBBF24, #F59E0B)', border: 'transparent', text: '#FFFFFF' },
    '启能班': { level: 4, bg: 'linear-gradient(135deg, #7C3AED, #4F46E5)', border: 'transparent', text: '#FFFFFF' },
    '超能班': { level: 5, bg: 'linear-gradient(135deg, #F6D365, #C9971A 45%, #8A5A00)', border: 'transparent', text: '#FFF9E6' },
  },

  // ── 教学点色块（紫粉中性淡底描边，按值固定区分）──
  TEACHING_POINT_COLORS: {
    '天成大厦': { bg: '#F3E8FF', border: '#E9D5FF', text: '#6D28D9' },
    '同创汇':   { bg: '#EDE9FE', border: '#DDD6FE', text: '#5B21B6' },
    '新宝利大厦':   { bg: '#F1F5F9', border: '#CBD5E1', text: '#334155' },
  },

  // 兜底淡色板（未知值按字符串哈希稳定取色，保证一致性；低饱和和谐）
  TINT_FALLBACK_PALETTE: [
    { bg: '#EEF2FF', border: '#C7D2FE', text: '#3730A3' },
    { bg: '#E0F2FE', border: '#BAE6FD', text: '#0369A1' },
    { bg: '#CCFBF1', border: '#99F6E4', text: '#0F766E' },
    { bg: '#D1FAE5', border: '#A7F3D0', text: '#047857' },
    { bg: '#FEF3C7', border: '#FDE68A', text: '#B45309' },
    { bg: '#FCE7F3', border: '#FBCFE8', text: '#9D174D' },
  ],

  getAdvisorTag(name, dynamicMap) {
    if (dynamicMap && name in dynamicMap) return dynamicMap[name];
    return this.ADVISOR_POINT_TAG[name] || '';
  },
  getAdvisorTagColor(name, isShare, dynamicMap) {
    const tag = this.getAdvisorTag(name, dynamicMap);
    if (!tag) return isShare ? this.DEFAULT_POINT_COLOR_SHARE : this.DEFAULT_POINT_COLOR;
    const colorMap = isShare ? this.POINT_COLOR_SHARE : this.POINT_COLOR;
    return colorMap[tag] || (isShare ? this.DEFAULT_POINT_COLOR_SHARE : this.DEFAULT_POINT_COLOR);
  },
  // 生成标签 pill HTML（统一入口）
  advisorTagPill(name, isShare, dynamicMap) {
    const tag = this.getAdvisorTag(name, dynamicMap);
    if (!tag) return '';
    const color = this.getAdvisorTagColor(name, isShare, dynamicMap);
    return `<span class="adv-point-tag" style="background:${color};color:#fff">${tag}</span>`;
  },

  // ── 期次 / 班型 / 教学点 色块（独立于学科色，按值固定区分）──
  _tintFallback(key) {
    let h = 0;
    for (const ch of String(key)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return this.TINT_FALLBACK_PALETTE[h % this.TINT_FALLBACK_PALETTE.length];
  },
  // 期次：返回实心色（白字）
  periodColor(p) {
    return this.PERIOD_COLORS[p] || this.PERIOD_FALLBACK;
  },
  // 班型：返回 {bg, border, text, level} 阶梯配色（未知值兜底淡色）
  classTypeColor(ct) {
    return this.CLASS_TYPE_COLORS[ct] || this._tintFallback(ct);
  },
  // 班型阶梯等级（1-5；未知=0）
  classTypeLevel(ct) {
    const c = this.CLASS_TYPE_COLORS[ct];
    return (c && c.level) || 0;
  },
  // 班型排序权重（阶梯顺序；未知排末尾）
  classTypeRank(ct) {
    const i = this.CLASS_TYPE_ORDER.indexOf(ct);
    return i < 0 ? 99 : i;
  },
  // 生成班型阶梯 pill HTML（统一入口，带等级台阶标识 + 高级档高光）
  classTypePill(ct) {
    if (!ct || ct === '-') return '';
    const c = this.classTypeColor(ct);
    const lv = c.level || 0;
    const isGradient = String(c.bg).indexOf('gradient') >= 0;
    // 等级台阶：用小方块数量表现阶梯感（1-5 递增）
    let steps = '';
    if (lv > 0) {
      const dotColor = isGradient ? 'rgba(255,255,255,.85)' : c.text;
      const dimColor = isGradient ? 'rgba(255,255,255,.28)' : (c.border || '#D7DEE8');
      for (let i = 1; i <= 5; i++) {
        steps += `<i class="ct-step" style="background:${i <= lv ? dotColor : dimColor}"></i>`;
      }
    }
    const shine = lv >= 5 ? ' ct-shine' : '';
    const border = c.border && c.border !== 'transparent'
      ? `border:1px solid ${c.border};` : 'border:1px solid transparent;';
    return `<span class="ct-pill ct-lv-${lv}${shine}" style="background:${c.bg};color:${c.text};${border}">`
         + `<span class="ct-content"><span class="ct-steps">${steps}</span><span class="ct-text">${this._esc(ct)}</span></span></span>`;
  },
  // 教学点：返回 {bg, border, text} 淡底描边
  teachingPointColor(pt) {
    return this.TEACHING_POINT_COLORS[pt] || this._tintFallback(pt);
  },

  // ── 课程类型（K列）/ 产品类型（M列 class_mode） 标签色 ──
  // 课程类型：特惠课=暖橙描边，系统课=冷蓝描边
  COURSE_TYPE_COLORS: {
    '特惠课': { bg: '#FFF7ED', border: '#FED7AA', text: '#B45309' },
    '系统课': { bg: '#EEF2FF', border: '#C7D2FE', text: '#3730A3' },
  },
  courseTypeColor(type) {
    return this.COURSE_TYPE_COLORS[type] || this._tintFallback(type);
  },
  courseTypePill(type) {
    if (!type || type === '-') return '';
    const c = this.courseTypeColor(type);
    const border = c.border && c.border !== 'transparent' ? `border:1px solid ${c.border};` : 'border:1px solid transparent;';
    return `<span class="ct-pill course-type-pill" data-course-type="${this._esc(type)}" style="background:${c.bg};color:${c.text};${border}">${this._esc(type)}</span>`;
  },

  // 产品类型：班课=青绿描边，1v1=紫描边
  CLASS_MODE_COLORS: {
    '班课': { bg: '#F0FDFA', border: '#99F6E4', text: '#0F766E' },
    '1v1': { bg: '#FAF5FF', border: '#E9D5FF', text: '#6D28D9' },
  },
  classModeColor(mode) {
    return this.CLASS_MODE_COLORS[mode] || this._tintFallback(mode);
  },
  classModePill(mode) {
    if (!mode || mode === '-') return '';
    const c = this.classModeColor(mode);
    const border = c.border && c.border !== 'transparent' ? `border:1px solid ${c.border};` : 'border:1px solid transparent;';
    return `<span class="ct-pill class-mode-pill" style="background:${c.bg};color:${c.text};${border}">${this._esc(mode)}</span>`;
  },

  // ── 续报标记 ──
  CONTINUE_FALL_POSITIVE: new Set(['是', '已续', 't', 'ac', 'al', 'true', 'yes', '1', 'y']),
  isContinueFall(val) {
    if (!val || val === '-') return false;
    return this.CONTINUE_FALL_POSITIVE.has(String(val).trim().toLowerCase());
  },

  // ── 筛选器配置（从后端 filter_config 覆盖）──
  filterConfig: null,
  filterDefaults: { year: '2026', season: '暑假', branch: '广州', grade: '初一' },
  applyFilterConfig(fc, fd) {
    if (fc) this.filterConfig = fc;
    if (fd) this.filterDefaults = fd;
  },

  // ── API端点 ──
  API_BASE: '',
  endpoints: {
    stats:         '/api/overview/stats',
    matrix:        '/api/overview/matrix',
    filters:       '/api/overview/filters',
    teacherList:   '/api/overview/teacher-list',
    advisorList:   '/api/overview/advisor-list',
    teacherDetail: '/api/overview/teacher/',
    advisorDetail: '/api/overview/advisor/',
    studentDetail: '/api/overview/student/',
    students:      '/api/overview/students',
    classes:       '/api/overview/classes',
    classDetail:   '/api/overview/class/',
    export:        '/api/overview/export',
    shareCard:     '/api/share-card',
    shareGenerate: '/api/share/generate',
    shareDeploy:   '/api/share/deploy',
    trends:        '/api/trends/data',
    acquisitionTrends: '/api/overview/acquisition-trends',
    acquisitionByChannel: '/api/overview/acquisition-by-channel',
    runs:          '/api/runs',
    runDetail:     '/api/runs/',
    pinRun:        '/api/runs/pin',
    calibrate:     '/api/calibrate',
    uploadFull:    '/api/upload-full',
    rebuild:       '/api/rebuild',
    download:      '/api/download/',
    dailyStats:    '/api/daily-stats',
  },

  // ── 颜色辅助 ──
  rateColor(rate) {
    if (rate >= 30) return 'high';
    if (rate >= 15) return 'mid';
    return 'low';
  },
  medalClass(idx) {
    if (idx === 0) return 'medal-gold';
    if (idx === 1) return 'medal-silver';
    if (idx === 2) return 'medal-bronze';
    return '';
  },

  // ── 学员卡片辅助（主讲/顾问/检索 统一 UI）──
  studentInitial(name) {
    const n = String(name || '').trim();
    return n ? n.charAt(0) : '·';
  },
  // 学科彩色 chip（色由 SUBJECT_TINT 控制，cfText 为续秋/状态附文）
  subjectChip(subject, cfText) {
    const short = this.SUBJECT_SHORT[subject] || subject;
    const color = this.SUBJECT_COLOR[subject] || '#999';
    const tint = this.SUBJECT_TINT[subject] || { bg: '#F1F5F9', border: '#E2E8F0', text: '#64748B' };
    const cf = cfText ? `<span class="sc-cf">${this._esc(cfText)}</span>` : '';
    return `<span class="subj-chip" style="background:${tint.bg};border-color:${tint.border};color:${tint.text}"><span class="sc-dot" style="background:${color}"></span>${this._esc(short)}${cf}</span>`;
  },
  // 续秋徽章（pre=课前续 / new=当期转化 / 其余已续秋 / 未续）
  renewalBadge(continueFall, renewalClass) {
    if (this.isContinueFall(continueFall)) {
      if (renewalClass === 'pre') return '<span class="badge-renew pre">课前续</span>';
      if (renewalClass === 'new') return '<span class="badge-renew new">当期转化</span>';
      return '<span class="badge-renew high">已续秋</span>';
    }
    return '<span class="badge-renew none">未续</span>';
  },

  // ── 学员卡片统一状态（主讲/顾问/检索 共用）──
  // 单科续报状态 → {text, cls}
  renewalState(continueFall, renewalClass) {
    if (!this.isContinueFall(continueFall)) return { text: '未续报', cls: 'none' };
    if (renewalClass === 'pre') return { text: '课前续', cls: 'pre' };
    if (renewalClass === 'new') return { text: '当期转化', cls: 'new' };
    return { text: '已续报', cls: 'done' };
  },
  // 合并多科续报 → 取最高优先级（new > pre > done > none）
  mergeRenewal(states) {
    const order = { new: 3, pre: 2, done: 1, none: 0 };
    let best = null;
    (states || []).forEach(st => { if (st && (!best || order[st.cls] > order[best.cls])) best = st; });
    return best || { text: '未续报', cls: 'none' };
  },
  // 在读 / 退费 → {text, cls}
  enrollState(statuses) {
    const arr = (statuses || []).filter(Boolean);
    const hasRefund = arr.some(s => String(s).indexOf('退') >= 0);
    return hasRefund ? { text: '退费', cls: 'refund' } : { text: '在读', cls: 'active' };
  },
  // 渲染右侧双 pill（续报 + 在读/退费）
  statusPillsHTML(renewal, enroll) {
    return `<div class="stu-status">
      <span class="stu-pill pill-renew-${renewal.cls}"><span class="dot"></span>${this._esc(renewal.text)}</span>
      <span class="stu-pill pill-enroll-${enroll.cls}"><span class="dot"></span>${this._esc(enroll.text)}</span>
    </div>`;
  },

  // ── 三科学科状态卡（学员检索/主讲/顾问看板 共用）──
  // data 支持对象 {学科: {status, continue_fall, renewal_class}} 或数组 [{subject, status, ...}]
  subjectStatusCards(data) {
    const map = {};
    if (Array.isArray(data)) {
      (data || []).forEach(sd => { if (sd && sd.subject) map[sd.subject] = sd; });
    } else if (data && typeof data === 'object') {
      Object.assign(map, data);
    }
    let html = '<div class="stu-subjects">';
    this.SUBJECTS.forEach(subj => {
      const sd = map[subj];
      const short = this.SUBJECT_SHORT[subj] || subj;
      const color = this.SUBJECT_COLOR[subj] || '#999';
      const tint = this.SUBJECT_TINT[subj] || { bg: '#F1F5F9', border: '#E2E8F0', text: '#64748B' };
      if (!sd || typeof sd !== 'object') {
        html += `<div class="subj-status-card ssc-empty">
          <div class="ssc-head" style="background:#CBD5E1">${this._esc(short)}</div>
          <div class="ssc-body">
            <div class="ssc-state">未报</div>
            <div class="ssc-renewal" style="background:#F1F5F9;color:#94A3B8">--</div>
          </div>
        </div>`;
        return;
      }
      const status = sd.status || '-';
      const isActive = String(status).indexOf('在读') >= 0;
      const isRefund = (String(status).indexOf('退') >= 0) || (String(status).indexOf('出班') >= 0) || sd.valid_refund === '是';
      const renewal = this.renewalState(sd.continue_fall, sd.renewal_class);

      // 退费：红色调（更突出），与其他未在读灰色卡片区分
      if (isRefund) {
        const stateText = sd.refund_kind || status || '退费';
        html += `<div class="subj-status-card ssc-refund">
          <div class="ssc-head" style="background:#EF4444">${this._esc(short)}</div>
          <div class="ssc-body">
            <div class="ssc-state">${this._esc(stateText)}</div>
            <div class="ssc-renewal">${this._esc(renewal.text)}</div>
          </div>
        </div>`;
        return;
      }
      // 报名了但未在读（结课/未报等）→ 统一灰色卡片
      if (!isActive) {
        const stateText = status && status !== '-' ? status : '未在读';
        html += `<div class="subj-status-card ssc-inactive">
          <div class="ssc-head" style="background:#CBD5E1">${this._esc(short)}</div>
          <div class="ssc-body">
            <div class="ssc-state">${this._esc(stateText)}</div>
            <div class="ssc-renewal" style="background:#F1F5F9;color:#94A3B8">${this._esc(renewal.text)}</div>
          </div>
        </div>`;
        return;
      }

      const stateText = '在读';
      const rc = { none: { bg: '#F1F5F9', text: '#64748B' }, pre: { bg: '#EEF2FF', text: '#4F6BED' }, new: { bg: '#DCFCE7', text: '#16A34A' }, done: { bg: '#DCFCE7', text: '#15803D' } }[renewal.cls] || { bg: '#F1F5F9', text: '#64748B' };
      html += `<div class="subj-status-card">
        <div class="ssc-head" style="background:${color}">${this._esc(short)}</div>
        <div class="ssc-body">
          <div class="ssc-state" style="color:${tint.text}">${this._esc(stateText)}</div>
          <div class="ssc-renewal" style="background:${rc.bg};color:${rc.text}">${this._esc(renewal.text)}</div>
        </div>
      </div>`;
    });
    html += '</div>';
    return html;
  },

  // ── 数字 / 时间 / 空态 辅助 ──
  fmtNum(n) {
    if (n === null || n === undefined || n === '') return '-';
    const num = Number(n);
    if (isNaN(num)) return String(n);
    return num.toLocaleString('en-US');
  },
  // 相对时间：输入 "2026-07-11 21:30:00" 或 ISO，返回 "3分钟前" 等
  relativeTime(str) {
    if (!str) return '';
    let d;
    const m = String(str).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
    if (m) {
      d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
    } else {
      d = new Date(str);
    }
    if (isNaN(d.getTime())) return '';
    const diff = Date.now() - d.getTime();
    if (diff < 0) return '刚刚';
    const sec = Math.floor(diff / 1000);
    if (sec < 60) return '刚刚';
    const min = Math.floor(sec / 60);
    if (min < 60) return min + '分钟前';
    const hr = Math.floor(min / 60);
    if (hr < 24) return hr + '小时前';
    const day = Math.floor(hr / 24);
    if (day < 30) return day + '天前';
    const mon = Math.floor(day / 30);
    if (mon < 12) return mon + '个月前';
    return Math.floor(mon / 12) + '年前';
  },
  // 统一空态渲染：icon 可选 emoji；msg 提示语；sub 次要说明
  renderEmpty(opts) {
    opts = opts || {};
    const icon = opts.icon || '📭';
    const msg = opts.msg || '暂无数据';
    const sub = opts.sub || '';
    return `<div class="uv-empty">
      <div class="uv-empty-icon">${icon}</div>
      <div class="uv-empty-msg">${UVConfig._esc(msg)}</div>
      ${sub ? `<div class="uv-empty-sub">${UVConfig._esc(sub)}</div>` : ''}
    </div>`;
  },

  _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  },

  // ── HTML转义 ──
  escapeAttr(str) {
    if (!str) return '';
    return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
  },
};
