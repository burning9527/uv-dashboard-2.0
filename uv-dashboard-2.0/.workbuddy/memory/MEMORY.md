# UV 2.0 系统 — 数据标签防遮挡插件约定

## 防遮挡数据标签（重要）

- **统一插件**: `static/js/uv-chart-labels.js` 导出 `UVChartLabels.dataLabelPlugin`（从 1.0 分享页 `dataLabelPlugin` 抽取，主题化）。
- **替代方案**: 不再使用 `chartjs-plugin-datalabels` CDN（已从 `index.html` 移除）。所有 2.0 图表的柱/线数据标签统一用此插件，自动碰撞避让。
- **用法**: 图表 config 加 `plugins:[UVChartLabels.dataLabelPlugin]`，并在 `options.plugins.uvDataLabels = { theme:'light'|'dark', fontFamily }` 配置主题。
  - `theme:'light'`（2.0 主 UI，白底标签 + 彩色文字）/ `theme:'dark'`（分享页 1.0 复刻，深底标签）。
- **行为**: 堆叠图→非顶层段内部居中标签 + 顶层段柱顶标签；组合图→所有柱柱顶标签；折线标签按数据密度抽样 + 碰撞时 flip/shift。自动读取 `ds.borderColor` 着色。
- **加载顺序**: `index.html` 在 chart.js UMD 之后、`uv-trends.js` 之前加载 `uv-chart-labels.js`。

## 分享页生成（1.0 复刻）

- 前端 `UVTrends.generateShare()` 发送 `subjects/teaching_points/periods/teachers`（Set→逗号串，空=全选），对应后端 `/api/share/generate`。
- 分享页模板 `templates/share_page.html` 为 1.0 暗色主题完整复刻，内嵌自有 `dataLabelPlugin`（id `dataLabels`，dark），含拉新/续报转化月度图表（`acqNewChart`/`acqConvChart`）。
- 生成的分享文件存 `static/shares/<id>.html`，经 `/share-view/<id>` 访问。
