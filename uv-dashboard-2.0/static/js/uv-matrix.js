/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 学期矩阵组件（v5 季节感知版）
   寒暑短学期 → 教学点 × 期次
   春秋长学期 → 教学点 × 星期（周五/六/日）
   数据来源：后端根据 season 自动选择矩阵类型并返回 columns / points / matrix
   ═══════════════════════════════════════════════════════════════ */

const UVMatrix = {
  async render() {
    const params = UVFilters.buildParams();
    const data = await UVApi.getMatrix(params);
    if (!data || !data.matrix) {
      document.getElementById('matrix-content').innerHTML = '<p class="no-data">暂无矩阵数据</p>';
      return;
    }
    this._renderTable(data);
  },

  _renderTable(data) {
    const container = document.getElementById('matrix-content');
    const { matrix, points, columns, matrix_type, season_label, season_badge } = data;
    const colKeys = columns.map(c => c.key);
    const rowUV = matrix['__row_uv__'] || {};
    const colUV = matrix['__col_uv__'] || {};
    const grandUV = matrix['__grand_uv__'] || 0;
    const rowCls = matrix['__row_cls__'] || {};
    const colCls = matrix['__col_cls__'] || {};
    const grandCls = matrix['__grand_cls__'] || 0;
    const rowSubjCls = matrix['__row_subj_cls__'] || {};
    const colSubjCls = matrix['__col_subj_cls__'] || {};
    const grandSubjCls = matrix['__grand_subj_cls__'] || {};

    // ── 标题文案 ──
    const titleText = matrix_type === 'short_term'
      ? `${season_label}期次 × 教学点矩阵`
      : `${season_label}学期 × 教学点矩阵`;
    const badgeClass = this._seasonBadgeClass(season_badge);

    // ── 预计算合计 ──
    let grandActive = 0, grandRenewed = 0;
    const colTotals = {};
    colKeys.forEach(ck => { colTotals[ck] = { active: 0, renewed: 0, subjects: {}, subjCls: {} }; });
    const grandSubjects = {};
    UVConfig.SUBJECTS.forEach(s => { grandSubjects[s] = 0; });

    points.forEach(pt => {
      const ptData = matrix[pt] || {};
      colKeys.forEach(ck => {
        const cell = ptData[ck] || {};
        const t = colTotals[ck];
        t.active += cell.active || 0;
        t.renewed += cell.renewed || 0;
        grandActive += cell.active || 0;
        grandRenewed += cell.renewed || 0;
        UVConfig.SUBJECTS.forEach(s => {
          const cnt = (cell.subjects || {})[s] || 0;
          t.subjects[s] = (t.subjects[s] || 0) + cnt;
          grandSubjects[s] = (grandSubjects[s] || 0) + cnt;
        });
      });
    });

    // ── 表头 ──
    let html = '<div class="matrix-season-header">';
    html += `<span class="season-badge ${badgeClass}">${season_badge}</span>`;
    html += `<span class="matrix-title">${titleText}</span>`;
    html += '</div>';
    html += '<table class="matrix-table"><thead><tr>';
    html += '<th class="row-label">教学点</th>';
    columns.forEach(c => {
      const noteHtml = c.note ? `<div class="mc-period-note">${c.note}</div>` : '';
      const dateHtml = c.date_range ? `<div class="mc-period-date">${c.date_range}</div>` : '';
      html += `<th><div class="mc-period-name">${c.label}</div>${dateHtml}${noteHtml}</th>`;
    });
    html += '<th class="col-total"><div class="mc-period-name">合计</div></th></tr></thead><tbody>';

    // ── 各教学点行 ──
    points.forEach(pt => {
      const ptData = matrix[pt] || {};
      let ptActive = 0, ptRenewed = 0;
      const ptSubjects = {};
      UVConfig.SUBJECTS.forEach(s => { ptSubjects[s] = 0; });

      html += `<tr><td class="row-label">${pt}</td>`;
      colKeys.forEach(ck => {
        const cell = ptData[ck] || { active: 0, renewed: 0, uv: 0, renewal_rate: 0, subjects: {}, class_count: 0, subject_classes: {} };
        ptActive += cell.active || 0;
        ptRenewed += cell.renewed || 0;
        UVConfig.SUBJECTS.forEach(s => {
          ptSubjects[s] += (cell.subjects || {})[s] || 0;
        });
        html += `<td>${this._cellHTML(cell)}</td>`;
      });

      const ptSubjCls = rowSubjCls[pt] || {};
      html += `<td class="total-cell">${this._totalHTML(ptActive, ptRenewed, rowUV[pt] || 0, rowCls[pt] || 0, ptSubjects, ptSubjCls)}</td></tr>`;
    });

    // ── 合计行 ──
    html += `<tr class="grand-row"><td class="row-label">合计</td>`;
    colKeys.forEach(ck => {
      const t = colTotals[ck];
      const pSubjCls = colSubjCls[ck] || {};
      html += `<td class="total-cell">${this._totalHTML(t.active, t.renewed, colUV[ck] || 0, colCls[ck] || 0, t.subjects, pSubjCls)}</td>`;
    });
    html += `<td class="total-cell">${this._totalHTML(grandActive, grandRenewed, grandUV, grandCls, grandSubjects, grandSubjCls)}</td></tr>`;

    html += '</tbody></table>';
    html += this._legendHTML();

    container.innerHTML = html;
  },

  _seasonBadgeClass(badge) {
    const map = { '暑': 'summer', '寒': 'winter', '春': 'spring', '秋': 'autumn' };
    return map[badge] || '';
  },

  _cellHTML(cell) {
    if (!cell.active || cell.active === 0) {
      return '<div class="matrix-cell empty">—</div>';
    }
    const rate = cell.renewal_rate || 0;
    const rateClass = this._rateClass(rate);
    const classCount = cell.class_count || 0;

    const pills = UVConfig.SUBJECTS.map(s => {
      const count = (cell.subjects || {})[s] || 0;
      if (!count) return '';
      const cls = UVConfig.SUBJECT_PILL_CLASS[s];
      const short = UVConfig.SUBJECT_SHORT[s];
      return `<span class="subj-pill ${cls}">${short}${count}</span>`;
    }).join('');

    const subjClasses = cell.subject_classes || {};
    const clsParts = UVConfig.SUBJECTS.map(s => {
      const cc = subjClasses[s] || 0;
      if (!cc) return '';
      return `${UVConfig.SUBJECT_SHORT[s]}${cc}`;
    }).filter(Boolean).join(' ');
    const clsTitle = clsParts ? `${classCount}个班 (${clsParts})` : `${classCount}个班`;

    return `<div class="matrix-cell" title="${clsTitle}">
      <div class="mc-top">
        <span class="mc-pv">${cell.active}<span class="mc-unit">PV</span></span>
        <span class="mc-rate ${rateClass}">${rate}%</span>
      </div>
      <div class="mc-pills">${pills}</div>
      <div class="mc-bottom">
        <span class="mc-uv">UV<b> ${cell.uv}</b></span>
        <span class="mc-sep">·</span>
        <span class="mc-cls"><b>${classCount}</b>班</span>
      </div>
    </div>`;
  },

  _totalHTML(active, renewed, uv, classCount, subjects, subjCls) {
    if (!active || active === 0) {
      return '<div class="matrix-cell empty">—</div>';
    }
    const rate = active > 0 ? (renewed / active * 100).toFixed(1) : 0;
    const rateClass = this._rateClass(rate);

    const pills = UVConfig.SUBJECTS.map(s => {
      const count = subjects[s] || 0;
      if (!count) return '';
      const cls = UVConfig.SUBJECT_PILL_CLASS[s];
      const short = UVConfig.SUBJECT_SHORT[s];
      const cc = (subjCls || {})[s] || 0;
      return `<span class="subj-pill ${cls}" title="${short}${cc}班">${short}${count}</span>`;
    }).join('');

    const clsParts = UVConfig.SUBJECTS.map(s => {
      const cc = (subjCls || {})[s] || 0;
      if (!cc) return '';
      return `${UVConfig.SUBJECT_SHORT[s]}${cc}`;
    }).filter(Boolean).join(' ');
    const clsTitle = clsParts ? `${classCount}个班 (${clsParts})` : `${classCount}个班`;

    return `<div class="matrix-cell" title="${clsTitle}">
      <div class="mc-top">
        <span class="mc-pv">${active}<span class="mc-unit">PV</span></span>
        <span class="mc-rate ${rateClass}">${rate}%</span>
      </div>
      <div class="mc-pills">${pills}</div>
      <div class="mc-bottom">
        <span class="mc-uv">UV<b> ${uv}</b></span>
        <span class="mc-sep">·</span>
        <span class="mc-cls"><b>${classCount}</b>班</span>
      </div>
    </div>`;
  },

  _rateClass(rate) {
    const r = parseFloat(rate) || 0;
    if (r === 0) return 'zero';
    if (r >= 30) return 'high';
    if (r >= 15) return 'mid';
    return 'low';
  },

  _legendHTML() {
    return `<div class="matrix-legend">
      <div class="legend-item"><span class="dot math"></span>雪球思维</div>
      <div class="legend-item"><span class="dot chinese"></span>悦读创作</div>
      <div class="legend-item"><span class="dot english"></span>双语素养</div>
      <div class="legend-item"><span class="dot science"></span>雪球科学</div>
      <div class="legend-divider"></div>
      <div class="legend-item"><span class="legend-rate high">≥30%</span> 高续报</div>
      <div class="legend-item"><span class="legend-rate mid">15-30%</span> 中等</div>
      <div class="legend-item"><span class="legend-rate low">&lt;15%</span> 低续报</div>
      <div class="legend-divider"></div>
      <div class="legend-item legend-hint">PV = 科目人次 · UV = 去重学员 · 班量 = 去重班级ID</div>
    </div>`;
  },
};
