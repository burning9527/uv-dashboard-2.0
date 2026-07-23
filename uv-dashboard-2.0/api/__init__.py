"""
UV Dashboard 2.0 — 薄API路由层
每个路由仅5-15行，调用 engine.compute() 或 repo 函数获取数据并返回。
所有业务逻辑在 engine 层，路由层只做参数提取 + 序列化。
"""

import json
import os
import sys
import traceback
import uuid
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template, send_file, Response
import json as _json


def jsonify_ordered(data):
    """保留 dict key 插入顺序的 jsonify（Flask 默认 jsonify 会按 key 排序）。

    用于需要保持 by_period / by_weekday 等按 PERIOD_ORDER / WEEKDAY_ORDER 顺序的场景。
    """
    return Response(_json.dumps(data, ensure_ascii=False, separators=(',', ':')),
                    mimetype='application/json')

from engine import MetricsEngine, FilterSpec
from engine.calibrator import (
    calibrate, generate_calibrated_ledger, generate_calibration_report,
)
from engine.order_detail_loader import import_to_production
from repository import (
    get_latest_run, get_all_runs, get_run_by_id, get_latest_students,
    get_student_detail, get_daily_stats, get_changes_by_run,
    get_filter_options, get_period_point_matrix, get_teacher_list,
    get_teacher_detail, get_class_schedule, get_filtered_students,
    get_advisor_detail,
    save_calibration_run, save_calibration_metadata, get_class_detail, get_student_detail_enhanced,
    merge_students_by_branch,
    get_acquisition_trends, get_data_dir, get_db,
    get_current_run_id, set_current_run_id, clear_current_run_id, get_pinned_run_id,
    rebuild_active_run, get_meta_value, set_meta_value,
)
from exporter import export_excel
from config import (
    DEFAULT_PORT, SUBJECTS, SUBJECT_COLOR, SUBJECT_LABEL, PERIOD_ORDER, PERIOD_SCHEDULE, auto_detect_period,
    get_advisor_tag, get_advisor_tag_color,
    is_continue_fall, classify_renewal_by_pay_time, is_renewal_denom, is_renewed_by_source,
    _is_cf, _detect_subj_period, _compute_filtered_new_count,
    get_line_subject, norm_class_mode,
    FILTER_CONFIG, FILTER_DEFAULTS,
)

# 学科显示名映射（前端展示用：雪球思维→数学）
subj_labels = SUBJECT_LABEL


engine = MetricsEngine()


# ═══════════════════════════════════════════════════════════════
# Overview Blueprint — 数据总览 + 筛选 + 矩阵 + 排行 + 趋势
# ═══════════════════════════════════════════════════════════════

overview_bp = Blueprint('overview', __name__)


def _get_run_id():
    """获取当前最新 run_id"""
    latest = get_latest_run()
    if latest is None:
        return None
    return latest['run']['run_id']


def _csv_list(s):
    """逗号分隔字符串 → 列表；空/None 返回 None（表示全选）"""
    if not s:
        return None
    return [x.strip() for x in s.split(',') if x.strip()]


@overview_bp.route('/api/overview/stats')
def api_overview_stats():
    """总览统计 — 核心指标，调用引擎一次计算全维度"""
    latest = get_latest_run()
    if not latest:
        return jsonify({'error': 'No data'})
    run_id = latest['run']['run_id']
    run_time = latest['run'].get('run_time', '')
    students = get_latest_students()
    fs = FilterSpec.from_params(
        period=request.args.get('period', ''),
        teaching_point=request.args.get('teaching_point', ''),
        teacher=request.args.get('teacher', ''),
        subject=request.args.get('subject', ''),
        advisor=request.args.get('advisor', ''),
        year=request.args.get('year', ''),
        season=request.args.get('season', ''),
        branch=request.args.get('branch', ''),
        grade=request.args.get('grade', ''),
        enrollment_status=request.args.get('enrollment_status', ''),
        renewal_status=request.args.get('renewal_status', ''),
        course_type=request.args.get('course_type', ''),
        product_type=request.args.get('product_type', ''),
        class_mode=request.args.get('class_mode', ''),

        student_type=request.args.get('student_type', ''),
    )
    result = engine.compute(students, fs)
    result['run_time'] = run_time
    result['current_run_id'] = latest.get('current_run_id')
    result['is_pinned'] = latest.get('is_pinned', False)
    return jsonify_ordered(result)


@overview_bp.route('/api/overview/matrix')
def api_overview_matrix():
    """期次×教学点矩阵"""
    run_id = _get_run_id()
    if not run_id:
        return jsonify({'error': 'No data'})
    fs = FilterSpec.from_params(
        period=request.args.get('period', ''),
        teaching_point=request.args.get('teaching_point', ''),
        teacher=request.args.get('teacher', ''),
        subject=request.args.get('subject', ''),
        advisor=request.args.get('advisor', ''),
        year=request.args.get('year', ''),
        season=request.args.get('season', ''),
        branch=request.args.get('branch', ''),
        grade=request.args.get('grade', ''),
        enrollment_status=request.args.get('enrollment_status', ''),
        renewal_status=request.args.get('renewal_status', ''),
        course_type=request.args.get('course_type', ''),
        product_type=request.args.get('product_type', ''),
        class_mode=request.args.get('class_mode', ''),

        student_type=request.args.get('student_type', ''),
    )
    matrix = get_period_point_matrix(run_id, fs)
    return jsonify_ordered(matrix)


@overview_bp.route('/api/overview/filters')
def api_overview_filters():
    """筛选器可选项 + 筛选器配置"""
    run_id = _get_run_id()
    if not run_id:
        return jsonify({'error': 'No data'})
    options = get_filter_options(run_id)
    # 附带筛选器配置和期次配置
    options['filter_config'] = FILTER_CONFIG
    options['filter_defaults'] = FILTER_DEFAULTS
    options['period_config'] = {
        'order': PERIOD_ORDER,
        'schedule': {p: {'start': f'{PERIOD_SCHEDULE[p]["start"][0]}/{PERIOD_SCHEDULE[p]["start"][1]}',
                          'end': f'{PERIOD_SCHEDULE[p]["end"][0]}/{PERIOD_SCHEDULE[p]["end"][1]}',
                          'note': PERIOD_SCHEDULE[p].get('note', '')}
                    for p in PERIOD_ORDER},
        'current': auto_detect_period(),
    }
    return jsonify(options)


@overview_bp.route('/api/overview/teacher-list')
def api_overview_teacher_list():
    """主讲排行列表"""
    run_id = _get_run_id()
    if not run_id:
        return jsonify({'error': 'No data'})
    period = request.args.get('period', '')
    pt = request.args.get('teaching_point', '')
    teacher = request.args.get('teacher', '')
    subject = request.args.get('subject', '')
    class_type = request.args.get('class_type', '')
    branch = request.args.get('branch', '')
    year = request.args.get('year', '')
    season = request.args.get('season', '')
    grade = request.args.get('grade', '')
    # 直接用 engine.compute 的 by_teacher
    students = get_latest_students()
    fs = FilterSpec.from_params(period=period, teaching_point=pt, teacher=teacher,
                                subject=subject, class_type=class_type, branch=branch,
                                year=year, season=season, grade=grade,
                                course_type=request.args.get('course_type', ''),
                                product_type=request.args.get('product_type', ''),
                                class_mode=request.args.get('class_mode', ''),
                                student_type=request.args.get('student_type', ''))
    result = engine.compute(students, fs)
    return jsonify(result.get('by_teacher', []))


@overview_bp.route('/api/overview/advisor-list')
def api_overview_advisor_list():
    """顾问排行列表 — UV+PV双维度"""
    run_id = _get_run_id()
    if not run_id:
        return jsonify({'error': 'No data'})
    period = request.args.get('period', '')
    pt = request.args.get('teaching_point', '')
    advisor = request.args.get('advisor', '')
    branch = request.args.get('branch', '')
    year = request.args.get('year', '')
    season = request.args.get('season', '')
    grade = request.args.get('grade', '')
    subject = request.args.get('subject', '')
    students = get_latest_students()
    fs = FilterSpec.from_params(period=period, teaching_point=pt, advisor=advisor, branch=branch,
                                year=year, season=season, grade=grade, subject=subject,
                                course_type=request.args.get('course_type', ''),
                                product_type=request.args.get('product_type', ''),
                                class_mode=request.args.get('class_mode', ''),
                                student_type=request.args.get('student_type', ''))
    result = engine.compute(students, fs)
    return jsonify(result.get('by_advisor', []))


@overview_bp.route('/api/overview/teacher/<teacher>')
def api_overview_teacher_detail(teacher):
    """讲师详情 — 名下学员列表"""
    run_id = _get_run_id()
    if not run_id:
        return jsonify({'error': 'No data'})
    period = request.args.get('period', '')
    pt = request.args.get('teaching_point', '')
    subject = request.args.get('subject', '')
    class_type = request.args.get('class_type', '')
    branch = request.args.get('branch', '')
    year = request.args.get('year', '')
    season = request.args.get('season', '')
    grade = request.args.get('grade', '')
    course_type = request.args.get('course_type', '')
    product_type = request.args.get('product_type', '')
    class_mode = request.args.get('class_mode', '')
    detail = get_teacher_detail(run_id, teacher, period=period, teaching_point=pt,
                                subject=subject, class_type=class_type, branch=branch,
                                year=year, season=season, grade=grade,
                                course_type=course_type, product_type=product_type,
                                class_mode=class_mode)
    return jsonify(detail)


@overview_bp.route('/api/overview/advisor/<path:advisor>')
def api_overview_advisor_detail(advisor):
    """顾问详情 — 名下学员列表 + UV/PV 双维度汇总"""
    run_id = _get_run_id()
    if not run_id:
        return jsonify({'error': 'No data'})
    period = request.args.get('period', '')
    pt = request.args.get('teaching_point', '')
    branch = request.args.get('branch', '')
    year = request.args.get('year', '')
    season = request.args.get('season', '')
    grade = request.args.get('grade', '')
    course_type = request.args.get('course_type', '')
    product_type = request.args.get('product_type', '')
    class_mode = request.args.get('class_mode', '')
    class_type = request.args.get('class_type', '')
    detail = get_advisor_detail(run_id, advisor, period=period, teaching_point=pt, branch=branch,
                                year=year, season=season, grade=grade,
                                course_type=course_type, product_type=product_type,
                                class_mode=class_mode, class_type=class_type)
    # 添加顾问标签（全称）
    tag = get_advisor_tag(advisor)
    tag_color = get_advisor_tag_color(advisor)
    # 尝试从学员数据提取教学点（动态）
    if not tag and detail.get('students'):
        dpt = detail['students'][0].get('teaching_point', '')
        tag = dpt
        tag_color = get_advisor_tag_color(advisor)  # 用全称匹配颜色
    return jsonify({
        'advisor': advisor, 'tag': tag, 'tag_color': tag_color,
        'summary': detail.get('summary', {}),
        'students': detail.get('students', []),
    })


@overview_bp.route('/api/overview/student/<uid>')
def api_overview_student_detail(uid):
    """学员详情 — 支持 ?season= 学季作用域（避免跨学季混排错乱）"""
    run_id = _get_run_id()
    if not run_id:
        return jsonify({'error': 'No data'})
    season = request.args.get('season', '') or ''
    student = get_student_detail_enhanced(run_id, uid, season=season)
    if not student:
        return jsonify({'error': 'Student not found'})
    return jsonify(student)


@overview_bp.route('/api/overview/class/<class_id>')
def api_overview_class_detail(class_id):
    """班级详情 — 该班学员、搭班老师、上课信息"""
    run_id = _get_run_id()
    if not run_id:
        return jsonify({'error': 'No data'})
    detail = get_class_detail(run_id, class_id)
    if not detail or not detail.get('students'):
        return jsonify({'error': 'Class not found'})
    return jsonify(detail)


@overview_bp.route('/api/overview/students', methods=['POST'])
def api_overview_students():
    """多维度筛选学员列表（支持 page_size 截断）

    返回格式（兼容两种）：
      - 传 page_size 时：{items, total, page, page_size}
      - 不传 page_size 时：直接 list（向后兼容旧调用）
    """
    run_id = _get_run_id()
    if not run_id:
        return jsonify({'error': 'No data'})
    filters = request.get_json(silent=True) or {}
    students = get_filtered_students(run_id, filters)
    # 分页支持（仅当显式传 page_size 时返回 dict；否则保持 list 向后兼容）
    if 'page_size' in filters or 'page' in filters:
        try:
            page = max(1, int(filters.get('page', 1)))
            page_size = max(1, min(500, int(filters.get('page_size', 100))))
        except (ValueError, TypeError):
            page, page_size = 1, 100
        total = len(students)
        start = (page - 1) * page_size
        end = start + page_size
        return jsonify({
            'items': students[start:end],
            'total': total,
            'page': page,
            'page_size': page_size,
        })
    return jsonify(students)


@overview_bp.route('/api/overview/classes')
def api_overview_classes():
    """排班看板 — 支持多选参数（逗号分隔）"""
    run_id = _get_run_id()
    if not run_id:
        return jsonify({'error': 'No data'})
    # 多选参数：逗号分隔→列表
    pt_raw = request.args.get('teaching_point', '')
    pts = [x.strip() for x in pt_raw.split(',') if x.strip()] if pt_raw else None
    period_raw = request.args.get('period', '')
    periods = [x.strip() for x in period_raw.split(',') if x.strip()] if period_raw else None
    teacher_raw = request.args.get('teacher', '')
    teachers = [x.strip() for x in teacher_raw.split(',') if x.strip()] if teacher_raw else None
    subject_raw = request.args.get('subject', '')
    subjects = [x.strip() for x in subject_raw.split(',') if x.strip()] if subject_raw else None
    class_type_raw = request.args.get('class_type', '')
    class_types = [x.strip() for x in class_type_raw.split(',') if x.strip()] if class_type_raw else None
    branch_raw = request.args.get('branch', '')
    branches = [x.strip() for x in branch_raw.split(',') if x.strip()] if branch_raw else None
    year_raw = request.args.get('year', '')
    years = [x.strip() for x in year_raw.split(',') if x.strip()] if year_raw else None
    season_raw = request.args.get('season', '')
    seasons = [x.strip() for x in season_raw.split(',') if x.strip()] if season_raw else None
    grade_raw = request.args.get('grade', '')
    grades = [x.strip() for x in grade_raw.split(',') if x.strip()] if grade_raw else None
    course_type_raw = request.args.get('course_type', '')
    course_types = [x.strip() for x in course_type_raw.split(',') if x.strip()] if course_type_raw else None
    class_mode_raw = request.args.get('class_mode', '')
    class_modes = [x.strip() for x in class_mode_raw.split(',') if x.strip()] if class_mode_raw else None
    result = get_class_schedule(run_id, teaching_points=pts, periods=periods,
                                teachers=teachers, subjects=subjects, class_types=class_types,
                                branches=branches, years=years, seasons=seasons, grades=grades,
                                course_types=course_types, class_modes=class_modes)
    return jsonify(result)


@overview_bp.route('/api/overview/export', methods=['POST'])
def api_overview_export():
    """导出数据为 Excel（students / matrix / schedule）"""
    run_id = _get_run_id()
    if not run_id:
        return jsonify({'error': 'No data'}), 400
    body = request.get_json(silent=True) or {}
    export_type = (body.get('export_type') or 'students').strip()
    if export_type not in ('students', 'matrix', 'schedule'):
        return jsonify({'error': 'Invalid export_type'}), 400
    try:
        if export_type == 'students':
            filters = body.get('filters', {})
            buf, fname = export_excel('students', run_id, filters=filters)
        elif export_type == 'matrix':
            fs = FilterSpec.from_params(
                period=body.get('period', ''),
                teaching_point=body.get('teaching_point', ''),
                teacher=body.get('teacher', ''),
                subject=body.get('subject', ''),
                advisor=body.get('advisor', ''),
                year=body.get('year', ''),
                season=body.get('season', ''),
                branch=body.get('branch', ''),
                grade=body.get('grade', ''),
                enrollment_status=body.get('enrollment_status', ''),
                renewal_status=body.get('renewal_status', ''),
                course_type=body.get('course_type', ''),
                product_type=body.get('product_type', ''),
                class_mode=body.get('class_mode', ''),
                student_type=body.get('student_type', ''),
            )
            buf, fname = export_excel('matrix', run_id, filter_spec=fs)
        else:  # schedule
            schedule_params = {
                'teaching_points': _csv_list(body.get('teaching_point', '')),
                'periods': _csv_list(body.get('period', '')),
                'teachers': _csv_list(body.get('teacher', '')),
                'subjects': _csv_list(body.get('subject', '')),
                'class_types': _csv_list(body.get('class_type', '')),
                'branches': _csv_list(body.get('branch', '')),
                'years': _csv_list(body.get('year', '')),
                'seasons': _csv_list(body.get('season', '')),
                'grades': _csv_list(body.get('grade', '')),
                'course_types': _csv_list(body.get('course_type', '')),
                'class_modes': _csv_list(body.get('class_mode', '')),
            }
            buf, fname = export_excel('schedule', run_id, schedule_params=schedule_params)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'导出失败: {str(e)}'}), 500
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=fname,
    )


@overview_bp.route('/api/trends/data')
def api_trends_data():
    """趋势数据 — 基于订单支付时间推算每日累计趋势（单次上传即可）"""
    period = request.args.get('period', '')
    pt = request.args.get('teaching_point', '')
    branch = request.args.get('branch', '')
    grade = request.args.get('grade', '')
    season = request.args.get('season', '')
    year = request.args.get('year', '')
    fs = FilterSpec.from_params(period=period, teaching_point=pt,
                                branch=branch, grade=grade, season=season, year=year,
                                course_type=request.args.get('course_type', ''),
                                product_type=request.args.get('product_type', ''),
                                class_mode=request.args.get('class_mode', ''),
                                student_type=request.args.get('student_type', ''))
    students = get_latest_students()
    if not students:
        return jsonify([])
    trends = engine.compute_trends_by_paytime(students, fs)
    # engine 已直接返回筛选后最晚支付日向前 7 个自然日
    return jsonify(trends)


@overview_bp.route('/api/overview/acquisition-trends')
def api_overview_acquisition_trends():
    """拉新×续报转化月度分析 — 支持期次/教学点/学科/主讲/分校/年级/学季/年份/课程类型/产品类型联动"""
    periods = request.args.get('period', '')
    pt = request.args.get('teaching_point', '')
    subj = request.args.get('subject', '')
    tch = request.args.get('teacher', '')
    branch = request.args.get('branch', '')
    grade = request.args.get('grade', '')
    season = request.args.get('season', '')
    year = request.args.get('year', '')
    course_type = request.args.get('course_type', '')
    product_type = request.args.get('product_type', '')
    class_mode = request.args.get('class_mode', '')
    result = get_acquisition_trends(periods=periods, teaching_point=pt, subject=subj, teacher=tch,
                                    branch=branch, grade=grade, season=season,
                                    year=year, course_type=course_type, product_type=product_type,
                                    class_mode=class_mode)
    return jsonify(result)


# ── 拉新渠道×转化效率 ──
# AL 列（channel_lead_l1 一级渠道） / AM 列（channel_lead_l2 二级渠道）
# 数据：拉新新生（学员工单 = 新生）的拉新/在读/续报/退费分布
# 前端柱状图堆叠 + 折线图续报数据
ACQ_CHAN_FIELDS = ['period', 'teaching_point', 'branch', 'grade', 'season', 'year',
                   'subject', 'teacher', 'course_type', 'class_mode', 'student_type']
@overview_bp.route('/api/overview/acquisition-by-channel')
def api_overview_acquisition_by_channel():
    channel_level = request.args.get('channel_level', request.args.get('channelLevel', 'l1'))  # 'l1' | 'l2'
    fs_kwargs = {f: request.args.get(f, '') for f in ACQ_CHAN_FIELDS}
    fs = FilterSpec.from_params(**fs_kwargs)
    students = get_latest_students()
    result = engine.compute(students, fs)
    by_key = 'by_channel_l2' if channel_level == 'l2' else 'by_channel_l1'
    raw = result.get(by_key, {}) or {}
    # 排序：拉新数降序，前端显示更直观
    channel_list = []
    for name, agg in raw.items():
        # 显示所有有 total_uv 的渠道（用户期望匹配 Excel 教学点统计）
        total_uv = agg.get('total_uv', 0)
        if total_uv <= 0:
            continue
        channel_list.append({
            'name': name,
            'acquired': agg.get('acquired', 0),
            'active_new': agg.get('active_new', 0),
            'renewed': agg.get('renewed', 0),
            'refunded': agg.get('refunded', 0),
            'renewal_rate': agg.get('renewal_rate', 0.0),
            'total_uv': total_uv,
        })
    channel_list.sort(key=lambda x: x.get('acquired', 0), reverse=True)
    return jsonify({
        'channel_level': channel_level,
        'channels': channel_list,
        'total': {
            'acquired': sum(c['acquired'] for c in channel_list),
            'active_new': sum(c['active_new'] for c in channel_list),
            'renewed': sum(c['renewed'] for c in channel_list),
            'refunded': sum(c['refunded'] for c in channel_list),
        },
    })


@overview_bp.route('/api/share-card')
def api_share_card():
    """分享卡片数据 — 完全复刻 1.0 的 student_snapshots 遍历逻辑（KPI/分教学点/分学科/老师排行/班级/顾问双维度）"""
    import json as j

    latest = get_latest_run()
    if latest is None:
        return jsonify({'error': '无数据'}), 400

    run_id = latest['run']['run_id']

    # 筛选参数
    period = request.args.get('period', '')       # 零期/一期/二期/三期
    point = request.args.get('teaching_point', '')  # 教学点
    subject = request.args.get('subject', '')       # 学科
    teacher = request.args.get('teacher', '')       # 老师
    advisor_filter = request.args.get('advisor', '')  # 顾问
    branch_filter = request.args.get('branch', '')    # 分校（全局切换器联动）
    year_filter = request.args.get('year', '')        # 年份（全局筛选联动）
    season_filter = request.args.get('season', '')    # 学季（全局筛选联动）
    course_type_filter = request.args.get('course_type', '')  # 课程类型（全局筛选联动）
    product_type_filter = request.args.get('product_type', '')  # 产品类型（全局筛选联动）
    class_mode_filter = request.args.get('class_mode', '')  # 班型/课程模式（全局筛选联动）
    grade_filter = request.args.get('grade', '')        # 年级（全局筛选联动）

    # 解析多选 comma-separated 为 set
    def _to_set(val):
        if not val: return set()
        return {x.strip() for x in val.split(',') if x.strip()}
    year_set = _to_set(year_filter)
    season_set = _to_set(season_filter)
    course_type_set = _to_set(course_type_filter)
    product_type_set = _to_set(product_type_filter)
    class_mode_set = _to_set(class_mode_filter)
    grade_set = _to_set(grade_filter)

    ALL_SUBJS = SUBJECTS
    subj_filter = subject if subject else None
    if subj_filter and subj_filter not in ALL_SUBJS:
        subj_filter = None

    rows = get_latest_students()

    # 分校过滤（全局切换器）：先过滤 rows，后续所有统计基于该分校
    if branch_filter:
        branch_list = [b.strip() for b in branch_filter.split(',') if b.strip()]
        rows = [r for r in rows if (r.get('branch') or '').strip() in branch_list]

    # 遍历筛选
    total_active = 0
    total_renewed = 0
    total_denom = 0
    total_renewed_lock = 0
    total_refund = 0
    total_uv = set()
    total_renewed_uv = set()
    total_denom_uv = set()
    total_renewed_lock_uv = set()
    total_classes = set()

    by_point = {}     # {pt: {active, renewed, refund, denom, renewed_lock, uv:set, renewed_uv:set, denom_uv:set, renewed_lock_uv:set, classes:set}}
    by_subject = {s: {'active': 0, 'renewed': 0, 'refund': 0, 'denom': 0, 'renewed_lock': 0} for s in ALL_SUBJS}
    by_teacher = {}   # {teacher: {active, renewed, refund, denom, renewed_lock}}
    by_class = {}     # {class_id: {active, renewed, denom, renewed_lock, uv:set, renewed_uv:set, denom_uv:set, renewed_lock_uv:set, subject, period}}

    for r in rows:
        uid = r['uid']
        pt = r.get('teaching_point') or ''

        # 顾问筛选
        r_advisor = r.get('advisor') or '未知'
        if not r_advisor or r_advisor == '-':
            r_advisor = '未知'
        if advisor_filter and r_advisor != advisor_filter:
            continue

        try:
            subjects = j.loads(r.get('subjects_json') or '{}')
        except Exception:
            continue

        for subj_name, sd in subjects.items():
            if not isinstance(sd, dict):
                continue
            subj_name = get_line_subject(sd, subj_name)
            if subj_filter and subj_name != subj_filter:
                continue

            status = sd.get('status', '-')
            period_val = sd.get('period', '') or ''
            teacher_val = sd.get('teacher', '') or ''
            class_id = sd.get('class_id', '') or ''

            # 期次筛选
            if period:
                plist = [p.strip() for p in period_val.split('/') if p.strip()]
                if period not in plist:
                    continue

            # 教学点筛选
            if point and pt != point:
                continue

            # 老师筛选
            if teacher and teacher_val != teacher:
                continue

            # 全局筛选行级过滤（与主看板口径一致）
            if year_set and (sd.get('year', '') or '') not in year_set:
                continue
            if season_set and (sd.get('season', '') or '') not in season_set:
                continue
            if course_type_set and (sd.get('course_type', '') or '') not in course_type_set:
                continue
            if product_type_set and (sd.get('product_type', '') or '') not in product_type_set:
                continue
            if class_mode_set and norm_class_mode(sd.get('class_mode', '') or '') not in class_mode_set:
                continue
            if grade_set and (sd.get('grade', '') or '') not in grade_set and (sd.get('grade', '') or '') != '':
                continue

            is_active = '在读' in status
            is_denom = is_renewal_denom(sd)
            is_renewed_lock = is_renewed_by_source(sd)
            is_refund = status and status != '-' and '在读' not in status

            if is_active:
                total_active += 1
                total_uv.add(uid)
                if class_id and class_id != '-':
                    total_classes.add(class_id)

                if pt not in by_point:
                    by_point[pt] = {'active': 0, 'renewed': 0, 'refund': 0, 'denom': 0, 'renewed_lock': 0, 'uv': set(), 'renewed_uv': set(), 'denom_uv': set(), 'renewed_lock_uv': set(), 'classes': set()}
                by_point[pt]['active'] += 1
                by_point[pt]['uv'].add(uid)
                if class_id and class_id != '-':
                    by_point[pt]['classes'].add(class_id)

                if subj_name in by_subject:
                    by_subject[subj_name]['active'] += 1

                if teacher_val and teacher_val != '-':
                    if teacher_val not in by_teacher:
                        by_teacher[teacher_val] = {'active': 0, 'renewed': 0, 'refund': 0, 'denom': 0, 'renewed_lock': 0}
                    by_teacher[teacher_val]['active'] += 1

                # 班级维度（仅当筛选了老师时才跟踪）
                if teacher and class_id and class_id != '-':
                    if class_id not in by_class:
                        by_class[class_id] = {'active': 0, 'renewed': 0, 'denom': 0, 'renewed_lock': 0, 'uv': set(), 'renewed_uv': set(), 'denom_uv': set(), 'renewed_lock_uv': set(), 'subject': subj_name, 'period': period_val}
                    by_class[class_id]['active'] += 1
                    by_class[class_id]['uv'].add(uid)

                # ── denom / renewed_lock 累积（不受 is_active 限制，独立计数维度）──
                if is_denom:
                    total_denom += 1
                    total_denom_uv.add(uid)
                    if pt in by_point:
                        by_point[pt]['denom'] += 1
                        by_point[pt]['denom_uv'].add(uid)
                    if subj_name in by_subject:
                        by_subject[subj_name]['denom'] += 1
                    if teacher_val and teacher_val != '-' and teacher_val in by_teacher:
                        by_teacher[teacher_val]['denom'] += 1
                    if class_id in by_class:
                        by_class[class_id]['denom'] += 1
                        by_class[class_id]['denom_uv'].add(uid)

                    if is_renewed_lock:
                        total_renewed_lock += 1
                        total_renewed_lock_uv.add(uid)
                        if pt in by_point:
                            by_point[pt]['renewed_lock'] += 1
                            by_point[pt]['renewed_lock_uv'].add(uid)
                        if subj_name in by_subject:
                            by_subject[subj_name]['renewed_lock'] += 1
                        if teacher_val and teacher_val != '-' and teacher_val in by_teacher:
                            by_teacher[teacher_val]['renewed_lock'] += 1
                        if class_id in by_class:
                            by_class[class_id]['renewed_lock'] += 1
                            by_class[class_id]['renewed_lock_uv'].add(uid)

            if is_refund:
                total_refund += 1
                if pt in by_point:
                    by_point[pt]['refund'] += 1
                if subj_name in by_subject:
                    by_subject[subj_name]['refund'] += 1
                if teacher_val and teacher_val != '-' and teacher_val in by_teacher:
                    by_teacher[teacher_val]['refund'] += 1

    # 提取全部老师/教学点/顾问（不受筛选影响，用于前端chip选择器）
    all_teachers = set()
    all_points = set()
    all_advisors = set()
    for r in rows:
        pt_all = r.get('teaching_point') or ''
        if pt_all and pt_all != '-':
            all_points.add(pt_all)
        adv_all = r.get('advisor') or '未知'
        if adv_all and adv_all != '-':
            all_advisors.add(adv_all)
        try:
            subjects_all = j.loads(r.get('subjects_json') or '{}')
        except Exception:
            subjects_all = {}
        for subj_name, sd in subjects_all.items():
            if not isinstance(sd, dict):
                continue
            tv = sd.get('teacher', '') or ''
            if tv and tv != '-':
                all_teachers.add(tv)

    # 组装返回数据
    renewal_rate = round(total_renewed_lock / total_denom * 100, 1) if total_denom > 0 else 0
    renewal_uv = len(total_renewed_lock_uv)
    uv_count = len(total_denom_uv)
    renewal_uv_rate = round(renewal_uv / uv_count * 100, 1) if uv_count > 0 else 0

    # 分教学点表格
    point_list = []
    for pt, v in sorted(by_point.items()):
        if not pt:
            continue
        pt_active = v['active']
        pt_renewed = v['renewed_lock']
        pt_uv = len(v['denom_uv'])
        pt_renewed_uv = len(v['renewed_lock_uv'])
        pt_rate = round(pt_renewed / v['denom'] * 100, 1) if v['denom'] > 0 else 0
        pt_uv_rate = round(pt_renewed_uv / pt_uv * 100, 1) if pt_uv > 0 else 0
        point_list.append({
            'name': pt,
            'active': pt_active,
            'uv': pt_uv,
            'renewed': pt_renewed,
            'renewed_uv': pt_renewed_uv,
            'refund': v['refund'],
            'class_count': len(v['classes']),
            'renewal_rate': pt_rate,
            'renewal_uv_rate': pt_uv_rate,
        })

    # 分学科（Q8：主名用产品原名；小标签=学科简称在下游 pill 渲染）
    subject_list = []
    subj_colors = SUBJECT_COLOR
    for s in ALL_SUBJS:
        v = by_subject[s]
        rate = round(v['renewed_lock'] / v['denom'] * 100, 1) if v['denom'] > 0 else 0
        subject_list.append({
            'name': s,
            'key': s,
            'active': v['active'],
            'renewed': v['renewed_lock'],
            'refund': v['refund'],
            'renewal_rate': rate,
            'color': subj_colors.get(s, '#888'),
        })

    # 老师排行
    teacher_list = []
    for t, v in by_teacher.items():
        if not t or t == '-':
            continue
        rate = round(v['renewed_lock'] / v['denom'] * 100, 1) if v['denom'] > 0 else 0
        teacher_list.append({
            'name': t,
            'active': v['active'],
            'renewed': v['renewed_lock'],
            'renewal_rate': rate,
        })
    teacher_list.sort(key=lambda x: x['renewal_rate'], reverse=True)

    # 班级续报详情（仅当筛选了老师时返回）
    class_list = []
    if teacher:
        for cid, v in sorted(by_class.items(), key=lambda x: x[1]['active'], reverse=True):
            c_active = v['active']
            c_renewed = v['renewed_lock']
            c_uv = len(v['denom_uv'])
            c_renewed_uv = len(v['renewed_lock_uv'])
            c_rate = round(c_renewed / v['denom'] * 100, 1) if v['denom'] > 0 else 0
            c_uv_rate = round(c_renewed_uv / c_uv * 100, 1) if c_uv > 0 else 0
            class_list.append({
                'class_id': cid,
                'subject': subj_labels.get(v['subject'], v['subject']),
                'period': v['period'] or '-',
                'active': c_active,
                'uv': c_uv,
                'renewed': c_renewed,
                'renewed_uv': c_renewed_uv,
                'renewal_rate': c_rate,
                'renewal_uv_rate': c_uv_rate,
            })

    # ── 顾问维度（联动筛选：period/point/subject/teacher/advisor）──
    # 使用秋季续费订单的支付时间判断 pre/new，无需快照基线
    from datetime import datetime as dt_now
    now_dt = dt_now.now()
    current_period = auto_detect_period()

    all_periods_mode = not period  # 无期次筛选 → 全部期次
    target_period_adv = period if period else current_period

    # 按顾问聚合（UV + PV 双维度），应用 point/subject/teacher/advisor 筛选
    advisor_stats = {}
    for r in rows:
        uid = r['uid']
        if point and (r.get('teaching_point') or '') != point:
            continue

        advisor = r.get('advisor') or '未知'
        if not advisor or advisor == '-':
            advisor = '未知'
        if advisor_filter and advisor != advisor_filter:
            continue

        try:
            subjects = j.loads(r.get('subjects_json') or '{}')
        except Exception:
            continue

        has_active = False
        active_subjs = []
        renewed_subjs = []
        pre_renewed_subjs = set()
        new_renewed_subjs = set()

        for _subj, _sd in subjects.items():
            if not isinstance(_sd, dict):
                continue
            # 筛选用真实学科名；PV 计数集合仍保留合成键 _subj（防止同科多单折叠丢失）
            if subj_filter and get_line_subject(_sd, _subj) != subj_filter:
                continue
            if teacher and _sd.get('teacher', '') != teacher:
                continue
            _status = _sd.get('status', '-')
            _period_val = _sd.get('period', '') or ''
            _period_list = [p.strip() for p in _period_val.split('/') if p.strip()]
            _is_active = '在读' in _status
            _is_renewed = is_renewed_by_source(_sd)

            if all_periods_mode:
                # 全部期次模式：只要在读就计入
                if _is_active:
                    has_active = True
                    active_subjs.append(_subj)
                if _is_renewed:
                    renewed_subjs.append(_subj)
                    # 用秋季续费支付时间判断 pre/new
                    subj_period = _period_list[0] if _period_list else ''
                    renewal_class = classify_renewal_by_pay_time(
                        _sd.get('fall_pay_time'), subj_period, now_dt.year,
                        start_date=_sd.get('start_date', ''))
                    if renewal_class == 'pre':
                        pre_renewed_subjs.add(_subj)
                    else:
                        new_renewed_subjs.add(_subj)
            else:
                # 单期模式：只看目标期次
                if target_period_adv in _period_list:
                    if _is_active:
                        has_active = True
                        active_subjs.append(_subj)
                    if _is_renewed:
                        renewed_subjs.append(_subj)
                        renewal_class = classify_renewal_by_pay_time(
                            _sd.get('fall_pay_time'), target_period_adv, now_dt.year,
                            start_date=_sd.get('start_date', ''))
                        if renewal_class == 'pre':
                            pre_renewed_subjs.add(_subj)
                        else:
                            new_renewed_subjs.add(_subj)

        if not has_active:
            continue

        if advisor not in advisor_stats:
            advisor_stats[advisor] = {
                'uv': {'active': set(), 'pre': set(), 'new': set()},
                'pv': {'active': 0, 'pre': 0, 'new': 0}
            }

        # UV: uid 级别
        advisor_stats[advisor]['uv']['active'].add(uid)
        if new_renewed_subjs:
            advisor_stats[advisor]['uv']['new'].add(uid)
        elif renewed_subjs:
            advisor_stats[advisor]['uv']['pre'].add(uid)

        # PV: (uid, subject) 级别
        for _subj in active_subjs:
            advisor_stats[advisor]['pv']['active'] += 1
            if _subj in renewed_subjs:
                if _subj in new_renewed_subjs:
                    advisor_stats[advisor]['pv']['new'] += 1
                else:
                    advisor_stats[advisor]['pv']['pre'] += 1

    advisor_list = []
    for advisor, sets in advisor_stats.items():
        uv_active = len(sets['uv']['active'])
        uv_pre = len(sets['uv']['pre'])
        uv_new = len(sets['uv']['new'])
        uv_should = uv_active - uv_pre
        uv_rate = round(uv_new / uv_should * 100, 1) if uv_should > 0 else 0
        pv_active = sets['pv']['active']
        pv_pre = sets['pv']['pre']
        pv_new = sets['pv']['new']
        pv_should = pv_active - pv_pre
        pv_rate = round(pv_new / pv_should * 100, 1) if pv_should > 0 else 0
        uv_total = uv_pre + uv_new
        pv_total = pv_pre + pv_new
        advisor_list.append({
            'name': advisor,
            'active': uv_active,
            'pre_renewed': uv_pre,
            'should_renew': uv_should,
            'new_renewed': uv_new,
            'total_renewed': uv_total,
            'renewal_rate': uv_rate,
            'pv_active': pv_active,
            'pv_pre_renewed': pv_pre,
            'pv_should_renew': pv_should,
            'pv_new_renewed': pv_new,
            'pv_total_renewed': pv_total,
            'pv_renewal_rate': pv_rate,
        })
    advisor_list.sort(key=lambda x: x['renewal_rate'], reverse=True)

    return jsonify({
        'kpi': {
            'active_pv': total_active,
            'uv': uv_count,
            'renewal_rate': renewal_rate,
            'renewal_pv': total_renewed,
            'renewal_uv': renewal_uv,
            'renewal_uv_rate': renewal_uv_rate,
            'refund_pv': total_refund,
            'class_count': len(total_classes),
        },
        'by_point': point_list,
        'by_subject': subject_list,
        'by_teacher': teacher_list,
        'by_class': class_list,
        'by_advisor': advisor_list,
        'advisor_current_period': '全部' if all_periods_mode else target_period_adv,
        'filters': {
            'period': period or '全部',
            'teaching_point': point or '全部',
            'subject': subj_labels.get(subj_filter, subj_filter) if subj_filter else '全部',
            'teacher': teacher or '全部',
            'advisor': advisor_filter or '全部',
        },
        'available_teachers': sorted(all_teachers),
        'available_points': sorted(all_points),
        'available_advisors': sorted(all_advisors),
        'run_time': latest['run'].get('run_time', ''),
    })


# ═══════════════════════════════════════════════════════════════
# Calibration Blueprint — 校准运行管理
# ═══════════════════════════════════════════════════════════════

calibration_bp = Blueprint('calibration', __name__)


@calibration_bp.route('/api/calibrate', methods=['POST'])
def api_calibrate():
    """执行校准 — 上传招生明细+原台帐，调用 calibrator 生成变动/报告/台帐"""
    try:
        enrollment_file = request.files.get('enrollment')
        ledger_file = request.files.get('ledger')
        fall_file = request.files.get('fall_orders')

        if not enrollment_file or not ledger_file:
            return jsonify({'error': '请上传招生明细和原UV台帐两个文件'}), 400

        def _ext(fn):
            return os.path.splitext(fn)[1].lower() if fn else '.xlsx'

        if _ext(enrollment_file.filename) not in ('.xlsx', '.xls') or \
           _ext(ledger_file.filename) not in ('.xlsx', '.xls'):
            return jsonify({'error': '仅支持 .xlsx / .xls 文件'}), 400

        # 保存上传文件（随机安全文件名，保留扩展名）
        run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        data_dir = get_data_dir()
        upload_dir = os.path.join(data_dir, 'calibration_uploads')
        output_dir = os.path.join(data_dir, 'calibration_output')
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        enf_path = os.path.join(upload_dir, f'{run_id}_enrollment{_ext(enrollment_file.filename)}')
        led_path = os.path.join(upload_dir, f'{run_id}_ledger{_ext(ledger_file.filename)}')
        enrollment_file.save(enf_path)
        ledger_file.save(led_path)

        fall_path = None
        if fall_file and _ext(fall_file.filename) in ('.xlsx', '.xls'):
            fall_path = os.path.join(upload_dir, f'{run_id}_fall{_ext(fall_file.filename)}')
            fall_file.save(fall_path)

        # 执行校准
        result = calibrate(enf_path, led_path, fall_path)

        # 生成输出文件（校准台帐 + 校准报告）
        ledger_out = os.path.join(output_dir, f'{run_id}_UV台帳校准版.xlsx')
        report_out = os.path.join(output_dir, f'{run_id}_台帳校准报告.xlsx')
        generate_calibrated_ledger(result, led_path, ledger_out)
        generate_calibration_report(result, report_out)

        # ── 纯校准模式：只保存元数据记录（用于运行监控+文件下载），不写学员快照、
        #    不设 overlay_run_id、不触发 rebuild_active_run，不对底层数据有任何干扰。
        save_calibration_metadata(run_id, result['stats'], result,
                                  ledger_out, report_out,
                                  enrollment_file.filename, ledger_file.filename)

        # 学员变动总览（按学员维度）
        student_changes = result.get('student_changes', [])
        new_students_list = [sc for sc in student_changes if sc['change_type'] == '新增学员']
        changed_list = [sc for sc in student_changes if sc['change_type'] == '信息变更']

        return jsonify({
            'success': True,
            'run_id': run_id,
            'stats': result['stats'],
            'student_changes': student_changes,
            'new_students_list': new_students_list,
            'changed_list': changed_list,
            'change_details': result.get('change_details', []),
            'anomalies': result.get('anomalies', []),
            'files': {
                'ledger': f'/api/download/{run_id}/ledger',
                'report': f'/api/download/{run_id}/report',
            }
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'校准失败: {str(e)}'}), 500


@calibration_bp.route('/api/runs')
def api_runs():
    """所有校准运行列表（标注当前生效的 run 与是否 pin）"""
    runs = get_all_runs()
    current = get_current_run_id()
    if not current and runs:
        current = runs[0]['run_id']
    pin = get_pinned_run_id()
    for r in runs:
        r['is_current'] = (r['run_id'] == current)
        r['is_pinned'] = bool(pin and r['run_id'] == pin)
    return jsonify(runs)


@calibration_bp.route('/api/runs/pin', methods=['POST'])
def api_runs_pin():
    """将某次校准设为当前基线（pin）。

    body: {"run_id": "..."}
    - run_id 为空 / "latest" → 清除 pin，回到最新
    - 否则校验存在后 pin 该 run
    所有看板/分享/趋势经 _get_run_id 自动随 pin 切换。
    """
    data = request.get_json(silent=True) or {}
    run_id = (data.get('run_id') or '').strip()
    if not run_id or run_id == 'latest':
        clear_current_run_id()
        return jsonify({'success': True, 'pinned': False, 'current_run_id': get_current_run_id()})
    run = get_run_by_id(run_id)
    if not run:
        return jsonify({'error': 'Run not found'}), 404
    set_current_run_id(run_id)
    return jsonify({'success': True, 'pinned': True, 'current_run_id': run_id})


@calibration_bp.route('/api/upload-full', methods=['POST'])
def api_upload_full():
    """上传全量订单明细表（昨日快照）作为合并模型的「全量基线」(base)。

    - 支持多文件（各分校独立明细表）：request.files.getlist('files') / 单文件 'file'
    - 仅 ADD 数据，不删除任何历史 run；可逆
    - 写入后标记 base_run_id 并触发 rebuild_active_run，按 uid 与已有校准(overlay)合并
      物化为 merged run 并 pin（校准优先、全量兜底）
    - 不影响现有校准管理流程
    """
    try:
        files = request.files.getlist('files')
        if not files:
            f = request.files.get('file')
            if f:
                files = [f]
        if not files:
            return jsonify({'error': '请上传至少一个订单明细表 (.xlsx)'}), 400

        data_dir = get_data_dir()
        upload_dir = os.path.join(data_dir, 'full_uploads')
        os.makedirs(upload_dir, exist_ok=True)
        saved = []
        for i, f in enumerate(files):
            ext = os.path.splitext(f.filename or '')[1].lower()
            if ext not in ('.xlsx', '.xls'):
                return jsonify({'error': f'仅支持 .xlsx / .xls 文件：{f.filename}'}), 400
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            path = os.path.join(upload_dir, f'full_{ts}_{i}{ext}')
            f.save(path)
            saved.append(path)

        db_path = os.path.join(data_dir, 'uv_dashboard.db')
        result = import_to_production(db_path, saved, set_current=True)
        return jsonify({
            'success': True,
            'run_id': result['run_id'],
            'students': result['students'],
            'active': result['active'],
            'refund': result['refund'],
            'rebuild': result.get('rebuild'),
            'kept_from_old_base': result.get('kept_from_old_base', 0),
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'全量上传失败: {str(e)}'}), 500


@calibration_bp.route('/api/rebuild', methods=['POST'])
def api_rebuild():
    """手动按 base(全量) + overlay(校准) 重新合并物化并 pin（无需重新上传）。

    适用：校准后想立即刷新合并结果；或调试时重算 merged run。
    """
    try:
        summary = rebuild_active_run()
        return jsonify({'success': True, 'summary': summary})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'重新合并失败: {str(e)}'}), 500


@calibration_bp.route('/api/runs/<run_id>')
def api_run_detail(run_id):
    """单次校准运行详情"""
    detail = get_run_by_id(run_id)
    if not detail:
        return jsonify({'error': 'Run not found'})
    return jsonify(detail)


@calibration_bp.route('/api/runs/<run_id>/changes')
def api_run_changes(run_id):
    """单次校准变动记录"""
    changes = get_changes_by_run(run_id)
    return jsonify(changes)


@calibration_bp.route('/api/daily-stats')
def api_daily_stats():
    """每日校准统计"""
    stats = get_daily_stats()
    return jsonify(stats)


@calibration_bp.route('/api/download/<run_id>/<file_type>')
def api_download(run_id, file_type):
    """下载校准输出文件"""
    run = get_run_by_id(run_id)
    if not run:
        return jsonify({'error': 'Run not found'}), 404
    path_map = {
        'ledger': run['run'].get('ledger_path'),
        'report': run['run'].get('report_path'),
    }
    path = path_map.get(file_type)
    if not path or not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(path, as_attachment=True)


# ═══════════════════════════════════════════════════════════════
# Share Blueprint — 分享页面生成与部署
# ═══════════════════════════════════════════════════════════════

share_bp = Blueprint('share', __name__)


@share_bp.route('/api/share/generate', methods=['POST'])
def api_share_generate():
    """
    生成分享页面：获取最新数据，渲染自包含HTML，保存到 static/shares/ 目录。
    完整复刻 1.0 的本地分享页数据逻辑（snapshot 迭代），并附加月度拉新/续报转化数据。
    支持筛选参数：start_date, end_date, subjects, teaching_points, periods, teachers。
    返回 share_id，前端可通过 /share-view/<share_id> 本地预览。
    """
    j = json
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')

    data = request.get_json(silent=True) or {}

    # ── 0. 解析筛选参数（与 1.0 保持一致）──
    start_date = (data.get('start_date') or '').strip()
    end_date   = (data.get('end_date') or '').strip()

    def _parse_filter(val):
        if not val:
            return []
        if isinstance(val, list):
            return [x.strip() for x in val if str(x).strip()]
        return [x.strip() for x in str(val).split(',') if x.strip()]

    subjects_filter = _parse_filter(data.get('subjects', ''))
    points_filter   = _parse_filter(data.get('teaching_points', ''))
    periods_filter  = _parse_filter(data.get('periods', ''))
    teachers_filter = _parse_filter(data.get('teachers', ''))
    branch_filter   = _parse_filter(data.get('branch', ''))
    year_filter     = _parse_filter(data.get('year', ''))
    season_filter   = _parse_filter(data.get('season', ''))
    course_type_filter = _parse_filter(data.get('course_type', ''))
    class_mode_filter  = _parse_filter(data.get('class_mode', ''))
    grade_filter       = _parse_filter(data.get('grade', ''))

    old_period = (data.get('period') or '').strip()
    old_point  = (data.get('teaching_point') or '').strip()
    if old_period and not periods_filter:
        periods_filter = [old_period]
    if old_point and not points_filter:
        points_filter = [old_point]

    # 分享页数据始终包含全部期次（仅用于 Tab 切换与筛选文案）
    selected_periods = periods_filter
    periods_filter = []

    PERIODS = PERIOD_ORDER

    # ── 1. 获取最新快照，计算 KPI / 主讲排行 / 顾问排行 ──
    latest = get_latest_run()
    if latest is None:
        return jsonify({'error': '无校准数据'}), 400
    run_id = latest['run']['run_id']
    run_time = latest['run'].get('run_time') or today_str

    conn = get_db()
    rows = conn.execute(
        'SELECT uid, name, teaching_point, advisor, subjects_json, branch FROM student_snapshots WHERE run_id = ?',
        (run_id,)
    ).fetchall()

    ALL_SUBJS = SUBJECTS

    total_active = 0
    total_renewed = 0
    total_denom = 0
    total_renewed_lock = 0
    total_refund = 0
    total_uv = set()
    total_renewed_uv = set()
    total_denom_uv = set()
    total_renewed_lock_uv = set()

    by_teacher_pv = {}   # {teacher: {active, renewed, refund, denom, renewed_lock, pre, new, subjects}}
    advisor_stats = {}   # {advisor: {uv:{active,set, pre:set, new:set}, pv:{...}}}

    by_teacher_period = {p: {} for p in PERIODS}
    by_advisor_period  = {p: {} for p in PERIODS}
    uv_by_period = {p: set() for p in PERIODS}
    renewed_uv_by_period = {p: set() for p in PERIODS}
    denom_uv_by_period = {p: set() for p in PERIODS}
    renewed_lock_uv_by_period = {p: set() for p in PERIODS}

    for r in rows:
        uid = r['uid']
        pt = (r['teaching_point'] or '').strip()
        advisor = r['advisor'] or '未知'
        if not advisor or advisor == '-':
            advisor = '未知'

        # 分校过滤（与全局分校切换器口径一致）
        sb = (r['branch'] or '').strip()
        if branch_filter and sb not in branch_filter:
            continue

        if points_filter and pt not in points_filter:
            continue

        try:
            subjects = json.loads(r['subjects_json'] or '{}')
        except Exception:
            continue

        uid_has_active = False
        uid_active_pv_count = 0
        uid_pre_set = set()
        uid_new_set = set()

        for subj_name, sd in subjects.items():
            if not isinstance(sd, dict):
                continue
            # 合成键 → 真实学科名（用于筛选 + 讲师执教学科展示集合，
            # active/pre/new 均为按行自增计数，不受此影响）
            subj_name = get_line_subject(sd, subj_name)

            if subjects_filter and subj_name not in subjects_filter:
                continue

            status     = sd.get('status', '-')
            period_val = sd.get('period', '') or ''
            teacher_val = sd.get('teacher', '') or ''

            if periods_filter:
                plist = [p.strip() for p in period_val.split('/') if p.strip()]
                if not any(p in periods_filter for p in plist):
                    continue

            if teachers_filter and teacher_val not in teachers_filter:
                continue

            # 全局筛选参数行级过滤（与主看板口径一致）
            season_val = sd.get('season', '') or ''
            if season_filter and season_val not in season_filter:
                continue
            course_type_val = sd.get('course_type', '') or ''
            if course_type_filter and course_type_val not in course_type_filter:
                continue
            class_mode_val = sd.get('class_mode', '') or ''
            if class_mode_filter and norm_class_mode(class_mode_val) not in class_mode_filter:
                continue
            grade_val = sd.get('grade', '') or ''
            if grade_filter and grade_val not in grade_filter and grade_val != '':
                continue

            is_active  = '在读' in status
            is_denom = is_renewal_denom(sd)
            is_renewed_lock = is_renewed_by_source(sd)
            is_refund  = status and status != '-' and '在读' not in status

            if is_active:
                total_active += 1
                total_uv.add(uid)
                uid_has_active = True
                uid_active_pv_count += 1

                for pp in [p.strip() for p in period_val.split('/') if p.strip()]:
                    if pp in uv_by_period:
                        uv_by_period[pp].add(uid)

                if teacher_val and teacher_val != '-':
                    if teacher_val not in by_teacher_pv:
                        by_teacher_pv[teacher_val] = {'active': 0, 'renewed': 0, 'refund': 0, 'denom': 0, 'renewed_lock': 0, 'pre': 0, 'new': 0, 'subjects': set()}
                    by_teacher_pv[teacher_val]['active'] += 1
                    by_teacher_pv[teacher_val]['subjects'].add(subj_name)

                    for pp in [p.strip() for p in period_val.split('/') if p.strip()]:
                        if pp in by_teacher_period and (not periods_filter or pp in periods_filter):
                            if teacher_val not in by_teacher_period[pp]:
                                by_teacher_period[pp][teacher_val] = {'active': 0, 'renewed': 0, 'denom': 0, 'renewed_lock': 0, 'pre': 0, 'new': 0, 'subjects': set()}
                            by_teacher_period[pp][teacher_val]['active'] += 1
                            by_teacher_period[pp][teacher_val]['subjects'].add(subj_name)

                # ── denom / renewed_lock 累积（不受 is_active 限制，独立计数维度）──
                if is_denom:
                    total_denom += 1
                    total_denom_uv.add(uid)
                    if teacher_val and teacher_val != '-' and teacher_val in by_teacher_pv:
                        by_teacher_pv[teacher_val]['denom'] += 1

                    for pp in [p.strip() for p in period_val.split('/') if p.strip()]:
                        if pp in denom_uv_by_period:
                            denom_uv_by_period[pp].add(uid)

                    for pp in [p.strip() for p in period_val.split('/') if p.strip()]:
                        if pp in by_teacher_period and (not periods_filter or pp in periods_filter):
                            if teacher_val and teacher_val != '-':
                                if teacher_val in by_teacher_period[pp]:
                                    by_teacher_period[pp][teacher_val]['denom'] += 1

                    if is_renewed_lock:
                        total_renewed_lock += 1
                        total_renewed_lock_uv.add(uid)
                        if teacher_val and teacher_val != '-' and teacher_val in by_teacher_pv:
                            by_teacher_pv[teacher_val]['renewed_lock'] += 1

                        for pp in [p.strip() for p in period_val.split('/') if p.strip()]:
                            if pp in renewed_lock_uv_by_period:
                                renewed_lock_uv_by_period[pp].add(uid)

                        for pp in [p.strip() for p in period_val.split('/') if p.strip()]:
                            if pp in by_teacher_period and (not periods_filter or pp in periods_filter):
                                if teacher_val and teacher_val != '-':
                                    if teacher_val in by_teacher_period[pp]:
                                        by_teacher_period[pp][teacher_val]['renewed_lock'] += 1

                        # pre/new 分类仍用旧口径 is_continue_fall + classify_renewal_by_pay_time
                        if periods_filter:
                            subj_periods = [p.strip() for p in period_val.split('/') if p.strip()]
                            matching = [p for p in periods_filter if p in subj_periods]
                            classify_period = matching[0] if matching else periods_filter[0]
                        else:
                            classify_period = _detect_subj_period(period_val)
                        renewal_class = classify_renewal_by_pay_time(
                            sd.get('fall_pay_time'), classify_period, now.year,
                            start_date=sd.get('start_date', ''))
                        if renewal_class == 'pre':
                            uid_pre_set.add(subj_name)
                        else:
                            uid_new_set.add(subj_name)
                        if teacher_val and teacher_val != '-' and teacher_val in by_teacher_pv:
                            if renewal_class == 'pre':
                                by_teacher_pv[teacher_val]['pre'] += 1
                            else:
                                by_teacher_pv[teacher_val]['new'] += 1
                        for pp in [p.strip() for p in period_val.split('/') if p.strip()]:
                            if pp in by_teacher_period and (not periods_filter or pp in periods_filter):
                                if teacher_val and teacher_val != '-' and teacher_val in by_teacher_period[pp]:
                                    if renewal_class == 'pre':
                                        by_teacher_period[pp][teacher_val]['pre'] += 1
                                    else:
                                        by_teacher_period[pp][teacher_val]['new'] += 1

            if is_refund:
                total_refund += 1
                if teacher_val and teacher_val != '-' and teacher_val in by_teacher_pv:
                    by_teacher_pv[teacher_val]['refund'] += 1

        if uid_has_active:
            if advisor not in advisor_stats:
                advisor_stats[advisor] = {
                    'uv': {'active': set(), 'pre': set(), 'new': set()},
                    'pv': {'active': 0, 'pre': 0, 'new': 0},
                }
            advisor_stats[advisor]['uv']['active'].add(uid)
            if uid_new_set:
                advisor_stats[advisor]['uv']['new'].add(uid)
            elif uid_pre_set:
                advisor_stats[advisor]['uv']['pre'].add(uid)
            advisor_stats[advisor]['pv']['active'] += uid_active_pv_count
            advisor_stats[advisor]['pv']['new'] += len(uid_new_set)
            advisor_stats[advisor]['pv']['pre'] += len(uid_pre_set)

            advisor_period_seen = set()
            for subj_name, sd in subjects.items():
                if not isinstance(sd, dict):
                    continue
                subj_name = get_line_subject(sd, subj_name)
                if subjects_filter and subj_name not in subjects_filter:
                    continue
                pv = sd.get('period', '') or ''
                status = sd.get('status', '-')
                if '在读' not in status:
                    continue
                teacher_val = sd.get('teacher', '') or ''
                if teachers_filter and teacher_val not in teachers_filter:
                    continue
                # 全局筛选行级过滤（与主循环口径一致）
                if season_filter and (sd.get('season', '') or '') not in season_filter:
                    continue
                if course_type_filter and (sd.get('course_type', '') or '') not in course_type_filter:
                    continue
                if class_mode_filter and norm_class_mode(sd.get('class_mode', '') or '') not in class_mode_filter:
                    continue
                for pp in [p.strip() for p in pv.split('/') if p.strip()]:
                    if pp not in by_advisor_period:
                        continue
                    if periods_filter and pp not in periods_filter:
                        continue
                    key = f'{pp}|{advisor}'
                    if key in advisor_period_seen:
                        continue
                    advisor_period_seen.add(key)
                    if advisor not in by_advisor_period[pp]:
                        by_advisor_period[pp][advisor] = {
                            'active': 0, 'pre': 0, 'new': 0,
                            'uv_active': set(), 'uv_pre': set(), 'uv_new': set(),
                        }
                    by_advisor_period[pp][advisor]['active'] += 1
                    by_advisor_period[pp][advisor]['uv_active'].add(uid)
                    if uid_new_set:
                        by_advisor_period[pp][advisor]['new'] += 1
                        by_advisor_period[pp][advisor]['uv_new'].add(uid)
                    elif uid_pre_set:
                        by_advisor_period[pp][advisor]['pre'] += 1
                        by_advisor_period[pp][advisor]['uv_pre'].add(uid)

    # ── 主讲排行（PV维度，含续报率+转化率）──
    # BUG 修复：系统课没有"应续"和"当期转化"概念（仅特惠课区分 pre/new）
    # 根据当前筛选的 course_type 动态返回正确格式
    teacher_list = []
    for tname, v in sorted(by_teacher_pv.items()):
        active = v['active']
        renewed = v['renewed_lock']
        denom = v['denom']
        if active == 0:
            continue
        rate = round(renewed / denom * 100, 1) if denom > 0 else 0
        item = {
            'name': tname, 'active': active, 'renewed': renewed,
            'renewal_rate': rate, 'subjects': sorted(v.get('subjects', set())),
        }
        # 仅特惠课（或未筛选 course_type 时默认特惠课格式）才返回 pre/should/new
        if is_system_only:
            # 系统课：无应续/转化细分，只返回续报率相关
            item['should_renew'] = 0
            item['new_renewed'] = 0
            item['total_renewed'] = renewed
            item['pre_renewed'] = 0
            item['conv_rate'] = 0
        else:
            # 特惠课/未限定：返回完整指标
            pre = v.get('pre', 0)
            new = v.get('new', 0)
            should = active - pre
            conv_rate = round(new / should * 100, 1) if should > 0 else 0
            item['pre_renewed'] = pre
            item['should_renew'] = should
            item['new_renewed'] = new
            item['total_renewed'] = pre + new
            item['conv_rate'] = conv_rate
        teacher_list.append(item)
    teacher_list.sort(key=lambda x: x['renewal_rate'], reverse=True)

    # ── 顾问排行（UV+PV双维度）──
    advisor_list_raw = []
    for aname, sets in advisor_stats.items():
        uv_active = len(sets['uv']['active'])
        uv_pre = len(sets['uv']['pre'])
        uv_new = len(sets['uv']['new'])
        uv_should = uv_active - uv_pre
        uv_total = uv_pre + uv_new
        pv_active = sets['pv']['active']
        pv_pre = sets['pv']['pre']
        pv_new = sets['pv']['new']
        pv_should = pv_active - pv_pre
        pv_total = pv_pre + pv_new
        conv_rate = round(uv_new / uv_should * 100, 1) if uv_should > 0 else 0
        if uv_active == 0:
            continue
        advisor_list_raw.append({
            'name': aname, 'active': uv_active, 'pre_renewed': uv_pre,
            'should_renew': uv_should, 'new_renewed': uv_new, 'total_renewed': uv_total,
            'conv_rate': conv_rate, 'pv_active': pv_active, 'pv_pre_renewed': pv_pre,
            'pv_should_renew': pv_should, 'pv_new_renewed': pv_new, 'pv_total_renewed': pv_total,
        })
    advisor_list_raw.sort(key=lambda x: x['conv_rate'], reverse=True)

    # ── 按期次主讲排行 ──
    teachers_by_period = {}
    for pp in PERIODS:
        tlist = []
        for tname, v in by_teacher_period[pp].items():
            active = v['active']
            renewed = v.get('renewed_lock', 0)
            denom = v.get('denom', 0)
            pre = v.get('pre', 0)
            new = v.get('new', 0)
            if active == 0:
                continue
            rate = round(renewed / denom * 100, 1) if denom > 0 else 0
            should = active - pre
            conv_rate = round(new / should * 100, 1) if should > 0 else 0
            tlist.append({
                'name': tname, 'active': active, 'renewed': renewed,
                'renewal_rate': rate, 'pre_renewed': pre, 'should_renew': should,
                'new_renewed': new, 'total_renewed': pre + new, 'conv_rate': conv_rate,
                'subjects': sorted(v.get('subjects', set())),
            })
        tlist.sort(key=lambda x: x['renewal_rate'], reverse=True)
        teachers_by_period[pp] = tlist

    # ── 按期次顾问排行 ──
    advisors_by_period = {}
    for pp in PERIODS:
        alist = []
        for aname, v in by_advisor_period[pp].items():
            uv_active = len(v.get('uv_active', set()))
            uv_pre = len(v.get('uv_pre', set()))
            uv_new = len(v.get('uv_new', set()))
            uv_should = uv_active - uv_pre
            pv_active = v['active']
            pv_pre = v.get('pre', 0)
            pv_new = v.get('new', 0)
            pv_should = pv_active - pv_pre
            if uv_active == 0:
                continue
            conv_rate = round(uv_new / uv_should * 100, 1) if uv_should > 0 else 0
            alist.append({
                'name': aname, 'active': uv_active, 'pre_renewed': uv_pre,
                'new_renewed': uv_new, 'should_renew': uv_should,
                'total_renewed': uv_pre + uv_new, 'conv_rate': conv_rate,
                'pv_active': pv_active, 'pv_pre_renewed': pv_pre,
                'pv_should_renew': pv_should, 'pv_new_renewed': pv_new,
                'pv_total_renewed': pv_pre + pv_new,
            })
        alist.sort(key=lambda x: x['conv_rate'], reverse=True)
        advisors_by_period[pp] = alist

    # ── KPI ──
    renewal_rate = round(total_renewed_lock / total_denom * 100, 1) if total_denom > 0 else 0
    uv_count = len(total_denom_uv)
    renewal_uv_count = len(total_renewed_lock_uv)
    renewal_uv_rate = round(renewal_uv_count / uv_count * 100, 1) if uv_count > 0 else 0

    kpis = {
        'active_pv': total_active, 'refund_pv': total_refund, 'renewal_pv': total_renewed_lock,
        'uv_count': uv_count, 'renewal_uv_count': renewal_uv_count,
        'renewal_rate': renewal_rate, 'renewal_uv_rate': renewal_uv_rate,
    }

    # ── 2. 趋势数据（按天、按期次聚合，含 new / new_renew）──
    from datetime import timedelta
    trend_sql = 'SELECT * FROM calibration_runs WHERE 1=1'
    trend_params = []
    if start_date:
        trend_sql += ' AND date(run_time) >= ?'
        trend_params.append(start_date)
    if end_date:
        trend_sql += ' AND date(run_time) <= ?'
        trend_params.append(end_date)
    if not start_date and not end_date:
        default_start = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        trend_sql += ' AND date(run_time) >= ?'
        trend_params.append(default_start)
    trend_sql += ' ORDER BY run_time ASC'

    trend_runs = conn.execute(trend_sql, trend_params).fetchall()

    day_map = {}
    for row in trend_runs:
        run = dict(row)
        day = run['run_time'][:10]
        if day not in day_map or run['run_time'] > day_map[day]['run_time']:
            day_map[day] = run

    trend_all = []
    trend_by_period = {p: [] for p in PERIODS}

    prev_renew_all = 0
    prev_renew_period = {p: 0 for p in PERIODS}

    for day in sorted(day_map.keys()):
        run = day_map[day]
        rid = run['run_id']
        snapshots = conn.execute(
            'SELECT * FROM student_snapshots WHERE run_id = ?', (rid,)
        ).fetchall()

        day_active = 0
        day_refund = 0
        day_renew  = 0
        day_denom  = 0
        pd = {p: {'active': 0, 'refund': 0, 'renew': 0, 'denom': 0} for p in PERIODS}

        for s_row in snapshots:
            s = dict(s_row)
            # 分校过滤（与主数据口径一致）
            if branch_filter:
                s_branch = (s.get('branch') or '').strip()
                if s_branch not in branch_filter:
                    continue
            s_pt = (s.get('teaching_point') or '').strip()
            if points_filter and s_pt not in points_filter:
                continue
            try:
                subs = json.loads(s.get('subjects_json') or '{}')
            except Exception:
                subs = {}

            for subj, sd in subs.items():
                if not isinstance(sd, dict):
                    continue
                subj = get_line_subject(sd, subj)
                if subjects_filter and subj not in subjects_filter:
                    continue

                status     = (sd.get('status') or '').strip()
                period_val = (sd.get('period') or '').strip()
                teacher_val = (sd.get('teacher') or '').strip()
                is_denom_line = is_renewal_denom(sd)
                is_ren_lock   = is_renewed_by_source(sd)

                if periods_filter:
                    plist = [p.strip() for p in period_val.split('/') if p.strip()]
                    if not any(p in periods_filter for p in plist):
                        continue
                if teachers_filter and teacher_val not in teachers_filter:
                    continue

                # 全局筛选行级过滤（与主数据口径一致）
                if year_filter and (sd.get('year', '') or '') not in year_filter:
                    continue
                if season_filter and (sd.get('season', '') or '') not in season_filter:
                    continue
                if course_type_filter and (sd.get('course_type', '') or '') not in course_type_filter:
                    continue
                if class_mode_filter and norm_class_mode(sd.get('class_mode', '') or '') not in class_mode_filter:
                    continue

                if '在读' in status:
                    day_active += 1

                    for p in period_val.split('/'):
                        p = p.strip()
                        if p not in pd:
                            continue
                        if periods_filter and p not in periods_filter:
                            continue
                        pd[p]['active'] += 1

                # ── denom / renewed_lock 累积（不受 is_active 限制，独立计数维度）──
                if is_denom_line:
                    day_denom += 1
                    if is_ren_lock:
                        day_renew += 1
                    for p in period_val.split('/'):
                        p = p.strip()
                        if p not in pd:
                            continue
                        if periods_filter and p not in periods_filter:
                            continue
                        pd[p]['denom'] += 1
                        if is_ren_lock:
                            pd[p]['renew'] += 1

                elif status and status != '-' and '在读' not in status:
                    day_refund += 1
                    for p in period_val.split('/'):
                        p = p.strip()
                        if p not in pd:
                            continue
                        if periods_filter and p not in periods_filter:
                            continue
                        pd[p]['refund'] += 1

        new_count = _compute_filtered_new_count(
            conn, rid, points_filter, subjects_filter, periods_filter, teachers_filter,
            branch_filter=branch_filter, year_filter=year_filter, season_filter=season_filter,
            course_type_filter=course_type_filter, class_mode_filter=class_mode_filter,
        )

        new_renew_all = max(0, day_renew - prev_renew_all)
        new_renew_pd = {}
        for p in PERIODS:
            new_renew_pd[p] = max(0, pd[p]['renew'] - prev_renew_period[p])

        prev_renew_all = day_renew
        for p in PERIODS:
            prev_renew_period[p] = pd[p]['renew']

        date_label = day[-5:]
        trend_all.append({
            'date': date_label, 'active': day_active, 'refund': day_refund,
            'renew': day_renew, 'denom': day_denom, 'new': new_count, 'new_renew': new_renew_all,
        })
        for p in PERIODS:
            trend_by_period[p].append({
                'date': date_label, 'active': pd[p]['active'], 'refund': pd[p]['refund'],
                'renew': pd[p]['renew'], 'denom': pd[p]['denom'], 'new': new_count, 'new_renew': new_renew_pd[p],
            })

    conn.close()

    trend_data = {'all': trend_all}
    for p in PERIODS:
        trend_data[p] = trend_by_period[p]

    periods_available = ['all']
    for p in PERIODS:
        has_data = any(
            d['active'] > 0 or d['refund'] > 0 or d['renew'] > 0 or d['new_renew'] > 0
            for d in trend_by_period[p]
        )
        if has_data:
            periods_available.append(p)

    # ── 2.5 按期次拆分的 KPI ──
    # PV 维度：使用主循环已统计的 by_teacher_period 累计值（避免取趋势图最后一天 0 值）
    period_active_pv = {}
    period_refund_pv = {}
    period_renewal_pv = {}
    period_denom_pv = {}
    for p in PERIODS:
        period_active_pv[p] = sum(v.get('active', 0) for v in by_teacher_period[p].values())
        period_refund_pv[p] = sum(v.get('refund', 0) for v in by_teacher_period[p].values())
        period_renewal_pv[p] = sum(v.get('renewed_lock', 0) for v in by_teacher_period[p].values())
        period_denom_pv[p] = sum(v.get('denom', 0) for v in by_teacher_period[p].values())

    kpis_by_period = {}
    for p in PERIODS:
        active = period_active_pv[p]
        refund = period_refund_pv[p]
        renew = period_renewal_pv[p]
        denom_pv = period_denom_pv[p] or active
        uv_active = len(denom_uv_by_period.get(p, set()))
        uv_renew = len(renewed_lock_uv_by_period.get(p, set()))
        kpis_by_period[p] = {
            'active_pv': active, 'refund_pv': refund, 'renewal_pv': renew,
            'uv_count': uv_active, 'renewal_uv_count': uv_renew,
            'renewal_rate': round(renew / denom_pv * 100, 1) if denom_pv > 0 else 0,
            'renewal_uv_rate': round(uv_renew / uv_active * 100, 1) if uv_active > 0 else 0,
        }

    # ── 3. 筛选文本 ──
    filter_parts = []
    if start_date:
        filter_parts.append(f'开始: {start_date}')
    if end_date:
        filter_parts.append(f'结束: {end_date}')
    if subjects_filter:
        filter_parts.append(f'学科: {"/".join(subjects_filter)}')
    if points_filter:
        filter_parts.append(f'校区: {"/".join(points_filter)}')
    if selected_periods:
        filter_parts.append(f'期次: {"/".join(selected_periods)}')
    if teachers_filter:
        filter_parts.append(f'主讲: {"/".join(teachers_filter)}')
    if branch_filter:
        filter_parts.append(f'分校: {"/".join(branch_filter)}')
    if season_filter:
        filter_parts.append(f'学季: {"/".join(season_filter)}')
    if course_type_filter:
        filter_parts.append(f'课程类型: {"/".join(course_type_filter)}')
    if class_mode_filter:
        filter_parts.append(f'班型: {"/".join(class_mode_filter)}')
    filter_text = ' · '.join(filter_parts) if filter_parts else '全部数据'

    default_period = selected_periods[0] if len(selected_periods) == 1 else '全部'

    # ── 3.5 页面标题与页脚（按分校动态化）──
    # 分享页标题分校独立：单分校 → 分校名；多分校 → 拼接；全部 → 全部
    share_campaign = '26暑新初一'
    if branch_filter:
        branch_title = '/'.join(branch_filter)
    else:
        branch_title = '全部'
    page_title = f'{branch_title}{share_campaign} · UV数据看板'
    footer_text = f'雪球素养 · {page_title}'

    # ── 4. 月度拉新 / 续报转化数据（与主数据同筛选：教学点/学科/主讲；期次放开全量展示）──
    product_type_filter = _parse_filter(data.get('product_type', ''))
    monthly_data = get_acquisition_trends(
        periods='',
        teaching_point=','.join(points_filter) if points_filter else '',
        subject=','.join(subjects_filter) if subjects_filter else '',
        teacher=','.join(teachers_filter) if teachers_filter else '',
        branch=','.join(branch_filter) if branch_filter else '',
        season=','.join(season_filter) if season_filter else '',
        year=','.join(year_filter) if year_filter else '',
        course_type=','.join(course_type_filter) if course_type_filter else '',
        product_type=','.join(product_type_filter) if product_type_filter else '',
        class_mode=','.join(class_mode_filter) if class_mode_filter else '',
    )

    # ── 5. 渲染模板 ──
    share_id = uuid.uuid4().hex[:12]
    if getattr(sys, 'frozen', False):
        share_dir = os.path.join(get_data_dir(), 'shares')
    else:
        share_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'static', 'shares')
    os.makedirs(share_dir, exist_ok=True)
    share_path = os.path.join(share_dir, f'{share_id}.html')

    html = render_template(
        'share_page.html',
        update_time=today_str,
        trend_data_json=j.dumps(trend_data, ensure_ascii=False),
        kpis_json=j.dumps(kpis, ensure_ascii=False),
        kpis_by_period_json=j.dumps(kpis_by_period, ensure_ascii=False),
        teachers_json=j.dumps(teacher_list, ensure_ascii=False),
        advisors_json=j.dumps(advisor_list_raw, ensure_ascii=False),
        teachers_by_period_json=j.dumps(teachers_by_period, ensure_ascii=False),
        advisors_by_period_json=j.dumps(advisors_by_period, ensure_ascii=False),
        periods_available_json=j.dumps(periods_available, ensure_ascii=False),
        monthly_data_json=j.dumps(monthly_data, ensure_ascii=False),
        filter_text=filter_text,
        default_period=default_period,
        period_order=PERIOD_ORDER,
        page_title=page_title,
        footer_text=footer_text,
    )

    with open(share_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return jsonify({
        'share_id': share_id,
        'url': f'/share-view/{share_id}',
        'share_dir': share_dir,
        'kpis': kpis,
        'filter_text': filter_text,
        'teacher_count': len(teacher_list),
        'advisor_count': len(advisor_list_raw),
        'trend_days': len(trend_all),
        'periods_available': periods_available,
    })


@share_bp.route('/share-view/<share_id>')
def share_view(share_id):
    """查看分享页面"""
    if getattr(sys, 'frozen', False):
        share_dir = os.path.join(get_data_dir(), 'shares')
    else:
        share_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'static', 'shares')
    share_path = os.path.join(share_dir, f'{share_id}.html')
    if not os.path.exists(share_path):
        return 'Share page not found', 404
    return send_file(share_path)


@share_bp.route('/api/share/deploy', methods=['POST'])
def api_share_deploy():
    """部署分享页面到云端"""
    # TODO: 接入 CloudStudio 部署
    return jsonify({'error': 'Deploy not implemented in 2.0 yet'})


@share_bp.route('/api/share/deploy-status/<request_id>')
def api_share_deploy_status(request_id):
    """部署状态查询"""
    return jsonify({'error': 'Deploy status not implemented in 2.0 yet'})
