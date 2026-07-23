/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 顾问看板组件
   左侧：顾问排名（UV/PV双维度 + 续报/转化切换，复用数据看板排行口径）
   右侧：详情 = 双维度汇总 + 名下学员（按学科聚合，续秋徽章，点击看详情）
   ═══════════════════════════════════════════════════════════════ */

const UVAdvisor = {
  advisors: [],
  rankMode: 'renewal',
  uvMode: 'uv',
  selectedAdvisor: null,

  _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  },

  // 全局筛选参数
  _params() {
    return UVFilters.buildParams();
  },

  async load() {
    const data = await UVApi.getAdvisorList(this._params());
    if (data) {
      this.advisors = data;
      this._buildAdvisorPtMap(data);
      this.render();
    }
  },

  _buildAdvisorPtMap(advisors) {
    const map = {};
    advisors.forEach(a => {
      if (a.teaching_point) map[a.name] = a.teaching_point;
    });
    if (Object.keys(map).length > 0) {
      UVFilters.advisorPtMap = map;
    }
  },

  switchRankMode(mode) {
    this.rankMode = mode;
    this.render();
    document.querySelectorAll('#advisor-rank-btns .rank-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
  },

  switchUVMode(mode) {
    this.uvMode = mode;
    this.render();
    document.querySelectorAll('#advisor-uv-btns .uv-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
  },

  render() {
    const container = document.getElementById('advisor-list-content');
    if (!container) return;

    const mode = this.rankMode;
    const dim = this.uvMode;
    const isUV = dim === 'uv';
    const ptMap = UVFilters.advisorPtMap;

    if (!this.advisors.length) { container.innerHTML = '<div class="no-data">暂无数据</div>'; return; }

    const getRate = (a) => {
      const active = isUV ? a.active : (a.pv_active || a.active);
      const should_renew = isUV ? a.should_renew : (a.pv_should_renew || (active - (a.pv_pre_renewed || a.pre_renewed)));
      const new_renewed = isUV ? a.new_renewed : (a.pv_new_renewed || a.new_renewed);
      const total_renewed = isUV ? a.total_renewed : (a.pv_total_renewed || a.total_renewed);
      return mode === 'renewal'
        ? (active > 0 ? total_renewed / active * 100 : 0)
        : (should_renew > 0 ? new_renewed / should_renew * 100 : 0);
    };

    const visible = this.advisors.filter(a => {
      const active = isUV ? a.active : (a.pv_active || a.active);
      return (active || 0) > 0;
    });
    if (!visible.length) { container.innerHTML = '<div class="no-data">暂无数据</div>'; return; }

    const sorted = [...visible].sort((a, b) => getRate(b) - getRate(a));
    const rates = sorted.map(a => getRate(a));
    const maxRate = Math.max(...rates, 1);

    let html = '<div class="advisor-ranking-list">';
    sorted.forEach((a, idx) => {
      const medal = UVConfig.medalClass(idx);
      const tagPill = UVConfig.advisorTagPill(a.name, false, ptMap);

      const active = isUV ? a.active : (a.pv_active || a.active);
      const should_renew = isUV ? a.should_renew : (a.pv_should_renew || (active - (a.pv_pre_renewed || a.pre_renewed)));
      const new_renewed = isUV ? a.new_renewed : (a.pv_new_renewed || a.new_renewed);
      const total_renewed = isUV ? a.total_renewed : (a.pv_total_renewed || a.total_renewed);

      const rate = mode === 'renewal'
        ? (active > 0 ? (total_renewed / active * 100).toFixed(1) : 0)
        : (should_renew > 0 ? (new_renewed / should_renew * 100).toFixed(1) : 0);
      const rateClass = UVConfig.rateColor(rate);
      const barWidth = Math.min(parseFloat(rate) / maxRate * 100, 100);

      const dimLabel = isUV ? 'UV' : 'PV';
      const statRow = `<div class="rank-stat-row">
        <div class="rank-stat-cell"><div class="rs-label">${dimLabel}</div><div class="rs-val">${active}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">应续</div><div class="rs-val">${should_renew}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">转化</div><div class="rs-val accent">${new_renewed}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">已转化</div><div class="rs-val">${total_renewed}</div></div>
      </div>`;

      const isActive = this.selectedAdvisor === a.name;
      html += `<div class="rank-item ${medal}${isActive ? ' active' : ''}" data-name="${this._esc(a.name)}" onclick="UVAdvisor.viewDetail(this.dataset.name)">
        <div class="rank-num">${idx + 1}</div>
        <div class="rank-info">
          <div class="rank-name">${tagPill} ${this._esc(a.name)}</div>
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
    this.selectedAdvisor = name;
    this.render(); // 高亮左侧选中的卡片

    const data = await UVApi.getAdvisorDetail(name, this._params());
    if (!data) return;
    const container = document.getElementById('advisor-detail-content');
    if (!container) return;

    const summary = data.summary || {};
    const students = (data.students || []).sort((a, b) => {
      const aRen = a.is_renewed ? 1 : 0;
      const bRen = b.is_renewed ? 1 : 0;
      return bRen - aRen;
    });
    const isUV = this.uvMode === 'uv';

    // 主维度汇总
    const sActive = isUV ? summary.uv_active : summary.pv_active;
    const sShould = isUV ? summary.uv_should : summary.pv_should;
    const sNew = isUV ? summary.uv_new : summary.pv_new;
    const sRenewed = isUV ? summary.uv_renewed : summary.pv_renewed;
    const sRate = isUV ? summary.uv_renewal_rate : summary.pv_renewal_rate;
    const sConv = isUV ? summary.uv_conv_rate : summary.pv_conv_rate;
    const dimLabel = isUV ? 'UV' : 'PV';

    // 副维度（对照）
    const oRate = isUV ? summary.pv_renewal_rate : summary.uv_renewal_rate;
    const oConv = isUV ? summary.pv_conv_rate : summary.uv_conv_rate;
    const oLabel = isUV ? 'PV' : 'UV';

    const tagPill = UVConfig.advisorTagPill(name, false, UVFilters.advisorPtMap);

    let html = `<div class="board-detail-head">
      <div class="bdh-title">${tagPill} ${this._esc(name)} <span class="bdh-sub">顾问详情 · ${dimLabel}</span></div>
    </div>`;

    // 主维度汇总条
    html += `<div class="board-summary">
      <div class="bs-item"><span class="bs-val">${sActive || 0}</span><span class="bs-label">在读${dimLabel}</span></div>
      <div class="bs-item"><span class="bs-val">${sShould || 0}</span><span class="bs-label">应续</span></div>
      <div class="bs-item"><span class="bs-val accent">${sNew || 0}</span><span class="bs-label">当期转化</span></div>
      <div class="bs-item"><span class="bs-val">${sRenewed || 0}</span><span class="bs-label">已转化</span></div>
      <div class="bs-item"><span class="bs-val rate-${UVConfig.rateColor(sRate || 0)}">${sRate || 0}%</span><span class="bs-label">续报率</span></div>
      <div class="bs-item"><span class="bs-val rate-${UVConfig.rateColor(sConv || 0)}">${sConv || 0}%</span><span class="bs-label">转化率</span></div>
    </div>`;
    // 副维度对照条
    html += `<div class="board-summary-secondary">${oLabel} 维度参考：续报率 <b>${oRate || 0}%</b> · 转化率 <b>${oConv || 0}%</b> · 学员数 <b>${summary.student_count || 0}</b></div>`;

    // 学员情况（统一学员卡片）
    html += `<div class="board-section">
      <div class="board-section-title">名下学员 <span class="bs-count">${students.length} 人</span></div>`;
    if (students.length) {
      html += '<div class="stu-list">';
      students.forEach(s => {
        const initial = UVConfig.studentInitial(s.name);
        const subjList = s.subjects || [];
        const statusCards = UVConfig.subjectStatusCards(subjList);
        html += `<div class="stu-card" data-uid="${this._esc(s.uid)}">
          <div class="stu-avatar">${this._esc(initial)}</div>
          <div class="stu-main">
            <div class="stu-line1">
              <span class="stu-name">${this._esc(s.name)}</span>
              <span class="stu-uid">${this._esc(s.uid)}</span>
            </div>
            <div class="stu-line3">
              <span class="sm-item"><b>教学点</b>${this._esc(s.teaching_point)}</span>
              <span class="sm-item"><b>在读学科</b>${subjList.length} 科</span>
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

    container.onclick = (e) => {
      const row = e.target.closest('.stu-card');
      if (row) UVModal.openStudentDetail(row.dataset.uid);
    };
  },
};
