#!/usr/bin/env python3
"""
UV Dashboard 2.0 — 筛选器综合测试脚本 v2

修复版：修正对多选/UV/PV 口径的误解
"""

import json
import sys
import urllib.parse
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

BASE = 'http://localhost:5200'

# ── 工具函数 ──────────────────────────────────────────────────────

def url(path: str, params: Optional[Dict] = None) -> str:
    if params:
        clean = {k: v for k, v in params.items() if v not in ('', None, [], {})}
        if clean:
            return f'{BASE}{path}?{urllib.parse.urlencode(clean, doseq=True)}'
    return f'{BASE}{path}'

def get(path: str, params: Optional[Dict] = None) -> Any:
    import urllib.request
    try:
        req = urllib.request.Request(url(path, params))
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        return {'_ERROR': str(e)}

def post(path: str, body: Dict) -> Any:
    import urllib.request
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

# ── 计数器 ────────────────────────────────────────────────────────

results = {'pass': 0, 'fail': 0, 'bugs': []}

def check(name: str, condition: bool, detail: str = ''):
    if condition:
        results['pass'] += 1
        print(f'  ✓ {name}')
    else:
        results['fail'] += 1
        results['bugs'].append((name, detail))
        print(f'  ✗ {name}')
        if detail:
            for line in detail.split('\n')[:5]:
                print(f'      {line}')

def in_tolerance(a, b, tol=2):
    return abs(a - b) <= tol

# ═══════════════════════════════════════════════════════════════
#  阶段 0：基线
# ═══════════════════════════════════════════════════════════════

print('═' * 60)
print('  阶段 0：基线数据')
print('═' * 60)

flt = get('/api/overview/filters')
fc = flt.get('filter_config', {})
combos = flt.get('combos', [])
combo_fields = flt.get('combo_fields', [])

YRS = flt.get('years', [])
BRS = flt.get('branches', [])
GRS = flt.get('grades', [])
SSS = flt.get('seasons', [])
PERS = flt.get('periods', [])
TPS = flt.get('teaching_points', [])
TCHRS = flt.get('teachers', [])
CTPS = flt.get('class_types', [])
STS = flt.get('enrollment_statuses', [])
COS = flt.get('course_types', [])
CMS = flt.get('class_modes', [])
STS_T = flt.get('student_types', [])
SBJS = [s['key'] if isinstance(s, dict) else s for s in flt.get('subjects', [])]

all_stats = get('/api/overview/stats')
ALL_UV = all_stats.get('total_uv', 0)
ALL_ACTIVE = all_stats.get('active_uv', 0)
ALL_REFUND = all_stats.get('refund_uv', 0)
print(f'  全局 total_uv={ALL_UV}, active_uv={ALL_ACTIVE}, refund_uv={ALL_REFUND}')

# ═══════════════════════════════════════════════════════════════
#  阶段 1：第一排 6 项不联动
# ═══════════════════════════════════════════════════════════════

print('\n' + '═' * 60)
print('  阶段 1：第一排 6 项不联动')
print('═' * 60)

cf_idx = {f: i for i, f in enumerate(combo_fields)}

# 1.1 fc.options 应有第一排全量兜底
print('\n[1.1] fc.options 兜底（年份/分校/学季/年级）')
fc_options = fc
PRIMARY_FULL = {
    'year': 3,           # [2025,2026,2027]
    'branch': 4,         # [广州,深圳,北京,上海]
    'season': 4,         # 4 学季
    'grade': 9,          # 9 年级
    'student_type': 3,   # [新生,老生,老生拓科]
    'renewal_status': 4,
    'enrollment_status': 2,
}
for f, min_n in PRIMARY_FULL.items():
    got = len(fc_options.get(f, {}).get('options', []))
    check(f'fc.{f}.options ≥ {min_n}', got >= min_n, f'actual={got}')

# 1.2 combo 数据中第一排全量
print('\n[1.2] combo 数据含第一排字段全量')
all_yr = set(c[cf_idx['year']] for c in combos) if 'year' in cf_idx else set()
all_br = set(c[cf_idx['branch']] for c in combos) if 'branch' in cf_idx else set()
all_ss = set(c[cf_idx['season']] for c in combos) if 'season' in cf_idx else set()
all_sb = set(c[cf_idx['subject']] for c in combos) if 'subject' in cf_idx else set()
all_ct = set(c[cf_idx['course_type']] for c in combos) if 'course_type' in cf_idx else set()
all_cm = set(c[cf_idx['class_mode']] for c in combos) if 'class_mode' in cf_idx else set()

check('combo year ⊇ 数据 years', set(YRS) <= all_yr | {''}, f'yrs={YRS} all_yr={all_yr}')
check('combo branch ⊇ 数据 branches', set(BRS) <= all_br | {''}, f'brs={BRS} all_br={all_br}')
check('combo season ⊇ 数据 seasons', set(SSS) <= all_ss | {''}, f'sss={SSS} all_ss={all_ss}')

# 1.3 第二排字段在第一排约束下应被收窄
print('\n[1.3] 第二排字段在第一排约束下应被收窄')

def get_secondary_after_primary(branch_filter: str, season_filter: str) -> Dict:
    result = defaultdict(set)
    for c in combos:
        if branch_filter and 'branch' in cf_idx and c[cf_idx['branch']] != branch_filter:
            continue
        if season_filter and 'season' in cf_idx and c[cf_idx['season']] != season_filter:
            continue
        for f in cf_idx:
            if f in ('year', 'branch', 'season', 'subject', 'course_type', 'class_mode'):
                continue
            v = c[cf_idx[f]]
            if v:
                result[f].add(v)
    return result

all_second = get_secondary_after_primary('', '')
gz_second = get_secondary_after_primary('广州', '')

check('branch=广州 后 teaching_point 收窄',
      len(gz_second['teaching_point']) < len(all_second['teaching_point']),
      f'全量={len(all_second["teaching_point"])} vs 广州后={len(gz_second["teaching_point"])}')
check('branch=广州 后 teacher 收窄',
      len(gz_second['teacher']) < len(all_second['teacher']),
      f'全量={len(all_second["teacher"])} vs 广州后={len(gz_second["teacher"])}')

# ═══════════════════════════════════════════════════════════════
#  阶段 2：单维度筛选
# ═══════════════════════════════════════════════════════════════

print('\n' + '═' * 60)
print('  阶段 2：单维度筛选')
print('═' * 60)

# 2.1 分校：广州+深圳 = 全局 (active_uv)
print('\n[2.1] 分校筛选')
gz = get('/api/overview/stats', {'branch': '广州'})
sz = get('/api/overview/stats', {'branch': '深圳'})
check('广州 active_uv > 0', gz.get('active_uv', 0) > 0)
check('深圳 active_uv > 0', sz.get('active_uv', 0) > 0)
check('广州 active_uv + 深圳 active_uv = 全局 active_uv',
      in_tolerance(gz.get('active_uv', 0) + sz.get('active_uv', 0), ALL_ACTIVE),
      f'gz={gz["active_uv"]} + sz={sz["active_uv"]} = {gz["active_uv"]+sz["active_uv"]} vs all={ALL_ACTIVE}')

# 2.2 不存在的分校
print('\n[2.2] 不存在的分校应返回空')
none_br = get('/api/overview/stats', {'branch': '不存在的分校'})
check('不存在的分校 total_uv=0', none_br.get('total_uv', -1) == 0)
check('不存在的分校 active_uv=0', none_br.get('active_uv', -1) == 0)

# 2.3 学员归属单值（学员级聚合 + 优先级去重）
print('\n[2.3] 学员归属单值（应可分桶+可加和≈全局）')
st_uvs = {}
for st in STS_T:
    r = get('/api/overview/stats', {'student_type': st})
    st_uvs[st] = r.get('active_uv', 0)
    check(f'student_type={st} 应有数据', r.get('active_uv', 0) > 0)
sum_st = sum(st_uvs.values())
check(f'学员归属 3 部分之和 ≈ 全局 active_uv（差异 < 5%）',
      abs(sum_st - ALL_ACTIVE) / max(ALL_ACTIVE, 1) < 0.05,
      f'sum={sum_st} parts={st_uvs} all={ALL_ACTIVE}')

# 2.4 单值字段都有数据
print('\n[2.4] 各单值字段都有数据')
single_value_tests = [
    ('year', '2026'),
    ('season', '暑假'),
    ('subject', SBJS[0] if SBJS else ''),
    ('course_type', COS[0] if COS else ''),
    ('class_mode', CMS[0] if CMS else ''),
    ('grade', '初一'),
    ('period', '一期'),
    ('teaching_point', '同创汇'),
    ('teacher', TCHRS[0] if TCHRS else ''),
    ('class_type', CTPS[0] if CTPS else ''),
    ('enrollment_status', '在读'),
    ('renewal_status', '已续报'),
]
for f, v in single_value_tests:
    if v:
        r = get('/api/overview/stats', {f: v})
        check(f'{f}={v} 有数据', r.get('active_uv', 0) > 0, f'{f}={v} → active_uv={r.get("active_uv")}')

# ═══════════════════════════════════════════════════════════════
#  阶段 3：多维度组合
# ═══════════════════════════════════════════════════════════════

print('\n' + '═' * 60)
print('  阶段 3：多维度组合')
print('═' * 60)

# 3.1 累加约束单调递减
print('\n[3.1] 累加约束单调递减')
t1 = get('/api/overview/stats', {'branch': '广州'}).get('active_uv', 0)
t2 = get('/api/overview/stats', {'branch': '广州', 'grade': '初一'}).get('active_uv', 0)
t3 = get('/api/overview/stats', {'branch': '广州', 'grade': '初一', 'enrollment_status': '在读'}).get('active_uv', 0)
check('广州 ≥ 广州+初一 ≥ 广州+初一+在读', t1 >= t2 >= t3,
      f'g={t1} g+1={t2} g+1+active={t3}')

# 3.2 八维组合
print('\n[3.2] 八维组合')
narrowest = get('/api/overview/stats', {
    'branch': '广州', 'season': '暑假', 'period': '一期',
    'teaching_point': '同创汇', 'subject': '雪球思维',
    'course_type': '特惠课', 'class_mode': '班课',
    'student_type': '新生',
})
check('八维组合 active_uv >= 0', narrowest.get('active_uv', -1) >= 0)

# 3.3 矛盾筛选
print('\n[3.3] 矛盾筛选')
nonsense = get('/api/overview/stats', {'branch': '广州', 'grade': '不存在的年级'})
check('矛盾筛选应返回 0', nonsense.get('active_uv', -1) == 0)

# 3.4 空字符串=无筛选
print('\n[3.4] 空字符串=无筛选')
empty = get('/api/overview/stats', {'branch': '', 'season': '', 'grade': ''})
check('空字符串筛选 = 全局', empty.get('active_uv', -1) == ALL_ACTIVE)

# 3.5 URL 编码
print('\n[3.5] URL 编码')
sz_correct = get('/api/overview/stats', {'branch': '深圳'})
sz_wrong = get('/api/overview/stats', {'branch': '深巳'})  # 错误编码
check('深圳 URL 编码正确有数据', sz_correct.get('active_uv', 0) > 0)
check('错误编码"深巳"应返回空', sz_wrong.get('active_uv', -1) == 0)

# ═══════════════════════════════════════════════════════════════
#  阶段 4：跨端一致性（同一筛选条件在多个 API 的 active_uv 一致）
# ═══════════════════════════════════════════════════════════════

print('\n' + '═' * 60)
print('  阶段 4：跨端一致性（active_uv + active_pv 口径）')
print('═' * 60)

test_filter = {'branch': '广州', 'season': '暑假', 'subject': '雪球思维'}

stats = get('/api/overview/stats', test_filter)
matrix = get('/api/overview/matrix', test_filter)
share = get('/api/share-card', test_filter)

base_uv = stats.get('active_uv', 0)
base_pv = stats.get('active_pv', 0)
matrix_uv = matrix.get('matrix', {}).get('__grand_uv__', 0)
matrix_pv = matrix.get('matrix', {}).get('__grand_pv__', 0)
share_uv = (share.get('kpi', {}) or {}).get('uv', 0)
share_pv = (share.get('kpi', {}) or {}).get('active_pv', 0)

print(f'  stats.active_uv   = {base_uv}, active_pv={base_pv}')
print(f'  matrix.__grand_uv__ = {matrix_uv}, __grand_pv__={matrix_pv}')
print(f'  share-card.kpi.uv = {share_uv}, active_pv={share_pv}')

check('matrix.__grand_uv__ ≈ stats.active_uv', in_tolerance(matrix_uv, base_uv, tol=2),
      f'matrix={matrix_uv} stats={base_uv}')
check('matrix.__grand_pv__ ≈ stats.active_pv', in_tolerance(matrix_pv, base_pv, tol=2),
      f'matrix={matrix_pv} stats={base_pv}')
check('share-card.kpi.uv ≈ stats.active_uv', in_tolerance(share_uv, base_uv, tol=2),
      f'share={share_uv} stats={base_uv}')
check('share-card.kpi.active_pv ≈ stats.active_pv', in_tolerance(share_pv, base_pv, tol=2),
      f'share={share_pv} stats={base_pv}')

# 学员检索（page_size=99999 拿全量）
paged = post('/api/overview/students', {**test_filter, 'page_size': 99999})
students_count = len(paged) if isinstance(paged, list) else paged.get('total', 0)
print(f'  students count = {students_count}')
# students count 应 ≥ stats.active_uv（因为 students 包含所有匹配学员，不限状态）
check('students count ≥ stats.active_uv (含退费+空状态)',
      students_count >= base_uv,
      f'students={students_count} active_uv={base_uv}')

# page_size 截断
paged5 = post('/api/overview/students', {**test_filter, 'page_size': 5, 'page': 1})
if isinstance(paged5, dict):
    check('page_size=5 截断生效', len(paged5.get('items', [])) == 5,
          f'items={len(paged5.get("items", []))}')

# 老师/顾问 PV 口径一致性
teacher_list = get('/api/overview/teacher-list', test_filter)
teacher_pv_sum = sum(t.get('active', 0) for t in teacher_list)
advisor_list = get('/api/overview/advisor-list', test_filter)
advisor_pv_sum = sum(a.get('active', 0) for a in advisor_list)
print(f'  teacher-list PV sum = {teacher_pv_sum}')
print(f'  advisor-list PV sum = {advisor_pv_sum}')
check('teacher PV sum ≈ stats.active_pv', in_tolerance(teacher_pv_sum, base_pv, tol=2),
      f'teacher_pv={teacher_pv_sum} stats_pv={base_pv}')
check('advisor PV sum ≈ stats.active_pv', in_tolerance(advisor_pv_sum, base_pv, tol=5),
      f'advisor_pv={advisor_pv_sum} stats_pv={base_pv}')

# ═══════════════════════════════════════════════════════════════
#  阶段 5：学员归属专项（学员级聚合 + 优先级去重）
# ═══════════════════════════════════════════════════════════════

print('\n' + '═' * 60)
print('  阶段 5：学员归属专项（学员级聚合 + 优先级去重）')
print('═' * 60)

# 单值
for st in STS_T:
    r = get('/api/overview/stats', {'student_type': st})
    print(f'  student_type={st}: total_uv={r.get("total_uv")} active_uv={r.get("active_uv")}')

# 优先级：老生拓科 > 老生 > 新生
# 这意味着：
#   新生（含单纯新生+新生+老生混合）= 实际"最具体=新生"的学员
#   老生（含单纯老生+老生+老生拓科混合，但归老生）= 实际"最具体=老生"的学员
#   老生拓科 = 实际"最具体=老生拓科"的学员
# 三者之和应接近全局

total_agg = sum(get('/api/overview/stats', {'student_type': st}).get('active_uv', 0) for st in STS_T)
check(f'学员归属 3 部分之和 ≈ 全局 active_uv（差 < 5%）',
      abs(total_agg - ALL_ACTIVE) / max(ALL_ACTIVE, 1) < 0.05,
      f'sum={total_agg} all={ALL_ACTIVE}')

# 优先级去重验证：选「老生拓科」= 实际最具体是老生拓科，不含单纯老生
# 选「老生」= 单纯老生 + 混合（老生+老生拓科，优先老生拓科被排除，单纯老生入选）
# 即：老生+老生拓科 部分有重叠
# 所以 student_type=老生,老生拓科 = student_type=老生 + student_type=老生拓科（因为同一学员最具体=老生拓科不会同时归到老生）

st_old = get('/api/overview/stats', {'student_type': '老生'}).get('active_uv', 0)
st_exp = get('/api/overview/stats', {'student_type': '老生拓科'}).get('active_uv', 0)
st_both = get('/api/overview/stats', {'student_type': '老生,老生拓科'}).get('active_uv', 0)
check('老生,老生拓科 = 老生 + 老生拓科（优先级去重无重叠）',
      in_tolerance(st_both, st_old + st_exp, tol=2),
      f'both={st_both} old+exp={st_old+st_exp}')

# 学员级聚合：单纯只有"老生"行（无老生拓科行）的学员应只归到老生
# 而有"新生+老生"行（无老生拓科）的学员优先老生

# ═══════════════════════════════════════════════════════════════
#  阶段 6：边界 + 异常场景
# ═══════════════════════════════════════════════════════════════

print('\n' + '═' * 60)
print('  阶段 6：边界 + 异常场景')
print('═' * 60)

# 6.1 全空字符串
print('\n[6.1] 全空字符串=无筛选')
empty = get('/api/overview/stats', {'branch': '', 'season': '', 'grade': '', 'period': '', 'subject': ''})
check('全空字符串 = 全局', empty.get('active_uv', -1) == ALL_ACTIVE)

# 6.2 不存在的字段值
print('\n[6.2] 不存在的字段值')
nx = get('/api/overview/stats', {'grade': '不存在的年级'})
check('不存在的年级 = 0', nx.get('active_uv', -1) == 0)

# 6.3 多分校逗号分隔
print('\n[6.3] 多分校逗号分隔 = 单分校之和')
both = get('/api/overview/stats', {'branch': '广州,深圳'})
check('branch=广州,深圳 ≈ 广州+深圳', in_tolerance(both.get('active_uv', 0), gz.get('active_uv', 0) + sz.get('active_uv', 0), tol=2),
      f'both={both.get("active_uv")} gz+sz={gz.get("active_uv")+sz.get("active_uv")}')

# 6.4 学员详情/班级详情/老师详情
print('\n[6.4] 详情 API')
if TCHRS:
    detail = get(f'/api/overview/teacher/{urllib.parse.quote(TCHRS[0])}', {'branch': '广州'})
    check('老师详情 200', '_ERROR' not in detail, f'errors: {detail.get("_ERROR", "")}')

# 6.5 全部不存在的筛选
print('\n[6.5] 全部矛盾')
nonsense = get('/api/overview/stats', {
    'branch': '不存在的分校',
    'grade': '不存在的年级',
    'subject': '不存在的学科',
})
check('全部矛盾应返回 0', nonsense.get('active_uv', -1) == 0)

# 6.6 share-card 200
print('\n[6.6] share-card HTTP 200')
sc = get('/api/share-card', test_filter)
check('share-card 返回 kpi', isinstance(sc, dict) and 'kpi' in sc,
      f'keys: {list(sc.keys()) if isinstance(sc, dict) else "NOT-DICT"}')

# ═══════════════════════════════════════════════════════════════
#  最终报告
# ═══════════════════════════════════════════════════════════════

print('\n' + '═' * 60)
print(f'  总计: {results["pass"]} 通过, {results["fail"]} 失败')
print('═' * 60)

if results['bugs']:
    print(f'\n发现 {len(results["bugs"])} 个问题：')
    for name, detail in results['bugs'][:30]:
        print(f'  - {name}')

sys.exit(0 if results['fail'] == 0 else 1)
