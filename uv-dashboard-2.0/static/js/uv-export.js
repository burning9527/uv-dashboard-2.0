/* ═══════════════════════════════════════════════════
   UV Dashboard 2.0 — 数据导出 + 轻量 Toast
   导出学员明细 / 期次矩阵 / 排班看板为 Excel
   ═════════════════════════════════════════════════════ */

/* ── 轻量 Toast（全局，供导出与回滚操作共用）── */
const UVToast = {
  _el: null,
  _timer: null,
  _ensure() {
    if (this._el) return this._el;
    let el = document.getElementById('uv-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'uv-toast';
      el.className = 'uv-toast';
      document.body.appendChild(el);
    }
    this._el = el;
    return el;
  },
  show(msg, type = 'info') {
    const el = this._ensure();
    el.textContent = msg;
    el.className = 'uv-toast show ' + type;
    if (this._timer) clearTimeout(this._timer);
    this._timer = setTimeout(() => {
      el.className = 'uv-toast ' + type;
    }, 2600);
  },
};

// 全局便捷函数
function showToast(msg, type) { UVToast.show(msg, type); }

/* ── 导出控制器 ── */
const UVExport = {
  _download(response, fallbackName) {
    if (!response || !response.ok) {
      UVToast.show('导出失败，请重试', 'error');
      return;
    }
    response.blob().then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      // 优先用后端 Content-Disposition 的文件名（优先 filename* 的 UTF-8 名称）
      const disp = response.headers.get('Content-Disposition') || '';
      let name = fallbackName;
      const star = disp.match(/filename\*=(?:UTF-8'')?["']?([^"';]+)/i);
      if (star) {
        name = decodeURIComponent(star[1].replace(/\+/g, ' '));
      } else {
        const plain = disp.match(/filename=["']?([^"';]+)/i);
        if (plain) name = plain[1];
      }
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      UVToast.show('导出成功', 'success');
    }).catch(() => UVToast.show('导出失败', 'error'));
  },

  _ts() {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`;
  },

  async exportStudents() {
    const filters = UVFilters.buildParams({ includeKeyword: true });
    const resp = await UVApi.exportExcel({ export_type: 'students', filters });
    this._download(resp, `学员明细_${this._ts()}.xlsx`);
  },

  async exportMatrix() {
    const params = UVFilters.buildParams();
    const resp = await UVApi.exportExcel(Object.assign({ export_type: 'matrix' }, params));
    this._download(resp, `期次矩阵_${this._ts()}.xlsx`);
  },

  async exportSchedule() {
    const params = UVFilters.buildParams();
    const resp = await UVApi.exportExcel(Object.assign({ export_type: 'schedule' }, params));
    this._download(resp, `排班看板_${this._ts()}.xlsx`);
  },
};
