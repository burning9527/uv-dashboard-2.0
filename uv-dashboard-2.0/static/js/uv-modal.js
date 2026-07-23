/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 班级详情弹窗 + 学员报班明细弹窗
   点击班级卡片 → 班级详情（学员列表、搭班老师、上课信息）
   点击学员姓名 → 学员报班明细（各科详情、续报分类、搭班老师）
   ═══════════════════════════════════════════════════════════════ */

// 续报状态分类：按课程类型(K列 course_type) 区分
//   续报状态分类：按课程类型(K列 course_type) 区分
//   特惠课：课前续 / 当期转化 / 已续报 / 未续报
//   系统课（含未知）：仅 已续报 / 未续报，忽略 pre/new 细分
// 返回 'pre' | 'new' | 'renewed' | 'not-renewed' | 'none'
function _uvRenewalKind(isR, rCls, isActive, courseType) {
  const isSpecial = courseType === '特惠课';
  if (isR) {
    if (isSpecial && rCls === 'pre') return 'pre';
    if (isSpecial && rCls === 'new') return 'new';
    return 'renewed';
  }
  if (isActive) return 'not-renewed';
  return 'none';
}

const UVModal = {
  // ── 班级详情弹窗 ──
  async openClassDetail(classId) {
    const data = await UVApi.getClassDetail(classId);
    if (!data || data.error) {
      alert('获取班级详情失败');
      return;
    }
    const modal = document.getElementById('class-modal');
    const content = document.getElementById('class-modal-content');
    content.innerHTML = this._renderClassDetail(data);
    modal.classList.add('open');
  },

  closeClassModal() {
    document.getElementById('class-modal').classList.remove('open');
  },

  copyClassId(classId) {
    navigator.clipboard.writeText(classId).then(() => {
      // 临时提示
      const badge = document.querySelector('.cd-class-id-badge');
      if (badge) {
        const orig = badge.innerHTML;
        badge.innerHTML = '<span style="color:#16A34A;font-weight:600">已复制!</span>';
        setTimeout(() => { badge.innerHTML = orig; }, 1200);
      }
    }).catch(() => {});
  },

  _renderClassDetail(data) {
    const C = UVConfig.COLORS;
    const sc = UVConfig.SUBJECT_PILL_CLASS;
    const subjPillCls = sc[data.subject] || '';
    const subjShort = UVConfig.SUBJECT_SHORT[data.subject] || data.subject;
    const subjColor = UVConfig.SUBJECT_COLOR[data.subject] || C.textTertiary;
    // 班级详情弹窗：取当前单学季用于"无"期次转 秋/春/暑/寒
    const modalSeason = UVFilters.currentSeason();
    const classPeriodLabel = UVConfig.displayPeriod(data.period || '', modalSeason);

    // ── 头部信息 ──
    const dateRange = (data.start_date && data.end_date)
      ? `${data.start_date} ~ ${data.end_date}`
      : (data.start_date || data.end_date || '-');

    // ── 统计指标：按课程类型区分 ──
    // 系统课：在读 / 已续报 / 续报率 / 退费 / 退费率
    // 特惠课：在读 / 应续 / 当期转化 / 已续费 / 转化率 / 续报率
    const isSpecialCourse = data.course_type === '特惠课';
    const rate = Math.min(data.renewal_rate || 0, 100);
    const rateColor = rate >= 50 ? C.success : (rate >= 25 ? C.warning : C.danger);
    let statsHtml = '';
    if (isSpecialCourse) {
      const shouldRenew = data.active_count - data.pre_count;
      const convRate = Math.min(shouldRenew > 0 ? Math.round((data.new_count || 0) / shouldRenew * 100) : 0, 100);
      const convColor = convRate >= 50 ? C.success : (convRate >= 25 ? C.warning : C.danger);
      statsHtml = `
        <div class="cd-stat"><span class="cd-stat-label">在读</span><strong>${data.active_count}</strong></div>
        <div class="cd-stat"><span class="cd-stat-label">应续</span><strong>${shouldRenew}</strong></div>
        <div class="cd-stat accent"><span class="cd-stat-label">当期转化</span><strong style="color:${C.success}">${data.new_count || 0}</strong></div>
        <div class="cd-stat"><span class="cd-stat-label">已续费</span><strong>${data.renewed_count}</strong></div>
        <div class="cd-stat accent"><span class="cd-stat-label">转化率</span><strong style="color:${convColor}">${convRate}%</strong></div>
        <div class="cd-stat accent"><span class="cd-stat-label">续报率</span><strong style="color:${rateColor}">${rate}%</strong></div>`;
    } else {
      // 系统课
      const refundCount = data.refund_count || 0;
      const refundRate = Math.min(data.refund_rate || 0, 100);
      const refundColor = refundRate >= 15 ? C.danger : (refundRate >= 5 ? C.warning : C.success);
      statsHtml = `
        <div class="cd-stat"><span class="cd-stat-label">在读</span><strong>${data.active_count}</strong></div>
        <div class="cd-stat"><span class="cd-stat-label">已续报</span><strong>${data.renewed_count}</strong></div>
        <div class="cd-stat accent"><span class="cd-stat-label">续报率</span><strong style="color:${rateColor}">${rate}%</strong></div>
        <div class="cd-stat"><span class="cd-stat-label">退费</span><strong>${refundCount}</strong></div>
        <div class="cd-stat accent"><span class="cd-stat-label">退费率</span><strong style="color:${refundColor}">${refundRate}%</strong></div>`;
    }

    // ── 学员列表 ──
    let studentListHtml = '';
    const students = data.students || [];
    students.sort((a, b) => {
      // 在读优先，然后续报优先
      const aActive = (a.status || '').includes('在读');
      const bActive = (b.status || '').includes('在读');
      if (aActive !== bActive) return bActive ? 1 : -1;
      const aR = UVConfig.isContinueFall(a.continue_fall);
      const bR = UVConfig.isContinueFall(b.continue_fall);
      if (aR !== bR) return bR ? 1 : -1;
      return 0;
    });

    students.forEach(st => {
      const isActive = (st.status || '').includes('在读');
      const isR = UVConfig.isContinueFall(st.continue_fall);
      const kind = _uvRenewalKind(isR, st.renewal_class || '', isActive, data.course_type);
      let tagHtml = '';
      if (kind === 'pre') tagHtml = '<span class="detail-tag tag-pre">课前续</span>';
      else if (kind === 'new') tagHtml = '<span class="detail-tag tag-new">当期转化</span>';
      else if (kind === 'renewed') tagHtml = '<span class="detail-tag tag-renewed">已续报</span>';
      else if (kind === 'not-renewed') tagHtml = '<span class="detail-tag tag-not-renewed">未续报</span>';
      const statusTag = isActive ? '<span class="detail-tag tag-active">在读</span>' :
        (st.status && st.status.includes('退') ? '<span class="detail-tag tag-refund">退费</span>' :
          (st.status ? `<span class="detail-tag tag-none">${st.status}</span>` : ''));

      // 搭班老师（弱灰展示，不抢重心）：仅显示当前班级同学季、在读的其他科目老师
      let coTeacherHtml = '';
      const coEntriesSt = Object.entries(st.co_teachers || {});
      if (coEntriesSt.length > 0) {
        coTeacherHtml = '<div class="cd-row-co-teachers">';
        coEntriesSt.forEach(([subjKey, teacher]) => {
          const sCls = sc[subjKey] || '';
          const sShort = UVConfig.SUBJECT_SHORT[subjKey] || subjKey;
          coTeacherHtml += `<span class="cd-co-item"><span class="cd-co-pill ${sCls}">${sShort}</span><span class="cd-co-name">${teacher}</span></span>`;
        });
        coTeacherHtml += '</div>';
      }

      const rowCls = isActive ? 'cd-student-row' : 'cd-student-row inactive';

      studentListHtml += `
        <div class="${rowCls}" onclick="UVModal.openStudentDetail('${st.uid}', '${data.season || ''}')">
          <div class="cd-col cd-col-name"><span class="cd-student-name">${st.name}</span></div>
          <div class="cd-col cd-col-status">${statusTag}</div>
          <div class="cd-col cd-col-renew">${tagHtml}</div>
          <div class="cd-col cd-col-coteachers">${coTeacherHtml}</div>
        </div>`;
    });

    return `
      <div class="class-detail">
        <div class="cd-header">
          <div class="cd-header-top">
            <span class="subj-pill ${subjPillCls}" style="font-size:14px">${subjShort}</span>
            <strong class="cd-teacher">${data.teacher}</strong>
            <span class="cd-class-id-badge" onclick="UVModal.copyClassId('${data.class_id}')" title="点击复制班级ID">
              <svg width="11" height="11" viewBox="0 0 16 16" fill="none" style="vertical-align:-1px;margin-right:3px"><rect x="4" y="4" width="9" height="9" rx="2" stroke="currentColor" stroke-width="1.5"/><rect x="3" y="3" width="9" height="9" rx="2" stroke="currentColor" stroke-width="1.5" fill="white"/></svg>${data.class_id}
            </span>
          </div>
          <div class="cd-header-info">
            <span class="cd-grade-badge">${data.grade || '-'}</span>
            <span class="cd-sep">·</span>
            <span>${classPeriodLabel}</span>
            <span class="cd-sep">·</span>
            ${UVConfig.classTypePill(data.class_type) || '<span>-</span>'}
            <span class="cd-sep">·</span>
            <span class="cd-course-type">${data.course_type || '-'}</span>
            <span class="cd-sep">·</span>
            <span>${data.room || '-'}</span>
            <span class="cd-sep">·</span>
            <span>${data.teaching_point || '-'}</span>
          </div>
          <div class="cd-header-dates">
            <span class="cd-date-range">${dateRange}</span>
            <span class="cd-sep">·</span>
            <span>${data.week_cycle || '-'}</span>
            <span class="cd-sep">·</span>
            <span>${data.time_slot || '-'}</span>
          </div>
        </div>
        <div class="cd-stats-bar">
          ${statsHtml}
        </div>
        <div class="cd-student-list">
          <div class="cd-student-list-header">学员名单（${students.length}人）</div>
          <div class="cd-student-list-thead">
            <div class="cd-col cd-col-name">姓名</div>
            <div class="cd-col cd-col-status">在读</div>
            <div class="cd-col cd-col-renew">续报</div>
            <div class="cd-col cd-col-coteachers">搭班老师</div>
          </div>
          ${studentListHtml}
        </div>
      </div>`;
  },

  // ── 学员报班明细弹窗 ──
  async openStudentDetail(uid, season) {
    // 关闭班级弹窗（如果打开）
    this.closeClassModal();

    // 学季作用域：显式传入优先；否则取当前单学季筛选（学员/排班/全局看板）
    if (!season) {
      season = UVFilters.currentSeason() || '';
    }

    const data = await UVApi.getStudentDetail(uid, season);
    if (!data || data.error) {
      alert('获取学员详情失败');
      return;
    }
    const modal = document.getElementById('student-modal');
    const content = document.getElementById('student-modal-content');
    content.innerHTML = this._renderStudentDetail(data);
    modal.classList.add('open');
  },

  closeModal() {
    document.getElementById('student-modal').classList.remove('open');
  },

  copyUid(text) {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => this._showCopyTip()).catch(() => this._fallbackCopy(text));
    } else {
      this._fallbackCopy(text);
    }
  },

  _fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      this._showCopyTip();
    } catch (err) {
      console.error('Copy failed', err);
    }
    document.body.removeChild(ta);
  },

  _showCopyTip() {
    const btn = document.querySelector('.sd-copy-btn');
    if (!btn) return;
    const old = btn.innerHTML;
    btn.classList.add('copied');
    btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M5.5 13.5l-4.5-4.5 1.4-1.4 3.1 3.1 7.6-7.6 1.4 1.4-9 9z"/></svg>';
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.innerHTML = old;
    }, 1200);
  },

  _renderStudentDetail(data) {
    const C = UVConfig.COLORS;
    const sc = UVConfig.SUBJECT_PILL_CLASS;
    const subjColor = UVConfig.SUBJECT_COLOR;
    const subjects = data.subjects || {};
    const manual = data.manual || {};
    const coTeachers = data.co_teachers || {};

    // ── 校内年级（来自 enrich_json）/ 公立校（学员级列）──
    let schoolGrade = '';
    try {
      const en = JSON.parse(data.enrich_json || '{}');
      schoolGrade = en.school_grade || '';
    } catch (e) {}
    const schoolName = data.school_name || '';

    // ── 顾问 + 三科老师 同一行 ──
    let staffRowHtml = '';
    const coEntries = Object.entries(coTeachers);
    const advisorPair = data.advisor ? `<div class="sd-staff-pair"><span class="sd-staff-label">顾问</span><span class="sd-staff-name">${data.advisor}</span></div>` : '';
    const teacherPairs = coEntries.map(([label, name]) => `<div class="sd-staff-pair"><span class="sd-staff-label">${label}</span><span class="sd-staff-name">${name}</span></div>`).join('');
    if (advisorPair || teacherPairs) {
      staffRowHtml = `<div class="sd-staff-row">${advisorPair}${teacherPairs}</div>`;
    }

    // ── 全局状态汇总 ──
    let activeCount = 0, renewedCount = 0, refundCount = 0, notRenewedCount = 0;
    UVConfig.SUBJECTS.forEach(subj => {
      const sd = subjects[subj];
      if (!sd || typeof sd !== 'object') return;
      const isActive = (sd.status || '').includes('在读');
      // BUG 修复：status 可能是"出班"（数据层真实值）
      const isRefund = (sd.status && (sd.status.includes('退') || sd.status.includes('出班'))) || sd.valid_refund === '是';
      const isR = UVConfig.isContinueFall(sd.continue_fall);
      if (isActive) activeCount++;
      if (isRefund) refundCount++;
      if (isR) renewedCount++;
      else if (isActive && !isRefund) notRenewedCount++;
    });

    const summaryHtml = `
      <div class="sd-summary">
        <div class="sd-sum-item sum-active">
          <span class="sd-sum-num">${activeCount}</span><span class="sd-sum-label">在读</span>
        </div>
        <div class="sd-sum-item sum-renewed">
          <span class="sd-sum-num">${renewedCount}</span><span class="sd-sum-label">已续报</span>
        </div>
        <div class="sd-sum-item sum-not-renewed">
          <span class="sd-sum-num">${notRenewedCount}</span><span class="sd-sum-label">未续报</span>
        </div>
        <div class="sd-sum-item sum-refund">
          <span class="sd-sum-num">${refundCount}</span><span class="sd-sum-label">退费</span>
        </div>
      </div>`;

    // ── 四科统一 Bento 网格：固定 2×2 布局，保证报名 1/2/3/4 科均和谐 ──
    const subjectsRaw = data.subjects_raw || {};
    const subjectCardsHtml = UVConfig.SUBJECTS.map(subj => {
      const sd = subjects[subj];
      const rawLines = subjectsRaw[subj] || [];
      const cls = sc[subj] || '';
      const short = UVConfig.SUBJECT_SHORT[subj] || subj;
      const color = subjColor[subj] || C.textTertiary;

      const isActive = sd && (sd.status || '').includes('在读');
      // BUG 修复：status 可能是"出班"（数据层真实值），不是"退费"
      // 任何 status 包含"退"或"出班"，或 valid_refund='是'，都视为退费
      const isRefund = sd && (sd.status && (sd.status.includes('退') || sd.status.includes('出班')) || sd.valid_refund === '是');
      const isR = sd && UVConfig.isContinueFall(sd.continue_fall);
      const rCls = sd ? sd.renewal_class || '' : '';
      const courseType = sd ? sd.course_type || '' : '';

      // 合并「状态标签 + 续报横幅」为单一状态徽标
      let statusText = '未报';
      let statusClass = 'sd-status-empty';
      if (isRefund) {
        // BUG 修复：精确化显示 refund_kind（"课前退" / "课后退"），无 refund_kind 时降级显示"退费"
        statusText = (sd && sd.refund_kind) ? sd.refund_kind : '退费';
        statusClass = 'sd-status-refund';
      } else if (isR) {
        const kind = _uvRenewalKind(isR, rCls, isActive, courseType);
        if (kind === 'pre') { statusText = '课前续'; statusClass = 'sd-status-pre'; }
        else if (kind === 'new') { statusText = '当期转化'; statusClass = 'sd-status-new'; }
        else { statusText = '已续报'; statusClass = 'sd-status-renewed'; }
      } else if (isActive) {
        statusText = '未续报';
        statusClass = 'sd-status-not-renewed';
      }

      // 未报科目：柔和占位
      if (!sd || typeof sd !== 'object' || rawLines.length === 0) {
        return `
          <div class="subject-card ${cls} empty-card">
            <div class="sc-top-bar" style="background:#E2E8F0"></div>
            <div class="sc-content">
              <div class="sc-hd">
                <div class="sc-title-left">
                  <span class="sc-subj-pill" style="background:#CBD5E1;color:#fff">${short}</span>
                  <span class="sc-subj-name" style="color:#94A3B8">${subj}</span>
                </div>
                <span class="sc-status-badge sd-status-empty">未报</span>
              </div>
              <div class="sc-empty-state">— 未报该科目 —</div>
            </div>
          </div>`;
      }

      // 班级行列表
      const classListHtml = rawLines.map((line, idx) => {
        const lineActive = (line.status || '').includes('在读');
        // BUG 修复：status 可能是"出班"，包含"退"或"出班"都视为退费
        const lineRefund = line.status && (line.status.includes('退') || line.status.includes('出班')) || line.valid_refund === '是';
        const lineR = UVConfig.isContinueFall(line.continue_fall);
        const lineRCls = line.renewal_class || '';
        let renewText = '';
        let renewClass = 'sc-renew-none';
        if (lineRefund) {
          renewText = '退费';
          renewClass = 'sc-renew-refund';
        } else if (lineR) {
          const kind = _uvRenewalKind(lineR, lineRCls, lineActive, line.course_type);
          if (kind === 'pre') { renewText = '课前续'; renewClass = 'sc-renew-pre'; }
          else if (kind === 'new') { renewText = '当期转化'; renewClass = 'sc-renew-new'; }
          else { renewText = '已续报'; renewClass = 'sc-renew-yes'; }
        } else if (lineActive) {
          renewText = '未续报';
          renewClass = 'sc-renew-no';
        } else {
          renewText = '未报';
          renewClass = 'sc-renew-none';
        }

        const seasonPeriodBadge = UVConfig.seasonPeriodBadge(line.period || '', line.season || '');
        const typePill = UVConfig.classTypePill(line.class_type)
          || `<span class="sc-class-type">${line.class_type || '-'}</span>`;

        return `
          <div class="sc-class-row">
            <div class="sc-class-row-main">
              <div class="sc-class-line sc-class-line1">
                <span class="sc-class-no">${idx + 1}</span>
                <span class="sc-class-id">${line.class_id || '-'}</span>
                <span class="sc-class-teacher">${line.teacher || '-'}</span>
              </div>
              <div class="sc-class-line sc-class-line2">
                ${seasonPeriodBadge}
                ${typePill}
                <span class="sc-class-renew ${renewClass}">${renewText}</span>
              </div>
            </div>
            <div class="sc-class-row-meta">
              <span class="sc-class-time">${line.time_slot || '-'}</span>
              <span class="sc-class-room">${line.room || '-'}</span>
            </div>
          </div>`;
      }).join('');

      return `
        <div class="subject-card ${cls}">
          <div class="sc-top-bar" style="background:linear-gradient(90deg,${color},${color}88)"></div>
          <div class="sc-content">
            <div class="sc-hd">
              <div class="sc-title-left">
                <span class="sc-subj-pill" style="background:${color};color:#fff">${short}</span>
                <span class="sc-subj-name">${subj}</span>
              </div>
              <span class="sc-status-badge ${statusClass}">${statusText}</span>
            </div>
            <div class="sc-class-list">${classListHtml}</div>
          </div>
        </div>`;
    }).join('');

    // ── 组装 ──
    return `
      <div class="student-detail">
        <div class="sd-header">
          <div class="sd-header-row">
            <strong class="sd-name">${data.name}</strong>
            <span class="sd-uid-wrap">
              <span class="sd-uid">${data.uid}</span>
              <button class="sd-copy-btn" onclick="UVModal.copyUid('${data.uid}')" title="复制学员ID" aria-label="复制学员ID">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M4 4V2a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2v2a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2zm2-2v6h6V2H6zM2 6v8h6V6H2z"/></svg>
              </button>
            </span>
            <span class="sd-pt">${data.teaching_point || '-'}</span>
          </div>
          ${(schoolGrade || schoolName) ? `<div class="sd-school-row">
            ${schoolGrade ? `<span class="sd-school-item"><span class="sd-school-k">校内年级</span>${schoolGrade}</span>` : ''}
            ${schoolName ? `<span class="sd-school-item"><span class="sd-school-k">公立校</span>${schoolName}</span>` : ''}
          </div>` : ''}
          ${staffRowHtml}
          ${(data.scope_season) ? `<div class="sd-scope-row"><span class="sd-scope-pill">学季作用域：${data.scope_season}</span><span class="sd-scope-hint">仅显示该学季在读班级</span></div>` : ''}
        </div>
        ${summaryHtml}
        <div class="sd-subjects-grid">${subjectCardsHtml}</div>
      </div>`;
  },
};
