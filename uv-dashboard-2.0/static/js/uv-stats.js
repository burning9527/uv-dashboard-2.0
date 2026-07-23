/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 统计卡片组件
   顶部10指标 + 学科卡片
   消费后端 by_period 的 PV/UV 分期维度数据
   ═══════════════════════════════════════════════════════════════ */

const UVStats = {
  render(stats) {
    if (!stats) return;
    this.renderTopCards(stats);
    this.renderSubjectCards(stats);
  },

  renderTopCards(stats) {
    const container = document.getElementById('stats-top');
    if (!container) return;
    const cp = UVConfig.currentPeriod();

    const cards = [
      { label: '学员总数UV', value: stats.total_uv, accent: 'blue', hint: 'by_period', hintKey: 'total_uv' },
      { label: '在读UV', value: stats.active_uv, accent: 'green', hint: 'by_period', hintKey: 'active_uv' },
      { label: '退费UV', value: stats.refund_uv, accent: 'red', hint: 'by_period', hintKey: 'refund_uv' },
      { label: '在读PV', value: stats.active_pv, accent: 'blue', hint: 'by_period', hintKey: 'active_pv' },
      { label: '退费PV', value: stats.refund_pv, accent: 'red', hint: 'by_period', hintKey: 'refund_pv' },
      { label: '续报PV', value: stats.renewed_pv, accent: 'green', hint: 'by_period', hintKey: 'renewed_pv' },
      { label: '课前续PV', value: stats.pre_renewed_pv, accent: 'purple', hint: 'by_period', hintKey: 'pre_renewed_pv' },
      { label: '当期转化PV', value: stats.new_renewed_pv, accent: 'orange', hint: 'by_period', hintKey: 'new_renewed_pv' },
      { label: 'PV续报率', value: stats.total_renewal_rate + '%', accent: 'green', hint: 'by_period_rate', hintKey: 'pv_renewal_rate' },
      { label: 'PV退费率', value: stats.total_refund_rate + '%', accent: 'red', hint: 'by_period_rate', hintKey: 'pv_refund_rate' },
    ];

    container.innerHTML = cards.map(c => {
      const periodHints = c.hint ? this._periodHintHTML(stats, c.hintKey, c.hint, cp) : '';
      return `
        <div class="stat-card side-hints accent-${c.accent}">
          <div class="stat-main">
            <div class="label">${c.label}</div>
            <div class="value">${c.value}</div>
          </div>
          ${periodHints}
        </div>`;
    }).join('');
  },

  renderSubjectCards(stats) {
    const container = document.getElementById('stats-subject');
    if (!container) return;
    const cp = UVConfig.currentPeriod();
    const subjects = stats.by_subject || [];

    container.innerHTML = subjects.map(s => {
      const rateClass = UVConfig.rateColor(s.renewal_rate);
      const pillCls = UVConfig.SUBJECT_PILL_CLASS[s.key] || '';
      const periodHints = this._periodHintHTML(stats, s.key, 'renewal_rate_by_period', cp);
      return `
        <div class="stat-card side-hints accent-blue">
          <div class="stat-main">
            <div class="label"><span class="subj-pill ${pillCls}">${UVConfig.SUBJECT_SHORT[s.key]}</span> ${s.name}续报率</div>
            <div class="value">${s.renewal_rate}%</div>
            <div class="stat-sub-info">在读${s.active} 退费${s.refund}</div>
          </div>
          ${periodHints}
        </div>`;
    }).join('');
  },

  _periodHintHTML(stats, key, hintType, currentPeriod) {
    if (!key) return '';
    const pc = stats.period_config || {};
    const chipDisplay = pc.chip_display || 'short_chips';
    const termType = pc.term_type || 'short_term';

    // ── 决定渲染哪条维度 ──
    const periodKeys = Object.keys(stats.by_period || {});
    const weekdayKeys = Object.keys(stats.by_weekday || {});

    // ── 春秋不显示 chip（用户要求）—— 但保留 hint 容器固定高度以防卡片大小变化 ──
    if (chipDisplay === 'none') {
      return '<div class="hint hint-empty">长学期（春/秋）</div>';
    }

    // short_only (mixed): 只显示短学期 chip
    // short_chips: 只显示短学期 chip
    if (chipDisplay === 'short_chips' || chipDisplay === 'short_only') {
      return this._shortChipHTML(stats, key, hintType, currentPeriod, periodKeys);
    }

    // 兼容旧 term_type=long_term 行为（理论上不会触发，但兜底）
    if (termType === 'long_term') {
      return this._weekdayChipHTML(stats, key, hintType, currentPeriod, weekdayKeys);
    }

    return '';
  },

  /**
   * 短学期 chip：按 data 中实际存在的期次（按分校/按筛选动态）
   */
  _shortChipHTML(stats, key, hintType, currentPeriod, periodKeys) {
    // 短学期但该分校没数据时：保持 hint 容器高度，但显示"无数据"占位
    if (!periodKeys.length) {
      return '<div class="hint hint-empty">暂无期次数据</div>';
    }
    const rows = periodKeys.map((p, i) => {
      let val = '-';
      if (hintType === 'by_period_rate') {
        val = stats.by_period?.[p]?.[key] != null
          ? stats.by_period[p][key] + '%'
          : '-';
      } else if (hintType === 'renewal_rate_by_period') {
        const rates = stats.renewal_rate_by_period?.[key] || stats.subject_period_renewal?.[key] || {};
        val = (rates[p] || 0) + '%';
      } else if (hintType === 'by_period') {
        if (stats.by_period?.[p]) {
          val = stats.by_period[p][key] ?? '-';
        }
      }
      const isCurrent = p === currentPeriod;
      return `<div class="period-row ${isCurrent ? 'current' : ''} p${i}">
        <span class="period-label">${p.charAt(0)}</span>
        <span class="period-val">${val}</span>
      </div>`;
    }).join('');
    return `<div class="hint">${rows}</div>`;
  },

  /**
   * 长学期 chip：按周显示（兜底，正常情况下 chip_display='none' 不会触发）
   */
  _weekdayChipHTML(stats, key, hintType, currentPeriod, weekdayKeys) {
    if (!weekdayKeys.length) return '';
    const rows = weekdayKeys.map((p, i) => {
      let val = '-';
      if (hintType === 'by_period_rate') {
        val = stats.by_weekday?.[p]?.[key] != null
          ? stats.by_weekday[p][key] + '%'
          : '-';
      } else if (hintType === 'renewal_rate_by_period') {
        const rates = stats.renewal_rate_by_period?.[key] || stats.subject_period_renewal?.[key] || {};
        val = (rates[p] || 0) + '%';
      } else if (hintType === 'by_period') {
        if (stats.by_weekday?.[p]) {
          val = stats.by_weekday[p][key] ?? '-';
        }
      }
      return `<div class="period-row p${i}">
        <span class="period-label">${p.replace('周', '')}</span>
        <span class="period-val">${val}</span>
      </div>`;
    }).join('');
    return `<div class="hint">${rows}</div>`;
  },
};
