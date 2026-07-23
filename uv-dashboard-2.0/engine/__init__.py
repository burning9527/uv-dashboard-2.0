"""
UV Dashboard 2.0 — 核心指标引擎
所有指标计算的唯一真相源。一次计算，多处消费。
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional

from config import (
    SUBJECTS, PERIOD_ORDER, PERIOD_DATES, PERIOD_SCHEDULE,
    WEEKDAY_ORDER, norm_weekday, term_type_for_seasons,
    SHORT_SEASONS, LONG_SEASONS,
    is_continue_fall, classify_renewal_by_pay_time,
    is_renewal_denom, is_renewed_by_source,
    get_room_teaching_point, student_teaching_points,
    get_line_subject, line_teaching_point,
    SUBJECT_SHORT, SUBJECT_LABEL, SUBJECT_COLOR,
    auto_detect_period, get_period_start_str,
    FILTER_CONFIG, FILTER_DEFAULTS,
    norm_class_mode,
)


def _parse_pay_time_safe(val):
    """安全解析支付时间字符串，返回 datetime 或 None"""
    if not val:
        return None
    s = str(val).strip()
    if not s:
        return None
    from datetime import datetime as _dt
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
                '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M', '%Y/%m/%d',
                '%Y.%m.%d', '%Y年%m月%d日'):
        try:
            return _dt.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    # 尝试 fromisoformat
    try:
        return _dt.fromisoformat(s)
    except (ValueError, TypeError):
        pass
    return None


# ═══════════════════════════════════════════════════════════════
# 筛选规格
# ═══════════════════════════════════════════════════════════════

@dataclass
class FilterSpec:
    """统一的筛选条件（11项筛选器，全部支持多选）"""
    periods: List[str] = field(default_factory=list)
    teaching_point: List[str] = field(default_factory=list)
    teachers: List[str] = field(default_factory=list)
    subjects: List[str] = field(default_factory=list)
    class_types: List[str] = field(default_factory=list)
    advisor: str = ''
    all_periods_mode: bool = True
    # 多选筛选器（全部支持comma-separated）
    # 默认值统一为空 = 全选（面向全国：空选即展示全部分校/年级/学季/年份的并集）
    year: List[str] = field(default_factory=list)
    season: List[str] = field(default_factory=list)
    branch: List[str] = field(default_factory=list)
    grade: List[str] = field(default_factory=list)
    enrollment_status: List[str] = field(default_factory=list)
    renewal_status: List[str] = field(default_factory=list)
    course_type: List[str] = field(default_factory=list)
    product_type: List[str] = field(default_factory=list)
    class_mode: List[str] = field(default_factory=list)  # 课程模式：班课/1v1（M列）
    student_type: List[str] = field(default_factory=list)  # 学员归属：新生/老生/老生拓科（BS列）

    @classmethod
    def from_params(cls, period='', teaching_point='', teacher='',
                    subject='', class_type='', advisor='',
                    year='', season='', branch='', grade='',
                    enrollment_status='', renewal_status='',
                    course_type='', product_type='', class_mode='',
                    student_type=''):
        periods = [p.strip() for p in period.split(',') if p.strip()] if period else []
        teachers = [t.strip() for t in teacher.split(',') if t.strip()] if teacher else []
        subjects = [s.strip() for s in subject.split(',') if s.strip()] if subject else []
        class_types = [c.strip() for c in class_type.split(',') if c.strip()] if class_type else []
        tps = [tp.strip() for tp in teaching_point.split(',') if tp.strip()] if teaching_point else []
        # 空参数 = 全选（不默认锁定单个分校/年级/学季/年份，面向全国多城市共存）
        years = [y.strip() for y in year.split(',') if y.strip()] if year else []
        seasons = [s.strip() for s in season.split(',') if s.strip()] if season else []
        branches = [b.strip() for b in branch.split(',') if b.strip()] if branch else []
        grades = [g.strip() for g in grade.split(',') if g.strip()] if grade else []
        e_statuses = [e.strip() for e in enrollment_status.split(',') if e.strip()] if enrollment_status else []
        r_statuses = [r.strip() for r in renewal_status.split(',') if r.strip()] if renewal_status else []
        # 兼容前端简称：「课前续」→「开课前续报」
        r_statuses = [('开课前续报' if r == '课前续' else r) for r in r_statuses]
        course_types = [c.strip() for c in course_type.split(',') if c.strip()] if course_type else []
        product_types = [p.strip() for p in product_type.split(',') if p.strip()] if product_type else []
        class_modes = [c.strip() for c in class_mode.split(',') if c.strip()] if class_mode else []
        student_types = [s.strip() for s in student_type.split(',') if s.strip()] if student_type else []
        all_mode = not period or period == 'all'
        if all_mode:
            periods = []
        return cls(
            periods=periods, teaching_point=tps,
            teachers=teachers, subjects=subjects, class_types=class_types,
            advisor=advisor.strip(), all_periods_mode=all_mode,
            year=years, season=seasons, branch=branches, grade=grades,
            enrollment_status=e_statuses, renewal_status=r_statuses,
            course_type=course_types, product_type=product_types,
            class_mode=class_modes, student_type=student_types,
        )


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _parse_subjects(sjson: str) -> dict:
    try:
        return json.loads(sjson or '{}')
    except (json.JSONDecodeError, TypeError):
        return {}

def _period_list(period_str: str) -> List[str]:
    return [p.strip() for p in period_str.split('/') if p.strip()]

def _safe_rate(num, denom, default=0):
    return round(num / denom * 100, 1) if denom > 0 else default


# ═══════════════════════════════════════════════════════════════
# 核心引擎
# ═══════════════════════════════════════════════════════════════

class MetricsEngine:
    """
    一次遍历，全维度输出。输入 student_rows，输出完整指标。
    student_rows: [{uid, name, teaching_point, advisor, subjects_json, ...}]
    """

    def compute(self, student_rows: List[dict],
                filter_spec: FilterSpec = None) -> dict:
        """
        核心计算入口。返回标准化 dict，所有 API 直接消费。
        """
        if filter_spec is None:
            filter_spec = FilterSpec()

        fs = filter_spec  # shorthand

        # ── helper: 按 (term_kind, key) 累加到 by_period / by_weekday ──
        def _bucket(term_kind, key):
            """term_kind in {'short', 'long'} → 返回对应 dict 并自动 lazy-init。"""
            if term_kind == 'short':
                bucket = by_period
            else:
                bucket = by_weekday
            if key not in bucket:
                bucket[key] = {
                    'active_pv': 0, 'refund_pv': 0, 'renewed_pv': 0,
                    'pre_pv': 0, 'new_pv': 0,
                    'denom_pv': 0, 'renewed_lock_pv': 0,
                    'active_uv': set(), 'renewed_uv': set(),
                    'denom_uv': set(), 'renewed_lock_uv': set(),
                }
            return bucket[key]

        def _bucket_subj(term_kind, key, subj):
            """学科×term×key 分桶。"""
            if term_kind == 'short':
                full = subj_period[subj].setdefault(key, {
                    'active': 0, 'renewed': 0, 'denom': 0, 'renewed_lock': 0})
            else:
                full = subj_period[subj].setdefault(key, {
                    'active': 0, 'renewed': 0, 'denom': 0, 'renewed_lock': 0})
            return full

        def _bucket_refund(term_kind, key):
            """退费 UV 按 term 维度分桶。"""
            return period_refund_uv[key]

        def _new_empty_term_bucket():
            """空期次桶（用于补齐 0 值的全 keys）"""
            return {
                'active_pv': 0, 'refund_pv': 0, 'renewed_pv': 0,
                'pre_pv': 0, 'new_pv': 0,
                'denom_pv': 0, 'renewed_lock_pv': 0,
                'active_uv': set(), 'renewed_uv': set(),
                'denom_uv': set(), 'renewed_lock_uv': set(),
            }

        def _term_keys(plist, line_season, week_cycle):
            """根据行级学期返回分桶 key 列表 + term_kind。

            短学期（寒/暑）：plist 中的'零/一/二/三/四'都是有效 key，'无' 排除
            长学期（春/秋）：用 week_cycle 归一为'周X'
            """
            if line_season in SHORT_SEASONS:
                keys = [p for p in plist if p in PERIOD_ORDER]
                return ('short', keys)
            elif line_season in LONG_SEASONS:
                wd = norm_weekday(week_cycle)
                if wd:
                    return ('long', [wd])
                return ('long', [])
            return (None, [])

        # ── 初始化计数器 ──
        total = {'active_pv': 0, 'refund_pv': 0, 'renewed_pv': 0,
                 'pre_pv': 0, 'new_pv': 0,
                 'denom_pv': 0, 'renewed_lock_pv': 0}

        # 分学科
        by_subj = {s: {'active': 0, 'refund': 0, 'renewed': 0, 'pre': 0, 'new': 0,
                       'denom': 0, 'renewed_lock': 0}
                   for s in SUBJECTS}

        # 分期次（按实际出现动态填充；不再预初始化 5 个零期次，避免长学期场景显示空白）
        by_period = {}  # {p: {active_pv, refund_pv, ..., active_uv:set, ...}}
        by_weekday = {}  # {weekday: {active_pv, ..., active_uv:set, ...}}（长学期用）
        # 也按 星期+期次 联合记账（混学期场景）
        period_refund_uv = defaultdict(lambda: defaultdict(set))  # [term][key] = {uid}

        # 分讲师
        by_teacher = {}  # {teacher: {active, renewed, refund, pre, new, denom, renewed_lock, subject}}

        # 分顾问（UV+PV双维度）
        by_advisor = {}  # {advisor: {uv:{active:set, pre:set, new:set, denom:set, renewed_lock:set}, pv:{active, pre, new, denom, renewed_lock}}}

        # 分渠道（拉新×转化效率）—— 仅新生学员（学员工单 order_origin=拉新）
        # 双维度：channel_l1（一级渠道 AL 列）、channel（=channel_l2 AM 列）
        by_channel_l1 = {}  # {l1: {acquired, active_new, renewed, refunded, total_uv}}
        by_channel_l2 = {}  # {l2: {...}}
        # 统计每个学员（uid）在每个 channel 是否计入
        seen_uid_l1 = {}  # {l1: set(uid)}
        seen_uid_l2 = {}

        # 分学科×分期次
        subj_period = {s: {} for s in SUBJECTS}  # {subj: {key: {active, renewed, denom, renewed_lock}}}

        # 分教学点
        by_point = {}    # {pt: {active_pv, refund_pv, renewed_pv, denom_pv, renewed_lock_pv, active_uv:set, renewed_uv:set, denom_uv:set, renewed_lock_uv:set, classes:set}}

        # 班级维度
        by_class = {}    # {class_id: {active, renewed, denom, renewed_lock, uv:set, renewed_uv:set, denom_uv:set, renewed_lock_uv:set, subject, period}}

        # UV集合
        active_uv_set: Set[str] = set()
        renewed_uv_set: Set[str] = set()
        denom_uv_set: Set[str] = set()
        renewed_lock_uv_set: Set[str] = set()

        # 退费UV归属
        uid_any_active: Dict[str, bool] = {}
        uid_period_active: Dict[str, Set[str]] = {}  # uid → 有在读科目的期次集合
        uid_period_has_subject: Dict[str, Set[str]] = {}  # uid → 有科目的期次集合（在读+退费）
        uid_refund_periods: Dict[str, list] = defaultdict(list)

        # ── 遍历学员 ──
        for row in student_rows:
            uid = row.get('uid', '')
            # 学员级注册教学点（仅作 fallback）
            student_pt = (row.get('teaching_point') or '').strip()
            advisor = row.get('advisor') or ''
            if not advisor or advisor == '-':
                advisor = '未知'

            subjects = _parse_subjects(row.get('subjects_json', ''))

            # ── 教学点筛选（学员级粗筛，作为快速排除；细粒度仍在逐行判断）──
            # 若按学科筛选，教学点归属只考虑被选学科
            eff_subjects = subjects
            if fs.subjects:
                eff_subjects = {k: v for k, v in subjects.items()
                                if get_line_subject(v, k) in set(fs.subjects)}
            student_pts = student_teaching_points(eff_subjects, student_pt)
            if fs.teaching_point and not (student_pts & set(fs.teaching_point)):
                continue
            if fs.advisor and advisor != fs.advisor:
                continue

            # 分校筛选（学员级：uid 归属单一分校）
            if fs.branch:
                sb = (row.get('branch') or '').strip()
                if sb not in set(fs.branch):
                    continue

            # ── 学员级 学员归属(BS列) 聚合筛选 ──
            # 同一学员多个班级行可能有不同 student_type，需先聚合去重再过滤。
            # 优先级（最具体优先）：老生拓科 > 老生 > 新生
            #   - 业务含义：BS 列反映每笔订单的"学员归属"性质。同一学员同时
            #     有"拉新"和"老生"订单行时，意味着他后续又续报了，最具体的事实
            #     是"老生"（或"老生拓科"），不是"新生"。
            #   - 行级过滤会导致跨 set 重复计数（同一学员被多次计入不同 set），
            #     学员级聚合 + 优先级去重是正确语义。
            # ── 学员级 student_type 筛选（行级优先语义）──
            # Excel 口径：BS=拉新 筛的是**行级**学生来源（一行=一个订单行）。
            #   学员级聚合 + 优先级去重会导致该筛的学员被错误剔除（学员有老生行时，st_main=老生）。
            #   改为：学员至少有一行的 student_type 匹配 fs.student_type → 纳入
            #         active_pv/refund_pv/renewed_pv 等行级计数**只算匹配的行**
            if fs.student_type:
                _st_set = set()
                for _sd in subjects.values():
                    if isinstance(_sd, dict):
                        _st_val = (_sd.get('student_type') or '').strip()
                        if _st_val:
                            _st_set.add(_st_val)
                if _st_set:
                    # 学员级聚合（仍用于 _st_main 派生，by_channel 拉新判定）
                    if '老生拓科' in _st_set:
                        _st_main = '老生拓科'
                    elif '老生' in _st_set:
                        _st_main = '老生'
                    elif '新生' in _st_set:
                        _st_main = '新生'
                    else:
                        _st_main = ''
                    # 学员级筛：学员至少有一行 student_type 在 fs.student_type 中
                    if not (_st_set & set(fs.student_type)):
                        continue
                else:
                    continue
            else:
                # 未按归属过滤：仍需算出该学员的主归属（用于 by_channel 拉新判定）
                _st_set = set()
                for _sd in subjects.values():
                    if isinstance(_sd, dict):
                        _st_val = (_sd.get('student_type') or '').strip()
                        if _st_val:
                            _st_set.add(_st_val)
                if '老生拓科' in _st_set:
                    _st_main = '老生拓科'
                elif '老生' in _st_set:
                    _st_main = '老生'
                elif '新生' in _st_set:
                    _st_main = '新生'
                else:
                    _st_main = ''

            # 学员级 year/season/grade（仅作 legacy 兜底；订单行数组模型下逐行判断）
            student_grade = (row.get('grade') or '').strip()
            student_season = (row.get('season') or '').strip()
            student_year = (row.get('year') or '').strip()

            student_has_active = False
            student_renewed = False
            student_processed_any = False  # 该学员是否有科目通过所有筛选并进入统计
            student_refund_periods = []
            student_period_active: Set[str] = set()   # 该学员有在读科目的期次
            student_period_has_subject: Set[str] = set()  # 该学员有科目（在读+退费）的期次
            # 行级 PV 计数（用于 by_channel 渠道图，与顶部 active_pv/renewed_pv/refund_pv 一致）
            student_line_active = 0
            student_line_renewed = 0
            student_line_refund = 0

            for _key, sd in subjects.items():
                if not isinstance(sd, dict):
                    continue
                subj = get_line_subject(sd, _key)
                # 未知学科（不在 SUBJECTS 配置内）跳过，避免分学科结构 KeyError
                if subj not in by_subj:
                    continue

                # 学科筛选
                if fs.subjects and subj not in fs.subjects:
                    continue
                # 主讲筛选
                teacher = (sd.get('teacher') or '').strip()
                if fs.teachers and teacher not in fs.teachers:
                    continue
                # 班型筛选
                if fs.class_types:
                    cls_type = (sd.get('class_type') or '').strip()
                    if cls_type not in fs.class_types:
                        continue
                # 课程类型筛选（特惠课/系统课）──「已知才排除」：行无 course_type 时不剔除
                if fs.course_type:
                    ct = (sd.get('course_type') or '').strip()
                    if ct and ct not in fs.course_type:
                        continue
                # 产品类型筛选（转化品/正价品）──「已知才排除」：行无 product_type 时不剔除
                if fs.product_type:
                    pt = (sd.get('product_type') or '').strip()
                    if pt and pt not in fs.product_type:
                        continue
                # 课程模式筛选（班课/1v1，来自 M 列 课程模式）
                # class_mode 有 class_type 兜底推断（_upgrade_old_subjects），故仍严格匹配
                if fs.class_mode:
                    cm = norm_class_mode(sd.get('class_mode'))
                    if cm not in fs.class_mode:
                        continue

                # 行级 student_type 筛选（行级优先，与 Excel BS 列口径一致）
                if fs.student_type:
                    line_st = (sd.get('student_type') or '').strip()
                    if line_st and line_st not in set(fs.student_type):
                        continue

                # ── 行级 年份/学季/年级 筛选（订单行数组模型的核心）──
                # 每条 line 自带 year/season/grade；旧格式无则回退学员级值。
                # year 采用「已知才排除」：line 无 year 信息时不因年份筛选被剔除。
                line_year = (sd.get('year') or '').strip() or student_year
                if fs.year and line_year and line_year not in set(fs.year):
                    continue
                line_season = (sd.get('season') or '').strip() or student_season
                if fs.season and line_season not in set(fs.season):
                    continue
                line_grade = (sd.get('grade') or '').strip() or student_grade
                if fs.grade and line_grade not in set(fs.grade):
                    continue

                status = (sd.get('status') or '').strip()
                period_str = (sd.get('period') or '').strip()
                class_id = (sd.get('class_id') or '').strip()
                cf_val = sd.get('continue_fall', '')
                fpt = sd.get('fall_pay_time', '')
                start_date = sd.get('start_date', '')
                plist = _period_list(period_str)

                # ── 教学点：优先行级显式教学点，否则教室推导，再 fallback 学员级 ──
                pt = line_teaching_point(sd, student_pt)
                # 教学点筛选：该行必须落在目标教学点才被统计
                if fs.teaching_point and pt not in fs.teaching_point:
                    continue

                # 期次筛选
                if not fs.all_periods_mode and fs.periods:
                    if not any(p in fs.periods for p in plist):
                        continue

                is_active = '在读' in status
                is_refund = status and status != '-' and '在读' not in status
                is_renewed = is_continue_fall(cf_val)
                # ── 续报率锁定分母口径（BW/AT/BG）──
                is_denom = is_renewal_denom(sd)
                is_renewed_lock = is_renewed_by_source(sd)

                if not (is_active or is_refund):
                    continue

                # ── 行级 在读状态/续报状态 筛选 ──
                # Q7：维度仅 {在读, 退费}；is_refund 已涵盖 出班/有效退费（数据中出班均属退费）
                if fs.enrollment_status:
                    _em_ok = (('在读' in fs.enrollment_status and is_active) or
                              ('退费' in fs.enrollment_status and is_refund))
                    if not _em_ok:
                        continue
                if fs.renewal_status:
                    _target_p = fs.periods[0] if (not fs.all_periods_mode and fs.periods) else (plist[0] if plist else '')
                    _cls = classify_renewal_by_pay_time(fpt, _target_p, start_date=start_date) if is_renewed else 'none'
                    _rm_ok = (('已续报' in fs.renewal_status and is_renewed) or
                              ('未续报' in fs.renewal_status and not is_renewed) or
                              ('开课前续报' in fs.renewal_status and is_renewed and _cls == 'pre') or
                              ('当期转化' in fs.renewal_status and is_renewed and _cls == 'new'))
                    if not _rm_ok:
                        continue

                student_processed_any = True  # 该行进入统计

                # ── 续报率锁定分母口径（BW/AT/BG）── 不受 is_active/is_refund 限制
                if is_denom:
                    total['denom_pv'] += 1
                    denom_uv_set.add(uid)
                    by_subj[subj]['denom'] += 1
                    _tk, _keys = _term_keys(plist, line_season, sd.get('week_cycle') or '')
                    for _k in _keys:
                        _bucket(_tk, _k)['denom_pv'] += 1
                        _bucket(_tk, _k)['denom_uv'].add(uid)
                        _bucket_subj(_tk, _k, subj)['denom'] += 1
                    # 讲师
                    if teacher and teacher != '-':
                        if teacher not in by_teacher:
                            by_teacher[teacher] = {'active': 0, 'renewed': 0, 'refund': 0,
                                                   'pre': 0, 'new': 0, 'denom': 0, 'renewed_lock': 0,
                                                   'subject': subj}
                        by_teacher[teacher]['denom'] += 1
                    # 教学点
                    if pt and pt != '-':
                        if pt not in by_point:
                            by_point[pt] = {'active_pv': 0, 'refund_pv': 0, 'renewed_pv': 0,
                                           'denom_pv': 0, 'renewed_lock_pv': 0,
                                           'active_uv': set(), 'renewed_uv': set(),
                                           'denom_uv': set(), 'renewed_lock_uv': set(),
                                           'classes': set()}
                        by_point[pt]['denom_pv'] += 1
                        by_point[pt]['denom_uv'].add(uid)
                    # 班级
                    if fs.teachers and class_id and class_id != '-':
                        if class_id not in by_class:
                            by_class[class_id] = {'active': 0, 'renewed': 0,
                                                 'denom': 0, 'renewed_lock': 0,
                                                 'uv': set(), 'renewed_uv': set(),
                                                 'denom_uv': set(), 'renewed_lock_uv': set(),
                                                 'subject': subj, 'period': period_str}
                        by_class[class_id]['denom'] += 1
                        by_class[class_id]['denom_uv'].add(uid)
                if is_renewed_lock:
                    total['renewed_lock_pv'] += 1
                    renewed_lock_uv_set.add(uid)
                    by_subj[subj]['renewed_lock'] += 1
                    _tk, _keys = _term_keys(plist, line_season, sd.get('week_cycle') or '')
                    for _k in _keys:
                        _bucket(_tk, _k)['renewed_lock_pv'] += 1
                        _bucket(_tk, _k)['renewed_lock_uv'].add(uid)
                        _bucket_subj(_tk, _k, subj)['renewed_lock'] += 1
                    # 讲师
                    if teacher and teacher != '-':
                        if teacher not in by_teacher:
                            by_teacher[teacher] = {'active': 0, 'renewed': 0, 'refund': 0,
                                                   'pre': 0, 'new': 0, 'denom': 0, 'renewed_lock': 0,
                                                   'subject': subj}
                        by_teacher[teacher]['renewed_lock'] += 1
                    # 教学点
                    if pt and pt != '-':
                        if pt not in by_point:
                            by_point[pt] = {'active_pv': 0, 'refund_pv': 0, 'renewed_pv': 0,
                                           'denom_pv': 0, 'renewed_lock_pv': 0,
                                           'active_uv': set(), 'renewed_uv': set(),
                                           'denom_uv': set(), 'renewed_lock_uv': set(),
                                           'classes': set()}
                        by_point[pt]['renewed_lock_pv'] += 1
                        by_point[pt]['renewed_lock_uv'].add(uid)
                    # 班级
                    if fs.teachers and class_id and class_id != '-':
                        if class_id not in by_class:
                            by_class[class_id] = {'active': 0, 'renewed': 0,
                                                 'denom': 0, 'renewed_lock': 0,
                                                 'uv': set(), 'renewed_uv': set(),
                                                 'denom_uv': set(), 'renewed_lock_uv': set(),
                                                 'subject': subj, 'period': period_str}
                        by_class[class_id]['renewed_lock'] += 1
                        by_class[class_id]['renewed_lock_uv'].add(uid)

                # 续报分类
                renewal_cls = 'pre'
                if is_renewed:
                    target_p = fs.periods[0] if (not fs.all_periods_mode and fs.periods) else (plist[0] if plist else '')
                    renewal_cls = classify_renewal_by_pay_time(fpt, target_p, start_date=start_date)

                if is_active:
                    student_has_active = True
                    student_line_active += 1
                    total['active_pv'] += 1
                    active_uv_set.add(uid)
                    by_subj[subj]['active'] += 1
                    # ── 行级 by_channel 累加（每行按行级 channel_l1/l2 算一次）──
                    line_l1 = (sd.get('channel_l1') or '').strip()
                    line_l2 = (sd.get('channel_l2') or '').strip()
                    if line_l1:
                        if line_l1 not in by_channel_l1:
                            by_channel_l1[line_l1] = {
                                'acquired': 0, 'active_new': 0, 'renewed': 0, 'refunded': 0,
                                'renewal_rate': 0.0, 'total_uv': 0,
                            }
                        by_channel_l1[line_l1]['active_new'] += 1
                    if line_l2:
                        if line_l2 not in by_channel_l2:
                            by_channel_l2[line_l2] = {
                                'acquired': 0, 'active_new': 0, 'renewed': 0, 'refunded': 0,
                                'renewal_rate': 0.0, 'total_uv': 0,
                            }
                        by_channel_l2[line_l2]['active_new'] += 1

                    _tk, _keys = _term_keys(plist, line_season, sd.get('week_cycle') or '')
                    for _k in _keys:
                        if _tk == 'short':
                            student_period_active.add(_k)
                            student_period_has_subject.add(_k)
                        _bucket(_tk, _k)['active_pv'] += 1
                        _bucket(_tk, _k)['active_uv'].add(uid)
                        _bucket_subj(_tk, _k, subj)['active'] += 1

                    # 续报
                    if is_renewed:
                        student_line_renewed += 1
                        total['renewed_pv'] += 1
                        by_subj[subj]['renewed'] += 1
                        student_renewed = True
                        renewed_uv_set.add(uid)
                        # by_channel 行级累加
                        if line_l1:
                            by_channel_l1[line_l1]['renewed'] += 1
                        if line_l2:
                            by_channel_l2[line_l2]['renewed'] += 1
                        if renewal_cls == 'pre':
                            total['pre_pv'] += 1
                            by_subj[subj]['pre'] += 1
                        else:
                            total['new_pv'] += 1
                            by_subj[subj]['new'] += 1

                        for _k in _keys:
                            _bucket(_tk, _k)['renewed_pv'] += 1
                            _bucket(_tk, _k)['renewed_uv'].add(uid)
                            _bucket_subj(_tk, _k, subj)['renewed'] += 1
                            if renewal_cls == 'pre':
                                _bucket(_tk, _k)['pre_pv'] += 1
                            else:
                                _bucket(_tk, _k)['new_pv'] += 1

                    # 讲师
                    if teacher and teacher != '-':
                        if teacher not in by_teacher:
                            by_teacher[teacher] = {'active': 0, 'renewed': 0, 'refund': 0,
                                                   'pre': 0, 'new': 0, 'denom': 0, 'renewed_lock': 0,
                                                   'subject': subj}
                        by_teacher[teacher]['active'] += 1
                        if is_renewed:
                            by_teacher[teacher]['renewed'] += 1
                            if renewal_cls == 'pre':
                                by_teacher[teacher]['pre'] += 1
                            else:
                                by_teacher[teacher]['new'] += 1

                    # 教学点
                    if pt and pt != '-':
                        if pt not in by_point:
                            by_point[pt] = {'active_pv': 0, 'refund_pv': 0, 'renewed_pv': 0,
                                           'denom_pv': 0, 'renewed_lock_pv': 0,
                                           'active_uv': set(), 'renewed_uv': set(),
                                           'denom_uv': set(), 'renewed_lock_uv': set(),
                                           'classes': set()}
                        by_point[pt]['active_pv'] += 1
                        by_point[pt]['active_uv'].add(uid)
                        if class_id and class_id != '-':
                            by_point[pt]['classes'].add(class_id)
                        if is_renewed:
                            by_point[pt]['renewed_pv'] += 1
                            by_point[pt]['renewed_uv'].add(uid)

                    # 班级
                    if fs.teachers and class_id and class_id != '-':
                        if class_id not in by_class:
                            by_class[class_id] = {'active': 0, 'renewed': 0,
                                                 'denom': 0, 'renewed_lock': 0,
                                                 'uv': set(), 'renewed_uv': set(),
                                                 'denom_uv': set(), 'renewed_lock_uv': set(),
                                                 'subject': subj, 'period': period_str}
                        by_class[class_id]['active'] += 1
                        by_class[class_id]['uv'].add(uid)
                        if is_renewed:
                            by_class[class_id]['renewed'] += 1
                            by_class[class_id]['renewed_uv'].add(uid)

                elif is_refund:
                    student_line_refund += 1
                    total['refund_pv'] += 1
                    by_subj[subj]['refund'] += 1
                    # by_channel 行级累加
                    line_l1 = (sd.get('channel_l1') or '').strip()
                    line_l2 = (sd.get('channel_l2') or '').strip()
                    if line_l1:
                        if line_l1 not in by_channel_l1:
                            by_channel_l1[line_l1] = {
                                'acquired': 0, 'active_new': 0, 'renewed': 0, 'refunded': 0,
                                'renewal_rate': 0.0, 'total_uv': 0,
                            }
                        by_channel_l1[line_l1]['refunded'] += 1
                    if line_l2:
                        if line_l2 not in by_channel_l2:
                            by_channel_l2[line_l2] = {
                                'acquired': 0, 'active_new': 0, 'renewed': 0, 'refunded': 0,
                                'renewal_rate': 0.0, 'total_uv': 0,
                            }
                        by_channel_l2[line_l2]['refunded'] += 1
                    _tk, _keys = _term_keys(plist, line_season, sd.get('week_cycle') or '')
                    for _k in _keys:
                        if _tk == 'short':
                            student_period_has_subject.add(_k)
                        _bucket(_tk, _k)['refund_pv'] += 1
                        student_refund_periods.append(_k)
                    if teacher and teacher != '-':
                        if teacher not in by_teacher:
                            by_teacher[teacher] = {'active': 0, 'renewed': 0, 'refund': 0,
                                                   'pre': 0, 'new': 0, 'denom': 0, 'renewed_lock': 0,
                                                   'subject': subj}
                        by_teacher[teacher]['refund'] += 1
                    if pt and pt != '-':
                        if pt not in by_point:
                            by_point[pt] = {'active_pv': 0, 'refund_pv': 0, 'renewed_pv': 0,
                                           'denom_pv': 0, 'renewed_lock_pv': 0,
                                           'active_uv': set(), 'renewed_uv': set(),
                                           'denom_uv': set(), 'renewed_lock_uv': set(),
                                           'classes': set()}
                        by_point[pt]['refund_pv'] += 1

                # 顾问维度（在读科目才计入）
                if is_active:
                    if advisor not in by_advisor:
                        by_advisor[advisor] = {
                            'uv': {'active': set(), 'pre': set(), 'new': set(),
                                   'denom': set(), 'renewed_lock': set()},
                            'pv': {'active': 0, 'pre': 0, 'new': 0,
                                   'denom': 0, 'renewed_lock': 0},
                            'teaching_point': student_pt,  # 顾问工作地点（学员级教学点）
                        }
                    by_advisor[advisor]['uv']['active'].add(uid)
                    by_advisor[advisor]['pv']['active'] += 1
                    if is_renewed:
                        if renewal_cls == 'new':
                            by_advisor[advisor]['uv']['new'].add(uid)
                            by_advisor[advisor]['pv']['new'] += 1
                        else:
                            by_advisor[advisor]['uv']['pre'].add(uid)
                            by_advisor[advisor]['pv']['pre'] += 1
                    # 续报率锁定分母口径（顾问维度）
                    if is_denom:
                        by_advisor[advisor]['uv']['denom'].add(uid)
                        by_advisor[advisor]['pv']['denom'] += 1
                    if is_renewed_lock:
                        by_advisor[advisor]['uv']['renewed_lock'].add(uid)
                        by_advisor[advisor]['pv']['renewed_lock'] += 1

            if not student_processed_any:
                continue  # 没有任何科目通过筛选，该学员不进入统计

            uid_any_active[uid] = student_has_active
            uid_refund_periods[uid] = student_refund_periods
            uid_period_active[uid] = student_period_active
            uid_period_has_subject[uid] = student_period_has_subject

            # ── 分渠道统计（拉新×转化效率）──
            # acquired / total_uv 学员级（按 uid 去重）；
            # active_new / renewed / refunded 已在 is_active/is_refund 块中按行级累加（行级 channel_l1/l2）。
            # 这里不再重复累加 PV，只补充 acquired / total_uv / 续报率（按学员级 channel）。
            l1 = (row.get('channel_l1') or '').strip()
            l2 = (row.get('channel') or '').strip()
            for ch_key, by_dict, seen_dict in [
                (l1, by_channel_l1, seen_uid_l1),
                (l2, by_channel_l2, seen_uid_l2),
            ]:
                if not ch_key:
                    continue
                if ch_key not in by_dict:
                    by_dict[ch_key] = {
                        'acquired': 0, 'active_new': 0, 'renewed': 0, 'refunded': 0,
                        'renewal_rate': 0.0,
                        'total_uv': 0,
                    }
                if ch_key not in seen_dict:
                    seen_dict[ch_key] = set()
                if uid in seen_dict[ch_key]:
                    continue
                seen_dict[ch_key].add(uid)
                by_dict[ch_key]['total_uv'] += 1
                if _st_main == '新生':
                    by_dict[ch_key]['acquired'] += 1
                # 续报率 = 已续 / 在读
                by_dict[ch_key]['renewal_rate'] = _safe_rate(
                    by_dict[ch_key]['renewed'],
                    by_dict[ch_key]['active_new'],
                )

        # ── 退费UV归属（逐期独立判断）──
        # 规则：对于每个学员的每个期次，如果该学员在该期次有科目但该期次没有在读科目，
        #       就计为该期次退费UV。总退费UV仍然是三科全退。
        # 结果：各期退费UV之和 ≥ 总退费UV（一个学员可同时归属多个期次）
        # 关键修复：当按具体期次筛选时，总退费UV应限定为所选期次的退费UV并集，
        #       而不是全局无在读学员（避免一期筛选时把其他期次在读学员也计为退费）。
        refund_uv_set: Set[str] = set()
        period_refund_uv = {p: set() for p in PERIOD_ORDER}
        for uid, has_active in uid_any_active.items():
            if not has_active:
                refund_uv_set.add(uid)
            period_active = uid_period_active.get(uid, set())
            period_has = uid_period_has_subject.get(uid, set())
            for p in period_has:
                if p not in period_active:
                    _bucket_refund('short', p).add(uid)

        # 按具体期次筛选时：总退费UV = 所选期次退费UV的并集
        if not fs.all_periods_mode and fs.periods:
            refund_uv_set = set()
            for p in fs.periods:
                if p in period_refund_uv:
                    refund_uv_set.update(period_refund_uv[p])

        # ── 汇总输出 ──
        active_uv = len(active_uv_set)
        refund_uv = len(refund_uv_set)
        total_uv = active_uv + refund_uv
        total_renewed_uv = len(renewed_uv_set)
        total_denom_uv = len(denom_uv_set)
        total_renewed_lock_uv = len(renewed_lock_uv_set)

        # 分学科续报率（锁定分母口径）
        subj_rates = {}
        for s in SUBJECTS:
            d = by_subj[s]
            subj_rates[s] = _safe_rate(d['renewed_lock'], d['denom'])

        # 分学科×分期次续报率（锁定分母口径）
        subj_period_rates = {}
        for s in SUBJECTS:
            rates = {}
            for p in subj_period[s]:
                dn = subj_period[s][p]['denom']
                rl = subj_period[s][p]['renewed_lock']
                rates[p] = _safe_rate(rl, dn)
            subj_period_rates[s] = rates

        # 分期次UV量化 + PV续报率/退费率各分量
        # ⚠️ 双轨输出：by_period（短学期期次 5 keys）+ by_weekday（长学期星期 7 keys）
        # 前端根据 period_config.term_type 决定显示哪个维度
        period_out = {}
        weekday_out = {}

        def _emit(target_dict, term_kind, key, d):
            """写入某个维度桶，empty 兜底"""
            a_pv = d['active_pv']
            r_pv = d['renewed_pv']
            pre_pv = d['pre_pv']
            new_pv = d['new_pv']
            ref_pv = d['refund_pv']
            dn_pv = d['denom_pv']
            rl_pv = d['renewed_lock_pv']
            a_uv = len(d['active_uv'])
            r_uv = len(d['renewed_uv'])
            dn_uv = len(d['denom_uv'])
            rl_uv = len(d['renewed_lock_uv'])
            # period_refund_uv 仅记录短学期期次 key
            ref_uv = len(period_refund_uv[key]) if term_kind == 'short' and key in period_refund_uv else 0
            target_dict[key] = {
                'term_kind': term_kind,
                # PV维度
                'active_pv': a_pv, 'refund_pv': ref_pv,
                'renewed_pv': r_pv, 'pre_renewed_pv': pre_pv, 'new_renewed_pv': new_pv,
                'denom_pv': dn_pv, 'renewed_lock_pv': rl_pv,
                'pv_renewal_rate': _safe_rate(rl_pv, dn_pv),
                'pv_pre_renewal_rate': _safe_rate(pre_pv, a_pv),
                'pv_conv_rate': _safe_rate(new_pv, a_pv - pre_pv),
                'pv_refund_rate': _safe_rate(ref_pv, a_pv + ref_pv),
                # UV维度
                'active_uv': a_uv, 'renewed_uv': r_uv,
                'denom_uv': dn_uv, 'renewed_lock_uv': rl_uv,
                'refund_uv': ref_uv, 'total_uv': a_uv + ref_uv,
                'uv_renewal_rate': _safe_rate(rl_uv, dn_uv),
                'uv_refund_rate': _safe_rate(ref_uv, a_uv + ref_uv),
                # 兼容旧字段
                'renewal_rate': _safe_rate(rl_pv, dn_pv),
                'refund_rate': _safe_rate(ref_pv, a_pv + ref_pv),
            }

        # 短学期：只输出实际有数据的期次（按分校/按筛选动态——该分校没有的期次不显示）
        # ⚠️ 按 PERIOD_ORDER 顺序排（零/一/二/三/四），不按数据首次出现顺序
        for k in sorted(by_period.keys(), key=lambda x: PERIOD_ORDER.index(x) if x in PERIOD_ORDER else 999):
            _emit(period_out, 'short', k, by_period[k])

        # 长学期：只输出实际有数据的星期（按 WEEKDAY_ORDER 排：一/二/三/四/五/六/日）
        for k in sorted(by_weekday.keys(), key=lambda x: WEEKDAY_ORDER.index(x) if x in WEEKDAY_ORDER else 999):
            _emit(weekday_out, 'long', k, by_weekday[k])

        # 讲师排行（字段与顾问排行统一命名）
        teacher_list = []
        # BUG 修复：系统课没有"应续"和"当期转化"概念（仅特惠课区分 pre/new）
        # 根据当前筛选的 course_type 动态返回正确格式
        ct = filter_spec.course_type if hasattr(filter_spec, 'course_type') else []
        is_system_only = bool(ct) and all(c == '系统课' for c in ct)
        for t, d in by_teacher.items():
            if not t or t == '-': continue
            a = d['active']
            pre = d['pre']
            new = d['new']
            total_ren = d['renewed']
            should = a - pre
            dn = d['denom']
            rl = d['renewed_lock']
            if is_system_only:
                # 系统课：无应续/转化细分，pre/should/new 归零
                item = {
                    'name': t, 'subject': d['subject'],
                    'active': a, 'renewed': rl,
                    'should_renew': 0,
                    'pre_renewed': 0, 'new_renewed': 0, 'total_renewed': rl,
                    'denom': dn, 'renewed_lock': rl,
                    'renewal_rate': _safe_rate(rl, dn),
                    'conv_rate': 0,
                    'active_pv': a, 'renewed_pv': rl, 'refund_pv': d['refund'],
                    'pre_renewed_pv': 0, 'new_renewed_pv': 0,
                    'active_count': a, 'renewed_count': rl,
                }
            else:
                item = {
                    'name': t, 'subject': d['subject'],
                    # UV维度（学员人次，统一命名）
                    'active': a, 'renewed': total_ren,
                    'should_renew': should,
                    'pre_renewed': pre, 'new_renewed': new, 'total_renewed': total_ren,
                    'denom': dn, 'renewed_lock': rl,
                    'renewal_rate': _safe_rate(rl, dn),
                    'conv_rate': _safe_rate(new, should),
                    # 兼容旧字段
                    'active_pv': a, 'renewed_pv': total_ren, 'refund_pv': d['refund'],
                    'pre_renewed_pv': pre, 'new_renewed_pv': new,
                    'active_count': a, 'renewed_count': total_ren,
                }
            teacher_list.append(item)
        teacher_list.sort(key=lambda x: x['renewal_rate'], reverse=True)

        # 顾问排行（UV+PV双维度，字段与主讲排行统一命名）
        advisor_list = []
        # 动态构建顾问→教学点映射（可扩展，优于硬编码）
        advisor_point_map = {}
        for a, agg in by_advisor.items():
            uv_a = len(agg['uv']['active'])
            uv_pre = len(agg['uv']['pre'])
            uv_new = len(agg['uv']['new'])
            uv_dn = len(agg['uv']['denom'])
            uv_rl = len(agg['uv']['renewed_lock'])
            pv_a = agg['pv']['active']
            pv_pre = agg['pv']['pre']
            pv_new = agg['pv']['new']
            pv_dn = agg['pv']['denom']
            pv_rl = agg['pv']['renewed_lock']
            should_uv = uv_a - uv_pre
            should_pv = pv_a - pv_pre
            # 从学员数据中提取该顾问的教学点（动态，优于硬编码）
            advisor_pt = agg.get('teaching_point', '')
            if advisor_pt:
                advisor_point_map[a] = advisor_pt
            advisor_list.append({
                'name': a,
                # UV维度（学员人数）
                'active': uv_a, 'should_renew': should_uv,
                'pre_renewed': uv_pre, 'new_renewed': uv_new,
                'total_renewed': uv_pre + uv_new,
                'denom': uv_dn, 'renewed_lock': uv_rl,
                'renewal_rate': _safe_rate(uv_rl, uv_dn),
                # PV维度（学员人次）
                'pv_active': pv_a, 'pv_should_renew': should_pv,
                'pv_pre_renewed': pv_pre, 'pv_new_renewed': pv_new,
                'pv_total_renewed': pv_pre + pv_new,
                'pv_denom': pv_dn, 'pv_renewed_lock': pv_rl,
                'pv_renewal_rate': _safe_rate(pv_rl, pv_dn),
                # 动态教学点标签
                'teaching_point': advisor_pt,
            })
        advisor_list.sort(key=lambda x: x['renewal_rate'], reverse=True)

        # 教学点
        point_list = []
        for pt, d in by_point.items():
            if not pt: continue
            point_list.append({
                'name': pt, 'active_pv': d['active_pv'], 'refund_pv': d['refund_pv'],
                'renewed_pv': d['renewed_pv'],
                'denom_pv': d['denom_pv'], 'renewed_lock_pv': d['renewed_lock_pv'],
                'uv': len(d['active_uv']), 'renewed_uv': len(d['renewed_uv']),
                'denom_uv': len(d['denom_uv']), 'renewed_lock_uv': len(d['renewed_lock_uv']),
                'class_count': len(d['classes']),
                'renewal_rate': _safe_rate(d['renewed_lock_pv'], d['denom_pv']),
                'renewal_uv_rate': _safe_rate(len(d['renewed_lock_uv']), len(d['denom_uv'])),
            })

        # 班级
        class_list = []
        for cid, d in by_class.items():
            class_list.append({
                'class_id': cid,
                'subject': SUBJECT_LABEL.get(d['subject'], d['subject']),
                'period': d.get('period', '-'),
                'active': d['active'], 'renewed': d['renewed'],
                'denom': d['denom'], 'renewed_lock': d['renewed_lock'],
                'uv': len(d['uv']), 'renewed_uv': len(d['renewed_uv']),
                'denom_uv': len(d['denom_uv']), 'renewed_lock_uv': len(d['renewed_lock_uv']),
                'renewal_rate': _safe_rate(d['renewed_lock'], d['denom']),
                'renewal_uv_rate': _safe_rate(len(d['renewed_lock_uv']), len(d['denom_uv'])),
            })

        # 学科列表（用于前端chip）
        subject_list = []
        for s in SUBJECTS:
            d = by_subj[s]
            subject_list.append({
                'name': s, 'key': s,
                'active': d['active'], 'renewed': d['renewed'], 'refund': d['refund'],
                'denom': d['denom'], 'renewed_lock': d['renewed_lock'],
                'renewal_rate': subj_rates[s], 'color': SUBJECT_COLOR[s],
            })

        return {
            'total_uv': total_uv, 'active_uv': active_uv, 'refund_uv': refund_uv,
            'active_pv': total['active_pv'], 'refund_pv': total['refund_pv'],
            'renewed_pv': total['renewed_pv'],
            'pre_renewed_pv': total['pre_pv'], 'new_renewed_pv': total['new_pv'],
            'denom_pv': total['denom_pv'], 'renewed_lock_pv': total['renewed_lock_pv'],
            'total_renewal_rate': _safe_rate(total['renewed_lock_pv'], total['denom_pv']),
            'total_refund_rate': _safe_rate(total['refund_pv'], total['active_pv'] + total['refund_pv']),
            'total_renewed_uv': total_renewed_uv,
            'total_renewal_uv_rate': _safe_rate(total_renewed_lock_uv, total_denom_uv),
            'total_denom_uv': total_denom_uv, 'total_renewed_lock_uv': total_renewed_lock_uv,

            'by_subject': subject_list,
            'by_period': period_out,
            'by_weekday': weekday_out,  # 长学期按周X分桶
            'by_teacher': teacher_list,
            'by_advisor': advisor_list,
            'by_point': point_list,
            'by_class': class_list,
            'by_channel_l1': by_channel_l1,  # 拉新×转化效率（按一级渠道 AL 列）
            'by_channel_l2': by_channel_l2,  # 拉新×转化效率（按二级渠道 AM 列）

            'renewal_rate_by_period': subj_period_rates,
            'subject_period_renewal': subj_period_rates,

            # 期次配置（供前端动态渲染）
            'period_config': {
                'order': PERIOD_ORDER,
                'schedule': {p: {'start': f'{PERIOD_SCHEDULE[p]["start"][0]}/{PERIOD_SCHEDULE[p]["start"][1]}',
                                  'end': f'{PERIOD_SCHEDULE[p]["end"][0]}/{PERIOD_SCHEDULE[p]["end"][1]}',
                                  'note': PERIOD_SCHEDULE[p].get('note', '')}
                            for p in PERIOD_ORDER},
                'current': auto_detect_period(),
                # 学期类型：当前查询覆盖的学期集合
                # 'short_term' = 全部短学期(寒/暑) → 显示期次 chip
                # 'long_term'  = 全部长学期(春/秋) → 显示星期 chip
                # 'mixed'      = 短+长混合 → 同时显示两套 chip
                # 'empty'      = 无学期筛选
                'term_type': (
                    'mixed' if (by_period and by_weekday)
                    else 'short_term' if by_period
                    else 'long_term' if by_weekday
                    else 'empty'
                ),
                # 卡片底部小字 chip 显示策略
                # 'short_chips' = 显示 5 个短学期期次 chip（按分校实际数据过滤）
                # 'none'        = 不显示 chip（用户要求：春秋不显示）
                # 'short_only'  = mixed 时只显示短学期 chip（长学期不显示）
                'chip_display': (
                    'short_only' if (by_period and by_weekday)
                    else 'short_chips' if by_period
                    else 'none'  # 长学期或空：都不显示
                ),
                'available_dimensions': {
                    'period': bool(by_period),
                    'weekday': bool(by_weekday),
                },
                'weekday_order': WEEKDAY_ORDER,
            },

            # 筛选器配置（供前端动态渲染）
            'filter_config': FILTER_CONFIG,

            # 旧字段兼容
            'total': total_uv, 'active': active_uv, 'refund': refund_uv,
        }

    def compute_trends(self, run_rows, students_by_run, filter_spec=None):
        """趋势数据：按天聚合，同一天只保留最新校准"""
        if filter_spec is None:
            filter_spec = FilterSpec()

        # 按天去重：同一天只保留 run_time 最大的校准
        latest_by_day = {}
        for run in run_rows:
            day = (run.get('run_time') or '')[:10]
            if not day:
                continue
            rt_full = run.get('run_time') or ''
            if day not in latest_by_day or rt_full > latest_by_day[day].get('run_time', ''):
                latest_by_day[day] = run

        # 按日期升序排列（趋势图时间轴从左到右）
        deduped_runs = sorted(latest_by_day.values(), key=lambda r: r.get('run_time') or '')

        trends = []
        for run in deduped_runs:
            rid = run['run_id']
            students = students_by_run.get(rid, [])
            result = self.compute(students, filter_spec)
            trends.append({
                'run_id': rid,
                'run_time': (run.get('run_time') or '')[:10],
                'total_uv': result['total_uv'],
                'active_pv': result['active_pv'],
                'refund_pv': result['refund_pv'],
                'renewal_pv': result['renewed_pv'],
                'new_count': run.get('new_students', 0) or run.get('total_students', 0),
                'by_subject': {
                    s: {'active': result['by_subject'][i]['active'] if i < len(result['by_subject']) else 0,
                        'refund': result['by_subject'][i]['refund'] if i < len(result['by_subject']) else 0,
                        'renewal': result['by_subject'][i]['renewed'] if i < len(result['by_subject']) else 0}
                    for i, s in enumerate(SUBJECTS)
                },
            })
        return trends

    def compute_trends_by_paytime(self, student_rows, filter_spec=None):
        """基于订单支付时间推算每日累计趋势（单次上传即可生成完整趋势）。

        核心思路：
        - 每条订单行有 pay_time（支付时间），按 pay_time 排序后逐日累计
        - 截止某日 D：pay_time <= D 的订单行计入统计
        - status/续报等取当前快照值（不做历史回溯，因底表无历史状态变更记录）

        输出：按天聚合的累计趋势数组（同 compute_trends 格式）
        """
        from datetime import datetime as _dt

        if filter_spec is None:
            filter_spec = FilterSpec()

        # ── Step1：收集所有通过筛选的订单行 + pay_time ──
        lines_with_pay = []  # [(pay_date_str, uid, is_active, is_refund, is_renewed, subj_idx)]
        seen_uids = set()

        for row in student_rows:
            uid = (row.get('uid') or '').strip()
            if not uid:
                continue
            # 分校筛选（学员级）
            if filter_spec.branch:
                sb = (row.get('branch') or '').strip()
                if sb not in set(filter_spec.branch):
                    continue
            subjects = row.get('subjects_json')
            if isinstance(subjects, str):
                try:
                    subjects = json.loads(subjects)
                except Exception:
                    subjects = {}
            if not isinstance(subjects, dict):
                continue

            # 学员级 student_type 聚合（行级优先筛）
            _st_set = set()
            for _sd in subjects.values():
                if isinstance(_sd, dict):
                    _st_val = (_sd.get('student_type') or '').strip()
                    if _st_val:
                        _st_set.add(_st_val)
            if _st_set:
                if '老生拓科' in _st_set:
                    _st_main = '老生拓科'
                elif '老生' in _st_set:
                    _st_main = '老生'
                elif '新生' in _st_set:
                    _st_main = '新生'
                else:
                    _st_main = ''
            else:
                _st_main = ''
            if filter_spec.student_type:
                if not (_st_set & set(filter_spec.student_type)):
                    continue

            student_grade = (row.get('grade') or '').strip()
            student_season = (row.get('season') or '').strip()
            student_year = (row.get('year') or '').strip()
            student_pt = (row.get('teaching_point') or '').strip()

            for _key, sd in subjects.items():
                if not isinstance(sd, dict):
                    continue
                subj = get_line_subject(sd, _key)
                if subj not in SUBJECTS:
                    continue
                subj_idx = SUBJECTS.index(subj)

                # 应用行级筛选（同 compute 的逻辑）
                if filter_spec.subjects and subj not in filter_spec.subjects:
                    continue
                teacher = (sd.get('teacher') or '').strip()
                if filter_spec.teachers and teacher not in filter_spec.teachers:
                    continue
                if filter_spec.class_types:
                    cls_type = (sd.get('class_type') or '').strip()
                    if cls_type not in filter_spec.class_types:
                        continue
                if filter_spec.course_type:
                    ct = (sd.get('course_type') or '').strip()
                    if ct and ct not in filter_spec.course_type:
                        continue
                if filter_spec.product_type:
                    pt_val = (sd.get('product_type') or '').strip()
                    if pt_val and pt_val not in filter_spec.product_type:
                        continue
                if filter_spec.class_mode:
                    cm = norm_class_mode(sd.get('class_mode'))
                    if cm not in filter_spec.class_mode:
                        continue
                if filter_spec.student_type:
                    line_st = (sd.get('student_type') or '').strip()
                    if line_st and line_st not in set(filter_spec.student_type):
                        continue

                line_year = (sd.get('year') or '').strip() or student_year
                if filter_spec.year and line_year and line_year not in set(filter_spec.year):
                    continue
                line_season = (sd.get('season') or '').strip() or student_season
                if filter_spec.season and line_season not in set(filter_spec.season):
                    continue
                line_grade = (sd.get('grade') or '').strip() or student_grade
                if filter_spec.grade and line_grade not in set(filter_spec.grade):
                    continue

                status = (sd.get('status') or '').strip()
                period_str = (sd.get('period') or '').strip()
                pt_val = line_teaching_point(sd, student_pt)
                if filter_spec.teaching_point and pt_val not in filter_spec.teaching_point:
                    continue
                plist = _period_list(period_str)
                if not filter_spec.all_periods_mode and filter_spec.periods:
                    if not any(p in filter_spec.periods for p in plist):
                        continue
                if filter_spec.enrollment_status:
                    is_active = '在读' in status
                    is_refund = status and status != '-' and '在读' not in status
                    if not (('在读' in filter_spec.enrollment_status and is_active) or
                            ('退费' in filter_spec.enrollment_status and is_refund)):
                        continue

                # 解析 pay_time（拉新事件时间）
                pay_time_str = (sd.get('pay_time') or '').strip()
                if not pay_time_str:
                    continue
                pay_dt = _parse_pay_time_safe(pay_time_str)
                if pay_dt is None:
                    continue
                pay_date = pay_dt.strftime('%Y-%m-%d')
                is_active = '在读' in status
                is_refund = bool(status and status != '-' and '在读' not in status)
                # BUG 修复：续报率分母 = renew_denom_incl=1 或 fallback 在读行
                is_denom = is_renewal_denom(sd)
                cf_val = sd.get('continue_fall', '')
                is_renewed = is_continue_fall(cf_val)
                # 解析续报事件时间 fall_pay_time（续费订单的支付时间）
                fall_pay_date = pay_date  # 默认 fall back 到 pay_time
                if is_renewed:
                    fall_pay_str = (sd.get('fall_pay_time') or '').strip()
                    if fall_pay_str:
                        fall_pay_dt = _parse_pay_time_safe(fall_pay_str)
                        if fall_pay_dt:
                            fall_pay_date = fall_pay_dt.strftime('%Y-%m-%d')

                lines_with_pay.append((pay_date, pay_dt, uid, is_active, is_refund, is_renewed, is_denom, subj_idx, fall_pay_date))

        if not lines_with_pay:
            return []

        # ── Step2：分离拉新和续报两个时间维度，分别累计 ──
        # 拉新/在读累计：按 pay_time（拉新事件时间）
        # 续报累计：按 fall_pay_time（续报事件时间 = 续费订单支付时间）
        # 这样续报率才反映"截止该日已发生的续报"，而不是当前快照

        # 按 pay_time 分组（拉新事件）
        daily_pay = {}  # date -> list of (uid, is_active, is_refund, is_denom, subj_idx)
        # 按 fall_pay_time 分组（续报事件）
        daily_renew = {}  # date -> list of (uid, subj_idx)
        for pay_date, pay_dt, uid, is_active, is_refund, is_renewed, is_denom, subj_idx, fall_pay_date in lines_with_pay:
            daily_pay.setdefault(pay_date, []).append((uid, is_active, is_refund, is_denom, subj_idx))
            if is_renewed:
                daily_renew.setdefault(fall_pay_date, []).append((uid, subj_idx))

        # 默认窗口：以"今天"为基准，向前 7 个自然日
        from datetime import datetime as _dt, timedelta as _td
        end_date = _dt.now().date()
        start_date = end_date - _td(days=6)
        natural_day_strs = [(start_date + _td(days=i)).strftime('%Y-%m-%d') for i in range(7)]

        # Fallback：若窗口内全无任何事件，回退到最晚支付日的近7个自然日
        has_data_in_window = any(daily_pay.get(d) or daily_renew.get(d) for d in natural_day_strs)
        if not has_data_in_window and lines_with_pay:
            latest_pay_date = lines_with_pay[-1][1].date()
            fb_end = latest_pay_date
            fb_start = fb_end - _td(days=6)
            natural_day_strs = [(fb_start + _td(days=i)).strftime('%Y-%m-%d') for i in range(7)]

        # 累计从窗口前所有事件开始（保证最终值 = stats API 当前值）
        trends = []
        # 累计：拉新/在读按 pay_time 累计；续报按 fall_pay_time 累计
        # BUG 修复：续报率分母改为 denom_pv（按 renew_denom_incl 口径），
        # 避免续报率超过 100%（用 active_pv 当分母在多科目场景会偏小）
        cum_total_uv = 0
        cum_active_pv = 0
        cum_refund_pv = 0
        cum_renewal_pv = 0
        cum_denom_pv = 0
        cum_by_subj = [{'active': 0, 'refund': 0, 'renewal': 0, 'denom': 0} for _ in SUBJECTS]
        seen_uids_cum = set()

        if natural_day_strs:
            window_start_str = natural_day_strs[0]
            # 累计窗口前所有 pay_time 事件
            for day_str, day_lines in daily_pay.items():
                if day_str < window_start_str:
                    for uid, is_active, is_refund, is_denom, subj_idx in day_lines:
                        if uid not in seen_uids_cum:
                            seen_uids_cum.add(uid)
                            cum_total_uv += 1
                        if is_active:
                            cum_active_pv += 1
                            cum_by_subj[subj_idx]['active'] += 1
                        elif is_refund:
                            cum_refund_pv += 1
                            cum_by_subj[subj_idx]['refund'] += 1
                        if is_denom:
                            cum_denom_pv += 1
                            cum_by_subj[subj_idx]['denom'] += 1
            # 累计窗口前所有 fall_pay_time 续报事件
            for day_str, day_lines in daily_renew.items():
                if day_str < window_start_str:
                    for uid, subj_idx in day_lines:
                        cum_renewal_pv += 1
                        cum_by_subj[subj_idx]['renewal'] += 1

        for day_str in natural_day_strs:
            day_new = 0
            # 拉新/在读累计（按 pay_time）
            for uid, is_active, is_refund, is_denom, subj_idx in daily_pay.get(day_str, []):
                if uid not in seen_uids_cum:
                    seen_uids_cum.add(uid)
                    cum_total_uv += 1
                    day_new += 1
                if is_active:
                    cum_active_pv += 1
                    cum_by_subj[subj_idx]['active'] += 1
                elif is_refund:
                    cum_refund_pv += 1
                    cum_by_subj[subj_idx]['refund'] += 1
                if is_denom:
                    cum_denom_pv += 1
                    cum_by_subj[subj_idx]['denom'] += 1
            # 续报累计（按 fall_pay_time）
            for uid, subj_idx in daily_renew.get(day_str, []):
                cum_renewal_pv += 1
                cum_by_subj[subj_idx]['renewal'] += 1

            trends.append({
                'run_id': f'paytime_{day_str}',
                'run_time': day_str,
                'total_uv': cum_total_uv,
                'active_pv': cum_active_pv,
                'refund_pv': cum_refund_pv,
                'renewal_pv': cum_renewal_pv,
                'denom_pv': cum_denom_pv,  # BUG 修复：续报率分母
                'new_count': day_new,
                'by_subject': {
                    s: {'active': cum_by_subj[i]['active'],
                        'refund': cum_by_subj[i]['refund'],
                        'renewal': cum_by_subj[i]['renewal'],
                        'denom': cum_by_subj[i]['denom']}
                    for i, s in enumerate(SUBJECTS)
                },
            })

        return trends
