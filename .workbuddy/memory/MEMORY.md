# UV Dashboard 2.0 项目约定

## 系统架构
- 1.0 端口5100 `uv-dashboard/`；2.0 端口5200 `uv-dashboard-2.0/`（launchd `com.uv.dashboard2` 自动 respawn，重启 `launchctl kickstart -k gui/$(id -u)/com.uv.dashboard2`）。
- **⚠️ Python `__pycache__` 缓存坑**：launchd 重启后 Python 仍可能加载旧 `.pyc` 缓存。每次修改 Python 源码后必须先执行 `find "项目路径" -type d -name __pycache__ -exec rm -rf {} +` 清除缓存，再 `launchctl kickstart` 重启，否则旧代码仍生效。
- **⚠️ launchd 真正重启用 `SIGTERM`**：`kickstart -k` 偶尔 PID 不变（进程不退），代码修改不生效。务必用 `launchctl kill SIGTERM gui/$(id -u)/com.uv.dashboard2` 再 `launchctl list | grep` 确认 PID 变化。
- **⚠️ 双 DB 路径陷阱**：开发模式下 `data_dir = RESOURCE_DIR`，即 `/Users/wangboning/WorkBuddy/2026-06-29-13-19-59/uv-dashboard-2.0/uv_dashboard.db`；打包模式用 `~/Library/Application Support/UV Dashboard 2.0/uv_dashboard.db`。手动跑 `repository.rebuild_active_run()` 须先 `set_data_dir()` 指向正确路径（否则会写错 DB）。
- 数据库物理隔离：1.0=`uv-dashboard/uv_dashboard.db`；2.0=`uv-dashboard-2.0/uv_dashboard.db`（2026-07-13 拆分）。**严禁** 2.0 `data_dir` 指回 `../uv-dashboard`（会重新污染两系统 pin）。各自独立 pin。
- **⚠️ Python 3.9.6 ≠ 3.13.12**：`/Users/wangboning/.workbuddy/binaries/python/envs/default/bin/python` 实际是符号链接到系统 Python 3.9.6（不是 3.13.12），所以 `python --version` 显示 3.9.6。手算、构建均用此版本。

## 不可违反核心规则
- 全局分校默认=全选（空列表=不筛），禁锁单城市（曾因默认 `branch=['广州']` 隐藏深圳数据）。
- 退费UV逐期独立：每学员每期次全科目退费计该期次退费UV；总退费UV按全局无在读科目。
- 教学点标准化：去"教学点"后缀；`K9广州分校`→`广州`。
- 期次"无"=秋/春季学期（期次仅存暑/寒短学期）。
- E列渠道来源从原台帐按uid继承，禁自动推断。
- 学员多班：同一科目可有多笔订单行（不同 class_id/期次/时间），学员详情须展示全部班级行（subjects_raw 未折叠），不可折叠成单班。
- 学员详情须**按学季作用域过滤**：下钻时传 `?season=`，后端 `get_student_detail_enhanced` 仅返回该学季且 status 含「在读」的班级行（避免跨学季混排错乱）。无 season 时返回全部学季（向后兼容）。班级详情 `get_class_detail` 返回 `season` 字段；前端 `openStudentDetail(uid, season)` 显式优先，否则 `UVFilters.currentSeason()` 取单学季，多学季选→全学季。学员多班行归属须与当前筛选学季一致。
- **班级详情续报标签**：必须以 `subjects_json` 原始行中 `class_id` 完全匹配的那一行计算（`status/continue_fall/fall_pay_time/period/start_date`），禁止用 `display_subjects` 折叠后的学科行（折叠会取错班级）。班级头部年级取自该班匹配行的 `grade`。`get_class_detail` 返回 `'grade'` 与每个学员的 `'grade'`。
- **班级详情搭班老师**：学员名单中的「搭班老师」必须按当前班级所属学季过滤，仅展示该学员与当前班级同季且 status 含「在读」的其他科目老师。禁止用 `display_subjects` 折叠后的学科数据（会跨季取错行），应从原始 `subjects_json` 行按 `season` + `status` + 科目匹配计算。
- **班级详情统计指标按课程类型区分**：特惠课班级详情展示 6 项——在读 / 应续 / 当期转化 / 已续费 / 转化率 / 续报率；系统课（及未知）展示 5 项——在读 / 已续报 / 续报率 / 退费 / 退费率。后端 `get_class_detail` 返回 `refund_count`（status 含「退」）与 `refund_rate`（退费 / 班级总人数 total）；前端 `uv-modal.js` 按 `course_type` 分支渲染。退费率颜色阈值：≥15% 红 / ≥5% 黄 / 低绿。
- **续报标签按课程类型(K列 course_type)区分**：仅**特惠课**存在转化细分（开课前续报/当期转化/已续报/未续报）；**系统课**（及未知）一律只显示 已续报/未续报，忽略 pre/new。前端 `uv-modal.js` 用 `_uvRenewalKind(isR,rCls,isActive,courseType)` 统一三处续报渲染；后端 `_renewal_label(cf,cls,course_type='')` 同样处理；班级详情/学员详情取 `course_type` 判定。

## 数据真相源与口径
- 新真相源=`订单明细(…)*.xlsx`（订单级粒度）；按 学生uid(跨分校唯一)+城市分校 合并全国。顾问主口径=`成单归属人`。
- **跨学季续报口径**：同uid同科目在 S 与 next_season(S) 均在读即续报人员；pre/new 用「下学季同名订单支付时间」vs「当前学季开课日(该学季全部行最早class_start)」判定（支付日<开课日=pre，否则new；无支付时间保守归pre）。SEASON_CYCLE=[寒,春,暑,秋]。数据层 `enrich_cross_season_renewal` 写 continue_fall/fall_pay_time/start_date，下游零改动自动正确。**坑**：跨学季重叠不要求下学季有支付时间才标续报（用户原则"重复即续报人员"），仅 pre/new 分类依赖支付时间。
- **⚠️ 续报配对必须「年份+学季」精确向后（防时间倒挂）**：`enrich_cross_season_renewal` 原仅按学季名配对（`秋季`→`寒假`），导致秋季Y误接回**同年的寒假Y**（如秋季2026↔寒假2026，1月早于9月，属过去冬季）而错误计续报。修正后配对单位为 `(year,season)`：`_next_year_season` = 寒假Y→春季Y→暑假Y→秋季Y→**寒假(Y+1)**。即秋季Y的下一季必须是次年寒假(Y+1)；若数据里尚无次年冬季（如当前仅2026全年），秋季Y续报应为0。改逻辑后须用脚本对全量 run 重算写回 `subjects_json`（见 2026-07-14 日志）。当前激活 run=`od_20260714_200845`。
- **拉新判定(B方案)**：直接取源表「订单来源[新绩效类型]」=拉新（不推导老生）。月份归属：PV=订单pay_time月份；UV=学员在S内最早拉新订单pay_time月份。
- **单管道+分校隔离**（2026-07-20 重构）：全量上传为**唯一数据源**，`import_to_production` 直接 `set_current_run_id(run_id)` pin（不再调 `rebuild_active_run`）。校准管理降级为**纯校准**（只输出报告，不写学员快照、不设 overlay、不 merge）。分校隔离：`import_to_production` 中 `kept_from_old_base` 保留非本次分校学员，本次分校完全替换。`save_calibration_metadata()` 只写 calibration_runs 元数据。
- **⚠️ subjects_json 两种格式**：新格式（2.0 loader 产出）键名如 `"雪球思维#0"`，含 year/season/grade/course_type/product_type/class_mode 等完整行级字段；旧格式（1.0 loader 产出）键名如 `"雪球思维"`（无 #suffix），仅含 class_id/teacher/room/time_slot/class_type/period/status/continue_fall/fall_pay_time，**缺少**行级字段。`_merge_rows()` 已增强：重叠 UID 时若 overlay 旧格式且 base 新格式则保留 base 的 subjects_json；校准独有 UID 若旧格式则 `_upgrade_old_subjects()` 从 student_row 推断缺失字段。
- **⚠️ 旧格式升级必须补全 status/period 兜底**（2026-07-16 修复）：`_upgrade_old_subjects()` 原只补 subject/class_mode/season/grade，但**不补空 status 和空 period**。引擎行级判断 `is_active = '在读' in status` 在 status="" 时为 False → 整行被 continue（导致旧格式学员 total_uv=0）；矩阵行级 `plist = period.split('/')` 在 period="" 时为空 → 整行被 continue（教学点×期次矩阵不显示该学员）。**修复**：升级时 `if not status.strip(): line['status'] = '在读'`；`if not period.strip(): line['period'] = '一期'`（短学期兜底，矩阵需此字段）。
- **⚠️ engine 筛选「已知才排除」策略**：course_type/product_type/year 筛选时，若行无该字段值则不剔除（避免旧格式数据被全量排除）；class_mode 因有 class_type 兜底推断故仍严格匹配。season/grade 从行级取值，缺失时回退到学员级。**分享端点 grade 过滤也采用此策略**（空值不排除）。

## 前端约定
- 4主Tab(数据看板/数据明细/校准管理/运行监控)+3子Tab(期次矩阵/排班看板/学员检索)。全多选筛选器空Set=全选，部分选中发 comma-separated。
- **全局筛选栏（2026-07-17 两 tier 不联动/联动）**：单一全局 state，**第一排 6 项固定不联动**（始终展示全量值）—— `['year','branch','season','subject','course_type','class_mode']`；**第二排 7 项联动收窄**（仅展示有值的可筛选项）—— `['grade','period','teaching_point','teacher','class_type','enrollment_status','renewal_status','student_type']`。`UVFilters._optionsForId(id)` 第一排字段**跳过 faceted**（永远展示全量），第二排走 faceted 联动。`UVFilters.state` 为扁平对象（14 个 Set 字段 + keyword），所有页面共用。`UVFilters.buildParams()` 无需 section 参数；`UVFilters.buildParams({includeKeyword:true})` 仅学员检索用；`UVFilters.currentSeason()` 取单学季或 null。
- **⚠️ 全局筛选器 default 全部为空**（2026-07-17 修复）：branch/grade/season 等以前 `default='广州'/'初一'/'暑假'` 会锁单城市/年级/学季，导致深圳学员看不到。修复方式：FILTER_CONFIG 全部 default='' + `_setDefaultSet` 不读 default + `state.branch=new Set()` 默认空 = 全选（不锁单）。
- **「学员归属」字段（2026-07-17 新增）**：取自订单明细 BS 列「订单来源[新绩效类型]」（不是 Excel 的"学员归属"列，Excel 没此列）。映射：拉新→新生 / 老生→老生 / 续报扩科→老生拓科。`engine.order_detail_loader._map_student_type()` 转换 + 写入 subjects_json 行级 `student_type` 字段。engine 行级过滤 + get_filtered_students 多选过滤 + get_filter_options 收集选项。
- **⚠️ student_type 学员级聚合 + 优先级去重**（2026-07-17 修复）：同一学员多班级行 student_type 可能不同（696 学员多归属），行级过滤跨 set 重复计数。修复为**学员级聚合**：聚合时按优先级去重（老生拓科 > 老生 > 新生）。行级 3224 → 学员级 2452 ≈ 全局 2450。
- **⚠️ 学员检索 season 过滤用行级优先**（2026-07-17 修复）：`get_filtered_students` 原用学员级 season 过滤，与 stats API（行级）口径不一致。改为行级 season 优先 + 学员级 fallback。
- **⚠️ 教学点标准化与 DB 一致性**（2026-07-17 修复）：`normalize_teaching_point` 把「新宝利」→「新宝利大厦」「天成」→「天成大厦」，但 DB 学员级 teaching_point 列仍存旧值。需 SQL 迁移学员级字段。
- **⚠️ advisor-list 必须传 subject**（2026-07-17 修复）：`api_overview_advisor_list` 原 `FilterSpec.from_params` 没传 `subject` 参数，导致 subject 过滤失效（advisor UV 比 stats 多 112 学员）。已修复。
- **⚠️ data cards 双轨维度（2026-07-17）**：数据卡片底部小 chip 之前硬编码 5 个寒暑假期次（零/一/二/三/四），春秋长学期显示全 0。改造为：
  - `engine` 拆分 `by_period`（短学期期次）+ `by_weekday`（长学期星期，从 `week_cycle` 归一化）
  - `period_config.term_type`: 'short_term' / 'long_term' / 'mixed' / 'empty'
  - `period_config.chip_display`: 'short_chips' / 'short_only' / 'none'（春秋不显示小字）
  - 只输出**实际有数据**的 keys（按分校/按筛选动态），不补齐 0 值
  - 前端根据 chip_display 渲染：none→不渲染，short_chips/short_only→按 by_period 实际 keys 渲染
  - `config.WEEKDAY_ORDER = ['周一', '周二', ..., '周日']`、`norm_weekday()` 工具函数
- **⚠️ norm_class_mode 严格归一**（2026-07-17）：`norm_class_mode` 只接受 `k9班课` / `k9一对一`（→'班课' / '1v1'），其他值（含脏数据如"潜能班"误填 M 列）视为空，避免污染 class_modes 集合。
- **⚠️ 分享功能全局筛选参数透传（2026-07-16 修复）**：`updateShareCard()` 和 `generateShare()` 必须完整透传全局 state 的所有筛选维度（branch/year/season/course_type/class_mode/grade），否则分享卡片/页面数据口径与主看板不一致。后端 `/api/share-card` 和 `/api/share/generate` 均已支持 grade 参数（采用「已知才排除」策略）。
- **⚠️ 全局"产品类型"=class_mode(班课/1v1)，非 product_type(转化品/正价品)**：数据层两字段并存（`product_type`=J列转化品/正价品；`class_mode`=M列班课/1v1）。为让单一全局 产品类型 联动所有页面，全局栏统一映射到 `class_mode`（`_fieldForSection(sec,'product_type')`→`class_mode`），下拉选项 `UVFilters.options.class_modes`。各板块 `buildParams` 现均 emit `class_mode`（dashboard/matrix/schedule/trends 原已正确；teacherBoard/advisorBoard/student/trends 已补）。后端 `/api/trends/data` 与 `/api/overview/acquisition-trends` 均透传 `class_mode`。若用户想要 转化品/正价品 作为全局 产品类型，需反转映射并同步 matrix/schedule 后端，改动更大——当前实现与"联动所有页面"最一致。
- 排班看板：期次/教学点 chips(带总班量)+主讲/学科/班型多选；卡片左侧学科色条；API两遍遍历(先收集选项+班量不受筛选，再筛选构建)。
- **排班卡片标签规范**：课程类型（K列 course_type：特惠课/系统课）与产品类型（M列 class_mode：班课/1v1）必须在卡片右上角标签区展示；布局顺序为「学季×期次徽章 → 课程类型+产品类型横向并置 → 班型阶梯 pill 独占一行」，用色统一：特惠课暖橙、系统课冷蓝、班课青绿、1v1 紫，均使用淡底描边 pill，不与班型实心阶梯 pill 冲突。`get_class_schedule` 返回的班级对象须包含 `course_type` 与 `class_mode`。`uv-config.js` 中统一用 `courseTypePill()` / `classModePill()` 生成。`uv-app.js renderClassCards` 为唯一渲染入口。
- 学员详情弹窗：每科目渲染 `subjects_raw` 多班级行(class_id/期次/时间/教室/续报)，仅显示当前学季作用域内班级（弹窗顶部「学季作用域：X」徽标）。
- Chart.js 用 UMD `chart.umd.min.js`(ESM会报import错误)；主色#4F6BED；图表标签防遮挡用 beforeUpdate 插件算 bar 峰值(堆叠按index累加)设 `scales.y.max=_niceMax(峰值*1.15)`，不靠 suggestedMax；百分比轴y1(已max=100)跳过。验证用 Node+jsdom+chart.js+canvas桩读 `chart.scales.y.max`，无需浏览器。

## 打包/导出/回滚
- 打包数据目录=~/Library/Application Support/UV Dashboard 2.0；PyInstaller 6.21.0，spec `uv_dashboard.spec`。
- Excel导出 `/api/overview/export`(POST，三处按钮)；校准回滚 `/api/runs/pin` + header「📌 已回溯至历史基线」。

## 已知遗留
- 期次矩阵仅覆盖暑期限次，秋/春/寒进总量未入矩阵；京/沪表到齐做三校合并；FilterSpec 扩~19项+指标改用原生字段(Phase 3-5)。
- 当前生产激活 run=`merged_20260717_112044`（广州1233+深圳1217合并，2450学员，BS列已落库；新生718/老生809/老生拓科269；学员归属筛选器全链路工作）。
