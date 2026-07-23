# UV Dashboard 2.0 数据基建升级方案

> 真相源由「招生明细」切换为「订单明细」｜草稿 v1（2026-07-13）
> 状态：**6 项待确认已全部确认，可进入 Phase 0–2 实现**。

---

## 0. 决策回顾（已拍板）

| # | 决策 | 系统影响 |
|---|---|---|
| 1 | **分校 = 各独立明细表** | 升级需做「合并导入层」：以 `学生uid(归一化)` + `城市分校` 为键，合并广州/深圳/北京/上海为全国统一数据 |
| 2 | **含退费直接用** | 退费学员纳入看板；退费率改用表原生 `是否课前/课后有效退费`、`是否有效退费` 标记（**取代**旧"按开课首日自算"算法） |
| 3 | **顾问主口径 = 成单归属人** | 顾问看板/排行/分享卡片主口径切到 `成单归属人`；其余 4 角色保留为可选维度 |
| 4 | **全学季 + 全年级** | 学季、年级进筛选器，默认不锁定（空选=全集） |

---

## 1. 新数据源画像：订单明细表

- 文件：`订单明细(…)_20260713_122429.xlsx`（Downloads）
- 结构：单 sheet，**4336 数据行 × 113 列**，有效约 **94 列**；末尾 19 列为空（col 95–113）。
- **粒度 = 学员 × 科目 × 订单**（同一学员报多科、或联报/续报产生多子订单 → 多行）。`学生uid(归一化)` 唯一值 1232，`子订单ID` 唯一值 4336。
- 当前仅含 `城市分校 = K9广州分校`（决策①要求补深/京/沪表后合并）。

### 关键维度取值（已实测）
| 维度 | 取值 |
|---|---|
| 城市分校 | K9广州分校（唯一） |
| 教学点 | 新宝利大厦/天成大厦/同创汇/龙晖大厦（4） |
| 学科 | 雪球思维 / 雪球科学 / 双语素养 / 悦读创作（4） |
| 学季 | 暑 / 秋 / 春 / 寒（4） |
| 期次 | 零期 / 一期 / 二期 / 三期 / 无（5） |
| **期次="无" 释义** | **本质=秋季/春季学期**。期次（零/一/二/三）是暑、寒短学期专属概念；秋、春是长学期，无期次细分，故标"无"。加载时需按 `学季` 还原：秋+"无"→秋季、春+"无"→春季（见 §3 period_combined / §7 聚合规则）。 |
| 班级年级 | 初三/初二/五年级/初一/四年级/三年级/六年级/一年级（8） |
| 学校年级 | 上述 + 高一 / 大班（11） |
| 班型 | 潜能 / 源能 / 启能 / 超能（4） |
| 课程类型 | 系统课 / 特惠课；课程模式：k9班课 / k9一对一 |
| 产品类型 | 正价品 / 转化品 |
| 班级主讲 | 31 人（覆盖全年级全学季，远超旧表 10 人） |
| 顾问角色 | 商机创建人 / 成单商机跟进人 / 订单商品码归属人 / 成单归属人 / 课程跟进顾问（各含 uname 系统账号） |
| 渠道 | 线索一级(5)/二级(15)、商机一级(5)/二级(15) |
| 订单来源[新绩效] | 老生 / 拉新 / 续报扩科 |
| 做工归属 | 上季续报 / 隔季续报 / 拉新 / 上季扩科 / 隔季扩科 / 续报扩科 |
| 公立校名称 | 105 所学校 |
| 退费原因分类 | 用户/课程调整/其他/课程内容/竞争/主讲/分校其他/价格（8） |

### 字段标签问题（必须在导入层清洗）
1. **拼写错误**：`商机创建人uanme`、`成单商机跟进人uanme`、`订单商品码归属人uname` → 规范为 `…uname`。
2. **尾部空列**：col 95–113 全空，丢弃。
3. **100% 空字段**：`订单来源(从暑开始算…)`、`暑专项体验是否续暑系统`、`暑专项体验是否续秋系统`、`是否联报` → 丢弃。
4. **常量列**（单一值，不进筛选器，作固定上下文）：业务线=K9、梯队=T0、学年=2026、分期=不分期、分校大区=三区、是否是团培班级=0、是否首次正续正=0。
5. **归一化**：`城市分校` 值 `K9广州分校` → 剥离前缀为 `广州`；`教学点` 去 `教学点` 后缀（沿用旧规则）。

---

## 2. 现有数据模型（student_snapshots，需扩展）

当前 schema（已在库，后迁移加了 `branch/grade/season`）：

```
uid, name, teaching_point, advisor, channel, status,
period_combined, subjects_json(JSON), manual_json(JSON),
branch, grade, season
```

`subjects_json` 是**学员×科目**核心：每学科子结构含 `period / teacher / status / class_type / class_id / room` 等。
看板所有指标（UV/PV、续报、退费）都从 `subjects_json` + 顶层列派生。

**升级结论**：保留 `subjects_json` 作为学科级主干，在其子结构内**扩展**新字段；新增一个 `enrich_json` 列承载学员级新增维度（多顾问角色、渠道四级、金额、退费布尔、续报布尔、公立校、hash、出勤等），避免频繁 ALTER TABLE。

---

## 3. 字段映射表（订单明细 → 系统模型）

> 列号指新表从 1 起的列序。`subjects_json.<f>` = 学科子结构字段；`enrich_json.<f>` = 学员级扩展字段。

| 系统目标字段 | 来源（新表列） | 转换规则 |
|---|---|---|
| `uid` | 92 学生uid(归一化) | 直接（**已确认跨分校唯一**，合并层按 uid 聚合安全） |
| `name` | 27 学生姓名 | 直接 |
| `branch` | 3 城市分校 | `K9广州分校`→`广州`（按分校表各自剥离前缀） |
| `teaching_point` | 4 教学点 | 去"教学点"后缀 |
| `grade` | 16 班级年级（**已确认**：用班级年级，非学校年级） | 决策：班级年级 |
| `season` | 7 学季 | 暑/秋/春/寒 → 映射 暑假/秋/春/寒（沿用旧 season 词表） |
| `advisor`（主） | 35 成单归属人 | 决策③ |
| `channel` | 39 订单线索二级渠道（**已确认**：用线索二级，非商机二级） | 决策：线索二级 |
| `status` | 43 在班状态 + 59/60/61 退费布尔 | 综合：在班=在读；出班且有效退费→课前退/课后退（用原生标记，**不再自算**） |
| `period_combined` | 9 期次 + 7 学季 | 派生 **effective_term**：期次≠"无"→用期次（零/一/二/三）；期次="无"→用学季（秋/春）。跨期 `/` 拼接（沿用旧规则） |
| `subjects_json` 子结构 | | 见下 |
| `enrich_json` | 见下 | 见下 |

**`subjects_json` 子结构扩展（每学科一行）：**
```
period, teacher(←18 班级主讲), status(派生), class_type(←14 班型),
class_id(←20 班级ID), room(←5 教室),
course_type(←11 课程类型), product_type(←10 产品类型),
class_mode(←13 课程模式), pay_time(←50 支付时间),
refund_time(←51 退费时间), refund_amount(←54),
pre_refund(←60 是否课前有效退费), post_refund(←61 是否课后有效退费),
valid_refund(←59 是否有效退费), attendance(←93 出勤讲次数),
start_date(←22), end_date(←23), week_cycle(←24 上课周期)
```

**`enrich_json`（学员级，新增）：**
```
advisor_roles: { creator(←29), deal_follower(←31), goods_owner(←33),
                 deal_owner(←35 主), course_follower(←37) },
channel_lead_l1(←38), channel_lead_l2(←39),
channel_deal_l1(←40), channel_deal_l2(←41),
income(←56 实际收入金额), order_origin(←71 新绩效类型),
work_attr(←73 做工归属), entry_type(←72 入班类型),
renew_next(←46 是否续下一学季), renew_next_type(←47),
renew_denom_incl_combo(←75), renew_denom_next(←76), renew_denom_next2(←77),
retain_last(←44 是否上学季留存), class_grade(←16 班级年级),
school_name(←89 公立校名称), uid_hash(←87),
refund_reason_cat(←64), refund_reason(←65)
```

---

## 4. 需扩展的 DB schema

```sql
ALTER TABLE student_snapshots ADD COLUMN enrich_json TEXT;
-- 学员级、可提升为顶层以加速过滤的维度：
ALTER TABLE student_snapshots ADD COLUMN school_name TEXT;   -- 公立校名称(105校)
ALTER TABLE student_snapshots ADD COLUMN order_origin TEXT;  -- 老生/拉新/续报扩科
ALTER TABLE student_snapshots ADD COLUMN work_attr TEXT;     -- 续报/扩科/拉新
ALTER TABLE student_snapshots ADD COLUMN renew_denom TEXT;   -- 应续分母(含联报)
ALTER TABLE student_snapshots ADD COLUMN refund_flag TEXT;   -- 有效/课前/课后
```

> 注意：`course_type`(系统/特惠)、`product_type`(正价/转化)、`class_mode`(班课/1v1)、`class_type`(班型) **随科目变化**（同一学员不同科目取值不同），**不提升为顶层列**，保留在 `subjects_json` 子结构内，查询时 `json_extract` 即可。仅 `school_name/order_origin/work_attr/renew_denom/refund_flag` 为学员级、提升顶层。

---

## 5. 需扩展的 FilterSpec（新增筛选器）

现有 11 项（`year/branch/grade/season/period/teaching_point/subject/teacher/advisor/class_type/...`）。
**新增**（全部 `multi_select`，空=全选）：

| 新筛选器 | 来源字段 | 说明 |
|---|---|---|
| `course_type` | 课程类型 | 系统课/特惠课 |
| `product_type` | 产品类型 | 正价品/转化品 |
| `class_mode` | 课程模式 | 班课/1v1 |
| `channel_lead` | 线索一/二级 | 两套渠道 |
| `channel_deal` | 商机一/二级 | 两套渠道 |
| `order_origin` | 订单来源[新绩效] | 老生/拉新/续报扩科 |
| `work_attr` | 做工归属 | 续报/扩科/拉新 |
| `refund_flag` | 退费标记 | 有效/课前/课后/不退 |
| `renew_status` | 是否续下一学季 | 是/否 |
| `school_name` | 公立校名称 | 105 校（越秀 9 校可预置高亮） |
| `advisor_role` | 顾问角色切换 | **暂不做**（决策④：先不进筛选器，仅成单归属人作主口径；其余 4 角色留 `enrich_json.advisor_roles` 备查） |

前端筛选器从当前 8 项扩展到 **~18 项**（组织/课程/人员/渠道/业务状态五类，详见上一轮对话清单）。

**学科标签色（决策⑤）**：新增「雪球科学」需补入 `SUBJECTS` / `SUBJECT_LABEL` 与标签色体系。建议沿用现有 4 色方案新增第 4 色（如青绿 `#2BB6A3`），旧 3 科学科（雪球思维/双语素养/悦读创作）色值保持不变，避免历史分享页/排行色块错位。

---

## 6. 指标计算口径（改用原生字段）

| 指标 | 旧算法 | 新算法（订单明细） |
|---|---|---|
| **在读 UV** | status 含"在读"学员去重 | 同左（status=在读） |
| **在读 PV** | subjects_json 中在读学科数 | 同左 |
| **退费 UV** | 自定义（开课首日前后） | `enrich_json.refund_flag` / `valid_refund=1` 学员 |
| **课前退 / 课后退** | 自算 | `pre_refund` / `post_refund`（原生标记） |
| **续报率** | 自算应续分母 | `renew_denom_incl_combo=1` 中 `renew_next=是` 占比 |
| **收入** | 无 | `SUM(enrich_json.income)` |
| **拉新** | 招商明细支付时间 | `order_origin=拉新` 或 `work_attr=拉新` |
| **学校维度** | 无 | `GROUP BY school_name`（越秀 9 校优先） |

---

## 7. 加载聚合算法（学员×科目×订单 → 学员行）

```
for each 订单明细文件 (按 branch 分组):
    read rows, 清洗(uanme→uname, 丢空列/空字段, 去后缀, K9剥离)
    group by 学生uid(归一化):
        学员行 = { uid, name, branch, teaching_point(取主), grade(班级年级), season,
                   advisor=成单归属人, channel=线索二级,
                   subjects_json={ 每(学科×班级)子结构 }, enrich_json={...} }
        # 同一学员多行 → 按 (学科, 班级ID) 合并；联报/续报多子订单并入同子结构
        # effective_term 派生：期次≠"无"→用期次；期次="无"→用学季(秋/春)
        # period_combined = 该学员所有 effective_term 去重 "/" 拼接
    upsert student_snapshots (run_id=新校准批次)
```

> 关键：聚合主键 = `(uid)`，学科级 = `(uid, 学科, 班级ID)`。订单级支付/退费信息并入对应学科子结构。
> `UID 跨分校唯一`（已确认）→ 合并层直接按 uid 聚合，同一学员不会跨分校重复。

---

## 8. 多分校合并导入层（决策①）

- 扫描 `Downloads/订单明细*.xlsx`（**已支持**，见 `repository.get_acquisition_trends` 既有扫描逻辑）。
- 每张表据 `城市分校` 打 `branch` 标签，统一清洗后 **UNION 导入**同一 `student_snapshots`。
- `学生uid(归一化)` 若跨分校唯一 → 直接按 uid 聚合；若同一学员不可能跨分校，安全。
- 现有"全国数据默认=全选"规则不变（空 branch=全集）。

---

## 9. 实施阶段

| Phase | 内容 | 状态 |
|---|---|---|
| 0 | 字段清洗工具（uanme/空列/后缀/K9剥离） | ✅ 完成 `engine/order_detail_loader.py` |
| 1 | 扩展 DB schema（enrich_json + 学员级顶层新列） | ✅ 完成（测试库验证，见 §11） |
| 2 | 新加载器聚合写入（替代 `load_enrollment_orders`） | ✅ 完成（独立测试库回读一致，未碰生产库） |
| 3 | 扩展 FilterSpec + engine.compute 过滤 + get_filter_options | ⬜ 待做 |
| 4 | 指标计算改用原生字段（退费/续报/收入） | ⬜ 待做 |
| 5 | 前端筛选器扩展到 ~18 项 + 学科色（雪球科学） | ⬜ 待做（色值已加 config） |
| 6 | 合并多分校 + 全链路验证（待深/京/沪表到齐） | ⬜ 待做 |

---

## 10. 用户确认的 6 项决策（已落地到 §3/§5/§7）

| # | 问题 | 用户确认 | 落位 |
|---|---|---|---|
| 1 | `channel` 用哪套 | **线索二级** | §3：`channel ← 39 订单线索二级` |
| 2 | `grade` 用哪个 | **班级年级** | §3：`grade ← 16 班级年级`；`enrich_json.class_grade←16` |
| 3 | UID 跨分校唯一 | **是** | §8 合并层按 uid 聚合安全；§7 注明 |
| 4 | 其余 4 顾问角色进筛选器 | **先不进** | 仅成单归属人作主；§5 `advisor_role` 暂不做，留 enrich_json 备查 |
| 5 | 雪球科学色 | **增加一个** | §5 学科色新增第 4 色（青绿 `#2BB6A3`），旧 3 色不变 |
| 6 | 期次"无"归类 | **本质=秋/春季学期** | §1 释义；§3/§7 `effective_term` 派生（无→学季） |

---

> 6 项全部确认，**即可进入 Phase 0–2 实现广州单表导入原型**（不依赖分校表）；
> 深/京/沪表到齐后做 Phase 6 合并。其余未决点（如越秀 9 校高亮、105 校排序）按默认实现，后续微调。

---

## 11. Phase 0–2 验证结果（2026-07-13，广州单表）

`engine/order_detail_loader.py` 已实现并 dry-run 验证（独立测试库 `/tmp/uv20_order_detail_test.db`，**未触碰生产库**）。

**读→清洗→聚合→写→回读 全链路一致：**
| 指标 | 值 |
|---|---|
| 原始订单行 | 4336 |
| 聚合学员数(uid) | 1232 |
| PV（学科数 = 唯一(uid,subject)对） | 2568 |
| 写入 student_snapshots 行数 | 1232 |
| 回读 subjects 数 | 2568 |
| 分校 | 广州（1232） |
| 教学点 | 新宝利574 / 同创汇344 / 天成296 / 龙晖18 |
| 学季 | 暑629 / 寒352 / 春135 / 秋116 |
| 汇总状态 | 在读1095 / 有效退费137 |
| 退费UV(任一科有效退费) | 351 |
| 续下学季UV | 171 |
| 顾问数 | 26 |
| 渠道(线索二级)数 | 16 |
| 学科 PV | 雪球思维1014 / 双语素养813 / 悦读创作619 / 雪球科学122 |

**关键校验**：4336 订单行 − 1768 同科目碰撞 = 2568 = PV，聚合无遗漏/无重复。
**多班级发现**：2568 个 (uid,subject) 组中，**905 组含多个不同 class_id**（同科目多班），仅 4 行为真·重复订单。→ 当前按**学科**聚合（匹配现有 `subjects_json` schema），多班被合并为 1 个学科条目（保留在读行的 teacher/class_id）。**Phase 2 决策点**：若班级级指标（按班 PV、主讲按班排行）需要精确，应改按 `(uid, subject, class_id)` 键；当前原型按学科键以对齐现有看板语义。

**已知简化（不影响原型验证）**：course_type/product_type/class_mode 未提升顶层（见 §4）；其余 4 顾问角色仅存 enrich_json。
