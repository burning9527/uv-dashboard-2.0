/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 学员检索组件
   多维度筛选 + 表格展示 + 详情弹窗
   弹窗升级：学科卡片带左彩条(::before) + subj-grid 4列布局
   ═══════════════════════════════════════════════════════════════ */

const UVStudent = {
  students: [],

  async loadFilters() {
    // 不重新 init UVFilters——init 在 app 启动时已调用，重新 init 会重置全局 state
    // 只需渲染下拉 + 绑定事件 + 搜索
    UVFilters.renderAllDropdowns();
    this.bindEvents();
    await this.search();
  },

  bindEvents() {
    const searchBtn = document.getElementById('student-search-btn');
    if (searchBtn) {
      searchBtn.removeEventListener('click', this._searchHandler);
      this._searchHandler = () => this.search();
      searchBtn.addEventListener('click', this._searchHandler);
    }
    const keywordInput = document.getElementById('student-keyword');
    if (keywordInput) {
      keywordInput.removeEventListener('keydown', this._keywordKeydownHandler);
      this._keywordKeydownHandler = (e) => {
        if (e.key === 'Enter') this.search();
      };
      keywordInput.addEventListener('keydown', this._keywordKeydownHandler);
    }
  },

  async search() {
    const keywordInput = document.getElementById('student-keyword');
    UVFilters.state.keyword = keywordInput?.value?.trim() || '';
    const filters = UVFilters.buildParams({ includeKeyword: true });
    // 续报状态：前端显示 未续报/课前续/当期转化（兼容旧值 已续费/未续费），
    // 后端 get_filtered_students 原生支持 未续报/课前续/当期转化/已续报
    if (filters.renewal_status) {
      filters.renewal_status = filters.renewal_status
        .split(',')
        .map(s => {
          if (s === '已续费') return '已续报';
          if (s === '未续费') return '未续报';
          return s;  // 未续报 / 课前续 / 当期转化 原样透传
        })
        .join(',');
    }
    const data = await UVApi.searchStudents(filters);
    if (data) {
      this.students = data;
      this.renderTable();
    }
  },

  renderTable() {
    const container = document.getElementById('student-table-content');
    if (!container) return;

    if (!this.students.length) {
      container.innerHTML = '<div class="no-data">未找到匹配的学员</div>';
      return;
    }

    let html = '<div class="stu-list">';
    this.students.forEach(s => {
      const subjects = s.subjects || {};
      const initial = UVConfig.studentInitial(s.name);
      const statusCards = UVConfig.subjectStatusCards(subjects);

      // ── 学员级退费状态判断 ──
      // 整体灰色 = 全部 4 科都退费（学员完全出班）
      // 部分退费（仍有在读）→ 仅退费科标红，主体不变灰
      let allRefund = true;   // 全部退费？默认 true（没找到在读则视为全退）
      let anyActive = false;  // 是否有任一科在读
      let anyRefund = false;  // 是否有任一科退费
      const subjectKeys = Object.keys(subjects);
      for (const k of subjectKeys) {
        const sd = subjects[k];
        if (!sd || typeof sd !== 'object') continue;
        const st = (sd.status || '');
        const isRefund = st.indexOf('退') >= 0 || st.indexOf('出班') >= 0 || sd.valid_refund === '是';
        const isActive = st.indexOf('在读') >= 0;
        if (isActive) { anyActive = true; allRefund = false; }
        if (isRefund) { anyRefund = true; }
      }
      // 全部 4 科都退费 且 无在读 → 整体灰色（"完全出班"）
      // 否则（部分退费或纯未读）→ 不整体标灰
      const hasRefund = subjectKeys.length > 0 && allRefund && !anyActive;
      const cardCls = hasRefund ? 'stu-card has-refund' : 'stu-card';

      html += `<div class="${cardCls}" data-uid="${UVConfig._esc(s.uid)}">
        <div class="stu-avatar">${UVConfig._esc(initial)}</div>
        <div class="stu-main">
          <div class="stu-line1">
            <span class="stu-name">${UVConfig._esc(s.name)}</span>
            <span class="stu-uid">${UVConfig._esc(s.uid)}</span>
          </div>
          <div class="stu-line3">
            <span class="sm-item"><b>教学点</b>${UVConfig._esc(s.teaching_point || '-')}</span>
            <span class="sm-item"><b>顾问</b>${UVConfig._esc(s.advisor || '-')}</span>
          </div>
        </div>
        <div class="stu-right">${statusCards}</div>
      </div>`;
    });
    html += '</div>';
    container.innerHTML = html;

    // 点击学员卡片 → 打开统一的学员详情弹窗
    container.onclick = (e) => {
      const row = e.target.closest('.stu-card');
      if (row) UVModal.openStudentDetail(row.dataset.uid);
    };
  },
};
