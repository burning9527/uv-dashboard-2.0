/* ═══════════════════════════════════════════════════════════════
   UV Dashboard 2.0 — API客户端
   统一的fetch wrapper，所有前端模块通过此模块调用后端API
   ═══════════════════════════════════════════════════════════════ */

const UVApi = {
  // ── 通用fetch ──
  async fetch(url, opts = {}) {
    try {
      const resp = await fetch(url, { ...opts, headers: { 'Content-Type': 'application/json', ...opts.headers } });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return resp.json();
    } catch (err) {
      console.error(`UVApi.fetch error: ${url}`, err);
      if (typeof showToast === 'function') showToast('数据加载失败，请检查网络', 'error');
      return null;
    }
  },

  // ── Overview Stats ──
  getStats(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.fetch(`${UVConfig.endpoints.stats}?${qs}`);
  },

  // ── Matrix ──
  getMatrix(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.fetch(`${UVConfig.endpoints.matrix}?${qs}`);
  },

  // ── Filter Options ──
  getFilters() { return this.fetch(UVConfig.endpoints.filters); },

  // ── Teacher ──
  getTeacherList(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.fetch(`${UVConfig.endpoints.teacherList}?${qs}`);
  },
  getTeacherDetail(name, params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.fetch(`${UVConfig.endpoints.teacherDetail}${encodeURIComponent(name)}?${qs}`);
  },

  // ── Advisor ──
  getAdvisorList(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.fetch(`${UVConfig.endpoints.advisorList}?${qs}`);
  },
  getAdvisorDetail(name, params = {}) {
    const qs = new URLSearchParams(params).toString();
    const url = qs ? `${UVConfig.endpoints.advisorDetail}${encodeURIComponent(name)}?${qs}` : `${UVConfig.endpoints.advisorDetail}${encodeURIComponent(name)}`;
    return this.fetch(url);
  },

  // ── Student ──
  getStudentDetail(uid, season = '') {
    const qs = season ? `?season=${encodeURIComponent(season)}` : '';
    return this.fetch(`${UVConfig.endpoints.studentDetail}${uid}${qs}`);
  },
  searchStudents(filters = {}) {
    return this.fetch(UVConfig.endpoints.students, { method: 'POST', body: JSON.stringify(filters) });
  },

  // ── Schedule/Classes ──
  getClasses(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.fetch(`${UVConfig.endpoints.classes}?${qs}`);
  },
  getClassDetail(classId) {
    return this.fetch(`${UVConfig.endpoints.classDetail}${classId}`);
  },

  // ── Trends ──
  getTrends(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.fetch(`${UVConfig.endpoints.trends}?${qs}`);
  },

  // ── Acquisition Trends (拉新×续报转化月度) ──
  getAcquisitionTrends(params = {}) {
    const qs = new URLSearchParams(params).toString();
    const url = qs ? `${UVConfig.endpoints.acquisitionTrends}?${qs}` : UVConfig.endpoints.acquisitionTrends;
    return this.fetch(url);
  },

  // ── Channel Acquisition (拉新渠道×转化效率) ──
  getChannelAcquisition(params = {}) {
    const qs = new URLSearchParams(params).toString();
    const url = qs ? `${UVConfig.endpoints.acquisitionByChannel}?${qs}` : UVConfig.endpoints.acquisitionByChannel;
    return this.fetch(url);
  },

  // ── Share ──
  getShareCard(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.fetch(`${UVConfig.endpoints.shareCard}?${qs}`);
  },
  generateShare(params = {}) {
    return this.fetch(UVConfig.endpoints.shareGenerate, { method: 'POST', body: JSON.stringify(params) });
  },

  // ── Runs ──
  getRuns() { return this.fetch(UVConfig.endpoints.runs); },
  getRunDetail(id) { return this.fetch(`${UVConfig.endpoints.runDetail}${id}`); },
  getRunChanges(id) { return this.fetch(`${UVConfig.endpoints.runDetail}${id}/changes`); },
  getDailyStats() { return this.fetch(UVConfig.endpoints.dailyStats); },

  // ── Export ──
  // 返回原始 fetch Response（便于取 blob 下载）
  exportExcel(params = {}) {
    return fetch(UVConfig.endpoints.export, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }).catch(err => { console.error('Export error:', err); if (typeof showToast === 'function') showToast('导出失败，请检查网络', 'error'); return null; });
  },

  // ── Pin run (回滚/设为当前基线) ──
  pinRun(runId) {
    return this.fetch(UVConfig.endpoints.pinRun, {
      method: 'POST',
      body: JSON.stringify({ run_id: runId || '' }),
    });
  },

  // ── Calibrate ──
  calibrate(formData) {
    return fetch(UVConfig.endpoints.calibrate, { method: 'POST', body: formData })
      .then(r => r.json())
      .catch(err => { console.error('Calibrate error:', err); if (typeof showToast === 'function') showToast('校准请求失败，请稍后重试', 'error'); return null; });
  },

  // ── 全量数据上传（订单明细 → 合并基线 base）──
  uploadFull(formData) {
    return fetch(UVConfig.endpoints.uploadFull, { method: 'POST', body: formData })
      .then(r => r.json())
      .catch(err => { console.error('UploadFull error:', err); if (typeof showToast === 'function') showToast('全量上传失败，请稍后重试', 'error'); return null; });
  },

  // ── 手动重新合并（base 全量 + overlay 校准）──
  rebuild() {
    return this.fetch(UVConfig.endpoints.rebuild, { method: 'POST' })
      .catch(err => { console.error('Rebuild error:', err); if (typeof showToast === 'function') showToast('重新合并失败，请稍后重试', 'error'); return null; });
  },

  // ── Download ──
  downloadUrl(runId, fileType) {
    return `${UVConfig.endpoints.download}${runId}/${fileType}`;
  },
};
