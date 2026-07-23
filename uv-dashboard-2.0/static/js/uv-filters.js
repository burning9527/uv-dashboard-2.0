/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 全局筛选器组件（统一版）
   单一全局 state，13项筛选维度，两 tier 布局
   第一排 7 项固定不联动（始终展示全量值）
   第二排 7 项联动收窄（仅展示有值的可筛选项，含「学员归属」BS列）
   全部多选下拉，支持搜索、全选、逗号参数
   ═══════════════════════════════════════════════════════════════ */

const UVFilters = {
  // ── 单一全局状态：所有筛选维度共用 ──
  // 空 Set = 全选（不发参数）；非空 = 部分选中（发 comma-separated）
  // class_mode 对应 UI 标签"产品类型"(班课/1v1)，API 参数名 class_mode
  state: {
    year: new Set(),
    branch: new Set(),
    season: new Set(),
    grade: new Set(),
    period: new Set(),
    subject: new Set(),
    course_type: new Set(),
    class_mode: new Set(),
    teaching_point: new Set(),
    teacher: new Set(),
    class_type: new Set(),
    enrollment_status: new Set(),
    renewal_status: new Set(),
    student_type: new Set(),
    keyword: '',
  },

  // ── 筛选维度分组（两 tier 布局）──
  // 第一排 7 项：固定不联动，选项始终展示全量（即使筛选后没数据返回空）
  PRIMARY_FIELDS: ['year', 'branch', 'season', 'grade', 'subject', 'course_type', 'class_mode'],
  // 第二排 7 项：与第一排联动收窄，仅展示有值的可筛选项（含「学员归属」BS列）
  SECONDARY_FIELDS: ['period', 'teaching_point', 'teacher', 'class_type', 'enrollment_status', 'renewal_status', 'student_type'],
  ALL_FIELDS: ['year', 'branch', 'season', 'grade', 'period', 'subject', 'course_type', 'class_mode', 'teaching_point', 'teacher', 'class_type', 'enrollment_status', 'renewal_status', 'student_type'],

  // ── 维度中文标签 ──
  FIELD_LABELS: {
    year: '年份', branch: '分校', season: '学季', grade: '年级',
    period: '期次', subject: '学科', course_type: '课程类型',
    class_mode: '产品类型', teaching_point: '教学点', teacher: '主讲',
    class_type: '班型', enrollment_status: '在读状态', renewal_status: '续报状态',
  },

  // ── "取消全选"状态追踪（ID→true = 该下拉当前处于"取消全选"模式）──
  _deselectedAll: new Set(),

  // ── 联动自动选中追踪（field key → true）──
  _autoSelected: new Set(),

  // ── 取全局字段的单一选中值（空Set→''全选；单选→该值；多选→逗号）──
  globalSingle(field) {
    const s = this.state[field];
    if (!s || !(s instanceof Set) || s.size === 0) return '';
    if (s.size === 1) return Array.from(s)[0];
    return Array.from(s).join(',');
  },

  // ── 当前学季（单选→该值；多选/全选→null）──
  currentSeason() {
    const s = this.state.season;
    if (s && s.size === 1) return [...s][0];
    return null;
  },

  // ── 分校 → {教学点/主讲/顾问} 级联选项映射 ──
  branchOptions: {},
  _fullOptions: null,

  // ── faceted 联动事实集 ──
  combos: null,
  comboFields: null,
  _facetOptions: null,

  // ── 筛选器选项缓存 ──
  options: {
    years: ['2025', '2026', '2027'],
    branches: ['广州', '深圳', '北京', '上海'],
    grades: ['一年级', '二年级', '三年级', '四年级', '五年级', '六年级', '初一', '初二', '初三'],
    seasons: ['寒假', '春季', '暑假', '秋季'],
    teaching_points: [],
    periods: [],
    teachers: [],
    advisors: [],
    subjects: [],
    class_types: [],
    enrollment_statuses: [],
    renewal_statuses: [],
    course_types: [],
    product_types: [],
    class_modes: [],
    student_types: ['新生', '老生', '老生拓科'],
  },

  // ── 排班看板选项（API 返回后动态填充，仅供排班展示用）──
  scheduleOptions: {
    teachingPoints: [],
    teachers: [],
    subjects: [],
    classTypes: [],
    courseTypes: [],
    classModes: [],
    ptClassCounts: {},
  },

  // ── ms-* ID → 选项源映射（全局筛选栏统一）──
  _msOptionsMap: {
    'ms-g-year':         () => UVFilters.options.years,
    'ms-g-branch':       () => UVFilters.options.branches,
    'ms-g-season':       () => UVFilters.options.seasons,
    'ms-g-grade':        () => UVFilters.options.grades,
    'ms-g-period':       () => UVConfig.PERIODS,
    'ms-g-subject':      () => UVConfig.SUBJECTS,
    'ms-g-course_type':  () => UVFilters.options.course_types,
    'ms-g-class_mode':   () => UVFilters.options.class_modes,
    'ms-g-tp':           () => UVFilters.options.teaching_points,
    'ms-g-teacher':      () => UVFilters.options.teachers,
    'ms-g-class_type':   () => UVFilters.options.class_types,
    'ms-g-enrollment':   () => UVFilters.options.enrollment_statuses,
    'ms-g-renewal':      () => ['未续报', '课前续', '当期转化'],
    'ms-g-student_type': () => UVFilters.options.student_types,
  },

  // ── ms-* ID → state 字段名映射 ──
  _msStateMap: {
    'ms-g-year':         'year',
    'ms-g-branch':       'branch',
    'ms-g-season':       'season',
    'ms-g-grade':        'grade',
    'ms-g-period':       'period',
    'ms-g-subject':      'subject',
    'ms-g-course_type':  'course_type',
    'ms-g-class_mode':   'class_mode',
    'ms-g-tp':           'teaching_point',
    'ms-g-teacher':      'teacher',
    'ms-g-class_type':   'class_type',
    'ms-g-enrollment':   'enrollment_status',
    'ms-g-renewal':      'renewal_status',
    'ms-g-student_type': 'student_type',
  },

  // ── 动态顾问→教学点映射 ──
  advisorPtMap: null,

  // ══════════════════════════════════════════════
  // 初始化
  // ══════════════════════════════════════════════
  async init() {
    const opts = await UVApi.getFilters();
    if (opts) {
      this.options = {
        years: opts.years || this.options.years,
        branches: opts.branches || this.options.branches,
        grades: opts.grades || this.options.grades,
        seasons: opts.seasons || this.options.seasons,
        teaching_points: opts.teaching_points || [],
        periods: opts.periods || [],
        teachers: opts.teachers || [],
        advisors: opts.advisors || [],
        subjects: opts.subjects ? opts.subjects.map(s => s.key || s) : [],
        class_types: opts.class_types || [],
        enrollment_statuses: opts.enrollment_statuses || [],
        renewal_statuses: opts.renewal_statuses || [],
        course_types: opts.course_types || [],
        product_types: opts.product_types || [],
        class_modes: opts.class_modes || [],
        student_types: opts.student_types || this.options.student_types,  // 学员归属（BS列）
      };
      if (opts.period_config) UVConfig.applyPeriodConfig(opts.period_config);
      if (opts.filter_config) {
        UVConfig.applyFilterConfig(opts.filter_config, opts.filter_defaults);
        const fc = opts.filter_config;
        if (fc.year?.options && !opts.years) this.options.years = fc.year.options;
        if (fc.branch?.options && !opts.branches) this.options.branches = fc.branch.options;
        if (fc.grade?.options && !opts.grades) this.options.grades = fc.grade.options;
        if (fc.season?.options && !opts.seasons) this.options.seasons = fc.season.options;
      }
      if (opts.filter_defaults) {
        UVConfig.filterDefaults = Object.assign({}, UVConfig.filterDefaults || {}, opts.filter_defaults);
        const fd = opts.filter_defaults;
        // 全局 state：有默认值的字段选中默认，无默认值字段默认全选（空Set）
        // ⚠️ 分校/学季/年级 全部默认空（=全选），避免锁单分校（如曾因默认「广州」隐藏深圳）
        this._setDefaultSet('year', fd.year, this.options.years);
        this._setDefaultSet('branch', '', this.options.branches);
        this._setDefaultSet('season', '', this.options.seasons);
        this._setDefaultSet('grade', '', this.options.grades);
        // 以下维度默认全选（空Set）
        this._setDefaultSet('period', '', UVConfig.PERIODS);
        this._setDefaultSet('subject', '', UVConfig.SUBJECTS);
        this._setDefaultSet('teaching_point', '', this.options.teaching_points);
        this._setDefaultSet('teacher', '', this.options.teachers);
        this._setDefaultSet('course_type', '', this.options.course_types);
        this._setDefaultSet('class_mode', fd.class_mode, this.options.class_modes);
        this._setDefaultSet('class_type', '', this.options.class_types);
        this._setDefaultSet('enrollment_status', '', this.options.enrollment_statuses);
        this._setDefaultSet('renewal_status', '', ['未续报', '课前续', '当期转化']);
        this._setDefaultSet('student_type', '', this.options.student_types);
      }
      this.branchOptions = opts.branch_options || {};
      this.combos = opts.combos || null;
      this.comboFields = opts.combo_fields || null;
    }
    this._fullOptions = {
      teaching_points: [...this.options.teaching_points],
      teachers: [...this.options.teachers],
      advisors: [...this.options.advisors],
    };
    this._recomputeFacets();
    this._autoSelectUnique();
    if (this.globalSingle('branch')) this._applyBranchScopedOptions();
    this.renderAllDropdowns();
    this.applyFilterGlossary();
  },

  // ── 设置默认值到 Set ──
  _setDefaultSet(field, defaultVal, allOptions) {
    const s = this.state[field];
    if (!(s instanceof Set)) return;
    s.clear();
    if (defaultVal) s.add(defaultVal);
  },

  // ══════════════════════════════════════════════
  // 构建API参数（单一全局 state，无 section 参数）
  // ══════════════════════════════════════════════
  buildParams(opts = {}) {
    const params = {};
    const optionSources = {
      year: this.options.years,
      branch: this.options.branches,
      season: this.options.seasons,
      grade: this.options.grades,
      period: UVConfig.PERIODS,
      subject: UVConfig.SUBJECTS,
      course_type: this.options.course_types,
      class_mode: this.options.class_modes,
      teaching_point: this.options.teaching_points,
      teacher: this.options.teachers,
      class_type: this.options.class_types,
      enrollment_status: this.options.enrollment_statuses,
      renewal_status: ['未续报', '课前续', '当期转化'],
      student_type: this.options.student_types,
    };
    for (const field of this.ALL_FIELDS) {
      if (opts.exclude && opts.exclude.includes(field)) continue;
      const val = this.state[field];
      if (!(val instanceof Set)) continue;
      const total = optionSources[field]?.length || 0;
      if (val.size === 0 || val.size === total) continue; // 全选不发参
      params[field] = Array.from(val).join(',');
    }
    if (opts.includeKeyword && this.state.keyword && this.state.keyword.trim()) {
      params.keyword = this.state.keyword.trim();
    }
    // 透传 opts 里的非筛选项字段（如 channelLevel 等专项参数）
    for (const k of Object.keys(opts)) {
      if (k === 'exclude' || k === 'includeKeyword') continue;
      if (params[k] === undefined && opts[k] !== undefined) {
        params[k] = opts[k];
      }
    }
    return params;
  },

  // ══════════════════════════════════════════════
  // Faceted 联动（单一全局 state 计算）
  // ══════════════════════════════════════════════
  _recomputeFacets() {
    const cf = this.comboFields;
    const combos = this.combos;
    const st = this.state;
    if (!cf || !combos || !Array.isArray(combos)) { this._facetOptions = null; return; }
    const facetFields = cf.filter(f => st[f] instanceof Set);
    const idx = {}; cf.forEach((f, i) => { idx[f] = i; });
    const avail = {}; facetFields.forEach(f => { avail[f] = new Set(); });
    for (let c = 0; c < combos.length; c++) {
      const combo = combos[c];
      const failed = [];
      for (let k = 0; k < facetFields.length; k++) {
        const f = facetFields[k];
        const sel = st[f];
        const val = combo[idx[f]];
        if (sel.size > 0 && !sel.has(val)) failed.push(k);
      }
      if (failed.length === 0) {
        for (let k = 0; k < facetFields.length; k++) {
          const v = combo[idx[facetFields[k]]];
          if (v !== '') avail[facetFields[k]].add(v);
        }
      } else if (failed.length === 1) {
        const f = facetFields[failed[0]];
        const v = combo[idx[f]];
        if (v !== '') avail[f].add(v);
      }
    }
    const out = {};
    facetFields.forEach(f => { out[f] = this._facetSort(f, Array.from(avail[f])); });
    this._facetOptions = out;
  },

  _facetSort(field, arr) {
    if (field === 'year') return arr.sort((a, b) => String(b).localeCompare(String(a)));
    if (field === 'period') {
      const order = UVConfig.PERIODS_ALL || UVConfig.PERIODS || [];
      return arr.sort((a, b) => {
        const ia = order.indexOf(a), ib = order.indexOf(b);
        return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
      });
    }
    return arr.sort((a, b) => String(a).localeCompare(String(b), 'zh'));
  },

  // 剔除因联动失效的已选项（迭代至稳定）
  _pruneInvalidSelections() {
    const fo = this._facetOptions;
    if (!fo) return;
    for (let iter = 0; iter < 8; iter++) {
      let changed = false;
      for (const field of Object.keys(fo)) {
        const sel = this.state[field];
        if (!(sel instanceof Set)) continue;
        // ── BUG 修复：第一排字段（固定不联动）不应被 prune 静默清空 ──
        // 第一排始终展示全量选项（_msOptionsMap），不应被联动收窄剪枝
        // 用户的"手动选择"在第二排才可能被联动清掉
        if (this.PRIMARY_FIELDS.includes(field)) continue;
        const valid = new Set(fo[field]);
        for (const v of Array.from(sel)) {
          if (!valid.has(v)) { sel.delete(v); changed = true; }
        }
      }
      if (!changed) break;
      this._recomputeFacets();
    }
  },

  // 联动自动选中唯一维度
  _autoSelectUnique() {
    const fo = this._facetOptions;
    if (!fo) return;
    for (let iter = 0; iter < 12; iter++) {
      let changed = false;
      for (const field of Object.keys(fo)) {
        const sel = this.state[field];
        if (!(sel instanceof Set)) continue;
        // ── BUG 修复：第二排字段不应被 _autoSelectUnique 清空 ──
        // 用户的"手动选择"（如退费）应被尊重；即使 facet 变宽，也保留用户选择
        // 第一排字段（PRIMARY_FIELDS）本来就不参与 _autoSelectUnique
        if (this.SECONDARY_FIELDS.includes(field)) continue;
        const avail = fo[field];
        if (avail && avail.length === 1) {
          const v = avail[0];
          const id = this._fieldToMsId(field);
          if (id && this._deselectedAll.has(id)) continue;
          if (sel.size === 1 && sel.has(v)) { this._autoSelected.add(field); continue; }
          sel.clear(); sel.add(v);
          this._autoSelected.add(field);
          changed = true;
        } else if (this._autoSelected.has(field)) {
          sel.clear();
          this._autoSelected.delete(field);
          changed = true;
        }
      }
      if (!changed) break;
      this._recomputeFacets();
    }
  },

  // 字段 → ms-* ID 反查
  _fieldToMsId(field) {
    for (const [id, f] of Object.entries(this._msStateMap)) {
      if (f === field) return id;
    }
    return null;
  },

  // ms-* ID → 当前可用选项
  // 第一排 7 项（年份/分校/学季/年级/学科/课程类型/产品类型）固定不联动，始终展示全量值
  // 第二排 7 项（期次/教学点/主讲/班型/在读状态/续报状态/学员归属）faceted 收窄，仅展示有值的可筛选项
  _optionsForId(id) {
    const field = this._msStateMap[id];
    if (field && this.PRIMARY_FIELDS.includes(field)) {
      const fn = this._msOptionsMap[id];
      return fn ? fn() : [];
    }
    if (field) {
      const fo = this._facetOptions && this._facetOptions[field];
      if (fo && fo.length) return fo;
    }
    const fn = this._msOptionsMap[id];
    return fn ? fn() : [];
  },

  // ══════════════════════════════════════════════
  // 多选下拉渲染与交互
  // ══════════════════════════════════════════════
  renderMultiSelect(id, options, selectedSet) {
    const container = document.getElementById(id);
    if (!container) return;
    const textEl = container.querySelector('.ms-text');
    const dropdown = container.querySelector('.ms-dropdown');
    if (!textEl || !dropdown) return;

    dropdown.innerHTML = '';
    if (options.length > 5) {
      const searchBox = document.createElement('div');
      searchBox.className = 'ms-search';
      searchBox.innerHTML = '<input type="text" placeholder="搜索..." class="ms-search-input">';
      dropdown.appendChild(searchBox);
      const searchInput = searchBox.querySelector('.ms-search-input');
      searchInput.addEventListener('input', () => {
        const keyword = searchInput.value.toLowerCase();
        dropdown.querySelectorAll('.ms-item:not(.ms-all)').forEach(item => {
          item.style.display = item.textContent.toLowerCase().includes(keyword) ? '' : 'none';
        });
      });
      searchInput.addEventListener('click', (e) => e.stopPropagation());
    }

    const isDeselectedAll = this._deselectedAll.has(id);
    const isAllSelected = !isDeselectedAll && (selectedSet.size === 0 || selectedSet.size === options.length);
    const allItem = document.createElement('div');
    allItem.className = 'ms-item ms-all';
    allItem.innerHTML = `<input type="checkbox" ${isAllSelected ? 'checked' : ''}> 全选`;
    allItem.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleAllMultiSelect(id, options, selectedSet);
    });
    dropdown.appendChild(allItem);

    options.forEach(opt => {
      const item = document.createElement('div');
      item.className = 'ms-item';
      const checked = isAllSelected || selectedSet.has(opt);
      item.innerHTML = `<input type="checkbox" ${checked ? 'checked' : ''}> ${opt}`;
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        this.onMultiSelectChange(id, opt, selectedSet);
      });
      dropdown.appendChild(item);
    });

    this.updateMultiSelectText(id, selectedSet, options);
  },

  toggleMultiSelect(id) {
    const container = document.getElementById(id);
    const dropdown = container?.querySelector('.ms-dropdown');
    if (!dropdown) return;
    document.querySelectorAll('.ms-dropdown.open').forEach(d => {
      if (d !== dropdown) d.classList.remove('open');
    });
    dropdown.classList.toggle('open');
    const searchInput = dropdown.querySelector('.ms-search-input');
    if (searchInput) setTimeout(() => searchInput.focus(), 50);
  },

  toggleAllMultiSelect(id, options, selectedSet) {
    const isDeselected = this._deselectedAll.has(id);
    const isAllSelected = !isDeselected && (selectedSet.size === 0 || selectedSet.size === options.length);
    if (isAllSelected) {
      this._deselectedAll.add(id);
      selectedSet.clear();
    } else {
      this._deselectedAll.delete(id);
      selectedSet.clear();
    }
    this.renderMultiSelect(id, options, selectedSet);
    this._onGlobalChange();
  },

  onMultiSelectChange(id, value, selectedSet) {
    const opts = this._optionsForId(id);
    const field = this._msStateMap[id];
    if (field) this._autoSelected.delete(field);

    const wasDeselectedAll = this._deselectedAll.has(id);
    this._deselectedAll.delete(id);

    if (wasDeselectedAll && selectedSet.size === 0) {
      selectedSet.clear(); selectedSet.add(value);
    } else if (selectedSet.size === 0) {
      opts.forEach(o => { if (o !== value) selectedSet.add(o); });
    } else if (selectedSet.has(value)) {
      selectedSet.delete(value);
    } else {
      selectedSet.add(value);
      if (selectedSet.size === opts.length) selectedSet.clear();
    }

    // faceted 联动 + 自动选中
    this._recomputeFacets();
    this._pruneInvalidSelections();
    this._autoSelectUnique();

    // 分校变化：收窄教学点/主讲
    if (field === 'branch') this._applyBranchScopedOptions();

    this.renderAllDropdowns();
    // 不自动刷新数据视图——等用户点"查询"按钮才刷新
    this._markPendingRefresh();

    // 分享卡片同步
    const shareOverlay = document.getElementById('shareOverlay');
    if (shareOverlay && shareOverlay.style.display === 'flex' && typeof updateShareCard === 'function') {
      updateShareCard();
    }
  },

  // ── 标记有未应用的筛选变更（高亮"查询"按钮）──
  _markPendingRefresh() {
    const btn = document.getElementById('gf-query-btn');
    if (btn) btn.classList.add('pending');
  },

  _clearPendingRefresh() {
    const btn = document.getElementById('gf-query-btn');
    if (btn) btn.classList.remove('pending');
  },

  updateMultiSelectText(id, selectedSet, options) {
    const container = document.getElementById(id);
    const textEl = container?.querySelector('.ms-text');
    if (!textEl) return;
    const total = options.length;
    const isDeselectedAll = this._deselectedAll.has(id);
    const isAll = !isDeselectedAll && (selectedSet.size === 0 || selectedSet.size === total);
    const isPartial = !isAll && !isDeselectedAll && selectedSet.size > 0;
    textEl.classList.toggle('has-selection', isPartial || isDeselectedAll);
    if (isDeselectedAll) textEl.textContent = '未选择';
    else if (isAll) textEl.textContent = '全部';
    else textEl.textContent = Array.from(selectedSet).join(', ');
  },

  // ══════════════════════════════════════════════
  // 全局筛选器变更：联动所有视图
  // ══════════════════════════════════════════════
  _onGlobalChange() {
    this._recomputeFacets();
    this._pruneInvalidSelections();
    this._autoSelectUnique();
    this.renderAllDropdowns();
    // 不自动刷新数据视图——等用户点"查询"按钮才刷新
    this._markPendingRefresh();
    const shareOverlay = document.getElementById('shareOverlay');
    if (shareOverlay && shareOverlay.style.display === 'flex' && typeof updateShareCard === 'function') {
      updateShareCard();
    }
  },

  // ── 重置全局筛选器 ──
  resetGlobalFilters() {
    const fd = UVConfig.filterDefaults || {};
    // ⚠️ 分校/学季/年级 全部默认空（=全选），避免锁单分校
    this._setDefaultSet('year', fd.year, this.options.years);
    this._setDefaultSet('branch', '', this.options.branches);
    this._setDefaultSet('season', '', this.options.seasons);
    this._setDefaultSet('grade', '', this.options.grades);
    this._setDefaultSet('period', '', UVConfig.PERIODS);
    this._setDefaultSet('subject', '', UVConfig.SUBJECTS);
    this._setDefaultSet('teaching_point', '', this.options.teaching_points);
    this._setDefaultSet('teacher', '', this.options.teachers);
    this._setDefaultSet('course_type', '', this.options.course_types);
    this._setDefaultSet('class_mode', fd.class_mode, this.options.class_modes);
    this._setDefaultSet('class_type', '', this.options.class_types);
    this._setDefaultSet('enrollment_status', '', this.options.enrollment_statuses);
    this._setDefaultSet('renewal_status', '', ['未续报', '课前续', '当期转化']);
    this._setDefaultSet('student_type', '', this.options.student_types);
    this._deselectedAll.clear();
    this._autoSelected.clear();
    this._recomputeFacets();
    this._autoSelectUnique();
    this._applyBranchScopedOptions();
    this.renderAllDropdowns();
    // 不自动刷新数据视图——等用户点"查询"按钮才刷新
    this._markPendingRefresh();
    const shareOverlay = document.getElementById('shareOverlay');
    if (shareOverlay && shareOverlay.style.display === 'flex' && typeof updateShareCard === 'function') {
      updateShareCard();
    }
  },

  // ══════════════════════════════════════════════
  // 分校级联
  // ══════════════════════════════════════════════
  _applyBranchScopedOptions() {
    const full = this._fullOptions || { teaching_points: [], teachers: [], advisors: [] };
    const gb = this.globalSingle('branch');
    const bo = gb ? this.branchOptions[gb] : null;
    this.options.teaching_points = bo ? (bo.teaching_points || []) : [...full.teaching_points];
    this.options.teachers        = bo ? (bo.teachers || [])        : [...full.teachers];
    this.options.advisors        = bo ? (bo.advisors || [])        : [...full.advisors];
    this._pruneBranchScopedSelections();
  },

  _pruneBranchScopedSelections() {
    const validTp = new Set(this.options.teaching_points);
    const validTc = new Set(this.options.teachers);
    const tpSet = this.state.teaching_point;
    const tcSet = this.state.teacher;
    if (tpSet instanceof Set) {
      for (const v of Array.from(tpSet)) if (!validTp.has(v)) tpSet.delete(v);
    }
    if (tcSet instanceof Set) {
      for (const v of Array.from(tcSet)) if (!validTc.has(v)) tcSet.delete(v);
    }
  },

  // ══════════════════════════════════════════════
  // 刷新当前视图
  // ══════════════════════════════════════════════
  _refreshCurrentView() {
    if (typeof currentMainTab === 'undefined') return;
    if (currentMainTab === 'dashboard') {
      if (typeof loadDashboard === 'function') loadDashboard();
    } else if (currentMainTab === 'detail') {
      if (typeof switchSubTab === 'function') switchSubTab(typeof currentSubTab !== 'undefined' ? currentSubTab : 'matrix');
    } else if (currentMainTab === 'monitor') {
      if (typeof loadMonitor === 'function') loadMonitor();
    }
  },

  // ══════════════════════════════════════════════
  // 渲染所有全局下拉
  // ══════════════════════════════════════════════
  renderAllDropdowns() {
    for (const [id, field] of Object.entries(this._msStateMap)) {
      const opts = this._optionsForId(id);
      const sel = this.state[field];
      if (sel instanceof Set) this.renderMultiSelect(id, opts, sel);
    }
  },

  // ══════════════════════════════════════════════
  // 期次 Chips（排班展示用，点击更新全局 state）
  // ══════════════════════════════════════════════
  renderPeriodChips(containerId, clickHandler, allLabel = '全部', periodItems = null) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (periodItems) this._periodChipsItems = periodItems;
    const items = this._periodChipsItems || UVConfig.PERIODS.map(p => ({ value: p, label: p }));
    container.innerHTML = '';
    const selectedSet = this.state.period;
    const allValues = items.map(i => i.value);
    const isAllSelected = selectedSet.size === 0 || allValues.every(v => selectedSet.has(v));
    const allChip = document.createElement('span');
    allChip.className = `period-chip ${isAllSelected ? 'active' : ''}`;
    allChip.textContent = allLabel;
    allChip.addEventListener('click', () => {
      selectedSet.clear();
      this.renderPeriodChips(containerId, clickHandler);
      this._onGlobalChange();
      if (typeof clickHandler === 'function') clickHandler('all');
    });
    container.appendChild(allChip);
    items.forEach(it => {
      const chip = document.createElement('span');
      chip.className = `period-chip ${selectedSet.has(it.value) ? 'active' : ''} ${it.value === UVConfig.currentPeriod() ? 'current' : ''}`;
      chip.textContent = it.label;
      chip.addEventListener('click', () => {
        if (selectedSet.has(it.value)) selectedSet.delete(it.value);
        else selectedSet.add(it.value);
        this.renderPeriodChips(containerId, clickHandler);
        this._onGlobalChange();
        if (typeof clickHandler === 'function') clickHandler(it.value);
      });
      container.appendChild(chip);
    });
  },

  // ══════════════════════════════════════════════
  // 教学点 Chips（排班展示用，带班量）
  // ══════════════════════════════════════════════
  renderTpChips(containerId, clickHandler) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    const pts = this.scheduleOptions.teachingPoints;
    const counts = this.scheduleOptions.ptClassCounts || {};
    const selectedSet = this.state.teaching_point;
    const allChip = document.createElement('span');
    const totalClasses = Object.values(counts).reduce((a, b) => a + b, 0);
    const isAllSelected = selectedSet.size === 0 || selectedSet.size === pts.length;
    allChip.className = `tp-chip ${isAllSelected ? 'active' : ''}`;
    allChip.textContent = `全部(${totalClasses})`;
    allChip.addEventListener('click', () => {
      selectedSet.clear();
      this.renderTpChips(containerId, clickHandler);
      this._onGlobalChange();
      if (typeof clickHandler === 'function') clickHandler('all');
    });
    container.appendChild(allChip);
    pts.forEach(pt => {
      const chip = document.createElement('span');
      const n = counts[pt] || 0;
      chip.className = `tp-chip ${selectedSet.has(pt) ? 'active' : ''}`;
      chip.textContent = `${pt}(${n})`;
      chip.addEventListener('click', () => {
        if (selectedSet.has(pt)) selectedSet.delete(pt);
        else selectedSet.add(pt);
        this.renderTpChips(containerId, clickHandler);
        this._onGlobalChange();
        if (typeof clickHandler === 'function') clickHandler(pt);
      });
      container.appendChild(chip);
    });
  },

  // ══════════════════════════════════════════════
  // 筛选标签释意 tooltip
  // ══════════════════════════════════════════════
  applyFilterGlossary() {
    const fc = UVConfig.filterConfig || {};
    document.querySelectorAll('.sf-label').forEach(el => {
      const field = this.FIELD_LABELS[(el.textContent || '').trim()];
      const g = el.dataset.glossary || (field && fc[field] && fc[field].glossary);
      if (g) el.title = g;
    });
  },

  // ── 兼容旧调用（不再需要 section 参数）──
  buildScheduleParams() { return this.buildParams(); },
  resetSection() { this.resetGlobalFilters(); },
};

// 点击空白处关闭所有多选下拉
document.addEventListener('click', (e) => {
  if (!e.target.closest('.multi-select')) {
    document.querySelectorAll('.ms-dropdown.open').forEach(d => d.classList.remove('open'));
  }
});
