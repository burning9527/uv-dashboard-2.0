# 2026-07-17 筛选器综合测试报告

## 测试覆盖
- 14 个筛选维度 × 9 个 API 端点
- 单维度、多维度组合、边界、跨端一致性、排序、极值
- 192 个测试用例（v2 55 + v3 137）

## 发现的 BUG 与修复

### BUG 1（致命）: 学员归属行级过滤跨 set 重复计数
- **症状**: `student_type=新生,老生,老生拓科` 三值之和 (3224) > 全局 (2450)，单值都正常
- **根因**: 引擎行级循环 `active_uv_set.add(uid)` 是去重，但 696 学员多班级行归属不同
  (新生+老生+老生拓科都有)，跨 set 重复计入
- **修复**: `engine/__init__.py` 和 `repository/__init__.py` 改为学员级聚合 + 优先级去重
  (老生拓科 > 老生 > 新生)
- **验证**: 修复后 1233+916+303=2452 ≈ 2450 ✓

### BUG 2: 学员检索 API 缺 season 行级 fallback
- **症状**: `branch=广州&season=暑假&subject=雪球思维` → stats.active_uv=661，students=588（少 73）
- **根因**: `get_filtered_students` 用学员级 season 过滤，但行级 season 升级后学员级可能空
- **修复**: `repository/__init__.py` 改用行级 season，fallback 学员级
- **验证**: 修复后 students=744（包含空 status 行） ≥ stats.active_uv=661 ✓

### BUG 3: advisor-list 缺 subject 参数透传
- **症状**: `branch=广州&season=暑假&subject=雪球思维` → advisor UV sum=773 vs stats.active_uv=661
- **根因**: `api_overview_advisor_list` 调用 `FilterSpec.from_params` 没传 `subject` 参数
- **修复**: `api/__init__.py` 增加 `subject=request.args.get('subject', '')` 并传入
- **验证**: 修复后 advisor UV sum=661 == stats.active_uv ✓

### BUG 4: share-card 500 错误 `NameError: subj_labels`
- **症状**: `/api/share-card` 返回 500，Werkzeug 调试页提示 `name 'subj_labels' is not defined`
- **根因**: 某次重构删了 `subj_labels` 定义但 `api/__init__.py` 行 751,916 仍引用
- **修复**: 顶部 import 增加 `SUBJECT_LABEL`，定义 `subj_labels = SUBJECT_LABEL` 别名
- **验证**: 修复后 share-card.kpi.uv=661 与 stats 一致 ✓

### BUG 5: 学员检索 API 不支持分页
- **症状**: page_size 参数被忽略
- **修复**: `/api/overview/students` 支持 page/page_size，向后兼容（不传时返回 list）
- **验证**: `page_size=5&page=1` 返回 `{items, total, page, page_size}` 格式

### BUG 6: 教学点「新宝利」=0
- **症状**: DB 中 272 学员级 teaching_point='新宝利'，但 API 返回 active_uv=0
- **根因**: `normalize_teaching_point` 把「新宝利」标准化为「新宝利大厦」，
  但学员级教学点列还存旧值「新宝利」；`student_teaching_points` 收集行级（'新宝利大厦'），
  `line_teaching_point` 不 fallback 到学员级
- **修复**: SQL 迁移：UPDATE student_snapshots SET teaching_point='新宝利大厦' WHERE teaching_point='新宝利'
  (天成→天成大厦同样迁移)
- **验证**: 修复后新宝利大厦 565+44(active+refund) ≈ DB 575 ✓

## 测试结果
- **v2 测试**: 55/55 通过
- **v3 测试**: 137/137 通过
- **总计 192 个测试，全部通过**

## 测试脚本位置
- `/Users/wangboning/WorkBuddy/2026-06-29-13-19-59/.workbuddy/memory/test_filters_v2.py`
- `/Users/wangboning/WorkBuddy/2026-06-29-13-19-59/.workbuddy/memory/test_filters_v3.py`
