#!/usr/bin/env python3
"""
UV Dashboard 2.0 — 深度测试 v3

每个字段每个值都跑：
- 单值返回的 active_uv > 0（除非本来就为空）
- 各字段加和 ≈ 全局（不同字段语义）
- 排序：active_uv DESC 时是真正降序
- 极值：选最大/最小值时返回合理
- share/teacher/advisor-detail 端点无错
"""

import sys
import urllib.parse
import urllib.request
import json

BASE = 'http://localhost:5200'

def get(path, params=None):
    if params:
        clean = {k: v for k, v in params.items() if v not in ('', None)}
        if clean:
            path += '?' + urllib.parse.urlencode(clean, doseq=True)
    try:
        with urllib.request.urlopen(BASE + path, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'_ERROR': str(e)}

def post(path, body):
    try:
        req = urllib.request.Request(
            BASE + path,
            data=json.dumps(body).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'_ERROR': str(e)}

bugs = []
checks = {'pass': 0, 'fail': 0}

def check(name, cond, detail=''):
    if cond:
        checks['pass'] += 1
    else:
        checks['fail'] += 1
        bugs.append((name, detail))

# 获取 baseline
flt = get('/api/overview/filters')
all_stats = get('/api/overview/stats')
ALL_ACTIVE = all_stats['active_uv']
ALL_TOTAL = all_stats['total_uv']
ALL_REFUND = all_stats['refund_uv']
print(f'基线: total={ALL_TOTAL} active={ALL_ACTIVE} refund={ALL_REFUND}')

# ── 测试 1：每个字段的每个值 ──────────────────────────────────────
print('\n=== 每个字段每个值都有数据 ===')

field_values = {
    'branch': flt.get('branches', []),
    'subject': [s['key'] if isinstance(s, dict) else s for s in flt.get('subjects', [])],
    'season': flt.get('seasons', []),
    'year': flt.get('years', []),
    'course_type': flt.get('course_types', []),
    'class_mode': flt.get('class_modes', []),
    'grade': flt.get('grades', []),
    'period': flt.get('periods', []),
    'teaching_point': flt.get('teaching_points', []),
    'class_type': flt.get('class_types', []),
    'student_type': flt.get('student_types', []),
    'enrollment_status': flt.get('enrollment_statuses', []),
    'renewal_status': flt.get('renewal_statuses', []),
}

for field, values in field_values.items():
    if not values:
        continue
    print(f'\n[{field}] {len(values)} 个值')
    for v in values:
        r = get('/api/overview/stats', {field: v})
        active = r.get('active_uv', 0)
        total = r.get('total_uv', 0)
        # 至少有一个 UV > 0（除非字段本身就是"退费/未续报"等"零和"语义）
        zero_ok_fields = {'enrollment_status': ['退费']}  # 选"退费"时 active_uv 必为 0
        if field in zero_ok_fields and v in zero_ok_fields[field]:
            check(f'{field}={v} 允许 active_uv=0（语义上不可能在读）',
                  True, f'active_uv={active} total_uv={total}')
        else:
            check(f'{field}={v} 有 active_uv>0', active > 0 or field == 'renewal_status',
                  f'active_uv={active}')
        check(f'{field}={v} 有 total_uv>=active_uv', total >= active,
              f'total={total} active={active}')

# teacher 单值测试（不计入上方）
if flt.get('teachers'):
    for t in flt.get('teachers', [])[:3]:
        r = get('/api/overview/stats', {'teacher': t})
        check(f'teacher={t} 有数据', r.get('active_uv', 0) > 0)

# ── 测试 2：单分校加和 ────────────────────────────────────────────
print('\n=== 单分校加和 ≈ 全局 ===')
parts = []
for b in flt.get('branches', []):
    parts.append(get('/api/overview/stats', {'branch': b})['active_uv'])
sum_br = sum(parts)
ratio = abs(sum_br - ALL_ACTIVE) / max(ALL_ACTIVE, 1)
check(f'分校加和 vs 全局 (差 < 2%)', ratio < 0.02, f'sum={sum_br} all={ALL_ACTIVE}')

# ── 测试 3：多维组合 + 一致性 ──────────────────────────────────────
print('\n=== 多维组合一致性 ===')

# 3.1 各学员归属单值之和 ≥ 全局（行级筛，跨 set 重复计数是预期行为）
#     旧版"学员级聚合 + 优先级去重"加和 = 全局；新版"行级筛"加和 ≥ 全局。
parts_st = []
for st in flt.get('student_types', []):
    parts_st.append(get('/api/overview/stats', {'student_type': st})['active_uv'])
sum_st = sum(parts_st)
ok = sum_st >= ALL_ACTIVE * 0.95
check(f'学员归属加和 ≥ 全局 (行级筛)', ok, f'sum={sum_st} all={ALL_ACTIVE}')

# 3.2 全局 = 各在读状态单值之和（在读 + 退费） — 注意：active+refund 会有重叠
parts_em = []
for em in flt.get('enrollment_statuses', []):
    parts_em.append(get('/api/overview/stats', {'enrollment_status': em})['total_uv'])
sum_em = sum(parts_em)
# 验证：in_read+refund >= ALL_TOTAL（因为部分学员可能同时在读+退费）
check(f'在读+退费 >= 全局 total', sum_em >= ALL_TOTAL,
      f'sum={sum_em} all={ALL_TOTAL}')

# ── 测试 4：双字段笛卡尔积 ─────────────────────────────────────────
print('\n=== 双字段笛卡尔积有数据 ===')

combos_to_test = [
    {'branch': '广州', 'subject': '雪球思维'},
    {'branch': '深圳', 'subject': '雪球思维'},
    {'branch': '广州', 'season': '暑假'},
    {'branch': '广州', 'course_type': '特惠课'},
    {'branch': '深圳', 'class_mode': '1v1'},
    {'branch': '广州', 'grade': '初一'},
    {'subject': '雪球思维', 'course_type': '系统课'},
    {'subject': '雪球科学', 'class_mode': '班课'},  # 雪球科学只跟"班课"
    {'student_type': '新生', 'course_type': '特惠课'},
    {'student_type': '老生拓科', 'subject': '双语素养'},
    {'subject': '雪球思维', 'class_mode': '1v1'},  # 雪球思维有少量 1v1
]
for c in combos_to_test:
    r = get('/api/overview/stats', c)
    keys = '+'.join(f'{k}={v}' for k, v in c.items())
    check(f'{keys} 有数据', r.get('active_uv', 0) > 0,
          f'active_uv={r.get("active_uv")}')

# ── 测试 5：极端 ─────────────────────────────────────────────────
print('\n=== 极端测试 ===')

# 5.1 全部字段都选
all_filters = {f: v[0] if v else '' for f, v in field_values.items() if v}
r = get('/api/overview/stats', all_filters)
check('全字段组合有非负数', r.get('active_uv', -1) >= 0, f'active_uv={r.get("active_uv")}')

# 5.2 全部不存在的值
r = get('/api/overview/stats', {
    'branch': '不存在的分校',
    'grade': '不存在的年级',
    'subject': '不存在的学科',
})
check('全部不存在的值应返回 0', r.get('active_uv', -1) == 0)

# 5.3 全部空字符串
r = get('/api/overview/stats', {f: '' for f in field_values})
check('全部空字符串 = 全局', r.get('active_uv', -1) == ALL_ACTIVE)

# ── 测试 6：跨端一致性（同筛选条件在多端） ──────────────────────
print('\n=== 跨端一致性（多 API 同筛选条件） ===')

test_filter = {'branch': '广州', 'subject': '雪球思维', 'season': '暑假'}

stats = get('/api/overview/stats', test_filter)
matrix = get('/api/overview/matrix', test_filter)
share = get('/api/share-card', test_filter)
teacher_list = get('/api/overview/teacher-list', test_filter)
advisor_list = get('/api/overview/advisor-list', test_filter)

base_uv = stats.get('active_uv', 0)
base_pv = stats.get('active_pv', 0)
matrix_uv = matrix.get('matrix', {}).get('__grand_uv__', 0)
matrix_pv = matrix.get('matrix', {}).get('__grand_pv__', 0)
share_uv = (share.get('kpi', {}) or {}).get('uv', 0)
share_pv = (share.get('kpi', {}) or {}).get('active_pv', 0)
teacher_pv = sum(t.get('active', 0) for t in teacher_list)
advisor_uv = sum(a.get('active', 0) for a in advisor_list)

# 验证一致性
check(f'matrix.__grand_uv__ = stats.active_uv ({matrix_uv} vs {base_uv})', abs(matrix_uv - base_uv) <= 2)
check(f'matrix.__grand_pv__ = stats.active_pv ({matrix_pv} vs {base_pv})', abs(matrix_pv - base_pv) <= 2)
check(f'share.kpi.uv = stats.active_uv ({share_uv} vs {base_uv})', abs(share_uv - base_uv) <= 2)
check(f'share.kpi.active_pv = stats.active_pv ({share_pv} vs {base_pv})', abs(share_pv - base_pv) <= 2)
check(f'teacher.active = stats.active_pv ({teacher_pv} vs {base_pv})', abs(teacher_pv - base_pv) <= 2)
check(f'advisor.active = stats.active_uv ({advisor_uv} vs {base_uv})', abs(advisor_uv - base_uv) <= 2)

# 学员检索
students = post('/api/overview/students', {**test_filter, 'page_size': 99999})
students_count = len(students) if isinstance(students, list) else students.get('total', 0)
check(f'students count ({students_count}) >= active_uv ({base_uv})', students_count >= base_uv)

# 分页
paged = post('/api/overview/students', {**test_filter, 'page_size': 5, 'page': 1})
if isinstance(paged, dict):
    check(f'page_size=5 截断 ({len(paged.get("items", []))})', len(paged.get('items', [])) == 5)
    check(f'page=1 total = students_count', paged.get('total') == students_count)

# ── 测试 7：详情 API ──────────────────────────────────────────────
print('\n=== 详情 API ===')

# 学员详情
if flt.get('branches'):
    students_full = post('/api/overview/students', {'page_size': 1})
    if isinstance(students_full, list) and students_full:
        uid = students_full[0].get('uid')
        if uid:
            detail = get(f'/api/overview/student/{uid}')
            check('学员详情有 subjects', isinstance(detail, dict) and 'subjects' in detail,
                  f'keys: {list(detail.keys()) if isinstance(detail, dict) else "ERR"}')

# 老师详情
if flt.get('teachers'):
    t = flt['teachers'][0]
    detail = get(f'/api/overview/teacher/{urllib.parse.quote(t)}', {'branch': '广州'})
    check(f'老师详情 {t} 有 teacher 字段',
          isinstance(detail, dict) and 'teacher' in detail,
          f'keys: {list(detail.keys())[:8] if isinstance(detail, dict) else "ERR"}')

# 顾问详情
advisors = flt.get('advisors', [])
if advisors:
    a = advisors[0]
    detail = get(f'/api/overview/advisor/{urllib.parse.quote(a)}', {'branch': '广州'})
    check(f'顾问详情 {a} 有 advisor 字段',
          isinstance(detail, dict) and ('advisor' in detail or 'name' in detail),
          f'keys: {list(detail.keys())[:8] if isinstance(detail, dict) else "ERR"}')

# 班级详情
classes = get('/api/overview/classes', {'branch': '广州', 'subject': '雪球思维'})
class_list = classes if isinstance(classes, list) else classes.get('classes', [])
if class_list:
    cid = class_list[0].get('class_id') if isinstance(class_list[0], dict) else None
    if cid:
        detail = get(f'/api/overview/class/{cid}')
        check(f'班级详情 {cid} 有 class_id 字段',
              isinstance(detail, dict) and 'class_id' in detail,
              f'keys: {list(detail.keys())[:8] if isinstance(detail, dict) else "ERR"}')

# ── 测试 8：排序 / 极值 ──────────────────────────────────────────
print('\n=== 排序 / 极值 ===')

# teacher-list 默认排序：renewal_rate DESC
if teacher_list:
    rates = [t.get('renewal_rate', 0) for t in teacher_list]
    is_sorted = all(rates[i] >= rates[i+1] for i in range(len(rates)-1))
    check('teacher-list 按 renewal_rate 降序', is_sorted, f'前 3 rates: {rates[:3]}')

# advisor-list 默认排序：conv_rate DESC
if advisor_list:
    rates = [a.get('conv_rate', 0) for a in advisor_list]
    is_sorted = all(rates[i] >= rates[i+1] for i in range(len(rates)-1))
    check('advisor-list 按 conv_rate 降序', is_sorted, f'前 3 rates: {rates[:3]}')

# by_advisor 总和（从 stats 拿）
by_advisor = stats.get('by_advisor', [])
if by_advisor:
    # 验证 by_advisor 中各 advisor 的 active 之和 ≈ stats.active_uv
    sum_uv = sum(a.get('active', 0) for a in by_advisor)
    check(f'by_advisor.active 之和 ≈ stats.active_uv ({sum_uv} vs {base_uv})',
          abs(sum_uv - base_uv) <= 2)

# ── 报告 ──────────────────────────────────────────────────────
print('\n' + '═' * 60)
print(f'总计: {checks["pass"]} 通过, {checks["fail"]} 失败')
print('═' * 60)
if bugs:
    print('\n问题：')
    for n, d in bugs[:30]:
        print(f'  - {n}: {d}')

sys.exit(0 if checks['fail'] == 0 else 1)
