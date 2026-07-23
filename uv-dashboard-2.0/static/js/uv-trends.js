/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 业务趋势组件
   趋势图表 + 主讲/顾问排行 + 分享按钮
   排行渲染升级：增加 rank-bar 进度条 + rank-stat-row 数据行
   ═══════════════════════════════════════════════════════════════ */

// ── Chart.js 专用色值常量（canvas 不支持 CSS 变量，必须用 hex/rgba）──
// 数据标签防遮挡逻辑统一由 uv-chart-labels.js 的 UVChartLabels.dataLabelPlugin 提供
const CHART_COLORS = {
  textTertiary:  '#6C7293',
  textPrimary:   '#1A1A2E',
  textSecondary: '#2D3142',
  textMuted:     '#A0A3BD',
  borderDefault: '#E5E7EB',
  gridLight:     'rgba(0,0,0,0.04)',
  gridXLight:    'rgba(0,0,0,0.03)',
  tooltipBg:     'rgba(255,255,255,0.97)',
};

const FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif';

const UVTrends = {
  trendData: null,
  statsData: null,
  acquisitionData: null,
  channelData: null,
  channelLevel: 'l1',
  teacherRankMode: 'renewal',
  advisorRankMode: 'renewal',
  advisorUVMode: 'uv',
  acqMode: 'uv',
  acqMonthFilter: [],
  charts: {},
  advisorPtMap: null,

  async load() {
    const [trends, stats, acquisition, channel] = await Promise.all([
      UVApi.getTrends(UVFilters.buildParams()),
      UVApi.getStats(UVFilters.buildParams()),
      UVApi.getAcquisitionTrends(UVFilters.buildParams()),
      UVApi.getChannelAcquisition(UVFilters.buildParams({ channelLevel: this.channelLevel })),
    ]);
    this.trendData = trends;
    this.statsData = stats;
    this.acquisitionData = acquisition;
    this.channelData = channel;
    if (stats && stats.by_advisor) {
      const map = {};
      stats.by_advisor.forEach(a => {
        if (a.teaching_point) map[a.name] = a.teaching_point;
      });
      if (Object.keys(map).length > 0) this.advisorPtMap = map;
    }
    if (trends) this.renderCharts(trends);
    if (acquisition) this.renderAcquisitionChart(acquisition);
    if (channel) this.renderChannelChart(channel);
    if (stats) this.renderRankings(stats);
  },

  renderCharts(trends) {
    const ctx = document.getElementById('chart-main-trend');
    if (!ctx) return;

    if (this.charts.main) this.charts.main.destroy();

    // 仅展示近7天数据
    const recent = trends.slice(-7);
    const dates = recent.map(t => t.run_time || '-');
    const activeData = recent.map(t => t.active_pv || 0);
    const refundData = recent.map(t => t.refund_pv || 0);
    const renewData = recent.map(t => t.renewal_pv || 0);
    // BUG 修复：续报率分母用 denom_pv（按 renew_denom_incl 口径），
    // 避免超过 100%（用 active_pv 当分母在多科目场景会偏小）
    const rateData = recent.map(t => {
      const denom = t.denom_pv || t.active_pv || 0;
      return denom > 0 ? Math.min(parseFloat((t.renewal_pv / denom * 100).toFixed(1)), 100) : 0;
    });

    // 统一色值（引用 UVConfig 设计令牌，避免硬编码）
    const C = UVConfig.COLORS;
    const colorRefund = { bg: 'rgba(232,80,91,0.70)', border: C.accentRed, label: C.accentRed };
    const colorActive = { bg: 'rgba(55,138,221,0.70)', border: C.accentBlue, label: C.accentBlue };
    const colorRenew  = { bg: 'rgba(22,163,74,0.75)',  border: C.accentGreen, label: C.accentGreen };
    const colorRate   = C.accentOrange;

    this.charts.main = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: dates,
        datasets: [
          {
            label: '退费 PV',
            data: refundData,
            backgroundColor: colorRefund.bg,
            borderColor: colorRefund.border,
            borderWidth: 0,
            borderRadius: 6,
            borderSkipped: false,
            order: 2,
            stack: 'stack1',
            maxBarThickness: 52,
          },
          {
            label: '在读 PV',
            data: activeData,
            backgroundColor: colorActive.bg,
            borderColor: colorActive.border,
            borderWidth: 0,
            borderRadius: 6,
            borderSkipped: false,
            order: 2,
            stack: 'stack1',
            maxBarThickness: 52,
          },
          {
            label: '续费 PV',
            data: renewData,
            backgroundColor: colorRenew.bg,
            borderColor: colorRenew.border,
            borderWidth: 0,
            borderRadius: { topLeft: 6, topRight: 6 },
            borderSkipped: false,
            order: 2,
            stack: 'stack1',
            maxBarThickness: 52,
          },
          {
            label: '续报率 %',
            data: rateData,
            type: 'line',
            borderColor: colorRate,
            backgroundColor: 'transparent',
            tension: 0.4,
            pointRadius: 5,
            pointHoverRadius: 7,
            pointBackgroundColor: '#fff',
            pointBorderColor: colorRate,
            pointBorderWidth: 2.5,
            pointHoverBorderWidth: 3,
            borderWidth: 3,
            order: 1,
            yAxisID: 'y1',
          },
        ]
      },
      plugins: [UVChartLabels.dataLabelPlugin],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        layout: { padding: { top: 18, right: 10, bottom: 0, left: 0 } },
        scales: {
          x: {
            stacked: true,
            ticks: {
              color: CHART_COLORS.textTertiary,
              font: { size: 11, weight: '500', family: FONT_FAMILY },
              padding: 8,
            },
            grid: { color: CHART_COLORS.gridXLight, drawBorder: false },
            border: { display: false },
          },
          y: {
            stacked: true,
            position: 'left',
            ticks: {
              color: CHART_COLORS.textTertiary,
              font: { size: 11, weight: '500', family: FONT_FAMILY },
              padding: 6,
            },
            grid: { color: CHART_COLORS.gridLight, drawBorder: false },
            border: { display: false },
          },
          y1: {
            position: 'right',
            ticks: {
              color: colorRate,
              font: { size: 11, weight: '600', family: FONT_FAMILY },
              callback: v => v + '%',
              padding: 6,
            },
            grid: { drawOnChartArea: false, drawBorder: false },
            border: { display: false },
            min: 0,
            max: 100,
          }
        },
        plugins: {
          legend: { display: false },
          uvDataLabels: { theme: 'light', fontFamily: FONT_FAMILY },
          tooltip: {
            backgroundColor: CHART_COLORS.tooltipBg,
            titleColor: CHART_COLORS.textPrimary,
            bodyColor: CHART_COLORS.textSecondary,
            borderColor: CHART_COLORS.borderDefault,
            borderWidth: 1,
            padding: 12,
            cornerRadius: 8,
            displayColors: true,
            boxPadding: 4,
            titleFont: { size: 13, weight: '600', family: FONT_FAMILY },
            bodyFont: { size: 12, family: FONT_FAMILY },
            callbacks: {
              label: function(context) {
                if (context.dataset.label === '续报率 %') {
                  return '续报率: ' + context.raw + '%';
                }
                return context.dataset.label + ': ' + context.raw;
              }
            }
          }
        }
      }
    });
    this.renderMainLegend();
  },

  renderMainLegend() {
    const el = document.getElementById('chart-main-legend');
    if (!el) return;
    const C = UVConfig.COLORS;
    el.innerHTML = `
      <div class="chart-legend-item"><span class="legend-dot" style="background:${C.accentRed}"></span>退费 PV</div>
      <div class="chart-legend-item"><span class="legend-dot" style="background:${C.accentBlue}"></span>在读 PV</div>
      <div class="chart-legend-item"><span class="legend-dot" style="background:${C.accentGreen}"></span>续费 PV</div>
      <div class="chart-legend-item"><span class="legend-dot line" style="background:${C.accentOrange}"></span>续报率 %</div>
    `;
  },

  renderRankings(stats) {
    this._syncTeacherModeButtons();
    this.renderTeacherRanking(stats.by_teacher || []);
    this.renderAdvisorRanking(stats.by_advisor || []);
  },

  // ── 拉新×续报转化月度图表 ──
  renderAcquisitionChart(data) {
    const canvasEl = document.getElementById('chart-acquisition-trend');
    if (!canvasEl || !data || !data.months) return;

    if (this.charts.acquisition) this.charts.acquisition.destroy();

    // ── 标题联动：根据后端返回的学季动态更新 ──
    const titleEl = document.getElementById('acq-chart-title');
    if (titleEl) {
      const season = data.season_label || '';
      titleEl.textContent = `${season}拉新×续报转化 · 月度分析（按订单来源=拉新）`;
    }

    // ── 月份 chips 动态生成 ──
    const chipsContainer = document.getElementById('acq-month-chips');
    if (chipsContainer && data.months) {
      const validLabels = new Set(data.months.map(m => m.month_label));
      if (this.acqMonthFilter && this.acqMonthFilter.length) {
        this.acqMonthFilter = this.acqMonthFilter.filter(m => validLabels.has(m));
      }
      const chips = [{ month: '', label: '全部' }].concat(
        data.months.map(m => ({ month: m.month_label, label: m.month_label.replace(/^0/, '') }))
      );
      chipsContainer.innerHTML = chips.map(c => {
        const active = c.month === '' ? !this.acqMonthFilter.length : this.acqMonthFilter.includes(c.month);
        return `<span class="acq-chip ${active ? 'active' : ''}" data-month="${c.month}" onclick="UVTrends.switchAcqMonth('${c.month}')">${c.label}</span>`;
      }).join('');
    }

    // ── 月份筛选 ──
    let months = data.months;
    if (this.acqMonthFilter && this.acqMonthFilter.length) {
      const fset = new Set(this.acqMonthFilter);
      months = months.filter(m => fset.has(m.month_label));
    }

    const isUV = this.acqMode === 'uv';
    const unit = isUV ? '人' : '科';
    const nextSeason = data.next_season_label || '秋';
    const notRenewedLabel = `未续${nextSeason}`;
    const renewedLabel = `已续${nextSeason}`;

    const labels = months.map(m => m.month_label);
    const pureNew    = months.map(m => isUV ? m.active_acquired : m.active_pv); // 纯拉新 = 已续 + 未续
    const notRenewed = months.map(m => isUV ? m.not_renewed : m.not_renewed_pv);
    const renewed    = months.map(m => isUV ? m.renewed_acquired : m.renewed_pv);
    const convRate   = months.map(m => isUV ? m.conv_rate : m.conv_rate_pv);

    // ── 合计行（基于筛选后的月份）──
    const sumActive = pureNew.reduce((a, b) => a + b, 0);
    const sumRenewed = renewed.reduce((a, b) => a + b, 0);
    const sumNotRenewed = notRenewed.reduce((a, b) => a + b, 0);
    const sumConvRate = sumActive > 0 ? Math.round(sumRenewed / sumActive * 1000) / 10 : 0;

    const totalLabel = `合计`;
    labels.push(totalLabel);
    pureNew.push(sumActive);
    notRenewed.push(sumNotRenewed);
    renewed.push(sumRenewed);
    convRate.push(sumConvRate);

    // ── 色值（2.0 设计令牌）──
    const C = UVConfig.COLORS;
    const cNotRenewed = C.primary;
    const cRenewed    = C.accentGreen;
    const cConvRate   = C.accentOrange;

    // 渲染图例
    this.renderAcqLegend(isUV, notRenewedLabel, renewedLabel);

    // ── 数据缺口提示 ──
    const hintEl = document.getElementById('acq-hint');
    if (hintEl) {
      const studentTotal = data.student_total || 0;
      if (!data.months || data.months.length === 0) {
        hintEl.textContent = data.hint || `当前筛选下暂无「${data.season_label || ''}」纯拉新数据，可能目标学季无「在读+订单来源=拉新」订单。`;
        hintEl.style.display = 'block';
      } else if (sumActive === 0 && studentTotal > 0) {
        hintEl.textContent = `当前筛选下有 ${studentTotal} 名纯拉新学员，但目标学季订单缺少有效支付时间，无法按月份归属。`;
        hintEl.style.display = 'block';
      } else {
        hintEl.style.display = 'none';
      }
    }

    this.charts.acquisition = new Chart(canvasEl, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          // 底部：未续下学期（蓝色）
          {
            label: notRenewedLabel,
            data: notRenewed,
            backgroundColor: cNotRenewed,
            borderWidth: 0,
            borderRadius: { topLeft: 0, topRight: 0, bottomLeft: 6, bottomRight: 6 },
            borderSkipped: false,
            stack: 'stack1',
            maxBarThickness: 52,
          },
          // 顶部：已续下学期（绿色）
          {
            label: renewedLabel,
            data: renewed,
            backgroundColor: cRenewed,
            borderWidth: 0,
            borderRadius: { topLeft: 6, topRight: 6, bottomLeft: 0, bottomRight: 0 },
            borderSkipped: false,
            stack: 'stack1',
            maxBarThickness: 52,
          },
          // 转化率折线（置顶显示，标签固定在线点上方）
          {
            label: '转化率 %',
            data: convRate,
            type: 'line',
            borderColor: cConvRate,
            backgroundColor: 'transparent',
            tension: 0.4,
            pointRadius: 5,
            pointHoverRadius: 7,
            pointBackgroundColor: '#fff',
            pointBorderColor: cConvRate,
            pointBorderWidth: 2.5,
            pointHoverBorderWidth: 3,
            borderWidth: 3,
            order: 99,
            yAxisID: 'y1',
          },
        ]
      },
      plugins: [UVChartLabels.dataLabelPlugin],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        layout: { padding: { top: 22, right: 10, bottom: 22, left: 14 } },
        scales: {
          x: {
            stacked: true,
            ticks: {
              color: CHART_COLORS.textTertiary,
              font: { size: 11, weight: '500', family: FONT_FAMILY },
              padding: 8,
            },
            grid: { color: CHART_COLORS.gridXLight, drawBorder: false },
            border: { display: false },
          },
          x2: {
            position: 'bottom',
            grid: { display: false, drawBorder: false },
            border: { display: false },
            ticks: {
              color: C.primary,
              font: { size: 12, weight: '700', family: FONT_FAMILY },
              padding: 6,
              callback: (value, index) => `${pureNew[index]}${unit}`,
            },
          },
          y: {
            stacked: true,
            position: 'left',
            title: { display: false },
            ticks: {
              color: CHART_COLORS.textTertiary,
              font: { size: 11, weight: '500', family: FONT_FAMILY },
              padding: 6,
            },
            grid: { color: CHART_COLORS.gridLight, drawBorder: false },
            border: { display: false },
            beginAtZero: true,
          },
          y1: {
            position: 'right',
            ticks: {
              color: cConvRate,
              font: { size: 11, weight: '600', family: FONT_FAMILY },
              callback: v => v + '%',
              padding: 6,
            },
            grid: { drawOnChartArea: false, drawBorder: false },
            border: { display: false },
            min: -10,
            max: 100,
          }
        },
        plugins: {
          legend: { display: false },
          uvDataLabels: { theme: 'light', fontFamily: FONT_FAMILY },
          acqX2Title: {
            afterDraw(chart) {
              const x2 = chart.scales.x2;
              if (!x2) return;
              const ctx = chart.ctx;
              ctx.save();
              ctx.font = '600 11px ' + FONT_FAMILY;
              ctx.fillStyle = C.primary;
              ctx.textAlign = 'right';
              ctx.textBaseline = 'middle';
              // 左侧蓝色说明文字，与 x2 刻度数字纵向居中对齐
              const x = chart.chartArea.left - 10;
              const y = x2.y + 6;
              ctx.fillText('拉新总数', x, y);
              ctx.restore();
            }
          },
          tooltip: {
            backgroundColor: CHART_COLORS.tooltipBg,
            titleColor: CHART_COLORS.textPrimary,
            bodyColor: CHART_COLORS.textSecondary,
            borderColor: CHART_COLORS.borderDefault,
            borderWidth: 1,
            padding: 12,
            cornerRadius: 8,
            displayColors: true,
            usePointStyle: true,
            boxPadding: 5,
            titleFont: { size: 13, weight: '600', family: FONT_FAMILY },
            bodyFont: { size: 12, family: FONT_FAMILY },
            callbacks: {
              label: function(context) {
                const idx = context.dataIndex;
                const lbl = context.dataset.label;
                if (lbl === '转化率 %') return `转化率: ${context.raw}%`;
                if (lbl === notRenewedLabel) return `${notRenewedLabel}: ${context.raw}${unit}`;
                if (lbl === renewedLabel) return `${renewedLabel}: ${context.raw}${unit}`;
                return `${lbl}: ${context.raw}`;
              },
              afterBody: function(tooltipItems) {
                const idx = tooltipItems[0].dataIndex;
                return `纯拉新: ${pureNew[idx]}${unit}`;
              }
            }
          }
        }
      }
    });
  },

  // ── 图例渲染（根据 UV/PV 模式 + 次学季动态生成）──
  renderAcqLegend(isUV, notRenewedLabel = '未续秋', renewedLabel = '已续秋') {
    const el = document.getElementById('acq-legend');
    if (!el) return;
    const unit = isUV ? '人' : '科';
    el.innerHTML = `
      <div class="chart-legend-item"><span class="legend-dot" style="background:${UVConfig.COLORS.primary}"></span>${notRenewedLabel} (${unit})</div>
      <div class="chart-legend-item"><span class="legend-dot" style="background:${UVConfig.COLORS.accentGreen}"></span>${renewedLabel} (${unit})</div>
      <div class="chart-legend-item"><span class="legend-dot line" style="background:${UVConfig.COLORS.accentOrange}"></span>转化率 %</div>
    `;
  },

  // ── 数据洞察图（学科构成 doughnut + 教学点 UV 分布 bar）──
  renderInsightCharts(stats) {
    if (!stats) return;
    const C = UVConfig.COLORS;

    // ── 学科在读构成 doughnut ──
    const doughnutEl = document.getElementById('chart-subject-doughnut');
    if (doughnutEl) {
      try {
        if (this.charts.subjectDoughnut) this.charts.subjectDoughnut.destroy();
        const bySubject = stats.by_subject || [];
        const labels = bySubject.map(s => s.name || s.key || '');
        const data = bySubject.map(s => s.active || 0);
        const colors = bySubject.map(s => UVConfig.SUBJECT_COLOR[s.key] || C.accentBlue);
        // 检查 wrap 完整性：canvas 必须仍是 wrap 的子元素
        const wrap = doughnutEl.parentElement;
        const canvasStillInDom = wrap && doughnutEl === wrap.querySelector('canvas');
        if (labels.length && data.some(v => v > 0) && canvasStillInDom) {
          this.charts.subjectDoughnut = new Chart(doughnutEl, {
            type: 'doughnut',
            data: { labels, datasets: [{ data, backgroundColor: colors, borderColor: '#fff', borderWidth: 2, hoverOffset: 6 }] },
            plugins: [UVChartLabels.dataLabelPlugin],
            options: {
              responsive: true, maintainAspectRatio: false, cutout: '62%',
              plugins: {
                legend: { position: 'right', labels: { color: CHART_COLORS.textSecondary, font: { size: 12, family: FONT_FAMILY }, boxWidth: 12, boxHeight: 12, padding: 12 } },
                tooltip: { backgroundColor: CHART_COLORS.tooltipBg, titleColor: CHART_COLORS.textPrimary, bodyColor: CHART_COLORS.textSecondary, borderColor: CHART_COLORS.borderDefault, borderWidth: 1, padding: 10, cornerRadius: 8, callbacks: { label: c => `${c.label}: ${UVConfig.fmtNum(c.raw)}` } },
                uvDataLabels: {
                  theme: 'light', fontFamily: FONT_FAMILY,
                  formatter: (value, ctx) => {
                    // 兼容两种 ctx 格式：{ chart, ... } 或直接 chart
                    const chart = ctx && ctx.chart ? ctx.chart : ctx;
                    const ds = chart && chart.data && chart.data.datasets && chart.data.datasets[0];
                    if (!ds) return '';
                    const total = ds.data.reduce((s, v) => s + v, 0);
                    if (!total) return '';
                    const pct = (value / total * 100).toFixed(1);
                    return pct + '%';
                  },
                  anchor: 'center', align: 'center',
                  color: '#fff', font: { size: 12, family: FONT_FAMILY, weight: '600' },
                },
              }
            }
          });
        } else if (wrap) {
          // canvas 不在 DOM 中（被替换过），重新插入；并用空态填充
          if (!canvasStillInDom) {
            wrap.innerHTML = '<canvas id="chart-subject-doughnut"></canvas>';
          }
          this.charts.subjectDoughnut && this.charts.subjectDoughnut.destroy();
          this.charts.subjectDoughnut = null;
          // 渲染空态
          const newCanvas = document.getElementById('chart-subject-doughnut');
          if (newCanvas) newCanvas.style.display = 'none';
          const empty = document.createElement('div');
          empty.className = 'uv-empty';
          empty.innerHTML = UVConfig.renderEmpty({ msg: '暂无学科数据' });
          wrap.appendChild(empty);
        }
      } catch (e) { console.error('renderInsightCharts doughnut error:', e); }
    }

    // ── 教学点 UV 分布 bar ──
    const barEl = document.getElementById('chart-point-bar');
    if (barEl) {
      try {
        if (this.charts.pointBar) this.charts.pointBar.destroy();
        const byPoint = stats.by_point || [];
        const labels = byPoint.map(p => p.name || '');
        const data = byPoint.map(p => (p.uv != null ? p.uv : (p.active_uv || 0)));
        const wrap = barEl.parentElement;
        const canvasStillInDom = wrap && barEl === wrap.querySelector('canvas');
        if (labels.length && data.some(v => v > 0) && canvasStillInDom) {
          this.charts.pointBar = new Chart(barEl, {
            type: 'bar',
            data: { labels, datasets: [{ label: '在读UV', data, backgroundColor: C.primary, borderRadius: 6, maxBarThickness: 48 }] },
            plugins: [UVChartLabels.dataLabelPlugin],
            options: {
              responsive: true, maintainAspectRatio: false,
              scales: {
                x: { ticks: { color: CHART_COLORS.textTertiary, font: { size: 12, family: FONT_FAMILY } }, grid: { display: false }, border: { display: false } },
                y: { beginAtZero: true, ticks: { color: CHART_COLORS.textTertiary, font: { size: 11, family: FONT_FAMILY } }, grid: { color: CHART_COLORS.gridLight, drawBorder: false }, border: { display: false } }
              },
              plugins: {
                legend: { display: false },
                uvDataLabels: { theme: 'light', fontFamily: FONT_FAMILY },
                tooltip: { backgroundColor: CHART_COLORS.tooltipBg, titleColor: CHART_COLORS.textPrimary, bodyColor: CHART_COLORS.textSecondary, borderColor: CHART_COLORS.borderDefault, borderWidth: 1, padding: 10, cornerRadius: 8, callbacks: { label: c => '在读UV: ' + UVConfig.fmtNum(c.raw) } }
              }
            }
          });
        } else if (wrap) {
          if (!canvasStillInDom) {
            wrap.innerHTML = '<canvas id="chart-point-bar"></canvas>';
          }
          this.charts.pointBar && this.charts.pointBar.destroy();
          this.charts.pointBar = null;
          const newCanvas = document.getElementById('chart-point-bar');
          if (newCanvas) newCanvas.style.display = 'none';
          const empty = document.createElement('div');
          empty.className = 'uv-empty';
          empty.innerHTML = UVConfig.renderEmpty({ msg: '暂无教学点数据' });
          wrap.appendChild(empty);
        }
      } catch (e) { console.error('renderInsightCharts bar error:', e); }
    }
  },

  // ── UV/PV 模式切换 ──
  switchAcqMode(mode) {
    this.acqMode = mode;
    const btns = document.querySelectorAll('#acq-mode-btns .acq-toggle-btn');
    btns.forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
    if (this.acquisitionData) this.renderAcquisitionChart(this.acquisitionData);
  },

  // ── 月份筛选切换（多选）──
  switchAcqMonth(month) {
    if (!Array.isArray(this.acqMonthFilter)) this.acqMonthFilter = [];
    if (month === '') {
      // 全部
      this.acqMonthFilter = [];
    } else {
      const i = this.acqMonthFilter.indexOf(month);
      if (i >= 0) this.acqMonthFilter.splice(i, 1);
      else this.acqMonthFilter.push(month);
    }
    const chips = document.querySelectorAll('#acq-month-chips .acq-chip');
    chips.forEach(chip => {
      if (chip.dataset.month === '') {
        chip.classList.toggle('active', this.acqMonthFilter.length === 0);
      } else {
        chip.classList.toggle('active', this.acqMonthFilter.includes(chip.dataset.month));
      }
    });
    if (this.acquisitionData) this.renderAcquisitionChart(this.acquisitionData);
  },

  // ── 拉新渠道×转化效率图（柱状堆叠+续报折线）──
  switchChannelLevel(level) {
    this.channelLevel = level;
    const btns = document.querySelectorAll('#channel-level-btns .acq-toggle-btn');
    btns.forEach(btn => btn.classList.toggle('active', btn.dataset.level === level));
    UVApi.getChannelAcquisition(UVFilters.buildParams({ channelLevel: level })).then(data => {
      this.channelData = data;
      this.renderChannelChart(data);
    });
  },

  renderChannelChart(data) {
    if (!data) return;
    const canvasEl = document.getElementById('chart-channel');
    if (!canvasEl) return;
    const C = UVConfig.COLORS;
    const wrap = canvasEl.parentElement;
    const channels = data.channels || [];
    const legendEl = document.getElementById('channel-legend');
    const hintEl = document.getElementById('channel-hint');

    if (this.charts.channel) { try { this.charts.channel.destroy(); } catch (e) {} }

    if (!channels.length) {
      if (wrap) wrap.innerHTML = UVConfig.renderEmpty({ msg: '当前筛选下无渠道数据', icon: '📡' });
      if (legendEl) legendEl.innerHTML = '';
      if (hintEl) hintEl.style.display = 'none';
      return;
    }
    if (wrap && wrap.querySelector('canvas') !== canvasEl) {
      wrap.innerHTML = '<canvas id="chart-channel"></canvas>';
    }
    if (hintEl) hintEl.style.display = 'none';

    // 颜色：在读新生=蓝绿色（与业务趋势主色一致），已续=绿（亮点），退费=红
    const labels = channels.map(c => c.name);
    const renewedData = channels.map(c => c.renewed || 0);
    const activeData = channels.map(c => c.active_new || 0);
    const refundData = channels.map(c => c.refunded || 0);
    // 堆叠：[在读新生（已续部分）= renewed, 在读新生（未续）= active_new - renewed, 退费 = refunded]
    // 这样堆叠高度 = acquired（拉新总数）
    const renewedPortion = renewedData.slice(); // 已续属于在读新生
    const notRenewedPortion = activeData.map((a, i) => Math.max(0, a - (renewedData[i] || 0)));
    const totalAcquired = renewedPortion.reduce((s, v, i) => s + v + notRenewedPortion[i] + (refundData[i] || 0), 0);
    // 折线：续报率（已续/在读新生）% —— 取代之前的"已续数"
    const renewalRateData = channels.map(c => +(c.renewal_rate || 0).toFixed(1));

    // 图例
    if (legendEl) {
      legendEl.innerHTML = `
        <div class="chart-legend-item"><span class="legend-dot" style="background:#0EA5A4"></span>已续(在读新生)</div>
        <div class="chart-legend-item"><span class="legend-dot" style="background:${C.primary}"></span>在读新生(未续)</div>
        <div class="chart-legend-item"><span class="legend-dot" style="background:${C.accentRed}"></span>退费新生</div>
        <div class="chart-legend-item"><span class="legend-dot line" style="background:${C.accentOrange}"></span>续报率 %</div>
      `;
    }

    this.charts.channel = new Chart(canvasEl, {
      data: {
        labels,
        datasets: [
          {
            type: 'bar',
            label: '已续(在读)',
            data: renewedPortion,
            backgroundColor: '#0EA5A4',
            borderRadius: 4,
            stack: 'acq',
            maxBarThickness: 38,
            order: 2,
          },
          {
            type: 'bar',
            label: '在读(未续)',
            data: notRenewedPortion,
            backgroundColor: C.primary,
            borderRadius: 4,
            stack: 'acq',
            maxBarThickness: 38,
            order: 2,
          },
          {
            type: 'bar',
            label: '退费',
            data: refundData,
            backgroundColor: C.accentRed,
            borderRadius: 4,
            stack: 'acq',
            maxBarThickness: 38,
            order: 2,
          },
          {
            type: 'line',
            label: '续报率 %',
            data: renewalRateData,
            borderColor: C.accentOrange,
            backgroundColor: C.accentOrange,
            borderWidth: 2.5,
            pointBackgroundColor: C.accentOrange,
            pointRadius: 4,
            pointHoverRadius: 6,
            tension: 0.35,
            yAxisID: 'yRate',
            order: 1,
          },
        ],
      },
      plugins: [UVChartLabels.dataLabelPlugin],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: {
            stacked: true,
            ticks: { color: '#6C7293', font: { size: 12, family: FONT_FAMILY } },
            grid: { display: false }, border: { display: false },
          },
          y: {
            stacked: true,
            beginAtZero: true,
            ticks: { color: '#6C7293', font: { size: 11, family: FONT_FAMILY } },
            grid: { color: 'rgba(108, 114, 147, 0.08)', drawBorder: false },
            border: { display: false },
            title: { display: true, text: '拉新数', color: '#6C7293', font: { size: 11, family: FONT_FAMILY } },
          },
          yRate: {
            position: 'right',
            beginAtZero: true,
            max: 100,
            ticks: {
              color: '#6C7293',
              font: { size: 11, family: FONT_FAMILY },
              callback: (v) => v + '%',
            },
            grid: { display: false },
            border: { display: false },
            title: { display: true, text: '续报率', color: C.accentOrange, font: { size: 11, family: FONT_FAMILY } },
          },
        },
        plugins: {
          legend: { display: false },
          uvDataLabels: { theme: 'light', fontFamily: FONT_FAMILY },
          tooltip: {
            backgroundColor: 'rgba(22,25,35,0.92)', titleColor: '#fff', bodyColor: '#d4d6e0',
            borderColor: 'rgba(255,255,255,0.08)', borderWidth: 1, padding: 10, cornerRadius: 8,
            callbacks: {
              title: (items) => items[0].label,
              label: (c) => {
                const v = c.raw;
                if (c.dataset.type === 'line') return `续报率: ${v}%`;
                return `${c.dataset.label}: ${v}`;
              },
            },
          },
        },
      },
    });
  },

  // ── 主讲排行渲染（含进度条 + stat-row）──
  renderTeacherRanking(teachers) {
    const container = document.getElementById('trends-teacher-ranking');
    if (!container) return;
    const mode = this.teacherRankMode;

    if (!teachers.length) { container.innerHTML = UVConfig.renderEmpty({ msg: '暂无主讲排行数据', icon: '👨‍🏫' }); return; }

    // 根据当前模式排序：续报模式按 renewal_rate，转化模式按 conv_rate
    const sorted = [...teachers].sort((a, b) => {
      const rateA = mode === 'renewal' ? a.renewal_rate : a.conv_rate;
      const rateB = mode === 'renewal' ? b.renewal_rate : b.conv_rate;
      return rateB - rateA;
    });

    // 计算最大值用于进度条
    const maxRate = Math.max(...sorted.map(t => mode === 'renewal' ? t.renewal_rate : t.conv_rate), 1);

    container.innerHTML = sorted.slice(0, 10).map((t, idx) => {
      const medal = UVConfig.medalClass(idx);
      const subjPill = `<span class="subj-pill ${UVConfig.SUBJECT_PILL_CLASS[t.subject] || ''}">${UVConfig.SUBJECT_SHORT[t.subject] || ''}</span>`;
      const rate = mode === 'renewal' ? t.renewal_rate : t.conv_rate;
      const rateClass = UVConfig.rateColor(rate);
      const barWidth = Math.min(rate / maxRate * 100, 100);

      // BUG 修复：根据当前筛选的 course_type 动态选择指标
      // 系统课无"应续"和"当期转化"概念（仅特惠课区分 pre/new）
      const ct = (typeof UVFilters !== 'undefined' && UVFilters.state && UVFilters.state.course_type instanceof Set)
        ? Array.from(UVFilters.state.course_type) : [];
      const isSystemOnly = ct.length === 1 && ct[0] === '系统课';
      const statRow = isSystemOnly ? `<div class="rank-stat-row">
        <div class="rank-stat-cell"><div class="rs-label">在读</div><div class="rs-val">${t.active || 0}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">已续</div><div class="rs-val">${t.renewed || 0}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">续报率</div><div class="rs-val accent">${t.renewal_rate || 0}%</div></div>
      </div>` : `<div class="rank-stat-row">
        <div class="rank-stat-cell"><div class="rs-label">在读</div><div class="rs-val">${t.active || 0}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">应续</div><div class="rs-val">${t.should_renew || 0}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">转化</div><div class="rs-val accent">${t.new_renewed || 0}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">已续</div><div class="rs-val">${t.total_renewed || 0}</div></div>
      </div>`;

      return `<div class="rank-item ${medal}">
        <div class="rank-num">${idx + 1}</div>
        <div class="rank-info">
          <div class="rank-name">${subjPill} ${t.name}</div>
          <div class="rank-bar-wrap"><div class="rank-bar-fill ${rateClass}" style="width:${barWidth}%"></div></div>
          ${statRow}
        </div>
        <div class="rank-rate ${rateClass}">${rate}%</div>
      </div>`;
    }).join('');
  },

  // ── 顾问排行渲染（含进度条 + stat-row）──
  renderAdvisorRanking(advisors) {
    const container = document.getElementById('trends-advisor-ranking');
    if (!container) return;
    const mode = this.advisorRankMode;
    const isUV = this.advisorUVMode === 'uv';
    const ptMap = this.advisorPtMap;

    if (!advisors.length) { container.innerHTML = UVConfig.renderEmpty({ msg: '暂无顾问排行数据', icon: '💼' }); return; }

    // 计算每个顾问的排序 rate，根据 mode 和 UV/PV 维度
    const getRate = (a) => {
      const active = isUV ? a.active : (a.pv_active || a.active);
      const should_renew = isUV ? a.should_renew : (a.pv_should_renew || (active - (a.pv_pre_renewed || a.pre_renewed)));
      const new_renewed = isUV ? a.new_renewed : (a.pv_new_renewed || a.new_renewed);
      const total_renewed = isUV ? a.total_renewed : (a.pv_total_renewed || a.total_renewed);
      return mode === 'renewal'
        ? (active > 0 ? total_renewed / active * 100 : 0)
        : (should_renew > 0 ? new_renewed / should_renew * 100 : 0);
    };

    // 根据当前模式+维度排序
    const sorted = [...advisors].sort((a, b) => getRate(b) - getRate(a));

    // 计算最大值用于进度条
    const rates = sorted.map(a => getRate(a));
    const maxRate = Math.max(...rates, 1);

    container.innerHTML = sorted.slice(0, 10).map((a, idx) => {
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

      const dim = isUV ? 'UV' : 'PV';
      const statRow = `<div class="rank-stat-row">
        <div class="rank-stat-cell"><div class="rs-label">${dim}</div><div class="rs-val">${active}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">应续</div><div class="rs-val">${should_renew}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">转化</div><div class="rs-val accent">${new_renewed}</div></div>
        <div class="rank-stat-cell"><div class="rs-label">已续</div><div class="rs-val">${total_renewed}</div></div>
      </div>`;

      return `<div class="rank-item ${medal}">
        <div class="rank-num">${idx + 1}</div>
        <div class="rank-info">
          <div class="rank-name">${tagPill} ${a.name}</div>
          <div class="rank-bar-wrap"><div class="rank-bar-fill ${rateClass}" style="width:${barWidth}%"></div></div>
          ${statRow}
        </div>
        <div class="rank-rate ${rateClass}">${rate}%</div>
      </div>`;
    }).join('');
  },

  // ── 切换按钮 ──
  switchTeacherMode(mode) {
    this.teacherRankMode = mode;
    // 切换按钮 active 状态
    const btns = document.querySelectorAll('#trends-teacher-btns .rank-btn');
    btns.forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
    if (this.statsData) this.renderTeacherRanking(this.statsData.by_teacher || []);
  },

  // BUG 修复：系统课时隐藏"转化率"按钮（系统课无应续/当期转化概念）
  _syncTeacherModeButtons() {
    const ct = (typeof UVFilters !== 'undefined' && UVFilters.state && UVFilters.state.course_type instanceof Set)
      ? Array.from(UVFilters.state.course_type) : [];
    const isSystemOnly = ct.length === 1 && ct[0] === '系统课';
    const btns = document.querySelectorAll('#trends-teacher-btns .rank-btn');
    btns.forEach(btn => {
      if (btn.dataset.mode === 'conversion') {
        btn.style.display = isSystemOnly ? 'none' : '';
        // 系统课自动切回"续报率"
        if (isSystemOnly && this.teacherRankMode === 'conversion') {
          this.teacherRankMode = 'renewal';
        }
      }
    });
    // 同步 active
    if (isSystemOnly) {
      btns.forEach(btn => btn.classList.toggle('active', btn.dataset.mode === 'renewal'));
    }
  },
  switchAdvisorMode(mode) {
    this.advisorRankMode = mode;
    const btns = document.querySelectorAll('#trends-advisor-btns .rank-btn');
    btns.forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
    if (this.statsData) this.renderAdvisorRanking(this.statsData.by_advisor || []);
  },
  switchAdvisorUVMode(mode) {
    this.advisorUVMode = mode;
    const btns = document.querySelectorAll('#trends-advisor-uv-btns .uv-btn');
    btns.forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
    if (this.statsData) this.renderAdvisorRanking(this.statsData.by_advisor || []);
  },

  // ── 分享 ──
  async generateShare() {
    // Set → comma-separated；空 Set = 全选 → 传空串（后端按全部处理）
    const toParam = (set) => (set && set.size) ? Array.from(set).join(',') : '';
    const params = {
      subjects: toParam(UVFilters.state.subject),
      teaching_points: toParam(UVFilters.state.teaching_point),
      periods: toParam(UVFilters.state.period),
      teachers: toParam(UVFilters.state.teacher),
      // 全局参数透传：分享页继承当前所有筛选条件
      branch: toParam(UVFilters.state.branch),
      year: toParam(UVFilters.state.year),
      season: toParam(UVFilters.state.season),
      course_type: toParam(UVFilters.state.course_type),
      class_mode: toParam(UVFilters.state.class_mode),
      grade: toParam(UVFilters.state.grade),
    };
    const result = await UVApi.generateShare(params);
    if (result && result.share_id) {
      const url = `${window.location.origin}/share-view/${result.share_id}`;
      window.open(url, '_blank');
    }
  },
};
