/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 主讲看板组件
   左侧：主讲排名（复用数据看板排行口径，period+teaching_point 全局筛选）
   右侧：详情 = 汇总 + 班级情况（卡片网格）+ 学员情况（表格）
   续报/转化切换只变更右上角百分数与排序
   ═══════════════════════════════════════════════════════════════ */

const UVTeacher = {
  teachers: [],
  rankMode: 'renewal',
  selectedTeacher: null,

  // HTML 转义（防 XSS / 破坏结构）
  _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  },

  // 全局筛选参数
  _params() {
    return UVFilters.buildParams();
  },

  async load() {
    const data = await UVApi.getTeacherList(this._params());
    if (data) {
      this.teachers = data;
      this.render();
    }
  },

  switchMode(mode) {
    this.rankMode = mode;
    this.render();
    document.querySelectorAll('#teacher-rank-btns .rank-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
  },

  render() {
    const container = document.getElementById('teacher-list-content');
    if (!container) return;
    const mode = this.rankMode;

    if (!this.teachers.length) { container.innerHTML = '<div class="no-data">暂无数据</div>'; return; }

    // 过滤：当前筛选下无学员/在读记录的老师不显示
    const visible = this.teachers.filter(t => (t.active || 0) > 0);
    if (!visible.length) { container.innerHTML = '<div class="no-data">暂无数据</div>'; return; }

    // 根据当前模式排序：续报模式按 renewal_rate，转化模式按 conv_rate
    const sorted = [...visible].sort((a, b) => {
      const rateA = mode === 'renewal' ? a.renewal_rate : a.conv_rate;
      const rateB = mode === 'renewal' ? b.renewal_rate : b.conv_rate;
      return rateB - rateA;
    });

    // 计算最大值用于进度条
    const maxRate = Math.max(...sorted.map(t => mode === 'renewal' ? t.renewal_rate : t.conv_rate), 1);

    let html = '<div class="teacher-ranking-list">';
    sorted.forEach((t, idx) => {
      const medal = UVConfig.medalClass(idx);
      const subjPill = `<span class="subj-pill ${UVConfig.SUBJECT_PILL_CLASS[t.subject] || ''}">${UVConfig.SUBJECT_SHORT[t.subject] || ''}</span>`;
      const rate = mode === 'renewal' ? t.renewal_rate : t.conv_rate;
      const rateClass = UVConfig.rateColor(rate);
      const barWidth = Math.min(rate / maxRate * 100, 100);

      // 统一 stat-row 数据行
      const statRow = `<div class="rank-stat-row">
        <div class="rank-stat-cell"><div class="rs-label">在读</div><div class="rs-val">${t.active || 0}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">应续</div><div class="rs-val">${t.should_renew || 0}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">转化</div><div class="rs-val accent">${t.new_renewed || 0}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">已续费</div><div class="rs-val">${t.total_renewed || 0}</div></div>
      </div>`;

      const isActive = this.selectedTeacher === t.name;
      html += `<div class="rank-item ${medal}${isActive ? ' active' : ''}" data-name="${this._esc(t.name)}" onclick="UVTeacher.viewDetail(this.dataset.name)">
        <div class="rank-num">${idx + 1}</div>
        <div class="rank-info">
          <div class="rank-name">${subjPill} ${this._esc(t.name)}</div>
          <div class="rank-bar-wrap"><div class="rank-bar-fill ${rateClass}" style="width:${barWidth}%"></div></div>
          ${statRow}
        </div>
        <div class="rank-rate ${rateClass}">${rate}%</div>
      </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
  },

  async viewDetail(name) {
    this.selectedTeacher = name;
    this.render(); // 高亮左侧选中的卡片

    const params = this._params();
    const data = await UVApi.getTeacherDetail(name, params);
    if (!data) return;
    const container = document.getElementById('teacher-detail-content');
    if (!container) return;

    const summary = data.summary || {};
    const classes = data.classes || [];
    const students = (data.students || []).sort((a, b) => {
      const aRen = UVConfig.isContinueFall(a.continue_fall) ? 1 : 0;
      const bRen = UVConfig.isContinueFall(b.continue_fall) ? 1 : 0;
      return bRen - aRen;
    });

    // 当前详情受全局学季筛选影响；单学季时，"无"期次显示为 秋/春/暑/寒
    const activeSeason = UVFilters.currentSeason();

    const subjPill = `<span class="subj-pill ${UVConfig.SUBJECT_PILL_CLASS[classes[0]?.subject] || ''}">${UVConfig.SUBJECT_SHORT[classes[0]?.subject] || ''}</span>`;

    // ── 详情头部（常规流）──
    const rateColor = UVConfig.rateColor(summary.renewal_rate || 0);
    const convColor = UVConfig.rateColor(summary.conv_rate || 0);
    let html = `<div class="board-detail-head">
      <div class="bdh-title">${subjPill} ${this._esc(name)} <span class="bdh-sub">主讲详情</span></div>
    </div>`;

    // ── 汇总条 ──
    html += `<div class="board-summary">
      <div class="bs-item"><span class="bs-val">${summary.total_active || 0}</span><span class="bs-label">在读科目</span></div>
      <div class="bs-item"><span class="bs-val">${summary.total_should || 0}</span><span class="bs-label">应续</span></div>
      <div class="bs-item"><span class="bs-val accent">${summary.total_new || 0}</span><span class="bs-label">当期转化</span></div>
      <div class="bs-item"><span class="bs-val">${summary.total_renewed || 0}</span><span class="bs-label">已续费</span></div>
      <div class="bs-item"><span class="bs-val rate-${rateColor}">${summary.renewal_rate || 0}%</span><span class="bs-label">续报率</span></div>
      <div class="bs-item"><span class="bs-val rate-${convColor}">${summary.conv_rate || 0}%</span><span class="bs-label">转化率</span></div>
      <div class="bs-item"><span class="bs-val">${summary.class_count || 0}</span><span class="bs-label">带班数</span></div>
    </div>`;

    // ── 班级情况（默认全部展示，按期次分组）──
    const totalClassActive = classes.reduce((sum, c) => sum + (c.active || 0), 0);
    html += `<div class="board-section">
      <div class="board-section-title">班级情况 <span class="bs-count">${classes.length} 个班 · ${totalClassActive} 人在读</span></div>`;
    if (classes.length) {
      // 按期次分组（后端已按期次排序，此处保持顺序聚合）
      const groups = this._groupClassesByPeriod(classes);
      groups.forEach(grp => {
        html += `<div class="class-period-group">
          <div class="cpg-head"><span class="cpg-dot"></span>${this._esc(UVConfig.displayPeriod(grp.period, activeSeason))}<span class="cpg-count">${grp.classes.length} 班</span></div>
          <div class="class-card-grid">`;
        grp.classes.forEach(c => {
          const subjShort = UVConfig.SUBJECT_SHORT[c.subject] || c.subject;
          const subjColor = UVConfig.SUBJECT_COLOR[c.subject] || '#999';
          const rateColorCls = c.renewal_rate >= 50 ? 'good' : (c.renewal_rate >= 25 ? 'warn' : 'bad');
          html += `<div class="class-card" data-class-id="${this._esc(c.class_id)}" onclick="UVModal.openClassDetail('${this._esc(c.class_id)}')">
            <div class="cc-bar" style="background:${subjColor}"></div>
            <div class="cc-body">
              <div class="cc-head">
                <span class="cc-subj" style="background:${subjColor};color:#fff">${subjShort}</span>
                <span class="cc-id">${this._esc(c.class_id)}</span>
              </div>
              <div class="cc-meta">
                <span class="cc-period">${this._esc(UVConfig.displayPeriod(c.period, activeSeason))}</span>
                <span class="cc-slot">${this._esc(c.time_slot || '-')}</span>
              </div>
              <div class="cc-stats">
                <div class="cc-stat"><span class="cc-num">${c.active || 0}</span><span class="cc-lbl">在读</span></div>
                <div class="cc-stat"><span class="cc-num renew">${c.renewed || 0}</span><span class="cc-lbl">续报</span></div>
                <div class="cc-stat rate"><span class="cc-num ${rateColorCls}">${c.renewal_rate || 0}%</span><span class="cc-lbl">续报率</span></div>
              </div>
            </div>
          </div>`;
        });
        html += '</div></div>';
      });
    } else {
      html += '<div class="no-data">该筛选条件下暂无带班数据</div>';
    }
    html += '</div>';

    // ── 学员情况（统一学员卡片，点击打开学员详情）──
    html += `<div class="board-section">
      <div class="board-section-title">学员情况 <span class="bs-count">${students.length} 条在读记录</span></div>`;
    if (students.length) {
      html += '<div class="stu-list">';
      students.forEach(s => {
        const initial = UVConfig.studentInitial(s.name);
        const statusCards = UVConfig.subjectStatusCards(s.subjects || {});
        html += `<div class="stu-card" data-uid="${this._esc(s.uid)}">
          <div class="stu-avatar">${this._esc(initial)}</div>
          <div class="stu-main">
            <div class="stu-line1">
              <span class="stu-name">${this._esc(s.name)}</span>
              <span class="stu-uid">${this._esc(s.uid)}</span>
            </div>
            <div class="stu-line3">
              <span class="sm-item"><b>教学点</b>${this._esc(s.teaching_point)}</span>
              <span class="sm-item"><b>期次</b>${this._esc(UVConfig.displayPeriod(s.period, activeSeason))}</span>
              <span class="sm-item"><b>班型</b>${UVConfig.classTypePill(s.class_type) || this._esc(s.class_type || '-')}</span>
              <span class="sm-item"><b>顾问</b>${this._esc(s.advisor)}</span>
              <span class="sm-item"><b>班级</b><span class="cc-id-link" title="${this._esc(s.class_id)}">${this._esc(s.class_id)}</span></span>
            </div>
          </div>
          <div class="stu-right">${statusCards}</div>
        </div>`;
      });
      html += '</div>';
    } else {
      html += '<div class="no-data">该筛选条件下暂无学员</div>';
    }
    html += '</div>';

    container.innerHTML = html;
    container.scrollTop = 0;

    // 事件委托：点击学员卡片 → 打开学员详情弹窗
    container.onclick = (e) => {
      const row = e.target.closest('.stu-card');
      if (row) { UVModal.openStudentDetail(row.dataset.uid); return; }
      const clsLink = e.target.closest('.cc-id-link');
      if (clsLink) { e.stopPropagation(); UVModal.openClassDetail(clsLink.textContent.trim()); }
    };
  },

  // 班级卡片的教学点：优先用聚合字段，否则从学员反查
  _ptOfClass(c, students) {
    const hit = students.find(s => s.class_id === c.class_id && s.subject === c.subject);
    return hit ? hit.teaching_point : '';
  },

  // 按期次分组班级（保持后端排序，按期次首次出现顺序聚合）
  _groupClassesByPeriod(classes) {
    const order = [];
    const map = {};
    classes.forEach(c => {
      const p = (c.period && c.period.trim()) ? c.period.trim() : '未排期';
      if (!map[p]) { map[p] = []; order.push(p); }
      map[p].push(c);
    });
    return order.map(p => ({ period: p, classes: map[p] }));
  },
};
