/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — 防遮挡数据标签插件 (uv-chart-labels.js)
   从 1.0 分享页 dataLabelPlugin 抽取为可复用模块，主题化以适配 2.0 浅色 UI。
   特性：
   - 自动收集所有数据标签（柱内段标签 / 柱顶标签 / 折线标签）
   - 按优先级放置，碰撞时自动 flip / shift，无法避让则跳过
   - 支持浅色/深色主题（theme: 'light' | 'dark'），自动读取 dataset 颜色
   用法：
     new Chart(ctx, {
       ...,
       plugins: [UVChartLabels.dataLabelPlugin],
       options: { plugins: { uvDataLabels: { theme: 'light', fontFamily: '...' } } }
     });
   ═══════════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';

  function _roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  function hexRgba(hex, a) {
    if (!hex || typeof hex !== 'string' || !hex.startsWith('#')) return `rgba(100,100,100,${a})`;
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${a})`;
  }

  // 向上取"nice"数：找到不小于 target 的最小规整刻度上界
  // （刻度能被 Chart.js 默认 tickCount 整除，避免奇怪的网格间隔）
  function _niceMax(target) {
    if (target <= 0) return target;
    const exp = Math.floor(Math.log10(target));
    const step = Math.pow(10, exp - 1); // 数量级小一阶的步长
    return Math.ceil(target / step) * step;
  }

  const dataLabelPlugin = {
    id: 'uvDataLabels',

    // 布局层面根治：在 Y 轴刻度计算完成后给 max 追加顶部留白，
    // 保证最高柱顶的标签也不会被绘图区顶部裁切。
    // 仅对未显式设 max 的线性 Y 轴生效（百分比轴 y1 已设 max=100，自动跳过）。
    // 布局层面根治：在轴计算前直接写入 Y 轴 max（显式值 Chart.js 必然采用，
    // 不像 suggestedMax 会被再次 nice 取整覆盖），给最高柱顶标签预留顶部空间，
    // 保证标签不会被绘图区顶部裁切。
    // 仅对未显式设 max 的 y 轴生效（百分比轴 y1 已设 max=100，自动跳过）。
    beforeUpdate(chart) {
      const opts = (chart.options && chart.options.scales) || {};
      const y = opts.y;
      if (!y || y.display === false) return;
      if (y.max !== undefined && y.max !== null) return; // 用户已显式设 max 不干预

      const dsList = chart.data.datasets || [];
      const isStacked = !!(opts.x && opts.x.stacked === true);
      const labels = chart.data.labels || [];
      let dataMax = 0;
      if (isStacked) {
        labels.forEach((_, bi) => {
          let sum = 0;
          dsList.forEach(d => {
            if ((d.type || chart.config.type) !== 'bar') return;
            const v = d.data ? d.data[bi] : null;
            if (v != null && !isNaN(v)) sum += v;
          });
          if (sum > dataMax) dataMax = sum;
        });
      } else {
        dsList.forEach(d => {
          if ((d.type || chart.config.type) !== 'bar') return;
          (d.data || []).forEach(v => {
            if (v != null && !isNaN(v) && v > dataMax) dataMax = v;
          });
        });
      }
      if (dataMax <= 0) return;

      const reserve = (chart.options.plugins && chart.options.plugins.uvDataLabels
        && chart.options.plugins.uvDataLabels.topReserve) || 0.15;
      y.max = _niceMax(dataMax * (1 + reserve));
    },

    // 用 afterDraw 而非 afterDatasetsDraw：确保标签在轴线（grid/axes）之上绘制。
    // 标签位置已由 beforeUpdate 的留白保证落在绘图区内，无需取消 clip 画到区外。
    afterDraw(chart) {
      const ctx = chart.ctx;
      const area = chart.chartArea;
      if (!area) return;

      const opt = (chart.options.plugins && chart.options.plugins.uvDataLabels) || {};
      const theme = opt.theme || 'light';
      const fontFamily = opt.fontFamily ||
        '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif';
      // 浅色主题：白底标签 + 彩色文字；深色主题：深底标签 + 浅色文字
      const lineFill = theme === 'dark' ? 'rgba(22,25,35,0.92)' : 'rgba(255,255,255,0.92)';
      const insideFill = theme === 'dark' ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.92)';

      const isStacked = !!(chart.options.scales && chart.options.scales.x && chart.options.scales.x.stacked === true);
      const hasBar = chart.data.datasets.some(ds => (ds.type || chart.config.type) === 'bar');
      const hasLine = chart.data.datasets.some(ds => (ds.type || chart.config.type) === 'line');
      const isCombo = hasBar && hasLine && !isStacked;

      // 堆叠图中"最上层"柱（柱集合中索引最大的那个）→ 柱顶标注
      const barDs = chart.data.datasets
        .map((ds, i) => ({ ds, i }))
        .filter(o => (o.ds.type || chart.config.type) === 'bar');
      const topBarIndex = barDs.length ? barDs[barDs.length - 1].i : -1;

      const FONT = `600 10px ${fontFamily}`;
      const FONT_SM = `600 9px ${fontFamily}`;
      const FONT_RENEW = `600 11px ${fontFamily}`;

      function mText(text, font) {
        ctx.save();
        ctx.font = font;
        const w = ctx.measureText(text).width;
        ctx.restore();
        return w;
      }

      function boxesOverlap(a, b) {
        return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
      }

      // 数据密度决定折线标签显示策略
      const chartWidth = area.right - area.left;
      const numPts = chart.data.labels ? chart.data.labels.length : 0;
      const pxPerPt = numPts ? chartWidth / numPts : 999;
      function lineLabelIndices(data) {
        const idxs = new Set();
        if (data[0] !== null && data[0] !== undefined) idxs.add(0);
        if (numPts > 1 && data[numPts - 1] !== null && data[numPts - 1] !== undefined) idxs.add(numPts - 1);
        let maxI = 0, minI = 0;
        for (let i = 0; i < data.length; i++) {
          if (data[i] === null || data[i] === undefined) continue;
          if (data[i] > (data[maxI] === null || data[maxI] === undefined ? -Infinity : data[maxI])) maxI = i;
          if (data[i] < (data[minI] === null || data[minI] === undefined ? Infinity : data[minI])) minI = i;
        }
        idxs.add(maxI); idxs.add(minI);
        const step = pxPerPt >= 80 ? 1 : pxPerPt >= 55 ? 2 : pxPerPt >= 40 ? 3 : 4;
        for (let i = step; i < numPts - 1; i += step) idxs.add(i);
        const result = [];
        idxs.forEach(i => {
          if (i >= 0 && i < data.length && data[i] !== null && data[i] !== undefined) result.push(i);
        });
        return result.sort((a, b) => a - b);
      }

      // 收集所有标签
      const allLabels = [];
      let labelId = 0;

      // 1. 堆叠图内部段标签（最上层柱改走柱顶标注，这里跳过）
      if (isStacked) {
        chart.data.datasets.forEach((ds, di) => {
          if (ds.type && ds.type !== 'bar') return;
          if (di === topBarIndex) return;
          const meta = chart.getDatasetMeta(di);
          if (meta.hidden || !meta.data) return;
          meta.data.forEach((bar, bi) => {
            const value = ds.data[bi];
            if (value === null || value === undefined) return;
            const segH = bar.height || Math.abs(bar.y - (bar.base || 0));
            if (segH < 14) return;
            const midY = (bar.y + (bar.base || 0)) / 2;
            const small = segH < 20;
            const font = small ? FONT_SM : FONT;
            const text = String(value);
            const tw = mText(text, font);
            const pad = small ? 4 : 6;
            const cH = small ? 14 : 18;
            const cW = tw + pad * 2;
            allLabels.push({
              id: labelId++, x: bar.x - cW / 2, y: midY - cH / 2, w: cW, h: cH,
              text, font, color: ds.borderColor || '#6C7293', fillColor: insideFill,
              textColor: ds.borderColor || '#6C7293', anchorX: bar.x, anchorY: midY, priority: 1, side: 'inside'
            });
          });
        });
      }

      // 2. 柱顶标签（堆叠图-最上层柱 / 组合图-任意柱）
      chart.data.datasets.forEach((ds, di) => {
        const meta = chart.getDatasetMeta(di);
        if (meta.hidden || !meta.data) return;
        const dsType = ds.type || chart.config.type;
        if (dsType !== 'bar') return;

        // 非堆叠图：所有 bar 都标注（堆叠图在最上层柱标注）
        let isTopBar = false;
        let topColor = '#6C7293';
        let font = FONT;
        let fillColor = 'rgba(100,100,100,0.15)';
        if (!isStacked) {
          isTopBar = true;
          topColor = typeof ds.borderColor === 'string' ? ds.borderColor : (ds.backgroundColor || '#6C7293');
          font = FONT;
          fillColor = hexRgba(topColor, 0.15);
        } else if (di === topBarIndex) {
          isTopBar = true;
          topColor = typeof ds.borderColor === 'string' ? ds.borderColor : (ds.backgroundColor || '#6C7293');
          font = FONT_RENEW;
          fillColor = hexRgba(topColor, 0.15);
        }

        if (!isTopBar) return;

        meta.data.forEach((bar, bi) => {
          const value = ds.data[bi];
          if (value === null || value === undefined || value === 0) return;
          const text = String(value);
          const tw = mText(text, font);
          const pad = font === FONT_RENEW ? 7 : 6;
          const cH = 16;
          const cW = tw + pad * 2;
          const y = bar.y - cH - 3;
          allLabels.push({
            id: labelId++, x: bar.x - cW / 2, y, w: cW, h: cH,
            text, font, color: topColor, fillColor, textColor: topColor,
            anchorX: bar.x, anchorY: bar.y, priority: 2, side: 'above', barTop: true
          });
        });
      });

      // 3.5 饼图/环形图段中心标签（doughnut/pie）
      const arcType = chart.config.type;
      if (arcType === 'doughnut' || arcType === 'pie') {
        const meta = chart.getDatasetMeta(0);
        if (meta && meta.data) {
          const formatter = opt.formatter;
          if (window.__UV_DEBUG_LABELS) {
            console.log('[doughnut labels] opt=', opt, 'formatter=', formatter);
          }
          meta.data.forEach((arc, bi) => {
            const value = chart.data.datasets[0].data[bi];
            if (value === null || value === undefined || value === 0) return;
            const dsLabel = (chart.data.labels && chart.data.labels[bi]) || '';
            const text = typeof formatter === 'function'
              ? formatter(value, { chart, dataIndex: bi, datasetIndex: 0, label: dsLabel })
              : String(value);
            if (!text) return;
            // arc 中心：内点 = 起点 + 终点连线 + 内缩 (1 - innerRadiusRatio) 比例
            // 简化：直接取 arc.x/arc.y 作为中心；doughnut 内部空间靠 cutout 控制
            const cx = arc.x;
            const cy = arc.y;
            // 计算内缩比例（按 cutout，doughnut 默认 0.5）
            const cutout = (chart.options && chart.options.cutout) || 0;
            const cutoutRatio = typeof cutout === 'string' ? parseFloat(cutout) / 100 : cutout;
            const lx = arc.x + (arc.x - arc.x) * 0; // arc 中心即 x/y
            // 用 arc 的 innerRadius / outerRadius 推算内点
            const innerR = arc.innerRadius || 0;
            const outerR = arc.outerRadius || 80;
            const midR = (innerR + outerR) / 2;
            const angle = (arc.startAngle + arc.endAngle) / 2;
            const tx = arc.x + Math.cos(angle) * midR;
            const ty = arc.y + Math.sin(angle) * midR;
            const tw = mText(text, FONT);
            const pad = 4;
            const cH = 14;
            const cW = tw + pad * 2;
            allLabels.push({
              id: labelId++,
              x: tx - cW / 2, y: ty - cH / 2, w: cW, h: cH,
              text, font: FONT, color: '#fff', fillColor: 'rgba(0,0,0,0)',
              textColor: '#fff',
              anchorX: tx, anchorY: ty, priority: 1, side: 'inside',
            });
          });
        }
      }

      chart.data.datasets.forEach((ds, di) => {
        const meta = chart.getDatasetMeta(di);
        if (meta.hidden || !meta.data) return;
        const dsType = ds.type || chart.config.type;
        if (dsType !== 'line') return;
        const lineColor = ds.borderColor || '#6C7293';
        const isRate = ds.label === '续报率 %' || ds.label === '转化率 %';
        const suffix = isRate ? '%' : '';
        const visibleIdxs = (isCombo || isStacked) ? lineLabelIndices(ds.data) : [ds.data.length - 1];

        visibleIdxs.forEach(idx => {
          const value = ds.data[idx];
          if (value === null || value === undefined) return;
          const pt = meta.data[idx];
          if (!pt) return;
          const text = String(isRate ? (+value).toFixed(1) : value) + suffix;
          const tw = mText(text, FONT);
          const pad = 5;
          const cH = 16;
          const cW = tw + pad * 2;
          allLabels.push({
            id: labelId++, x: pt.x - cW / 2, y: pt.y - cH - 6, w: cW, h: cH,
            text, font: FONT, color: lineColor, fillColor: lineFill, textColor: lineColor,
            anchorX: pt.x, anchorY: pt.y, priority: 3, side: 'above', canFlip: true, canShift: true, line: true
          });
        });
      });

      // 碰撞解决：按优先级排序，高优先级先放置
      allLabels.sort((a, b) => a.priority - b.priority || a.id - b.id);
      const placed = [];
      const finalLabels = [];

      allLabels.forEach(lb => {
        let x = lb.x;
        let y = lb.y;
        let w = lb.w;
        let h = lb.h;

        x = Math.max(area.left, Math.min(x, area.right - w));

        function testConflicts(tx, ty) {
          const box = { x: tx, y: ty, w, h };
          return placed.some(p => boxesOverlap(box, p));
        }

        let conflicts = testConflicts(x, y);
        if (conflicts && lb.canFlip && lb.side === 'above') {
          const belowY = lb.anchorY + 8;
          if (!testConflicts(x, belowY)) {
            y = belowY; lb.side = 'below'; conflicts = false;
          }
        }

        if (conflicts && lb.canShift !== false) {
          const shifts = [-18, -12, +12, +18, -26, +26, -34, +34];
          for (const s of shifts) {
            const clampedY = Math.max(area.top + 2, Math.min(y + s, area.bottom - h - 2));
            if (!testConflicts(x, clampedY)) {
              y = clampedY; conflicts = false; break;
            }
          }
        }

        if (conflicts) return;

        y = Math.max(area.top + 2, Math.min(y, area.bottom - h - 2));
        lb.x = x; lb.y = y;
        placed.push({ x, y, w, h });
        finalLabels.push(lb);
      });

      // 绘制所有标签
      finalLabels.forEach(lb => {
        ctx.save();
        ctx.font = lb.font;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        _roundRect(ctx, lb.x, lb.y, lb.w, lb.h, 6);
        ctx.fillStyle = lb.fillColor;
        ctx.fill();
        ctx.strokeStyle = lb.color;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.fillStyle = lb.textColor;
        ctx.fillText(lb.text, lb.anchorX || (lb.x + lb.w / 2), lb.y + lb.h / 2);
        ctx.restore();
      });
    }
  };

  const UVChartLabels = { dataLabelPlugin };
  global.UVChartLabels = UVChartLabels;
  // 兼容 share_page 风格引用（避免漏改导致 ReferenceError）
  global.dataLabelPlugin = dataLabelPlugin;
})(window);
