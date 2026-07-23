"""
UV台帳管理系统 数据库层
存储校准历史、台帐快照等
"""
import sqlite3
import json
import os
import sys
from datetime import datetime

# ── 教室→教学点映射（班级ID的教学点归属由教室决定）──
ROOM_POINT_MAP = {
    '01智慧林': '同创汇',
    '02彩虹桥': '同创汇',
    '03识海阁': '同创汇',
    '03品尚': '天成大厦',
    '教室2': '新宝利',
    '教室3': '新宝利',
    '教室4': '新宝利',
    '教室5': '新宝利',
}

def get_room_teaching_point(room_name, fallback=''):
    """从教室名推导教学点归属（班级归属由教室绑定）"""
    if not room_name:
        return fallback
    room = str(room_name).strip()
    return ROOM_POINT_MAP.get(room, fallback)


# ── 数据目录：支持打包模式 ──
_DATA_DIR = None

def set_data_dir(dir_path):
    """设置数据目录（打包为 .app 时由 app.py 调用）"""
    global DB_PATH, _DATA_DIR
    _DATA_DIR = dir_path
    DB_PATH = os.path.join(dir_path, 'uv_dashboard.db')

def _default_data_dir():
    if getattr(sys, 'frozen', False):
        return os.path.expanduser('~/Library/Application Support/UV Dashboard')
    return os.path.dirname(os.path.abspath(__file__))

if _DATA_DIR is None:
    DB_PATH = os.path.join(_default_data_dir(), 'uv_dashboard.db')
else:
    DB_PATH = os.path.join(_DATA_DIR, 'uv_dashboard.db')


def is_continue_fall(val):
    """判断任意形式的续秋标记是否表示已续报：支持布尔、是/已续/T/AC/AL/1/true 等"""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if not s or s == '-':
        return False
    return s in {'是', '已续', 't', 'ac', 'al', 'true', 'yes', '1', 'y'}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS calibration_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT UNIQUE NOT NULL,
            run_time TEXT NOT NULL,
            total_students INTEGER,
            active_students INTEGER,
            refund_students INTEGER,
            new_students INTEGER,
            changes_count INTEGER,
            stats_json TEXT,
            students_json TEXT,
            ledger_path TEXT,
            report_path TEXT,
            enrollment_file TEXT,
            old_ledger_file TEXT
        );

        CREATE TABLE IF NOT EXISTS student_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            uid TEXT NOT NULL,
            name TEXT,
            teaching_point TEXT,
            advisor TEXT,
            channel TEXT,
            status TEXT,
            period_combined TEXT,
            subjects_json TEXT,
            manual_json TEXT,
            FOREIGN KEY (run_id) REFERENCES calibration_runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS change_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            uid TEXT NOT NULL,
            name TEXT,
            subject TEXT,
            change_type TEXT,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            FOREIGN KEY (run_id) REFERENCES calibration_runs(run_id)
        );

        CREATE INDEX IF NOT EXISTS idx_snapshot_run ON student_snapshots(run_id);
        CREATE INDEX IF NOT EXISTS idx_snapshot_uid ON student_snapshots(uid);
        CREATE INDEX IF NOT EXISTS idx_change_run ON change_records(run_id);
    ''')

    # 迁移：若 students_json 列不存在则新增
    cursor = conn.execute('PRAGMA table_info(calibration_runs)')
    columns = [row['name'] for row in cursor.fetchall()]
    if 'students_json' not in columns:
        conn.execute('ALTER TABLE calibration_runs ADD COLUMN students_json TEXT')
        conn.commit()

    conn.close()


def _compute_diffs(curr_students, prev_students):
    """对比两次快照，生成变动记录列表"""
    changes = []
    prev_by_uid = {s['uid']: s for s in prev_students}
    curr_by_uid = {s['uid']: s for s in curr_students}

    for uid, curr in curr_by_uid.items():
        prev = prev_by_uid.get(uid)
        if prev is None:
            # 新增学员
            for subj in ['雪球思维', '悦读创作', '双语素养']:
                if curr.get(f'{subj}_status', '-') == '在读':
                    changes.append({
                        'uid': uid, 'name': curr['name'], 'subject': subj,
                        'type': '新增学员', 'field': '全部',
                        'old': '-', 'new': f"{subj}-{curr.get(f'{subj}_class_id', '')}"
                    })
            continue

        # 比较各科
        for subj in ['雪球思维', '悦读创作', '双语素养']:
            curr_subj = {}
            prev_subj = {}
            try:
                curr_subj = json.loads(curr.get('subjects_json', '{}'))
            except:
                pass
            try:
                prev_subj = json.loads(prev.get('subjects_json', '{}'))
            except:
                pass

            c_subj = curr_subj.get(subj, {}) if isinstance(curr_subj, dict) else {}
            p_subj = prev_subj.get(subj, {}) if isinstance(prev_subj, dict) else {}

            curr_status = c_subj.get('status', '-') if isinstance(c_subj, dict) else '-'
            prev_status = p_subj.get('status', '-') if isinstance(p_subj, dict) else '-'

            # 退费检测
            if '退费' in curr_status and '退费' not in prev_status:
                changes.append({
                    'uid': uid, 'name': curr['name'], 'subject': subj,
                    'type': '退费出班', 'field': '状态',
                    'old': prev_status, 'new': curr_status
                })

            # 字段变动检查（仅比对在读学科）
            if '在读' in curr_status:
                for field, field_cn in [
                    ('class_id', '班级ID'), ('teacher', '主讲'), ('room', '教室'),
                    ('time_slot', '上课时段'), ('class_type', '班型'), ('period', '期次')
                ]:
                    cv = str(c_subj.get(field, '')) if isinstance(c_subj, dict) else ''
                    pv = str(p_subj.get(field, '')) if isinstance(p_subj, dict) else ''
                    if cv and pv and cv != pv and cv != '-' and pv != '-':
                        # 归类变动类型
                        change_type = '细节变动'
                        if field in ('period',):
                            if field == 'period':
                                change_type = '仅调期'
                        if field in ('class_id', 'class_type'):
                            change_type = '仅换班'
                        if field == 'period' and (cv and pv and cv != pv):
                            # check if both period and class changed
                            c_class = str(c_subj.get('class_id', '')) if isinstance(c_subj, dict) else ''
                            p_class = str(p_subj.get('class_id', '')) if isinstance(p_subj, dict) else ''
                            if c_class and p_class and c_class != p_class:
                                change_type = '调期+换班'
                            else:
                                change_type = '仅调期'
                        if field in ('class_id',):
                            c_period = str(c_subj.get('period', '')) if isinstance(c_subj, dict) else ''
                            p_period = str(p_subj.get('period', '')) if isinstance(p_subj, dict) else ''
                            if c_period and p_period and c_period != p_period:
                                change_type = '调期+换班'
                            else:
                                change_type = '仅换班'

                        changes.append({
                            'uid': uid, 'name': curr['name'], 'subject': subj,
                            'type': change_type, 'field': field_cn,
                            'old': pv, 'new': cv
                        })

    return changes


def save_calibration_run(run_id, stats, result, ledger_path, report_path, enrollment_file, old_ledger_file):
    """保存一次校准运行的完整记录，并自动对比上一次快照生成变动记录"""
    conn = get_db()

    # 获取上一次运行的学员快照用于diff
    prev_run = conn.execute(
        'SELECT run_id FROM calibration_runs ORDER BY run_time DESC LIMIT 1'
    ).fetchone()
    prev_students = []
    if prev_run:
        prev_rows = conn.execute(
            'SELECT * FROM student_snapshots WHERE run_id = ?', (prev_run['run_id'],)
        ).fetchall()
        prev_students = [dict(r) for r in prev_rows]

    # 清空本次run_id的旧数据（如果重复校准）
    conn.execute('DELETE FROM student_snapshots WHERE run_id = ?', (run_id,))
    conn.execute('DELETE FROM change_records WHERE run_id = ?', (run_id,))

    # 保存学员快照（先保存，方便后续diff）
    curr_students_for_diff = []
    for s in result.get('students', []):
        subjects = {}
        for subj in ['雪球思维', '悦读创作', '双语素养']:
            # fall_pay_time: datetime → ISO string for JSON serialization
            fpt = s.get(f'{subj}_fall_pay_time')
            fpt_str = fpt.isoformat() if fpt and hasattr(fpt, 'isoformat') else None
            subjects[subj] = {
                'class_id': s.get(f'{subj}_class_id', ''),
                'teacher': s.get(f'{subj}_teacher', ''),
                'room': s.get(f'{subj}_room', ''),
                'time_slot': s.get(f'{subj}_time_slot', ''),
                'class_type': s.get(f'{subj}_class_type', ''),
                'period': s.get(f'{subj}_period_single', ''),
                'status': s.get(f'{subj}_status', ''),
                'continue_fall': s.get(f'{subj}_continue_fall', ''),
                'fall_pay_time': fpt_str,
            }

        manual = {
            'channel': s.get('channel', ''),
            'purpose': s.get('purpose', ''),
            'notes': s.get('notes', ''),
            'vip_group': s.get('vip_group', ''),
            'renew_willingness': s.get('renew_willingness', ''),
        }

        conn.execute('''
            INSERT INTO student_snapshots
            (run_id, uid, name, teaching_point, advisor, channel, status, period_combined, subjects_json, manual_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            run_id,
            s['uid'],
            s['name'],
            s.get('teaching_point', ''),
            s.get('advisor', ''),
            s.get('channel', ''),
            s['status'],
            s.get('period_combined', ''),
            json.dumps(subjects, ensure_ascii=False),
            json.dumps(manual, ensure_ascii=False),
        ))

        curr_students_for_diff.append({
            'uid': s['uid'], 'name': s['name'],
            'subjects_json': json.dumps(subjects, ensure_ascii=False),
        })

    # 使用 calibrator 直接生成的 change_details（优先），否则回退到 _compute_diffs
    computed_changes = result.get('change_details', [])
    if not computed_changes and prev_students:
        computed_changes = _compute_diffs(curr_students_for_diff, prev_students)

    # 统计
    active_count = sum(1 for s in result.get('students', []) if '在读' in s.get('status', ''))
    new_count = stats.get('new_students', 0)
    refund_count = stats.get('new_refund_students', stats.get('refund_students', 0))
    change_count = stats.get('changes_count', len(computed_changes))

    # 保存变动记录（使用 calibrator 的 change_details 格式）
    for c in computed_changes:
        conn.execute('''
            INSERT INTO change_records
            (run_id, uid, name, subject, change_type, field_name, old_value, new_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            run_id,
            c.get('uid', ''),
            c.get('name', ''),
            c.get('subject', ''),
            c.get('change_type', c.get('type', '')),
            c.get('field_name', c.get('field', '')),
            str(c.get('old_value', c.get('old', ''))),
            str(c.get('new_value', c.get('new', ''))),
        ))

    # 保存运行记录
    conn.execute('''
        INSERT OR REPLACE INTO calibration_runs
        (run_id, run_time, total_students, active_students, refund_students,
         new_students, changes_count, stats_json, students_json,
         ledger_path, report_path, enrollment_file, old_ledger_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        run_id,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        stats.get('total_students', 0),
        active_count,
        refund_count,
        new_count,
        change_count,
        json.dumps(stats, ensure_ascii=False, default=str),
        json.dumps(result.get('students', []), ensure_ascii=False, default=str),
        ledger_path,
        report_path,
        enrollment_file,
        old_ledger_file,
    ))

    conn.commit()
    conn.close()


def get_all_runs():
    """获取所有校准运行记录"""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM calibration_runs ORDER BY run_time DESC'
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_run_by_id(run_id):
    """获取单次运行详情"""
    conn = get_db()
    run = conn.execute(
        'SELECT * FROM calibration_runs WHERE run_id = ?', (run_id,)
    ).fetchone()
    if not run:
        conn.close()
        return None

    students = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ?', (run_id,)
    ).fetchall()

    changes = conn.execute(
        'SELECT * FROM change_records WHERE run_id = ?', (run_id,)
    ).fetchall()

    conn.close()
    return {
        'run': dict(run),
        'students': [dict(s) for s in students],
        'changes': [dict(c) for c in changes],
    }


def get_latest_run():
    """获取最新一次校准运行"""
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM calibration_runs ORDER BY run_time DESC LIMIT 1'
    ).fetchone()
    if row is None:
        conn.close()
        return None
    run_id = row['run_id']
    students = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ?', (run_id,)
    ).fetchall()
    changes = conn.execute(
        'SELECT * FROM change_records WHERE run_id = ?', (run_id,)
    ).fetchall()
    conn.close()
    return {
        'run': dict(row),
        'students': [dict(s) for s in students],
        'changes': [dict(c) for c in changes],
    }


def get_daily_stats():
    """获取每日校准统计（用于监控趋势）"""
    conn = get_db()
    rows = conn.execute('''
        SELECT date(run_time) as day,
               COUNT(*) as run_count,
               MAX(total_students) as students,
               MAX(refund_students) as refunds,
               MAX(new_students) as new_students
        FROM calibration_runs
        GROUP BY date(run_time)
        ORDER BY day
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_filtered_students(run_id, filters=None):
    """
    多维度筛选学员
    filters: dict with keys: teaching_point, teacher, period, subject, class_name, status
    """
    conn = get_db()
    query = 'SELECT * FROM student_snapshots WHERE run_id = ?'
    params = [run_id]

    rows = conn.execute(query, params).fetchall()
    conn.close()

    students = [dict(r) for r in rows]

    if not filters:
        return students

    result = []
    for s in students:
        subjects = json.loads(s.get('subjects_json', '{}'))

        # 教学点筛选
        if filters.get('teaching_point'):
            if s.get('teaching_point', '') != filters['teaching_point']:
                continue

        # 状态筛选
        if filters.get('status'):
            if filters['status'] not in s.get('status', ''):
                continue

        # 期次筛选：检查任一科期次包含筛选值
        if filters.get('period'):
            matched = False
            for subj_data in subjects.values():
                if isinstance(subj_data, dict) and filters['period'] in subj_data.get('period', ''):
                    matched = True
                    break
            if not matched:
                continue

        # 老师筛选（支持多选，逗号分隔）
        if filters.get('teacher'):
            teacher_list = [t.strip() for t in filters['teacher'].split(',') if t.strip()]
            matched = False
            for subj_data in subjects.values():
                if isinstance(subj_data, dict):
                    tch = subj_data.get('teacher', '')
                    if any(t in tch for t in teacher_list):
                        matched = True
                        break
            if not matched:
                continue

        # 秋季续费状态筛选（按任一科目是否已续）
        if filters.get('continue_fall'):
            cf_mode = filters['continue_fall']
            has_any_renewed = False
            for subj_data in subjects.values():
                if isinstance(subj_data, dict) and is_continue_fall(subj_data.get('continue_fall', '')):
                    has_any_renewed = True
                    break
            if cf_mode == 'renewed' and not has_any_renewed:
                continue
            if cf_mode == 'not_renewed' and has_any_renewed:
                continue

        # 学科状态筛选
        if filters.get('subject_status'):
            subj, status = filters['subject_status'].split(':', 1)
            if subj in subjects:
                subj_data = subjects[subj]
                if isinstance(subj_data, dict) and status not in subj_data.get('status', ''):
                    continue

        result.append(s)

    return result


def get_distinct_values(run_id, field):
    """获取某字段的所有distinct值"""
    conn = get_db()
    if field == 'teaching_point':
        rows = conn.execute(
            'SELECT DISTINCT teaching_point FROM student_snapshots WHERE run_id = ? AND teaching_point != "" ORDER BY teaching_point',
            (run_id,)
        ).fetchall()
        conn.close()
        return [r['teaching_point'] for r in rows]

    if field == 'period':
        # 从subjects_json中提取
        rows2 = conn.execute(
            'SELECT subjects_json FROM student_snapshots WHERE run_id = ?', (run_id,)
        ).fetchall()
        conn.close()
        periods = set()
        for r in rows2:
            try:
                subjects = json.loads(r['subjects_json'])
            except Exception:
                continue
            for subj_data in subjects.values():
                if isinstance(subj_data, dict):
                    p = subj_data.get('period', '')
                    if p and p != '-':
                        for pp in p.split('/'):
                            pp = pp.strip()
                            if pp:
                                periods.add(pp)
        return sorted(periods)

    if field == 'teacher':
        # 从subjects_json中提取
        rows2 = conn.execute(
            'SELECT subjects_json FROM student_snapshots WHERE run_id = ?', (run_id,)
        ).fetchall()
        conn.close()
        teachers = set()
        for r in rows2:
            try:
                subjects = json.loads(r['subjects_json'])
            except Exception:
                continue
            for subj_data in subjects.values():
                if isinstance(subj_data, dict):
                    t = subj_data.get('teacher', '')
                    if t and t != '-':
                        teachers.add(t)
        return sorted(teachers)

    if field == 'advisor':
        rows = conn.execute(
            'SELECT DISTINCT advisor FROM student_snapshots WHERE run_id = ? AND advisor != "" ORDER BY advisor',
            (run_id,)
        ).fetchall()
        conn.close()
        return [r['advisor'] for r in rows]

    conn.close()
    return []


def get_period_teaching_point_matrix(run_id):
    """期次×教学点矩阵：每格 = 在读科目人次 + 分学科 / UV人头 / 续报率
    教学点归属从教室推导（班级归属由教室决定）
    """
    period_order = ['零期', '一期', '二期', '三期']
    conn = get_db()
    rows = conn.execute(
        'SELECT uid, teaching_point, subjects_json FROM student_snapshots WHERE run_id = ?',
        (run_id,)
    ).fetchall()
    conn.close()

    subject_order = ['雪球思维', '悦读创作', '双语素养']

    # ── 教学点集合：从教室推导 ──
    points_set = set()
    for r in rows:
        fallback_pt = r['teaching_point']
        try:
            subjects = json.loads(r['subjects_json'])
        except Exception:
            continue
        for subj, sd in subjects.items():
            if not isinstance(sd, dict):
                continue
            room = (sd.get('room') or '').strip()
            pt = get_room_teaching_point(room, fallback_pt)
            if pt:
                points_set.add(pt)
        if fallback_pt:
            points_set.add(fallback_pt)
    pts_sorted = sorted(points_set)

    # 初始化矩阵: { pt: { period: { active, renewed, uv: set(), subjects: {}, classes: set() } } }
    matrix = {}
    for pt in pts_sorted:
        matrix[pt] = {}
        for p in period_order:
            matrix[pt][p] = {
                'active': 0, 'renewed': 0, 'uv': set(),
                'subjects': {s: 0 for s in subject_order},
                'classes': {s: set() for s in subject_order},
                'all_classes': set()
            }

    for r in rows:
        fallback_pt = r['teaching_point']
        uid = r['uid']
        try:
            subjects = json.loads(r['subjects_json'])
        except Exception:
            continue
        for subj_name, subj_data in subjects.items():
            if not isinstance(subj_data, dict):
                continue
            period = subj_data.get('period', '')
            if not period or period == '-':
                continue
            # ── 教学点从教室推导 ──
            room = (subj_data.get('room') or '').strip()
            pt = get_room_teaching_point(room, fallback_pt)
            if not pt or pt not in matrix:
                continue
            status = subj_data.get('status', '-')
            is_active = '在读' in status
            is_renewed = is_continue_fall(subj_data.get('continue_fall', ''))
            class_id = subj_data.get('class_id', '') or ''
            for p in period.split('/'):
                p = p.strip()
                if p not in period_order:
                    continue
                if is_active:
                    matrix[pt][p]['active'] += 1
                    matrix[pt][p]['uv'].add(uid)
                    if subj_name in matrix[pt][p]['subjects']:
                        matrix[pt][p]['subjects'][subj_name] += 1
                    if class_id and class_id != '-':
                        matrix[pt][p]['classes'][subj_name].add(class_id)
                        matrix[pt][p]['all_classes'].add(class_id)
                if is_renewed:
                    matrix[pt][p]['renewed'] += 1

    # 组装结果: 将uv set转为count, 计算续报率, 班级数
    result_matrix = {}
    pt_totals = {}
    for pt in pts_sorted:
        result_matrix[pt] = {}
        pt_totals[pt] = {'active': 0, 'renewed': 0, 'uv': 0, 'subjects': {s: 0 for s in subject_order}, 'classes': {s: 0 for s in subject_order}, 'class_count': 0}
        pt_class_set = set()
        for p in period_order:
            cell = matrix[pt][p]
            uv_count = len(cell['uv'])
            renewal_rate = round(cell['renewed'] / cell['active'] * 100, 1) if cell['active'] > 0 else 0
            class_count = len(cell['all_classes'])
            subject_classes = {s: len(cell['classes'][s]) for s in subject_order}
            result_matrix[pt][p] = {
                'active': cell['active'],
                'renewed': cell['renewed'],
                'uv': uv_count,
                'subjects': dict(cell['subjects']),
                'renewal_rate': renewal_rate,
                'class_count': class_count,
                'subject_classes': subject_classes,
            }
            pt_totals[pt]['active'] += cell['active']
            pt_totals[pt]['renewed'] += cell['renewed']
            for s in subject_order:
                pt_totals[pt]['subjects'][s] += cell['subjects'][s]
                pt_totals[pt]['classes'][s] += subject_classes[s]
            pt_class_set.update(cell['all_classes'])
        pt_totals[pt]['uv'] = len(set().union(*[matrix[pt][p]['uv'] for p in period_order]))
        pt_totals[pt]['class_count'] = len(pt_class_set)
        pt_totals[pt]['renewal_rate'] = round(pt_totals[pt]['renewed'] / pt_totals[pt]['active'] * 100, 1) if pt_totals[pt]['active'] > 0 else 0

    # 行列合计
    period_totals = {}
    for p in period_order:
        period_totals[p] = {'active': 0, 'renewed': 0, 'uv': 0, 'subjects': {s: 0 for s in subject_order}, 'classes': {s: 0 for s in subject_order}, 'class_count': 0}
        period_class_set = set()
        for pt in pts_sorted:
            period_totals[p]['active'] += result_matrix[pt][p]['active']
            period_totals[p]['renewed'] += result_matrix[pt][p]['renewed']
            period_totals[p]['uv'] += result_matrix[pt][p]['uv']
            period_class_set.update(matrix[pt][p]['all_classes'])
            for s in subject_order:
                period_totals[p]['subjects'][s] += result_matrix[pt][p]['subjects'][s]
                period_totals[p]['classes'][s] += result_matrix[pt][p]['subject_classes'][s]
        period_totals[p]['class_count'] = len(period_class_set)
        period_totals[p]['renewal_rate'] = round(period_totals[p]['renewed'] / period_totals[p]['active'] * 100, 1) if period_totals[p]['active'] > 0 else 0

    grand = {'active': 0, 'renewed': 0, 'uv': 0, 'subjects': {s: 0 for s in subject_order}, 'classes': {s: 0 for s in subject_order}, 'class_count': 0}
    grand_class_set = set()
    for pt in pts_sorted:
        for p in period_order:
            grand['active'] += result_matrix[pt][p]['active']
            grand['renewed'] += result_matrix[pt][p]['renewed']
            grand_class_set.update(matrix[pt][p]['all_classes'])
    grand['uv'] = len(set().union(*[set().union(*[matrix[pt][p]['uv'] for p in period_order]) for pt in pts_sorted]))
    for s in subject_order:
        grand['subjects'][s] = period_totals[period_order[0]]['subjects'].get(s, 0) + \
            period_totals[period_order[1]]['subjects'].get(s, 0) + \
            period_totals[period_order[2]]['subjects'].get(s, 0) + \
            period_totals[period_order[3]]['subjects'].get(s, 0)
        grand['classes'][s] = period_totals[period_order[0]]['classes'].get(s, 0) + \
            period_totals[period_order[1]]['classes'].get(s, 0) + \
            period_totals[period_order[2]]['classes'].get(s, 0) + \
            period_totals[period_order[3]]['classes'].get(s, 0)
    grand['class_count'] = len(grand_class_set)
    grand_rate = round(grand['renewed'] / grand['active'] * 100, 1) if grand['active'] > 0 else 0
    grand['renewal_rate'] = grand_rate

    return {
        'periods': period_order,
        'subjects': subject_order,
        'teaching_points': pts_sorted,
        'matrix': result_matrix,
        'period_totals': period_totals,
        'point_totals': pt_totals,
        'grand_total': grand,
    }


def get_class_schedule(run_id, teaching_point=None, periods=None, teacher=None):
    """排班排课数据：按教学点归类的班级列表，只含在读学员，支持期次多选/教学点/老师筛选
    
    去重逻辑：按班级ID唯一，班级归属教学点由教室决定（教室→教学点映射）
    """
    conn = get_db()
    rows = conn.execute(
        'SELECT uid, name, teaching_point, subjects_json FROM student_snapshots WHERE run_id = ?',
        (run_id,)
    ).fetchall()
    conn.close()

    if teaching_point:
        rows = [r for r in rows if r['teaching_point'] == teaching_point]

    # 第一阶段：按 (class_id, subject) 聚合，教学点从教室推导
    classes_raw = {}  # key: (class_id, subject)
    
    for r in rows:
        try:
            subjects = json.loads(r['subjects_json'])
        except Exception:
            continue
        for subj, subj_data in subjects.items():
            if not isinstance(subj_data, dict):
                continue
            class_id = subj_data.get('class_id', '')
            if not class_id or class_id == '-':
                continue
            status = subj_data.get('status', '-')
            is_active = '在读' in status
            # 只统计在读学员
            if not is_active:
                continue
            # 老师筛选（支持多选，逗号分隔）
            if teacher:
                teacher_list = [t.strip() for t in teacher.split(',') if t.strip()]
                if subj_data.get('teacher', '') not in teacher_list:
                    continue
            # 期次筛选：如果指定了期次，班级period必须匹配至少一个
            class_period = subj_data.get('period', '')
            if periods and class_period:
                matched = any(p in class_period for p in periods)
                if not matched:
                    continue

            # ── 教学点从教室推导（班级归属由教室决定）──
            room = subj_data.get('room', '')
            fallback_tp = r['teaching_point']
            class_pt = get_room_teaching_point(room, fallback_tp)

            key = (class_id, subj)
            if key not in classes_raw:
                classes_raw[key] = {
                    'class_id': class_id,
                    'subject': subj,
                    'teaching_point': class_pt,
                    'teacher': subj_data.get('teacher', '-'),
                    'room': subj_data.get('room', '-'),
                    'time_slot': subj_data.get('time_slot', '-'),
                    'period': class_period,
                    'class_type': subj_data.get('class_type', '-'),
                    'active_count': 0,
                    'renewed_count': 0,
                    'students': [],
                }
            is_renewed = is_continue_fall(subj_data.get('continue_fall', ''))
            classes_raw[key]['active_count'] += 1
            if is_renewed:
                classes_raw[key]['renewed_count'] += 1
            classes_raw[key]['students'].append({
                'uid': r['uid'],
                'name': r['name'],
                'is_active': True,
                'is_renewed': is_renewed,
            })

    # 第二阶段：去重合并（教室已确定教学点，无需多数原则）
    classes = {}  # key: (class_id, subject) - 去重后的班级
    for key, cls in classes_raw.items():
        classes[key] = cls

    # 按教学点归组
    by_point = {}
    for key, cls in classes.items():
        pt = cls['teaching_point']
        if pt not in by_point:
            by_point[pt] = []
        by_point[pt].append(cls)

    # 每个教学点内按学科+期次+时段排序（时间顺序）
    for pt in by_point:
        by_point[pt].sort(key=lambda c: (c['subject'], c['period'], c['time_slot'], c['class_id']))

    return {
        'teaching_points': sorted(by_point.keys()),
        'classes_by_point': by_point,
        'total_classes': len(classes),
        'total_active': sum(c['active_count'] for c in classes.values()),
        'total_renewed': sum(c['renewed_count'] for c in classes.values()),
    }


def get_teacher_detail(run_id, teacher, period=None, teaching_point=None):
    """老师维度详情：名下班级、期次、教学点、学员汇总，支持期次/教学点筛选"""
    conn = get_db()
    rows = conn.execute(
        'SELECT uid, name, teaching_point, advisor, status, period_combined, subjects_json, manual_json '
        'FROM student_snapshots WHERE run_id = ?',
        (run_id,)
    ).fetchall()
    conn.close()

    # 找出该老师名下的所有学科
    # key: (class_id, subject) — 按班级ID唯一，跨教学点不拆分
    teacher_class_raw = {}  # (class_id, subject) -> { tp: count, ... }
    teacher_students = []

    for r in rows:
        # 教学点筛选
        if teaching_point and r['teaching_point'] != teaching_point:
            continue
        try:
            subjects = json.loads(r['subjects_json'])
        except Exception:
            continue
        for subj, subj_data in subjects.items():
            if not isinstance(subj_data, dict):
                continue
            if teacher not in subj_data.get('teacher', ''):
                continue
            class_id = subj_data.get('class_id', '')
            status = subj_data.get('status', '-')
            is_active = '在读' in status
            is_renewed = is_continue_fall(subj_data.get('continue_fall', ''))
            period_val = subj_data.get('period', '')
            # 期次筛选
            if period:
                period_list = [p.strip() for p in period_val.split('/') if p.strip()]
                if period not in period_list:
                    continue

            # 收集三科主讲老师
            math_teacher = ''
            chinese_teacher = ''
            english_teacher = ''
            for s_name, s_data in subjects.items():
                if not isinstance(s_data, dict):
                    continue
                t = s_data.get('teacher', '')
                if s_name == '雪球思维':
                    math_teacher = t
                elif s_name == '悦读创作':
                    chinese_teacher = t
                elif s_name == '双语素养':
                    english_teacher = t

            key = (class_id, subj)
            if key not in teacher_class_raw:
                teacher_class_raw[key] = {
                    'class_id': class_id,
                    'subject': subj,
                    'period': period_val,
                    'time_slot': subj_data.get('time_slot', '-'),
                    'room': subj_data.get('room', '-'),
                    'class_type': subj_data.get('class_type', '-'),
                    'active_count': 0,
                    'renewed_count': 0,
                    'tp_counts': {},  # teaching_point -> count
                }
            if is_active:
                teacher_class_raw[key]['active_count'] += 1
            if is_renewed:
                teacher_class_raw[key]['renewed_count'] += 1
            teacher_class_raw[key]['tp_counts'][r['teaching_point']] = \
                teacher_class_raw[key]['tp_counts'].get(r['teaching_point'], 0) + 1

            try:
                raw_manual = r['manual_json']
                manual = json.loads(raw_manual) if raw_manual else {}
            except Exception:
                manual = {}

            teacher_students.append({
                'uid': r['uid'],
                'name': r['name'],
                'teaching_point': r['teaching_point'],
                'advisor': r['advisor'] or '',
                'period_combined': r['period_combined'] or '',
                'subject': subj,
                'status': status,
                'period': period_val,
                'class_id': class_id,
                'is_active': is_active,
                'is_renewed': is_renewed,
                'continue_fall': subj_data.get('continue_fall', ''),
                'time_slot': subj_data.get('time_slot', '-'),
                'class_type': subj_data.get('class_type', '-'),
                'math_teacher': math_teacher,
                'chinese_teacher': chinese_teacher,
                'english_teacher': english_teacher,
                'channel': manual.get('channel', ''),
                'renew_willingness': manual.get('renew_willingness', ''),
            })

    # 班级归属教学点从教室推导，未知教室回退到学员多数原则
    teacher_classes = []
    for key, cdata in teacher_class_raw.items():
        tp_counts = cdata.pop('tp_counts', {})
        room = cdata.get('room', '')
        class_pt = get_room_teaching_point(room)
        if not class_pt and tp_counts:
            class_pt = max(tp_counts, key=tp_counts.get)
        cdata['teaching_point'] = class_pt
        cdata['tp_distribution'] = tp_counts  # 保留分布信息供参考
        period_counts = set()
        if cdata['period'] and cdata['period'] != '-':
            for p in cdata['period'].split('/'):
                p = p.strip()
                if p:
                    period_counts.add(p)
        cdata['periods_list'] = sorted(period_counts)
        teacher_classes.append(cdata)

    # 汇总统计
    active_students = [s for s in teacher_students if s['is_active']]
    renewed_students = [s for s in teacher_students if s['is_renewed']]

    by_point = {}
    for s in active_students:
        pt = s['teaching_point']
        by_point[pt] = by_point.get(pt, 0) + 1

    by_period = {}
    for s in active_students:
        if s['period'] and s['period'] != '-':
            for p in s['period'].split('/'):
                p = p.strip()
                if p:
                    by_period[p] = by_period.get(p, 0) + 1

    return {
        'teacher': teacher,
        'classes': sorted(teacher_classes, key=lambda c: (c['subject'], c['period'])),
        'total_classes': len(teacher_classes),
        'total_active': len(active_students),
        'total_renewed': len(renewed_students),
        'by_teaching_point': by_point,
        'by_period': by_period,
        'students': sorted(teacher_students, key=lambda s: (s['subject'], s['name'])),
    }


def get_student_detail(run_id, uid):
    """学员详情：三科在读信息"""
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ? AND uid = ?',
        (run_id, uid)
    ).fetchone()
    conn.close()

    if not row:
        return None

    try:
        subjects = json.loads(row['subjects_json'])
    except Exception:
        subjects = {}

    try:
        manual = json.loads(row['manual_json'])
    except Exception:
        manual = {}

    # Format subjects with all detail
    formatted_subjects = {}
    for subj in ['雪球思维', '悦读创作', '双语素养']:
        sd = subjects.get(subj, {})
        if isinstance(sd, dict):
            formatted_subjects[subj] = {
                'class_id': sd.get('class_id', '-'),
                'teacher': sd.get('teacher', '-'),
                'room': sd.get('room', '-'),
                'time_slot': sd.get('time_slot', '-'),
                'class_type': sd.get('class_type', '-'),
                'period': sd.get('period', '-'),
                'status': sd.get('status', '-'),
                'continue_fall': sd.get('continue_fall', '-'),
            }
        else:
            formatted_subjects[subj] = {'status': '-', 'period': '-', 'class_id': '-', 'teacher': '-',
                                         'room': '-', 'time_slot': '-', 'class_type': '-', 'continue_fall': '-'}

    return {
        'uid': row['uid'],
        'name': row['name'],
        'teaching_point': row['teaching_point'],
        'advisor': row['advisor'],
        'channel': manual.get('channel', ''),
        'status': row['status'],
        'period_combined': row['period_combined'],
        'subjects': formatted_subjects,
        'manual': manual,
    }


def get_teacher_list(run_id, period=None, teaching_point=None, teacher=None):
    """获取所有老师和每个老师的简要统计，支持期次/教学点/老师筛选
    含续报率 + 转化率双维度数据"""
    period_order = ['零期', '一期', '二期', '三期']
    period_schedule = {
        '零期': {'start': (6, 29), 'end': (7, 10)},
        '一期': {'start': (7, 13), 'end': (7, 24)},
        '二期': {'start': (7, 27), 'end': (8, 7)},
        '三期': {'start': (8, 10), 'end': (8, 21)},
    }

    def classify_renewal_db(fall_pay_time_str, period_name):
        """简化版续报分类：支付时间 < 开课日期 → 'pre'，否则 → 'new'"""
        if not fall_pay_time_str:
            return 'pre'
        try:
            pay_time = datetime.fromisoformat(str(fall_pay_time_str))
        except (ValueError, TypeError):
            return 'pre'
        schedule = period_schedule.get(period_name)
        if not schedule:
            return 'pre'
        year = datetime.now().year
        m, d = schedule['start']
        period_start = datetime(year, m, d)
        return 'pre' if pay_time < period_start else 'new'

    conn = get_db()
    rows = conn.execute(
        'SELECT uid, name, teaching_point, subjects_json FROM student_snapshots WHERE run_id = ?',
        (run_id,)
    ).fetchall()
    conn.close()

    teacher_stats = {}
    for r in rows:
        # 教学点筛选
        if teaching_point and r['teaching_point'] != teaching_point:
            continue
        try:
            subjects = json.loads(r['subjects_json'])
        except Exception:
            continue
        for subj, subj_data in subjects.items():
            if not isinstance(subj_data, dict):
                continue
            tch = subj_data.get('teacher', '')
            if not tch or tch == '-':
                continue
            # 老师筛选（支持多选，逗号分隔）
            if teacher:
                teacher_list = [t.strip() for t in teacher.split(',') if t.strip()]
                if tch not in teacher_list:
                    continue
            status = subj_data.get('status', '-')
            is_active = '在读' in status
            is_renewed = is_continue_fall(subj_data.get('continue_fall', ''))
            class_period = subj_data.get('period', '')
            # 期次筛选
            if period:
                period_list = [p.strip() for p in class_period.split('/') if p.strip()]
                if period not in period_list:
                    continue
            if tch not in teacher_stats:
                teacher_stats[tch] = {
                    'name': tch,
                    'active_count': 0,
                    'renewed_count': 0,
                    'pre_renewed': 0,
                    'new_renewed': 0,
                    'subjects': set(),
                    'teaching_points': set(),
                }
            if is_active:
                teacher_stats[tch]['active_count'] += 1
            if is_renewed:
                teacher_stats[tch]['renewed_count'] += 1
                # pre/new 分类
                if period:
                    classify_period = period
                else:
                    parts = [p.strip() for p in class_period.split('/') if p.strip()]
                    classify_period = parts[0] if parts else ''
                renewal_class = classify_renewal_db(subj_data.get('fall_pay_time'), classify_period)
                if renewal_class == 'pre':
                    teacher_stats[tch]['pre_renewed'] += 1
                else:
                    teacher_stats[tch]['new_renewed'] += 1
            if is_active:
                teacher_stats[tch]['subjects'].add(subj)
                teacher_stats[tch]['teaching_points'].add(r['teaching_point'])

    result = []
    for t, stats in teacher_stats.items():
        stats['subjects'] = sorted(stats['subjects'])
        stats['teaching_points'] = sorted(stats['teaching_points'])
        # 计算转化维度
        active = stats['active_count']
        pre = stats['pre_renewed']
        new = stats['new_renewed']
        should = active - pre
        total = pre + new
        stats['should_renew'] = should
        stats['total_renewed'] = total
        stats['conv_rate'] = round(new / should * 100, 1) if should > 0 else 0
        result.append(stats)

    result.sort(key=lambda x: -(x['renewed_count'] / x['active_count']) if x['active_count'] > 0 else 0)
    return result

# 初始化：由 app.py 在 set_data_dir 后调用，不在模块加载时自动执行
# （打包模式需要先设置 DATA_DIR，再初始化数据库）

