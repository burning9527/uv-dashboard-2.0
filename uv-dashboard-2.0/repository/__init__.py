"""
UV Dashboard 2.0 — 数据访问层
干净的 SQLite 读写，与 1.0 共享同一数据库。
只做数据存取，不做任何业务逻辑。
"""

import sqlite3
import json
import os
import sys
from datetime import datetime
from collections import Counter, defaultdict
from typing import List, Dict, Optional

from config import (
    SUBJECTS, PERIOD_ORDER, PERIODS_ALL, is_continue_fall,
    is_renewal_denom, is_renewed_by_source,
    normalize_teaching_point, classify_renewal_by_pay_time,
    get_room_teaching_point, student_teaching_points, line_teaching_point,
    get_line_subject, display_subjects,
    SUBJECT_LABEL, FILTER_CONFIG,
    norm_class_mode,
)
from datetime import datetime as dt_datetime

# 学科反向映射：前端传SUBJECT_LABEL值（数学/语文/英语），数据库用SUBJECTS键（雪球思维/悦读创作/双语素养）
_LABEL_TO_SUBJECT = {v: k for k, v in SUBJECT_LABEL.items()}


# ═══════════════════════════════════════════════════════════════
# 数据库路径
# ═══════════════════════════════════════════════════════════════

_DATA_DIR = None
DB_PATH = None


def set_data_dir(dir_path: str):
    """设置数据目录（打包模式由 app.py 调用）"""
    global DB_PATH, _DATA_DIR
    _DATA_DIR = dir_path
    DB_PATH = os.path.join(dir_path, 'uv_dashboard.db')


def get_data_dir() -> str:
    """返回当前数据目录（校准上传/输出文件的存放根）"""
    return _DATA_DIR or _default_data_dir()


def _default_data_dir() -> str:
    if getattr(sys, 'frozen', False):
        if sys.platform == 'win32':
            return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')),
                                'UV Dashboard 2.0')
        return os.path.expanduser('~/Library/Application Support/UV Dashboard 2.0')
    return os.path.dirname(os.path.abspath(__file__))


if DB_PATH is None:
    DB_PATH = os.path.join(_default_data_dir(), 'uv_dashboard.db')


def get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表结构"""
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
            student_changes_json TEXT,
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

        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_snapshot_run ON student_snapshots(run_id);
        CREATE INDEX IF NOT EXISTS idx_snapshot_uid ON student_snapshots(uid);
        CREATE INDEX IF NOT EXISTS idx_change_run ON change_records(run_id);
    ''')
    # 迁移：若 students_json / student_changes_json 列不存在则新增
    cursor = conn.execute('PRAGMA table_info(calibration_runs)')
    columns = [row['name'] for row in cursor.fetchall()]
    if 'students_json' not in columns:
        conn.execute('ALTER TABLE calibration_runs ADD COLUMN students_json TEXT')
    if 'student_changes_json' not in columns:
        conn.execute('ALTER TABLE calibration_runs ADD COLUMN student_changes_json TEXT')

    # 迁移：student_snapshots 新增分校/年级/学季 列（面向全国多城市数据）
    cursor = conn.execute('PRAGMA table_info(student_snapshots)')
    snap_cols = [row['name'] for row in cursor.fetchall()]
    for col in ('branch', 'grade', 'season'):
        if col not in snap_cols:
            conn.execute(f'ALTER TABLE student_snapshots ADD COLUMN {col} TEXT')

    # 迁移：calibration_runs 新增 source 列（'full'|'calibration'|'merged'）
    # 用于区分「全量数据上传」与「实时校准」两条写入管道，支撑合并物化。
    cr_cols = [row['name'] for row in conn.execute(
        'PRAGMA table_info(calibration_runs)').fetchall()]
    if 'source' not in cr_cols:
        conn.execute('ALTER TABLE calibration_runs ADD COLUMN source TEXT')
    # 回填：历史 run 均为全量上传（od_ 前缀），统一标记为 'full'
    conn.execute(
        "UPDATE calibration_runs SET source='full' WHERE source IS NULL OR source=''"
    )

    # 回填：历史导入的广州数据无分校/年级/学季，统一标记为广州/初一/暑假
    # （仅作用于尚未标注分校的行，后续真实多城市导入不受影响）
    conn.execute(
        "UPDATE student_snapshots SET branch='广州', grade='初一', season='暑假' "
        "WHERE branch IS NULL OR branch=''"
    )
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════
# 读操作
# ═══════════════════════════════════════════════════════════════

def _get_pin(conn) -> Optional[str]:
    """读取当前 pin 的 run_id（无则返回 None）"""
    try:
        row = conn.execute(
            "SELECT value FROM app_meta WHERE key='current_run_id'"
        ).fetchone()
        return row['value'] if row else None
    except Exception:
        return None


def get_current_run_id() -> Optional[str]:
    """返回当前生效的 run_id（pin 优先；无 pin 则返回最新）"""
    conn = get_db()
    pin = _get_pin(conn)
    conn.close()
    if pin:
        return pin
    conn2 = get_db()
    row = conn2.execute(
        'SELECT run_id FROM calibration_runs ORDER BY run_time DESC LIMIT 1'
    ).fetchone()
    conn2.close()
    return row['run_id'] if row else None


def set_current_run_id(run_id: str):
    """将某次校准设为当前基线（pin）"""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('current_run_id', ?)",
        (run_id,)
    )
    conn.commit()
    conn.close()


def clear_current_run_id():
    """清除 pin，回到最新 run"""
    conn = get_db()
    try:
        conn.execute("DELETE FROM app_meta WHERE key='current_run_id'")
        conn.commit()
    finally:
        conn.close()


def get_pinned_run_id() -> Optional[str]:
    """返回当前 pin 的 run_id（无 pin 则返回 None，区别于 get_current_run_id 的回退最新）"""
    conn = get_db()
    pin = _get_pin(conn)
    conn.close()
    return pin


# ═══════════════════════════════════════════════════════════════
# 全量上传 × 实时校准 合并（物化 merged run）
# 设计：base(full 全量) + overlay(calibration 实时校准) → merged run
#  - 校准优先：重叠 uid 用校准版本（enrich 列从全量回填空缺，保留 richness）
#  - 全量兜底：仅全量独有的 uid 保留全量版本
#  - 仅一个槽位存在时退化为该 run；两槽皆空则清除 pin 回最新
# 读取路径（_get_run_id / get_latest_run）零改动：merged 通过 current_run_id 暴露
# ═══════════════════════════════════════════════════════════════

def get_meta_value(key: str) -> Optional[str]:
    """读取 app_meta 任意 key（用于 base_run_id / overlay_run_id 等槽位）"""
    conn = get_db()
    row = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else None


def set_meta_value(key: str, value: str):
    """写入 app_meta 任意 key（INSERT OR REPLACE）"""
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


# 合并写回时使用的 student_snapshots 列顺序（与写管道对齐）
_STUDENT_WRITE_COLS = [
    'run_id', 'uid', 'name', 'teaching_point', 'advisor', 'channel', 'status',
    'period_combined', 'subjects_json', 'manual_json', 'branch', 'grade', 'season',
    'enrich_json', 'school_name', 'order_origin', 'work_attr', 'renew_denom', 'refund_flag',
]

# 合并时仅从全量回填的 enrich 类列（校准行通常为空，避免覆盖校准实时字段）
_ENRICH_COLS = ('enrich_json', 'school_name', 'order_origin', 'work_attr', 'renew_denom', 'refund_flag')


def _ensure_calibration_source_col(conn):
    cols = [r[1] for r in conn.execute(
        "PRAGMA table_info(calibration_runs)").fetchall()]
    if 'source' not in cols:
        conn.execute("ALTER TABLE calibration_runs ADD COLUMN source TEXT")


def delete_run(run_id: str):
    """物理删除某次 run（含快照/变动/运行记录），用于清理旧 merged run（可逆：base/overlay 保留）"""
    if not run_id:
        return
    conn = get_db()
    conn.execute("DELETE FROM student_snapshots WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM change_records WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM calibration_runs WHERE run_id=?", (run_id,))
    conn.commit()
    conn.close()


def _is_new_format_subjects(subs: dict) -> bool:
    """判断 subjects_json 是否为新格式（键含 #suffix 或行含 year 字段）。
    新格式=2.0 loader 产出，含完整行级字段(year/season/grade/class_mode/course_type等)；
    旧格式=1.0 loader 产出，仅有 class_id/teacher/room/time_slot/class_type/period/status/continue_fall。
    """
    for key, sd in subs.items():
        if not isinstance(sd, dict):
            continue
        # 新格式键名带 #0/#1 等后缀，或行含 year/class_mode 等行级字段
        if '#' in key or sd.get('year') or sd.get('class_mode'):
            return True
    return False


def _upgrade_old_subjects(subs: dict, student_row: dict) -> dict:
    """升级旧格式 subjects_json：从 student_row 及行内已有字段推断缺失的行级字段。
    旧格式行仅有 class_id/teacher/room/time_slot/class_type/period/status/continue_fall，
    缺少 year/season/grade/class_mode/course_type/product_type 等筛选依赖字段。
    推断策略：
      - class_mode ← class_type (经 norm_class_mode 归一化)
      - season ← student_row.season（引擎已有 fallback，此处显式写入）
      - grade ← student_row.grade
      - subject ← 键名（剥离 #suffix）
      - status ← 空值/缺失时默认「在读」（旧格式常无 status，引擎需此字段判断行活跃性）
      - period ← 空值时默认「一期」（短学期最常见；矩阵需此字段判定列键）
      - year/course_type/product_type 无法可靠推断，留空（引擎"已知才排除"兜底）
      - channel_l1/channel_l2 ← student_row.channel_l1/channel（学员级 fallback）
        行级 None 时补学员级，让 by_channel 行级累加不漏数据
    """
    stu_season = (student_row.get('season') or '').strip()
    stu_grade = (student_row.get('grade') or '').strip()
    stu_ch1 = (student_row.get('channel_l1') or '').strip()
    stu_ch2 = (student_row.get('channel') or '').strip()
    upgraded = {}
    for key, sd in subs.items():
        if not isinstance(sd, dict):
            upgraded[key] = sd
            continue
        line = dict(sd)
        # subject 字段：从键名提取
        if not line.get('subject'):
            line['subject'] = key.split('#')[0] if '#' in key else key
        # class_mode ← class_type
        if not line.get('class_mode') and line.get('class_type'):
            line['class_mode'] = norm_class_mode(line.get('class_type') or '')
        # season ← student_row
        if not line.get('season') and stu_season:
            line['season'] = stu_season
        # grade ← student_row
        if not line.get('grade') and stu_grade:
            line['grade'] = stu_grade
        # status ← 空值/缺失时默认「在读」（旧格式常无 status 或空字符串，
        # 引擎 is_active='在读' in status, is_refund=status and ... 需有值才不跳过）
        if not line.get('status') or not line.get('status').strip():
            line['status'] = '在读'
        # period ← 空值时默认「一期」（旧格式无 period，但学员有实际排课；
        # 矩阵需此字段判定列键（短学期直接取 period 为列），否则整行被 continue）
        if not (line.get('period') or '').strip():
            line['period'] = '一期'
        # channel_l1/channel_l2 行级 None 时补学员级
        if not (line.get('channel_l1') or '').strip() and stu_ch1:
            line['channel_l1'] = stu_ch1
        if not (line.get('channel_l2') or '').strip() and stu_ch2:
            line['channel_l2'] = stu_ch2
        upgraded[key] = line
    return upgraded


def _merge_rows(base_students: List[Dict], overlay_students: List[Dict]) -> List[Dict]:
    """按 uid 合并：校准(overlay)优先，但 subjects_json 格式不一致时保留 base 新格式。

    - 重叠 uid：
      1. 以校准行为主体（实时 status/advisor 等学员级字段优先）
      2. enrich 列从 base 回填空缺
      3. **subjects_json**：若 overlay 为旧格式（缺行级字段）且 base 为新格式，
         保留 base 的 subjects_json（避免筛选字段丢失）；否则 overlay 优先。
    - 全量独有 uid：直接保留全量行。
    - 校准独有 uid：直接采用校准行；若旧格式则升级推断缺失字段。
    """
    base_uids = {s['uid'] for s in base_students}
    by_uid: Dict[str, Dict] = {}
    for s in base_students:
        by_uid[s['uid']] = dict(s)
    for s in overlay_students:
        uid = s['uid']
        overlay_subs = _parse_json_safe(s.get('subjects_json'))
        if uid in by_uid:
            merged = dict(s)  # 校准优先（实时学员级字段）
            full = by_uid[uid]
            # ── enrich 列回填 ──
            for c in _ENRICH_COLS:
                cal_val = (s.get(c) or '').strip()
                full_val = (full.get(c) or '').strip()
                if not cal_val and full_val:
                    merged[c] = full[c]
            # ── subjects_json 格式保护 ──
            # overlay 旧格式覆盖 base 新格式是已知 bug 源：
            # 旧格式缺 year/season/grade/class_mode/course_type 等行级字段，
            # 导致引擎筛选全部不匹配 → PV=0。
            base_subs = _parse_json_safe(full.get('subjects_json'))
            if overlay_subs and base_subs:
                overlay_new = _is_new_format_subjects(overlay_subs)
                base_new = _is_new_format_subjects(base_subs)
                if not overlay_new and base_new:
                    # overlay 旧格式 + base 新格式 → 保留 base 的 subjects_json
                    merged['subjects_json'] = full['subjects_json']
            by_uid[uid] = merged
        else:
            # 校准独有 uid：若旧格式 subjects_json，升级推断缺失字段
            row = dict(s)
            if overlay_subs and not _is_new_format_subjects(overlay_subs):
                upgraded = _upgrade_old_subjects(overlay_subs, row)
                row['subjects_json'] = json.dumps(upgraded, ensure_ascii=False)
            by_uid[uid] = row
    # base 独有 uid 已在初始 by_uid 中，无需额外处理
    return list(by_uid.values())


def _parse_json_safe(raw) -> dict:
    """安全解析 JSON 字符串为 dict，失败返回空 dict"""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _compute_run_stats(students: List[Dict]) -> Dict:
    """合并 run 的汇总统计（与 import_to_production 口径一致）"""
    total = len(students)
    active = 0
    refund = 0
    bc = Counter()
    sc = Counter()
    for s in students:
        if (s.get('status') or '').strip() == '在读':
            active += 1
        try:
            subs = json.loads(s.get('subjects_json') or '{}')
        except Exception:
            subs = {}
        has_refund = False
        for key, sd in subs.items():
            if not isinstance(sd, dict):
                continue
            if sd.get('valid_refund') == '是':
                has_refund = True
            sc[get_line_subject(sd, key)] += 1
        if has_refund:
            refund += 1
        bc[(s.get('branch') or '').strip()] += 1
    return {'total': total, 'active': active, 'refund': refund,
            'branch': dict(bc), 'subject': dict(sc)}


def _write_run(run_id: str, source: str, students: List[Dict], stats: Dict):
    """将合并结果物化为一次 run（写 student_snapshots + calibration_runs）"""
    conn = get_db()
    _ensure_calibration_source_col(conn)
    conn.execute("DELETE FROM student_snapshots WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM calibration_runs WHERE run_id=?", (run_id,))
    for s in students:
        vals = []
        for c in _STUDENT_WRITE_COLS:
            if c == 'run_id':
                vals.append(run_id)
            else:
                v = s.get(c)
                vals.append('' if v is None else v)
        placeholders = ','.join(['?'] * len(_STUDENT_WRITE_COLS))
        conn.execute(
            f"INSERT INTO student_snapshots ({','.join(_STUDENT_WRITE_COLS)}) "
            f"VALUES ({placeholders})", vals
        )
    run_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("""
        INSERT INTO calibration_runs
          (run_id, run_time, total_students, active_students, refund_students,
           new_students, changes_count, stats_json, source)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (run_id, run_time, stats.get('total', 0), stats.get('active', 0),
          stats.get('refund', 0), 0, 0,
          json.dumps(stats, ensure_ascii=False), source))
    conn.commit()
    conn.close()


def rebuild_active_run() -> Dict:
    """按 uid 合并 base(full) + overlay(calibration) → merged run 并 pin。

    返回合并结果摘要。读取路径经 current_run_id 自动切换，无需改动引擎/前端。
    """
    conn = get_db()
    base = conn.execute(
        "SELECT value FROM app_meta WHERE key='base_run_id'").fetchone()
    overlay = conn.execute(
        "SELECT value FROM app_meta WHERE key='overlay_run_id'").fetchone()
    base = base['value'] if base else None
    overlay = overlay['value'] if overlay else None
    # 校验 run 仍存在（防止 meta 指向已删 run）
    if base:
        if not conn.execute("SELECT 1 FROM calibration_runs WHERE run_id=?", (base,)).fetchone():
            base = None
    if overlay:
        if not conn.execute("SELECT 1 FROM calibration_runs WHERE run_id=?", (overlay,)).fetchone():
            overlay = None
    # 回退兼容：base_run_id 未设置时（历史部署仅有全量 run，
    # 如 current_run_id=od_xxx），取最新 source='full' run 作为全量基线，
    # 保证「校准优先 + 全量兜底」合并模型始终可用。
    if not base:
        row = conn.execute(
            "SELECT run_id FROM calibration_runs WHERE source='full' "
            "ORDER BY run_time DESC LIMIT 1").fetchone()
        if row:
            base = row['run_id']
            set_meta_value('base_run_id', base)
    conn.close()

    # 两槽皆空 → 清除 pin，回到最新
    if not base and not overlay:
        clear_current_run_id()
        return {'source': None, 'current_run_id': get_current_run_id()}

    # 仅全量 → 直接 pin 全量
    if base and not overlay:
        set_current_run_id(base)
        return {'source': 'full', 'current_run_id': base, 'base_run_id': base}

    # 仅校准 → 直接 pin 校准
    if overlay and not base:
        set_current_run_id(overlay)
        return {'source': 'calibration', 'current_run_id': overlay, 'overlay_run_id': overlay}

    # 两者皆存在 → 物化 merged run
    base_run = get_run_by_id(base)
    overlay_run = get_run_by_id(overlay)
    base_students = base_run['students'] if base_run else []
    overlay_students = overlay_run['students'] if overlay_run else []
    merged_students = _merge_rows(base_students, overlay_students)
    stats = _compute_run_stats(merged_students)
    run_id = 'merged_' + datetime.now().strftime('%Y%m%d_%H%M%S')

    # 先写新 merged + pin，再删旧 merged（避免读取空窗）
    _write_run(run_id, 'merged', merged_students, stats)
    set_current_run_id(run_id)
    old = get_current_run_id()
    # 注意：上方 pin 后 current_run_id == run_id；但需清理「上一次」merged
    # 通过扫描所有 merged run（排除刚写的）删除历史 merged
    conn = get_db()
    old_merged = conn.execute(
        "SELECT run_id FROM calibration_runs WHERE source='merged' AND run_id <> ?",
        (run_id,)).fetchall()
    conn.close()
    for r in old_merged:
        delete_run(r['run_id'])

    return {
        'source': 'merged', 'run_id': run_id, 'current_run_id': run_id,
        'base_run_id': base, 'overlay_run_id': overlay,
        'students': len(merged_students), 'stats': stats,
        'base_students': len(base_students),
        'overlay_students': len(overlay_students),
        'cleaned_merged': [r['run_id'] for r in old_merged],
    }


def get_latest_run() -> Optional[Dict]:
    """获取当前生效的校准运行 + 学员 + 变动（pin 优先，否则最新）"""
    conn = get_db()
    pin = _get_pin(conn)
    if pin:
        row = conn.execute(
            'SELECT * FROM calibration_runs WHERE run_id = ?', (pin,)
        ).fetchone()
        if row is not None:
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
                'is_pinned': True,
                'current_run_id': run_id,
            }
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
        'is_pinned': False,
        'current_run_id': run_id,
    }


def get_all_runs() -> List[Dict]:
    """获取所有校准运行记录"""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM calibration_runs ORDER BY run_time DESC'
    ).fetchall()
    conn.close()
    runs = [dict(r) for r in rows]
    for r in runs:
        if r.get('stats_json'):
            try:
                r['stats'] = json.loads(r['stats_json'])
            except:
                r['stats'] = {}
    return runs


def get_run_by_id(run_id: str) -> Optional[Dict]:
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
    return {'run': dict(run), 'students': [dict(s) for s in students],
            'changes': [dict(c) for c in changes]}


def get_latest_students() -> List[Dict]:
    """获取最新一次校准的所有学员快照（供指标引擎消费）

    同步从 enrich_json 提升 channel_lead_l1 → s['channel_l1']，便于按一级渠道聚合。
    """
    latest = get_latest_run()
    if latest is None:
        return []
    for s in latest['students']:
        try:
            ej = json.loads(s.get('enrich_json') or '{}')
        except Exception:
            ej = {}
        # 一级渠道：enrich_json.channel_lead_l1（AL 列）
        s['channel_l1'] = ej.get('channel_lead_l1', '') or ''
        # 二级渠道：学员级 channel 字段（已是 channel_lead_l2 = AM 列）
        s.setdefault('channel', ej.get('channel_lead_l2', '') or s.get('channel', ''))
    return latest['students']


def get_student_detail(run_id: str, uid: str) -> Optional[Dict]:
    """学员详情"""
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ? AND uid = ?',
        (run_id, uid)
    ).fetchone()
    if not row:
        conn.close()
        return None
    student = dict(row)
    try:
        student['subjects'] = display_subjects(json.loads(student.get('subjects_json', '{}')))
    except:
        student['subjects'] = {}
    try:
        student['manual'] = json.loads(student.get('manual_json', '{}'))
    except:
        student['manual'] = {}
    conn.close()
    return student


def get_daily_stats() -> List[Dict]:
    """每日校准统计"""
    conn = get_db()
    rows = conn.execute('''
        SELECT date(run_time) as day,
               COUNT(*) as run_count,
               MAX(total_students) as students,
               MAX(refund_students) as refunds,
               MAX(new_students) as new_students
        FROM calibration_runs GROUP BY date(run_time) ORDER BY day
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_changes_by_run(run_id: str) -> List[Dict]:
    """获取某次校准的变动记录"""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM change_records WHERE run_id = ? ORDER BY id', (run_id,)
    ).fetchall()
    conn.close()
    return [dict(c) for c in rows]


# ═══════════════════════════════════════════════════════════════
# 筛选器可选项
# ═══════════════════════════════════════════════════════════════

def get_filter_options(run_id: str) -> Dict:
    """获取筛选器可选项：分校、年级、学季、教学点、期次、主讲、顾问、学科、在读状态"""
    conn = get_db()
    rows = conn.execute(
        'SELECT uid, teaching_point, advisor, subjects_json, branch, grade, season '
        'FROM student_snapshots WHERE run_id = ?',
        (run_id,)
    ).fetchall()
    conn.close()

    points = set()
    periods = set()
    teachers = set()
    advisors = set()
    statuses = set()
    class_types = set()
    branches = set()
    grades = set()
    seasons = set()
    years = set()
    course_types = set()
    product_types = set()
    class_modes = set()
    student_types = set()  # 学员归属：新生/老生/老生拓科（BS列）

    # 分校 → {教学点/主讲/顾问} 级联映射（切换分校时前端据此收窄选项）
    branch_map = {}  # {branch: {'teaching_points': set, 'teachers': set, 'advisors': set}}

    def _bm(br):
        if br not in branch_map:
            branch_map[br] = {'teaching_points': set(), 'teachers': set(), 'advisors': set()}
        return branch_map[br]

    # ── 全维度联动事实集（faceted combos）──
    # 每条订单行贡献一个去重元组，字段顺序见 COMBO_FIELDS。
    # 前端据此对任意维度做交叉联动：某维度选项 = 满足其它已选维度的行的该维度取值集。
    COMBO_FIELDS = ['year', 'branch', 'season', 'grade', 'period',
                    'teaching_point', 'teacher', 'subject', 'class_type',
                    'course_type', 'product_type', 'class_mode', 'enrollment_status',
                    'student_type']
    combos = set()

    for r in rows:
        br = (r['branch'] or '').strip()
        stu_grade = (r['grade'] or '').strip()
        stu_season = (r['season'] or '').strip()
        stu_pt = (r['teaching_point'] or '').strip()
        if stu_pt:
            points.add(stu_pt)
            if br:
                _bm(br)['teaching_points'].add(stu_pt)
        adv = r['advisor'] or ''
        if adv and adv != '-':
            advisors.add(adv)
            if br:
                _bm(br)['advisors'].add(adv)
        if br:
            branches.add(br)
        if stu_grade:
            grades.add(stu_grade)
        if stu_season:
            seasons.add(stu_season)
        try:
            subs = json.loads(r['subjects_json'] or '{}')
        except:
            continue
        for subj_key, sd in subs.items():
            if not isinstance(sd, dict): continue
            real_subj = get_line_subject(sd, subj_key)
            # 行级维度（优先行级值，回退学员级）
            line_year = (sd.get('year') or '').strip()
            line_season = (sd.get('season') or '').strip() or stu_season
            line_grade = (sd.get('grade') or '').strip() or stu_grade
            t = (sd.get('teacher') or '').strip()
            ct = (sd.get('class_type') or '').strip()
            room = (sd.get('room') or '').strip()
            room_pt = get_room_teaching_point(room, stu_pt)
            if line_year:
                years.add(line_year)
            p_raw = (sd.get('period') or '').strip()
            plist = [pp.strip() for pp in p_raw.split('/') if pp.strip()] if p_raw and p_raw != '-' else []
            for pp in plist:
                periods.add(pp)
            if t and t != '-':
                teachers.add(t)
                if br:
                    _bm(br)['teachers'].add(t)
            if room_pt:
                points.add(room_pt)
                if br:
                    _bm(br)['teaching_points'].add(room_pt)
            # Q7：在读状态维度仅 {在读, 退费}；出班→退费（数据中出班均属退费）
            raw_status = (sd.get('status') or '').strip()
            is_refund_line = bool(sd.get('pre_refund') or sd.get('post_refund') or (sd.get('valid_refund') == '是'))
            line_status = '退费' if is_refund_line else ('在读' if '在读' in raw_status else '退费')
            if line_status:
                statuses.add(line_status)
            if ct and ct != '-': class_types.add(ct)
            # 课程类型 / 产品类型（Q2）
            ctype = (sd.get('course_type') or '').strip()
            ptype = (sd.get('product_type') or '').strip()
            if ctype and ctype != '-': course_types.add(ctype)
            if ptype and ptype != '-': product_types.add(ptype)
            cmode = norm_class_mode(sd.get('class_mode'))
            if cmode: class_modes.add(cmode)
            # 学员归属（BS列）：新生/老生/老生拓科
            stype = (sd.get('student_type') or '').strip()
            if stype and stype != '-': student_types.add(stype)

            # ── 组装 combos（一行 × 每个期次值 = 一个元组）──
            combo_pt = room_pt or stu_pt or ''
            _plist = plist if plist else ['']
            for pp in _plist:
                combos.add((
                    line_year, br, line_season, line_grade, pp,
                    combo_pt, (t if t and t != '-' else ''),
                    real_subj, (ct if ct and ct != '-' else ''),
                (ctype if ctype and ctype != '-' else ''),
                (ptype if ptype and ptype != '-' else ''),
                (cmode if cmode else ''),
                line_status,
                (stype if stype and stype != '-' else ''),
            ))

    branch_options = {
        b: {
            'teaching_points': sorted(v['teaching_points']),
            'teachers': sorted(v['teachers']),
            'advisors': sorted(v['advisors']),
        }
        for b, v in branch_map.items()
    }

    # 期次排序：零<一<二<三<四<无（PERIODS_ALL 顺序），其它未知排最后
    def _period_key(p):
        return PERIODS_ALL.index(p) if p in PERIODS_ALL else 999

    return {
        'years': sorted(years, reverse=True),
        'branches': sorted(branches),
        'grades': sorted(grades),
        'seasons': sorted(seasons),
        'teaching_points': sorted(points),
        'periods': sorted(periods, key=_period_key),
        'teachers': sorted(teachers),
        'advisors': sorted(advisors),
        'subjects': [{'key': s, 'label': s} for s in SUBJECTS],
        'class_types': sorted(class_types),
        'enrollment_statuses': sorted(statuses),
        'course_types': sorted(course_types),
        'product_types': sorted(product_types),
        'class_modes': sorted(class_modes),
        'student_types': sorted(student_types),  # 学员归属（BS列）
        'renewal_statuses': FILTER_CONFIG.get('renewal_status', {}).get('options', []),
        'branch_options': branch_options,
        # 全维度联动事实集
        'combo_fields': COMBO_FIELDS,
        'combos': sorted(combos),
    }


# ═══════════════════════════════════════════════════════════════
# 写操作
# ═══════════════════════════════════════════════════════════════

def save_calibration_run(run_id: str, stats: dict, result: dict,
                         ledger_path: str, report_path: str,
                         enrollment_file: str, old_ledger_file: str):
    """保存一次校准运行"""
    conn = get_db()
    _ensure_calibration_source_col(conn)

    # 清空旧数据
    conn.execute('DELETE FROM student_snapshots WHERE run_id = ?', (run_id,))
    conn.execute('DELETE FROM change_records WHERE run_id = ?', (run_id,))

    # 保存学员快照
    for s in result.get('students', []):
        subjects = {}
        for subj in SUBJECTS:
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
            (run_id, uid, name, teaching_point, advisor, channel, status, period_combined,
             branch, grade, season, subjects_json, manual_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            run_id, s['uid'], s['name'],
            s.get('teaching_point', ''), s.get('advisor', ''),
            s.get('channel', ''), s.get('status', ''),
            s.get('period_combined', ''),
            s.get('branch', ''), s.get('grade', ''), s.get('season', ''),
            json.dumps(subjects, ensure_ascii=False),
            json.dumps(manual, ensure_ascii=False),
        ))

    # 保存变动记录
    for c in result.get('change_details', []):
        conn.execute('''
            INSERT INTO change_records
            (run_id, uid, name, subject, change_type, field_name, old_value, new_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            run_id, c.get('uid', ''), c.get('name', ''),
            c.get('subject', ''), c.get('change_type', c.get('type', '')),
            c.get('field_name', c.get('field', '')),
            str(c.get('old_value', c.get('old', ''))),
            str(c.get('new_value', c.get('new', ''))),
        ))

    # 保存运行记录
    merged_students = result.get('students', [])
    active_count = sum(1 for s in merged_students if '在读' in s.get('status', ''))
    refund_count = sum(1 for s in merged_students if s.get('status', '') == '退费')
    new_count = stats.get('new_students', 0)
    changes_count = stats.get('changes_count', len(result.get('change_details', [])))

    conn.execute('''
        INSERT OR REPLACE INTO calibration_runs
        (run_id, run_time, total_students, active_students, refund_students,
         new_students, changes_count, stats_json, students_json, student_changes_json,
         ledger_path, report_path, enrollment_file, old_ledger_file, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        run_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        len(merged_students), active_count, refund_count,
        new_count, changes_count,
        json.dumps(stats, ensure_ascii=False, default=str),
        json.dumps(result.get('students', []), ensure_ascii=False, default=str),
        json.dumps(result.get('student_changes', []), ensure_ascii=False, default=str),
        ledger_path, report_path, enrollment_file, old_ledger_file, 'calibration',
    ))

    # 校准管道：标记 overlay_run_id（不再清除 current pin，交给 rebuild_active_run 合并物化）
    try:
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('overlay_run_id', ?)",
            (run_id,))
    except Exception:
        pass
    conn.commit()
    conn.close()
    # 触发合并物化：base(全量) + overlay(本次校准) → merged run 并 pin。
    # 若 base_run_id 尚未设置（历史部署仅有全量 run），rebuild 会自动回退到最新全量 run。
    return rebuild_active_run()


def save_calibration_metadata(run_id: str, stats: dict, result: dict,
                              ledger_path: str, report_path: str,
                              enrollment_file: str, old_ledger_file: str):
    """纯校准模式：只保存校准运行的元数据记录（用于运行监控+文件下载）。

    与 save_calibration_run 的区别：
      - 不写 student_snapshots（不干扰底层数据）
      - 不写 change_records
      - 不设 overlay_run_id
      - 不触发 rebuild_active_run
    校准管理降级为"纯校准功能"：只输出校准台帐和报告，不对底层数据有干扰。
    """
    conn = get_db()
    _ensure_calibration_source_col(conn)

    merged_students = result.get('students', [])
    active_count = sum(1 for s in merged_students if '在读' in s.get('status', ''))
    refund_count = sum(1 for s in merged_students if s.get('status', '') == '退费')
    new_count = stats.get('new_students', 0)
    changes_count = stats.get('changes_count', len(result.get('change_details', [])))

    conn.execute('''
        INSERT OR REPLACE INTO calibration_runs
        (run_id, run_time, total_students, active_students, refund_students,
         new_students, changes_count, stats_json, students_json, student_changes_json,
         ledger_path, report_path, enrollment_file, old_ledger_file, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        run_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        len(merged_students), active_count, refund_count,
        new_count, changes_count,
        json.dumps(stats, ensure_ascii=False, default=str),
        json.dumps(result.get('students', []), ensure_ascii=False, default=str),
        json.dumps(result.get('student_changes', []), ensure_ascii=False, default=str),
        ledger_path, report_path, enrollment_file, old_ledger_file, 'calibration',
    ))
    conn.commit()
    conn.close()


def merge_students_by_branch(new_students: List[Dict]) -> List[Dict]:
    """按分校增量合并：返回 历史(非本次分校) + 本次导入 的全国并集。
    用于导入新城市数据时，不覆盖其他城市已有学员（解决多城市互斥问题）。
    """
    new_branches = {s.get('branch', '') for s in new_students if s.get('branch')}
    prev = get_latest_run()
    prev_students = prev.get('students', []) if prev else []
    # 丢弃历史上属于本次导入分校的学员，用新数据整体替换
    kept = [s for s in prev_students if s.get('branch', '') not in new_branches]
    return kept + new_students


# ═══════════════════════════════════════════════════════════════
# 矩阵 / 排班 / 讲师 / 学员 详细查询
# ═══════════════════════════════════════════════════════════════

def get_period_point_matrix(run_id: str, filter_spec=None) -> Dict:
    """学期矩阵：寒暑短学期按 教学点×期次，春秋长学期按 教学点×星期。
    期次/星期的上课时间从订单实际 class_start/class_end 动态析出，并过滤空行空列。"""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ?',
        (run_id,)
    ).fetchall()
    conn.close()

    students = []
    for r in rows:
        s = dict(r)
        try:
            s['subjects'] = json.loads(s.get('subjects_json') or '{}')
        except Exception:
            s['subjects'] = {}
        students.append(s)

    if filter_spec is not None:
        students = _filter_matrix_students(students, filter_spec)

    # ═══════════════════════════════════════════════════════════════
    # 1. 判定目标学季与矩阵类型
    # ═══════════════════════════════════════════════════════════════
    SHORT_SEASONS = {'暑假', '寒假'}
    LONG_SEASONS = {'春季', '秋季'}
    SEASON_BADGE = {'暑假': '暑', '寒假': '寒', '春季': '春', '秋季': '秋'}
    WEEKDAY_NAME = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五', 5: '周六', 6: '周日'}
    WEEKDAY_ORDER = {v: i for i, v in WEEKDAY_NAME.items()}

    # 统计在读行的学季，用于自动推断
    season_counts = Counter()
    for s in students:
        student_season = (s.get('season') or '').strip()
        for subj, sd in s.get('subjects', {}).items():
            if not isinstance(sd, dict):
                continue
            if '在读' not in str(sd.get('status', '')):
                continue
            line_season = (sd.get('season') or '').strip() or student_season
            if line_season:
                season_counts[line_season] += 1

    selected_seasons = set(filter_spec.season) if filter_spec and filter_spec.season else set()
    if len(selected_seasons) == 1:
        target_season = next(iter(selected_seasons))
    elif season_counts:
        target_season = season_counts.most_common(1)[0][0]
    else:
        target_season = ''

    if target_season in SHORT_SEASONS:
        matrix_type = 'short_term'
    elif target_season in LONG_SEASONS:
        matrix_type = 'long_term'
    else:
        # 兜底：数据里若存在短学期期次则视为短学期，否则长学期
        has_short = any(
            isinstance(sd, dict) and (sd.get('period') or '').strip() not in ('', '无')
            for s in students for sd in s.get('subjects', {}).values()
        )
        matrix_type = 'short_term' if has_short else 'long_term'

    season_badge = SEASON_BADGE.get(target_season, '')

    # ═══════════════════════════════════════════════════════════════
    # 2. 聚合矩阵（key=教学点，col=期次/星期）
    # ═══════════════════════════════════════════════════════════════
    cells = defaultdict(lambda: defaultdict(lambda: {
        'active': 0, 'renewed': 0, 'denom': 0, 'renewed_lock': 0, 'uv': set(),
        'subjects': {s: 0 for s in SUBJECTS},
        'classes': {s: set() for s in SUBJECTS},
        'all_classes': set()
    }))
    row_uv = defaultdict(set)
    col_uv = defaultdict(set)
    grand_uv = set()
    row_cls = defaultdict(set)
    col_cls = defaultdict(set)
    grand_cls = set()
    row_subj_cls = defaultdict(lambda: {s: set() for s in SUBJECTS})
    col_subj_cls = defaultdict(lambda: {s: set() for s in SUBJECTS})
    grand_subj_cls = {s: set() for s in SUBJECTS}
    col_meta = defaultdict(lambda: {'pairs': Counter()})

    for s in students:
        fallback_pt = normalize_teaching_point(s.get('teaching_point') or '')
        uid = s.get('uid', '')
        subs = s.get('subjects', {})
        student_year = (s.get('year') or '').strip()
        student_season = (s.get('season') or '').strip()
        student_grade = (s.get('grade') or '').strip()

        for subj_key, sd in subs.items():
            if not isinstance(sd, dict):
                continue
            subj = get_line_subject(sd, subj_key)
            pt = line_teaching_point(sd, fallback_pt)
            if not pt:
                continue
            period = (sd.get('period') or '').strip()
            status = (sd.get('status') or '').strip()
            is_active = '在读' in status
            is_renewed = is_active and is_continue_fall(sd.get('continue_fall', ''))  # 分类标签用
            is_denom = is_renewal_denom(sd)
            is_renewed_lock = is_renewed_by_source(sd)
            class_id = (sd.get('class_id') or '').strip()
            teacher = (sd.get('teacher') or '').strip()
            plist = [p.strip() for p in period.split('/') if p.strip()]
            line_season = (sd.get('season') or '').strip() or student_season

            # 只保留目标学季的行
            if line_season != target_season:
                continue

            # 确定列键（短学期：期次；长学期：上课周期 week_cycle，直接取 X 列值，不用开课日推导）
            col_keys = []
            if matrix_type == 'short_term':
                col_keys = [p for p in plist if p not in ('', '无')]
                if not col_keys:
                    continue
            else:
                wc_raw = (sd.get('week_cycle') or '').strip()
                if wc_raw:
                    # 支持 "每周五/每周六" 或 "周五/周六" 或单值，统一规范化为 "周五"
                    col_keys = []
                    for w in wc_raw.split('/'):
                        w = w.strip()
                        if not w:
                            continue
                        if w.startswith('每周'):
                            w = '周' + w[2:]
                        col_keys.append(w)
                if not col_keys:
                    continue

            # 行级筛选（与 engine 一致）
            if filter_spec is not None:
                fs = filter_spec
                if fs.subjects and subj not in fs.subjects:
                    continue
                if fs.teachers and teacher not in fs.teachers:
                    continue
                # 期次筛选：短学期按 plist，长学期只认"无"
                if not fs.all_periods_mode and fs.periods:
                    if matrix_type == 'short_term':
                        if not any(p in fs.periods for p in plist):
                            continue
                    else:
                        if '无' not in fs.periods:
                            continue
                if fs.course_type:
                    if (sd.get('course_type') or '').strip() not in fs.course_type:
                        continue
                if fs.product_type:
                    if (sd.get('product_type') or '').strip() not in fs.product_type:
                        continue
                if fs.class_mode:
                    if norm_class_mode(sd.get('class_mode')) not in fs.class_mode:
                        continue
                line_year = (sd.get('year') or '').strip() or student_year
                if fs.year and line_year and line_year not in set(fs.year):
                    continue
                if fs.season and line_season not in set(fs.season):
                    continue
                line_grade = (sd.get('grade') or '').strip() or student_grade
                if fs.grade and line_grade not in set(fs.grade):
                    continue
                if fs.enrollment_status:
                    status_match = False
                    if '在读' in fs.enrollment_status and is_active:
                        status_match = True
                    if '退费' in fs.enrollment_status and not is_active:
                        status_match = True
                    if not status_match:
                        continue
                cf = sd.get('continue_fall', '')
                is_ren = is_renewed_by_source(sd)
                fpt = sd.get('fall_pay_time', '')
                start_date_val = sd.get('start_date', '')
                first_p = plist[0] if plist else ''
                renewal_cls = classify_renewal_by_pay_time(fpt, first_p, start_date=start_date_val) if is_ren else ''
                if fs.renewal_status:
                    rs_match = False
                    if '已续报' in fs.renewal_status and is_ren:
                        rs_match = True
                    if '未续报' in fs.renewal_status and not is_ren:
                        rs_match = True
                    if '开课前续报' in fs.renewal_status and renewal_cls == 'pre':
                        rs_match = True
                    if '当期转化' in fs.renewal_status and renewal_cls == 'new':
                        rs_match = True
                    if not rs_match:
                        continue

            # 收集列的日期元信息（用众数日期对，避免脏数据的异常跨期行把范围拉宽）
            for ck in col_keys:
                start_date = sd.get('start_date', '').strip()
                end_date = sd.get('end_date', '').strip()
                if start_date and end_date:
                    col_meta[ck]['pairs'][(start_date, end_date)] += 1

            # 聚合到单元格
            for ck in col_keys:
                cell = cells[pt][ck]
                if is_active:
                    cell['active'] += 1
                    cell['uv'].add(uid)
                    row_uv[pt].add(uid)
                    col_uv[ck].add(uid)
                    grand_uv.add(uid)
                    if subj in cell['subjects']:
                        cell['subjects'][subj] += 1
                    if class_id and class_id != '-':
                        if subj in cell['classes']:
                            cell['classes'][subj].add(class_id)
                        cell['all_classes'].add(class_id)
                        row_cls[pt].add(class_id)
                        col_cls[ck].add(class_id)
                        grand_cls.add(class_id)
                        row_subj_cls[pt][subj].add(class_id)
                        col_subj_cls[ck][subj].add(class_id)
                        grand_subj_cls[subj].add(class_id)
                if is_renewed:
                    cell['renewed'] += 1
                if is_denom:
                    cell['denom'] += 1
                if is_renewed_lock:
                    cell['renewed_lock'] += 1

    # ═══════════════════════════════════════════════════════════════
    # 3. 过滤空行空列，并排序列
    # ═══════════════════════════════════════════════════════════════
    all_pts = sorted(cells.keys())
    active_pts = [pt for pt in all_pts if any(cells[pt][ck]['active'] > 0 for ck in cells[pt])]
    active_cols = set()
    for pt in all_pts:
        for ck in cells[pt]:
            if cells[pt][ck]['active'] > 0:
                active_cols.add(ck)

    if matrix_type == 'short_term':
        _period_rank = {'零期': 0, '一期': 1, '二期': 2, '三期': 3, '四期': 4}
        def _col_sort_key(ck):
            pairs = col_meta[ck]['pairs']
            if pairs:
                top = pairs.most_common(1)[0][0]
                start = datetime.fromisoformat(top[0])
            else:
                start = datetime.max
            return (start, _period_rank.get(ck, 99))
        sorted_cols = sorted(active_cols, key=_col_sort_key)
    else:
        sorted_cols = sorted(active_cols, key=lambda k: WEEKDAY_ORDER.get(k, 99))

    # 列元信息（上课时间范围：取最频繁的 start-end 日期对）
    columns = []
    for ck in sorted_cols:
        meta = col_meta[ck]
        date_range = ''
        pairs = meta['pairs']
        if pairs:
            top = pairs.most_common(1)[0][0]
            sdt = datetime.fromisoformat(top[0])
            edt = datetime.fromisoformat(top[1])
            if sdt.year == edt.year:
                date_range = f'{sdt.month}月{sdt.day}日-{edt.month}月{edt.day}日'
            else:
                date_range = f'{sdt.year}年{sdt.month}月{sdt.day}日-{edt.year}年{edt.month}月{edt.day}日'
        columns.append({
            'key': ck,
            'label': ck,
            'date_range': date_range,
            'note': '',
        })

    # ═══════════════════════════════════════════════════════════════
    # 4. 组装结果
    # ═══════════════════════════════════════════════════════════════
    result_matrix = {}
    for pt in active_pts:
        result_matrix[pt] = {}
        for ck in sorted_cols:
            cell = cells[pt][ck]
            result_matrix[pt][ck] = {
                'active': cell['active'], 'renewed': cell['renewed'],
                'denom': cell['denom'], 'renewed_lock': cell['renewed_lock'],
                'uv': len(cell['uv']),
                'subjects': dict(cell['subjects']),
                'renewal_rate': round(cell['renewed_lock'] / cell['denom'] * 100, 1) if cell['denom'] > 0 else 0,
                'class_count': len(cell['all_classes']),
                'subject_classes': {s: len(cell['classes'][s]) for s in SUBJECTS},
            }

    # 合计 UV / PV / 班量
    result_matrix['__row_uv__'] = {pt: len(row_uv[pt]) for pt in active_pts}
    result_matrix['__col_uv__'] = {ck: len(col_uv[ck]) for ck in sorted_cols}
    result_matrix['__grand_uv__'] = len(grand_uv)
    result_matrix['__row_pv__'] = {pt: sum(result_matrix[pt][ck]['active'] for ck in sorted_cols) for pt in active_pts}
    result_matrix['__col_pv__'] = {ck: sum(result_matrix[pt][ck]['active'] for pt in active_pts) for ck in sorted_cols}
    result_matrix['__grand_pv__'] = sum(result_matrix['__row_pv__'][pt] for pt in active_pts)
    result_matrix['__row_cls__'] = {pt: len(row_cls[pt]) for pt in active_pts}
    result_matrix['__col_cls__'] = {ck: len(col_cls[ck]) for ck in sorted_cols}
    result_matrix['__grand_cls__'] = len(grand_cls)
    result_matrix['__row_subj_cls__'] = {pt: {s: len(row_subj_cls[pt][s]) for s in SUBJECTS} for pt in active_pts}
    result_matrix['__col_subj_cls__'] = {ck: {s: len(col_subj_cls[ck][s]) for s in SUBJECTS} for ck in sorted_cols}
    result_matrix['__grand_subj_cls__'] = {s: len(grand_subj_cls[s]) for s in SUBJECTS}

    return {
        'matrix_type': matrix_type,
        'season_label': target_season,
        'season_badge': season_badge,
        'columns': columns,
        'matrix': result_matrix,
        'points': active_pts,
    }


def _filter_matrix_students(students, fs):
    """根据 FilterSpec 过滤矩阵所需的学员（与 engine 筛选口径一致）"""
    result = []
    for s in students:
        # 教学点过滤（班级/教室推导：学员归属默认跟随各班级所在教学点）
        _student_pts = student_teaching_points(s.get('subjects', {}), s.get('teaching_point', ''))
        if fs.teaching_point and not (_student_pts & set(fs.teaching_point)):
            continue
        # 顾问过滤（与 engine 一致：严格相等）
        if fs.advisor and (s.get('advisor') or '') != fs.advisor:
            continue
        # 分校过滤（学员级）
        if fs.branch:
            sb = (s.get('branch') or '').strip()
            if sb not in set(fs.branch):
                continue
        # 年级/学季筛选已下沉到矩阵主循环的行级判断，避免学员级聚合值误导。
        subs = s.get('subjects', {})
        # 学员维度续报状态（在学科循环前计算一次，避免多科学生被重复/错计）
        _renewed_any = False
        _renewal_pre = False
        _renewal_new = False
        for _subj, _sd in subs.items():
            if not isinstance(_sd, dict):
                continue
            if is_renewed_by_source(_sd):
                _renewed_any = True
                _pt = (_sd.get('period') or '').strip()
                _plist = [p.strip() for p in _pt.split('/') if p.strip()]
                _first = _plist[0] if _plist else ''
                _cls = classify_renewal_by_pay_time(
                    _sd.get('fall_pay_time', ''), _first, start_date=_sd.get('start_date', ''))
                if _cls == 'pre':
                    _renewal_pre = True
                elif _cls == 'new':
                    _renewal_new = True
        matched_any = False
        for subj, sd in subs.items():
            if not isinstance(sd, dict):
                continue
            subj = get_line_subject(sd, subj)
            # 学科过滤
            if fs.subjects and subj not in fs.subjects:
                continue
            # 期次过滤
            period = (sd.get('period') or '').strip()
            plist = [p.strip() for p in period.split('/') if p.strip()]
            if fs.periods and not any(p in fs.periods for p in plist):
                continue
            # 主讲过滤
            teacher = (sd.get('teacher') or '').strip()
            if fs.teachers and teacher not in fs.teachers:
                continue
            # 在读状态过滤（Q7：{在读, 退费}，出班→退费）
            status = (sd.get('status') or '').strip()
            is_active = '在读' in status
            if fs.enrollment_status:
                status_match = False
                if '在读' in fs.enrollment_status and is_active:
                    status_match = True
                if '退费' in fs.enrollment_status and not is_active:
                    status_match = True
                if not status_match:
                    continue
            # 课程类型 / 产品类型筛选（Q2）
            if fs.course_type:
                if (sd.get('course_type') or '').strip() not in fs.course_type:
                    continue
            if fs.product_type:
                if (sd.get('product_type') or '').strip() not in fs.product_type:
                    continue
            if fs.class_mode:
                if norm_class_mode(sd.get('class_mode')) not in fs.class_mode:
                    continue
            # 续报状态过滤（学员维度：已续报=任一科已续；未续报=无任何科已续）
            if fs.renewal_status:
                rs_match = False
                if '已续报' in fs.renewal_status and _renewed_any:
                    rs_match = True
                if '未续报' in fs.renewal_status and not _renewed_any:
                    rs_match = True
                if '开课前续报' in fs.renewal_status and _renewal_pre:
                    rs_match = True
                if '当期转化' in fs.renewal_status and _renewal_new:
                    rs_match = True
                if not rs_match:
                    continue
            matched_any = True
            break
        if not matched_any:
            continue
        result.append(s)
    return result


def get_teacher_list(run_id: str, period: str = None,
                     teaching_point: str = None, teacher: str = None) -> List[Dict]:
    """讲师列表（含续报统计）"""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ?', (run_id,)
    ).fetchall()
    conn.close()

    teacher_agg = {}
    for r in rows:
        student = dict(r)
        pt = student.get('teaching_point', '')
        if teaching_point and pt != teaching_point:
            continue
        try:
            subjects = json.loads(student.get('subjects_json', '{}'))
        except: continue
        for subj, sd in subjects.items():
            if not isinstance(sd, dict): continue
            subj = get_line_subject(sd, subj)
            t = (sd.get('teacher') or '').strip()
            if not t or t == '-': continue
            if teacher and t != teacher: continue
            status = (sd.get('status') or '').strip()
            p_str = (sd.get('period') or '').strip()
            if period and period not in p_str: continue
            if '在读' not in status: continue

            cf = sd.get('continue_fall', '')
            is_cf = is_continue_fall(cf)
            is_denom_line = is_renewal_denom(sd)
            is_ren_lock = is_renewed_by_source(sd)
            fpt = sd.get('fall_pay_time', '')
            cls = classify_renewal_by_pay_time(
                fpt,
                period or p_str.split('/')[0].strip() if p_str else '',
                start_date=sd.get('start_date', ''))

            if t not in teacher_agg:
                teacher_agg[t] = {'active_count': 0, 'renewed_count': 0,
                                  'pv_active': 0, 'pv_renewed': 0,
                                  'pv_pre': 0, 'pv_new': 0,
                                  'pv_denom': 0, 'pv_renewed_lock': 0,
                                  'subject': subj}
            teacher_agg[t]['active_count'] += 1
            teacher_agg[t]['pv_active'] += 1
            if is_denom_line:
                teacher_agg[t]['pv_denom'] += 1
            if is_ren_lock:
                teacher_agg[t]['pv_renewed_lock'] += 1
            if is_cf:
                teacher_agg[t]['renewed_count'] += 1
                teacher_agg[t]['pv_renewed'] += 1
                if cls == 'pre':
                    teacher_agg[t]['pv_pre'] += 1
                else:
                    teacher_agg[t]['pv_new'] += 1

    result = []
    for t, d in teacher_agg.items():
        a = d['active_count']
        r = d['renewed_count']
        dn = d.get('pv_denom', 0)
        rl = d.get('pv_renewed_lock', 0)
        pre = d['pv_pre']
        new = d['pv_new']
        should = a - pre
        result.append({
            'name': t, 'subject': d['subject'],
            'active_count': a, 'renewed_count': r,
            'pv_active': d['pv_active'], 'pv_renewed': d['pv_renewed'],
            'pv_denom': dn, 'pv_renewed_lock': rl,
            'pre_renewed': pre, 'should_renew': should,
            'new_renewed': new, 'total_renewed': pre + new,
            'renewal_rate': round(rl / dn * 100, 1) if dn > 0 else 0,
            'conv_rate': round(new / should * 100, 1) if should > 0 else 0,
        })
    result.sort(key=lambda x: x['renewal_rate'], reverse=True)
    return result


def _split_periods(period: str) -> List[str]:
    """逗号分隔的期次字符串 → 列表；空/None 返回 []（表示全期次）"""
    if not period:
        return []
    return [p.strip() for p in period.split(',') if p.strip()]


def get_teacher_detail(run_id: str, teacher_name: str,
                       period: str = None, teaching_point: str = None,
                       subject: str = None, class_type: str = None,
                       branch: str = None, year: str = None, season: str = None,
                       grade: str = None, course_type: str = None,
                       product_type: str = None, class_mode: str = None) -> Dict:
    """讲师维度详情：班级情况 + 名下学员列表

    修复：期次筛选由子串判断改为「任一期次命中」集合判断，
    兼容 dashboard 传入的逗号分隔期次（如「一期,二期」）。
    支持 subject（学科）、class_type（班型）多选过滤（逗号分隔）。
    支持 branch（分校）多选过滤，与全局分校切换器口径一致。
    支持 year/season/grade/course_type/product_type/class_mode 行级过滤，
    与 engine.compute 全局筛选口径一致。
    """
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ?', (run_id,)
    ).fetchall()
    conn.close()

    period_list = _split_periods(period)
    subject_list = _split_periods(subject)
    class_type_list = _split_periods(class_type)
    tp_list = _split_periods(teaching_point)
    branch_list = _split_periods(branch)
    year_list = _split_periods(year)
    season_list = _split_periods(season)
    grade_list = _split_periods(grade)
    course_type_list = _split_periods(course_type)
    product_type_list = _split_periods(product_type)
    class_mode_list = _split_periods(class_mode)
    # 归一化 class_mode（k9班课→班课, k9一对一→1v1）
    norm_cm_set = set(norm_class_mode(cm) for cm in class_mode_list) if class_mode_list else set()
    co_map = {
        '雪球思维': ('chinese_teacher', 'english_teacher'),
        '悦读创作': ('math_teacher', 'english_teacher'),
        '双语素养': ('math_teacher', 'chinese_teacher'),
    }

    students = []
    classes = {}  # (class_id, subject) → 班级聚合

    for r in rows:
        s = dict(r)
        # 分校过滤（学员级，与 engine.compute 口径一致）
        if branch_list:
            sb = (s.get('branch') or '').strip()
            if sb not in set(branch_list):
                continue
        pt = s.get('teaching_point', '')
        try:
            subjects = json.loads(s.get('subjects_json', '{}'))
        except: continue

        # 先收集搭班老师
        co_teachers = {}
        for s2, sd2 in subjects.items():
            if isinstance(sd2, dict) and '在读' in (sd2.get('status') or ''):
                s2 = get_line_subject(sd2, s2)
                if s2 == '悦读创作': co_teachers['chinese_teacher'] = sd2.get('teacher', '')
                elif s2 == '双语素养': co_teachers['english_teacher'] = sd2.get('teacher', '')
                elif s2 == '雪球思维': co_teachers['math_teacher'] = sd2.get('teacher', '')

        for subj, sd in subjects.items():
            if not isinstance(sd, dict): continue
            subj = get_line_subject(sd, subj)
            t = (sd.get('teacher') or '').strip()
            if t != teacher_name: continue
            # 学科过滤
            if subject_list and subj not in subject_list: continue
            # 班型过滤
            if class_type_list and (sd.get('class_type') or '').strip() not in class_type_list: continue
            status = (sd.get('status') or '').strip()
            if '在读' not in status: continue
            # 教学点过滤（班级/教室推导：学员归属默认跟随其班级所在教学点）
            room = (sd.get('room') or '').strip()
            room_pt = get_room_teaching_point(room, pt)
            if tp_list and room_pt not in tp_list: continue
            p_str = (sd.get('period') or '').strip()
            plist = [pp.strip() for pp in p_str.split('/') if pp.strip()]
            # 期次过滤（任一命中即通过）
            if period_list and not any(p in plist for p in period_list): continue
            # 学季过滤（行级）
            if season_list and (sd.get('season') or '').strip() not in season_list: continue
            # 年份过滤（行级）
            if year_list and (sd.get('year') or '').strip() not in year_list: continue
            # 年级过滤（行级）
            if grade_list and (sd.get('grade') or '').strip() not in grade_list: continue
            # 课程类型过滤（行级）
            if course_type_list and (sd.get('course_type') or '').strip() not in course_type_list: continue
            # 产品类型过滤（行级，使用原始 product_type 字段）
            if product_type_list and (sd.get('product_type') or '').strip() not in product_type_list: continue
            # 班课模式过滤（行级，归一化 class_mode）
            if norm_cm_set and norm_class_mode(sd.get('class_mode') or '') not in norm_cm_set: continue

            cf = sd.get('continue_fall', '')
            is_ren = is_continue_fall(cf)  # 分类标签用
            is_ren_lock = is_renewed_by_source(sd)  # 续报率口径
            is_denom_line = is_renewal_denom(sd)
            cls = classify_renewal_by_pay_time(
                sd.get('fall_pay_time', ''),
                plist[0] if plist else '',
                start_date=sd.get('start_date', '')
            ) if is_ren else ''
            co_keys = co_map.get(subj, ('', ''))

            students.append({
                'uid': s['uid'], 'name': s['name'],
                'teaching_point': room_pt, 'subject': subj,
                'period': p_str, 'class_id': sd.get('class_id', ''),
                'time_slot': sd.get('time_slot', ''),
                'class_type': sd.get('class_type', ''),
                'course_type': sd.get('course_type', ''),
                'product_type': sd.get('product_type', ''),
                'class_mode': norm_class_mode(sd.get('class_mode') or ''),
                'season': sd.get('season', ''),
                'year': sd.get('year', ''),
                'grade': sd.get('grade', ''),
                'teacher': teacher_name,
                'co_teacher_1': co_teachers.get(co_keys[0], ''),
                'co_teacher_2': co_teachers.get(co_keys[1], ''),
                'advisor': s.get('advisor', ''),
                'status': status,
                'continue_fall': cf,
                'renewal_class': cls,
                'is_denom': is_denom_line,
                'is_renewed_lock': is_ren_lock,
                'subjects': display_subjects(subjects, current_season=season_list[0] if season_list else ''),
            })

            # ── 班级聚合 ──
            cid = sd.get('class_id', '').strip()
            if cid and cid != '-':
                key = (cid, subj)
                if key not in classes:
                    classes[key] = {
                        'class_id': cid, 'subject': subj,
                        'period': p_str, 'time_slot': sd.get('time_slot', ''),
                        'class_type': sd.get('class_type', ''),
                        'course_type': sd.get('course_type', ''),
                        'product_type': sd.get('product_type', ''),
                        'class_mode': norm_class_mode(sd.get('class_mode') or ''),
                        'season': sd.get('season', ''),
                        'year': sd.get('year', ''),
                        'grade': sd.get('grade', ''),
                        'teacher': teacher_name,
                        'active': 0, 'renewed': 0, 'pre': 0, 'new': 0,
                        'denom': 0, 'renewed_lock': 0,
                    }
                c = classes[key]
                c['active'] += 1
                if is_denom_line:
                    c['denom'] += 1
                if is_ren_lock:
                    c['renewed_lock'] += 1
                if is_ren:
                    c['renewed'] += 1
                    if cls == 'pre':
                        c['pre'] += 1
                    elif cls == 'new':
                        c['new'] += 1

    # 班级列表（按期次排序，同期次内按 class_id）
    def _period_sort_key(cls_item):
        p_str = cls_item.get('period', '') or ''
        idxs = [PERIOD_ORDER.index(pp.strip()) for pp in p_str.split('/')
                if pp.strip() in PERIOD_ORDER]
        return (min(idxs) if idxs else 999, cls_item.get('class_id', ''))
    class_list = sorted(classes.values(), key=_period_sort_key)
    for c in class_list:
        dn = c.get('denom', 0)
        rl = c.get('renewed_lock', 0)
        c['renewal_rate'] = round(rl / dn * 100, 1) if dn else 0
        c['should'] = c['active'] - c['pre']
        c['conv_rate'] = round(c['new'] / c['should'] * 100, 1) if c['should'] else 0

    # ── 汇总（与 by_teacher 排行口径一致：PV = 在读科目数）──
    total_active = len(students)
    total_renewed = sum(1 for st in students if st.get('is_renewed_lock'))
    total_denom = sum(1 for st in students if st.get('is_denom'))
    total_pre = sum(1 for st in students if st['renewal_class'] == 'pre')
    total_new = sum(1 for st in students if st['renewal_class'] == 'new')
    total_should = total_active - total_pre
    summary = {
        'total_active': total_active,
        'total_renewed': total_renewed,
        'total_pre': total_pre,
        'total_new': total_new,
        'total_should': total_should,
        'renewal_rate': round(total_renewed / total_denom * 100, 1) if total_denom else 0,
        'conv_rate': round(total_new / total_should * 100, 1) if total_should else 0,
        'class_count': len(class_list),
    }

    return {
        'teacher': teacher_name,
        'total': total_active,
        'summary': summary,
        'classes': class_list,
        'students': students,
    }


def get_advisor_detail(run_id: str, advisor_name: str,
                       period: str = None, teaching_point: str = None,
                       branch: str = None, year: str = None, season: str = None,
                       grade: str = None, course_type: str = None,
                       product_type: str = None, class_mode: str = None,
                       class_type: str = None) -> Dict:
    """顾问维度详情：名下学员列表 + UV/PV 双维度汇总

    筛选口径与 by_advisor 排行一致（period + teaching_point + advisor），
    保证看板左侧排名与右侧详情数字对齐。
    支持 branch（分校）多选过滤，与全局分校切换器口径一致。
    支持 year/season/grade/course_type/product_type/class_mode/class_type 行级过滤，
    与 engine.compute 全局筛选口径一致。
    """
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ?', (run_id,)
    ).fetchall()
    conn.close()

    period_list = _split_periods(period)
    tp_list = _split_periods(teaching_point)
    branch_list = _split_periods(branch)
    year_list = _split_periods(year)
    season_list = _split_periods(season)
    grade_list = _split_periods(grade)
    course_type_list = _split_periods(course_type)
    product_type_list = _split_periods(product_type)
    class_mode_list = _split_periods(class_mode)
    class_type_list = _split_periods(class_type)
    # 归一化 class_mode（k9班课→班课, k9一对一→1v1）
    norm_cm_set = set(norm_class_mode(cm) for cm in class_mode_list) if class_mode_list else set()

    uv_active = set()
    uv_renewed = set()
    uv_pre = set()
    uv_new = set()
    pv_active = 0
    pv_renewed = 0
    pv_pre = 0
    pv_new = 0

    students_out = []

    for r in rows:
        s = dict(r)
        # 分校过滤（学员级，与 engine.compute 口径一致）
        if branch_list:
            sb = (s.get('branch') or '').strip()
            if sb not in set(branch_list):
                continue
        adv = s.get('advisor') or ''
        if not adv or adv == '-':
            adv = '未知'
        if adv != advisor_name:
            continue
        pt = s.get('teaching_point', '')
        try:
            subjects = json.loads(s.get('subjects_json', '{}'))
        except:
            continue
        # 教学点过滤（班级/教室推导：学员归属默认跟随各班级所在教学点）
        student_pts = student_teaching_points(subjects, pt)
        if tp_list and not (student_pts & set(tp_list)):
            continue

        subj_summaries = []
        student_has_active = False
        student_has_renewed = False
        student_classes = set()

        for subj, sd in subjects.items():
            if not isinstance(sd, dict):
                continue
            subj = get_line_subject(sd, subj)
            status = (sd.get('status') or '').strip()
            if '在读' not in status:
                continue
            p_str = (sd.get('period') or '').strip()
            plist = [pp.strip() for pp in p_str.split('/') if pp.strip()]
            if period_list and not any(p in plist for p in period_list):
                continue
            # 学季过滤（行级）
            if season_list and (sd.get('season') or '').strip() not in season_list:
                continue
            # 年份过滤（行级）
            if year_list and (sd.get('year') or '').strip() not in year_list:
                continue
            # 年级过滤（行级）
            if grade_list and (sd.get('grade') or '').strip() not in grade_list:
                continue
            # 课程类型过滤（行级）
            if course_type_list and (sd.get('course_type') or '').strip() not in course_type_list:
                continue
            # 产品类型过滤（行级）
            if product_type_list and (sd.get('product_type') or '').strip() not in product_type_list:
                continue
            # 班课模式过滤（行级，归一化 class_mode）
            if norm_cm_set and norm_class_mode(sd.get('class_mode') or '') not in norm_cm_set:
                continue
            # 班型过滤（行级）
            if class_type_list and (sd.get('class_type') or '').strip() not in class_type_list:
                continue
            cf = sd.get('continue_fall', '')
            is_ren = is_renewed_by_source(sd)
            cls = classify_renewal_by_pay_time(
                sd.get('fall_pay_time', ''),
                plist[0] if plist else '',
                start_date=sd.get('start_date', '')
            ) if is_ren else ''
            subj_summaries.append({
                'subject': subj,
                'period': p_str,
                'class_id': sd.get('class_id', ''),
                'teacher': sd.get('teacher', ''),
                'status': status,
                'continue_fall': cf,
                'renewal_class': cls,
            })
            student_has_active = True
            pv_active += 1
            if is_ren:
                student_has_renewed = True
                pv_renewed += 1
                if cls == 'pre':
                    pv_pre += 1
                    student_classes.add('pre')
                elif cls == 'new':
                    pv_new += 1
                    student_classes.add('new')

        if student_has_active:
            uv_active.add(s['uid'])
            if student_has_renewed:
                uv_renewed.add(s['uid'])
                if 'pre' in student_classes:
                    uv_pre.add(s['uid'])
                if 'new' in student_classes:
                    uv_new.add(s['uid'])
            students_out.append({
                'uid': s['uid'], 'name': s['name'],
                'teaching_point': '/'.join(sorted(student_pts)) if student_pts else pt, 'advisor': adv,
                'subjects': subj_summaries,
                'is_renewed': student_has_renewed,
            })

    uv_active_n = len(uv_active)
    uv_renewed_n = len(uv_renewed)
    uv_pre_n = len(uv_pre)
    uv_new_n = len(uv_new)
    uv_should = uv_active_n - uv_pre_n
    pv_should = pv_active - pv_pre
    summary = {
        'uv_active': uv_active_n,
        'uv_renewed': uv_renewed_n,
        'uv_pre': uv_pre_n,
        'uv_new': uv_new_n,
        'uv_should': uv_should,
        'uv_renewal_rate': round(uv_renewed_n / uv_active_n * 100, 1) if uv_active_n else 0,
        'uv_conv_rate': round(uv_new_n / uv_should * 100, 1) if uv_should else 0,
        'pv_active': pv_active,
        'pv_renewed': pv_renewed,
        'pv_pre': pv_pre,
        'pv_new': pv_new,
        'pv_should': pv_should,
        'pv_renewal_rate': round(pv_renewed / pv_active * 100, 1) if pv_active else 0,
        'pv_conv_rate': round(pv_new / pv_should * 100, 1) if pv_should else 0,
        'student_count': len(students_out),
    }

    return {'advisor': advisor_name, 'summary': summary, 'students': students_out}


def get_class_schedule(run_id: str, teaching_points: List[str] = None,
                       periods: List[str] = None, teachers: List[str] = None,
                       subjects: List[str] = None, class_types: List[str] = None,
                       branches: List[str] = None,
                       years: List[str] = None, seasons: List[str] = None,
                       grades: List[str] = None,
                       course_types: List[str] = None,
                       class_modes: List[str] = None) -> Dict:
    """排班排课看板 — 支持多选参数（含分校/年份/学季/年级）"""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ?', (run_id,)
    ).fetchall()
    conn.close()

    year_set = set(years) if years else None
    season_set = set(seasons) if seasons else None
    grade_set = set(grades) if grades else None

    def _line_dim_ok(s, sd):
        """行级 年份/学季/年级 过滤（与 engine.compute 口径一致：year 已知才排除）"""
        if year_set:
            ly = (sd.get('year') or '').strip() or (s.get('year') or '').strip()
            if ly and ly not in year_set:
                return False
        if season_set:
            ls = (sd.get('season') or '').strip() or (s.get('season') or '').strip()
            if ls not in season_set:
                return False
        if grade_set:
            lg = (sd.get('grade') or '').strip() or (s.get('grade') or '').strip()
            if lg not in grade_set:
                return False
        return True

    # ── 第一遍：收集选项。排班看板联动全局分校筛选，
    # 若指定分校，选项只返回该分校；未指定则返回全部 ──
    branch_set = set(branches) if branches else None
    all_teaching_points = set()
    all_teachers = set()
    all_subjects = set()
    all_class_types = set()
    all_course_types = set()
    all_class_modes = set()
    all_pt_class_ids = {}  # pt → set of class_ids，用于统计总班量

    for r in rows:
        s = dict(r)
        pt = s.get('teaching_point', '')
        # 分校过滤（选项级）
        if branch_set:
            sb = (s.get('branch') or '').strip()
            if sb not in branch_set:
                continue
        try:
            subj_json = json.loads(s.get('subjects_json', '{}'))
        except: continue
        for subj, sd in subj_json.items():
            if not isinstance(sd, dict): continue
            subj = get_line_subject(sd, subj)
            status = (sd.get('status') or '').strip()
            if '在读' not in status: continue
            if not _line_dim_ok(s, sd): continue
            t = (sd.get('teacher') or '').strip()
            ct = (sd.get('class_type') or '').strip()
            cm = norm_class_mode(sd.get('class_mode') or '')
            room = (sd.get('room') or '').strip()
            room_pt = get_room_teaching_point(room, pt)
            if room_pt: all_teaching_points.add(room_pt)
            if t: all_teachers.add(t)
            if subj: all_subjects.add(subj)
            if ct: all_class_types.add(ct)
            if (sd.get('course_type') or '').strip(): all_course_types.add((sd.get('course_type') or '').strip())
            if cm: all_class_modes.add(cm)
            cid = sd.get('class_id', '')
            if not cid or cid == '-': continue
            # 总班量统计（按class_id去重；教学点以班级所在教室推导）
            if room_pt not in all_pt_class_ids:
                all_pt_class_ids[room_pt] = set()
            all_pt_class_ids[room_pt].add(cid)

    # ── 第二遍：筛选 + 构建班级 ──
    classes = {}
    # 同一班级下学生按 UID 唯一计数（消除同一学员多订单行重复计入）
    seen_uids = {}
    # ── 同时计算联动后的教学点班量（排除教学点筛选，其他筛选生效）──
    filtered_pt_class_ids = {}  # pt → set of class_ids（仅排除tp筛选）

    for r in rows:
        s = dict(r)
        pt = s.get('teaching_point', '')
        # 分校筛选（学员级）：仅统计所选分校的班级（排班看板联动全局分校筛选）
        if branches:
            sb = (s.get('branch') or '').strip()
            if sb not in set(branches):
                continue
        try:
            subj_json = json.loads(s.get('subjects_json', '{}'))
        except: continue
        for subj, sd in subj_json.items():
            if not isinstance(sd, dict): continue
            subj = get_line_subject(sd, subj)
            status = (sd.get('status') or '').strip()
            if '在读' not in status: continue
            if not _line_dim_ok(s, sd): continue
            t = (sd.get('teacher') or '').strip()
            ct = (sd.get('class_type') or '').strip()
            cm = norm_class_mode(sd.get('class_mode') or '')
            ctype = (sd.get('course_type') or '').strip()
            p_str = (sd.get('period') or '').strip()
            plist = [pp.strip() for pp in p_str.split('/') if pp.strip()]
            cid = sd.get('class_id', '')
            if not cid or cid == '-': continue
            room = (sd.get('room') or '').strip()
            room_pt = get_room_teaching_point(room, pt)

            # ── 联动班量：排除教学点筛选，其他筛选生效 ──
            other_match = True
            if teachers and t not in teachers: other_match = False
            if subjects and subj not in subjects: other_match = False
            if class_types and ct not in class_types: other_match = False
            if course_types and ctype not in course_types: other_match = False
            if class_modes and cm not in class_modes: other_match = False
            if periods and not any(pp in periods for pp in plist): other_match = False
            if other_match and room_pt:
                if room_pt not in filtered_pt_class_ids:
                    filtered_pt_class_ids[room_pt] = set()
                filtered_pt_class_ids[room_pt].add(cid)

            # ── 完整筛选（含教学点：班级所在教室推导）──
            if teaching_points and room_pt not in teaching_points: continue
            # 多选筛选
            if teachers and t not in teachers: continue
            if subjects and subj not in subjects: continue
            if class_types and ct not in class_types: continue
            if course_types and ctype not in course_types: continue
            if class_modes and cm not in class_modes: continue
            if periods and not any(pp in periods for pp in plist): continue

            if cid not in classes:
                classes[cid] = {
                    'class_id': cid, 'subject': subj,
                    'teacher': t, 'period': p_str,
                    'season': (sd.get('season') or '').strip(),
                    'time_slot': sd.get('time_slot', ''),
                    'class_type': ct, 'course_type': ctype,
                    'class_mode': cm, 'room': room,
                    'teaching_point': room_pt,
                    'students': [], 'renewed_count': 0,
                }
                seen_uids[cid] = set()
            uid = s['uid']
            if uid in seen_uids[cid]:
                continue  # 同一学员在同一班级只计一次（UID 唯一）
            seen_uids[cid].add(uid)
            classes[cid]['students'].append({
                'uid': uid, 'name': s['name'],
                'status': status, 'continue_fall': sd.get('continue_fall', ''),
            })
            if is_renewed_by_source(sd):
                classes[cid]['renewed_count'] += 1

    # 补充续报率 + 活跃人数
    for cid, c in classes.items():
        total = len(c['students'])
        c['total'] = total
        c['renewal_rate'] = round(c['renewed_count'] / total * 100, 1) if total > 0 else 0

    return {
        'classes': list(classes.values()),
        'teaching_points': sorted(all_teaching_points),
        'teachers': sorted(all_teachers),
        'subjects': sorted(all_subjects),
        'class_types': sorted(all_class_types),
        'course_types': sorted(all_course_types),
        'class_modes': sorted(all_class_modes),
        'pt_class_counts': {pt: len(ids) for pt, ids in all_pt_class_ids.items()},
        'filtered_pt_class_counts': {pt: len(ids) for pt, ids in filtered_pt_class_ids.items()},
    }


def get_filtered_students(run_id: str, filters: dict = None) -> List[Dict]:
    """多维度筛选学员（支持多选、关键字搜索、续报状态）"""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ?', (run_id,)
    ).fetchall()
    conn.close()

    students = [dict(r) for r in rows]
    if not filters:
        return _prepare_students(students)

    keyword = (filters.get('keyword') or '').strip().lower()
    tp_list = _split_periods(filters.get('teaching_point', ''))
    period_list = _split_periods(filters.get('period', ''))
    teacher_list = _split_periods(filters.get('teacher', ''))
    enrollment_list = _split_periods(filters.get('enrollment_status', ''))
    renewal_list = _split_periods(filters.get('renewal_status', ''))
    season_list = _split_periods(filters.get('season', ''))
    # 兼容前端简称：「课前续」→「开课前续报」
    renewal_list = [('开课前续报' if r == '课前续' else r) for r in renewal_list]
    subject_list = _split_periods(filters.get('subject', ''))
    branch_list = _split_periods(filters.get('branch', ''))
    grade_list = _split_periods(filters.get('grade', ''))
    season_list = _split_periods(filters.get('season', ''))
    year_list = _split_periods(filters.get('year', ''))
    course_type_list = _split_periods(filters.get('course_type', ''))
    product_type_list = _split_periods(filters.get('product_type', ''))
    student_type_list = _split_periods(filters.get('student_type', ''))
    # 前端传 SUBJECT_LABEL 值（数学/语文/英语）或数据库键，统一映射回数据库键
    subject_keys = set()
    for sub in subject_list:
        if sub in _LABEL_TO_SUBJECT:
            subject_keys.add(_LABEL_TO_SUBJECT[sub])
        else:
            subject_keys.add(sub)

    result = []
    for s in students:
        subjects = json.loads(s.get('subjects_json', '{}'))

        # 关键字搜索：姓名 / 学生ID / 班级ID
        if keyword:
            uid = (s.get('uid') or '').lower()
            name = (s.get('name') or '').lower()
            class_ids = [
                (sd.get('class_id') or '').lower()
                for sd in subjects.values() if isinstance(sd, dict)
            ]
            if not (keyword in uid or keyword in name or any(keyword in cid for cid in class_ids)):
                continue

        # 分校多选（学员级）
        if branch_list and (s.get('branch') or '') not in set(branch_list):
            continue
        # 年级多选（学员级）
        if grade_list and (s.get('grade') or '') not in set(grade_list):
            continue
        # 学季多选（行级优先，回退学员级；与 engine 一致）
        if season_list:
            stu_season = (s.get('season') or '').strip()
            line_seasons = {(sd.get('season') or '').strip() for sd in subjects.values() if isinstance(sd, dict)}
            line_seasons.discard('')
            all_seasons = line_seasons | ({stu_season} if stu_season else set())
            if not (all_seasons & set(season_list)):
                continue
        # 年份多选（行级：subjects_json 中无学员级 year 列，需任一科目命中）
        if year_list:
            matched = False
            for sd in subjects.values():
                if isinstance(sd, dict) and (sd.get('year') or '') in year_list:
                    matched = True; break
            if not matched: continue

        # 教学点多选（班级/教室推导：学员归属默认跟随各班级所在教学点）
        student_pts = student_teaching_points(subjects, s.get('teaching_point', ''))
        if tp_list and not (student_pts & set(tp_list)):
            continue

        # 学科多选：任一科目命中任一目标学科（数据库键）
        if subject_keys:
            matched = False
            for subj_key, sd in subjects.items():
                if isinstance(sd, dict) and get_line_subject(sd, subj_key) in subject_keys:
                    matched = True; break
            if not matched: continue

        # 期次多选：任一科目命中任一目标期次
        if period_list:
            matched = False
            for sd in subjects.values():
                if isinstance(sd, dict):
                    p_str = (sd.get('period') or '')
                    p_list = [p.strip() for p in p_str.split('/') if p.strip()]
                    if any(p in p_list for p in period_list):
                        matched = True; break
            if not matched: continue

        # 主讲多选：任一科目命中任一目标主讲
        if teacher_list:
            matched = False
            for sd in subjects.values():
                if isinstance(sd, dict) and (sd.get('teacher') or '') in teacher_list:
                    matched = True; break
            if not matched: continue

        # 在读状态多选（Q7：{在读, 退费}，出班→退费）
        if enrollment_list:
            matched = False
            for sd in subjects.values():
                if not isinstance(sd, dict): continue
                st = (sd.get('status') or '')
                is_refund = bool(sd.get('pre_refund') or sd.get('post_refund') or (sd.get('valid_refund') == '是'))
                line_status = '退费' if is_refund else ('在读' if '在读' in st else '退费')
                if line_status in enrollment_list:
                    matched = True; break
            if not matched: continue

        # 课程类型 / 产品类型多选（Q2）
        if course_type_list:
            matched = False
            for sd in subjects.values():
                if isinstance(sd, dict) and (sd.get('course_type') or '') in course_type_list:
                    matched = True; break
            if not matched: continue
        if product_type_list:
            matched = False
            for sd in subjects.values():
                if isinstance(sd, dict) and (sd.get('product_type') or '') in product_type_list:
                    matched = True; break
            if not matched: continue
        class_mode_list = _split_periods(filters.get('class_mode', ''))
        if class_mode_list:
            matched = False
            for sd in subjects.values():
                if isinstance(sd, dict) and norm_class_mode(sd.get('class_mode')) in class_mode_list:
                    matched = True; break
            if not matched: continue
        # 学员归属多选（BS列 → 新生/老生/老生拓科）：学员级聚合 + 优先级去重
        # 同一学员多班级行可能归属不同（最具体优先：老生拓科 > 老生 > 新生）
        if student_type_list:
            st_set = set()
            for sd in subjects.values():
                if isinstance(sd, dict):
                    st_val = (sd.get('student_type') or '').strip()
                    if st_val:
                        st_set.add(st_val)
            if st_set:
                if '老生拓科' in st_set:
                    st_main = '老生拓科'
                elif '老生' in st_set:
                    st_main = '老生'
                elif '新生' in st_set:
                    st_main = '新生'
                else:
                    st_main = ''
                if st_main not in set(student_type_list):
                    continue

        # 续报状态多选：学员维度
        # 已续报 = 至少一科已续；未续报 = 没有任何科目已续
        # 开课前续报 = 已续且支付时间早于期次开课；当期转化 = 已续且支付时间晚于开课
        if renewal_list:
            has_any_renewed = False
            has_pre = False
            has_new = False
            for sd in subjects.values():
                if not isinstance(sd, dict): continue
                if is_renewed_by_source(sd):
                    has_any_renewed = True
                    p_str = (sd.get('period') or '').strip()
                    plist = [p.strip() for p in p_str.split('/') if p.strip()]
                    first_p = plist[0] if plist else ''
                    cls = classify_renewal_by_pay_time(
                        sd.get('fall_pay_time', ''), first_p, start_date=sd.get('start_date', ''))
                    if cls == 'pre':
                        has_pre = True
                    elif cls == 'new':
                        has_new = True
            status_map = {
                '已续报': has_any_renewed,
                '未续报': not has_any_renewed,
                '开课前续报': has_pre,
                '当期转化': has_new,
            }
            if not any(status_map.get(r, False) for r in renewal_list):
                continue

        # 覆盖教学点字段为班级推导的教学点集合（用于前端展示）
        if student_pts:
            s['teaching_point'] = '/'.join(sorted(student_pts))
        result.append(s)

    return _prepare_students(result, current_season=season_list[0] if season_list else '')


def _prepare_students(students: List[Dict], current_season: str = '') -> List[Dict]:
    """解析学员 JSON 字段为对象。

    订单行数组模型下 subjects_json 键为合成 id，前端按真实学科名查找，
    故用 display_subjects 重键为 {真实学科: line}。

    BUG 修复：传入 current_season 时，display_subjects 优先保留匹配学季的行。
    避免长学期（秋/春）下"数/语/英"科目错配到暑假行（带跨学季续报标签）。
    """
    for s in students:
        try: s['subjects'] = display_subjects(json.loads(s.get('subjects_json', '{}')), current_season=current_season)
        except: s['subjects'] = {}
        try: s['manual'] = json.loads(s.get('manual_json', '{}'))
        except: s['manual'] = {}
    return students


def get_class_detail(run_id: str, class_id: str) -> Dict:
    """班级详情 — 该班所有学员、搭班老师、上课信息"""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ?', (run_id,)
    ).fetchall()
    conn.close()

    # ── 收集该 class_id 的主讲学员 ──
    target_subject = ''
    target_teacher = ''
    target_period = ''
    target_time_slot = ''
    target_class_type = ''
    target_room = ''
    target_pt = ''
    target_season = ''
    target_grade = ''
    target_course_type = ''
    target_start_date = ''
    target_end_date = ''
    target_week_cycle = ''
    students_in_class = []

    # ── 同时收集搭班信息 ──
    co_teachers = {}  # {subj: teacher_name}
    all_subjects_in_class = set()

    for r in rows:
        s = dict(r)
        pt = s.get('teaching_point', '')
        try:
            subj_json = json.loads(s.get('subjects_json', '{}'))
        except:
            continue

        # 检查该学员是否有该 class_id 的科目
        has_target_class = False
        for subj, sd in subj_json.items():
            if not isinstance(sd, dict):
                continue
            subj = get_line_subject(sd, subj)
            cid = (sd.get('class_id') or '').strip()
            if cid == class_id:
                has_target_class = True
                if not target_subject:
                    target_subject = subj
                    target_teacher = (sd.get('teacher') or '').strip()
                    target_period = (sd.get('period') or '').strip()
                    target_time_slot = (sd.get('time_slot') or '').strip()
                    target_class_type = (sd.get('class_type') or '').strip()
                    target_course_type = (sd.get('course_type') or '').strip()
                    target_room = (sd.get('room') or '').strip()
                    target_pt = pt
                    target_season = (sd.get('season') or '').strip()
                    target_grade = (sd.get('grade') or '').strip()
                    target_start_date = (sd.get('start_date') or '').strip()
                    target_end_date = (sd.get('end_date') or '').strip()
                    target_week_cycle = (sd.get('week_cycle') or '').strip()
                # 收集搭班老师
                status = (sd.get('status') or '').strip()
                if '在读' in status and cid == class_id:
                    all_subjects_in_class.add(subj)

        if not has_target_class:
            continue

        # ── 学员完整信息（重键为真实学科名，供按学科名回查）──
        subjects = display_subjects(subj_json)
        manual = {}
        try:
            manual = json.loads(s.get('manual_json', '{}'))
        except:
            pass

        # 定位该学员在该班级(class_id)的原始订单行（避免 display_subjects 折叠后取错行）
        sd_class = None
        for _key, _line in subj_json.items():
            if not isinstance(_line, dict):
                continue
            _cid = (_line.get('class_id') or '').strip()
            if _cid == class_id:
                sd_class = _line
                break

        # 该班当前学科折叠状态（兜底）
        sd_subject = subjects.get(target_subject, {}) if isinstance(subjects.get(target_subject), dict) else {}

        # 判断该学员在该班的续报状态（必须以该 class_id 对应行的 continue_fall/period/start_date 为准）
        cf_in_class = ''
        cf_cls = ''
        line_status = ''
        line_grade = ''
        is_denom_line = False
        is_ren_lock = False
        if isinstance(sd_class, dict):
            cf_in_class = sd_class.get('continue_fall', '')
            line_status = sd_class.get('status', '')
            line_grade = (sd_class.get('grade') or '').strip()
            is_denom_line = is_renewal_denom(sd_class)
            is_ren_lock = is_renewed_by_source(sd_class)
            if is_renewed_by_source(sd_class):
                pay_time = sd_class.get('fall_pay_time', '')
                period = (sd_class.get('period') or '').split('/')[0].strip()
                start_date = sd_class.get('start_date', '')
                cf_cls = classify_renewal_by_pay_time(pay_time, period, start_date=start_date)
        if not line_status and isinstance(sd_subject, dict):
            line_status = sd_subject.get('status', '')
        if not line_grade and isinstance(sd_subject, dict):
            line_grade = (sd_subject.get('grade') or '').strip()

        # 计算该学员在当前学季的搭班老师（仅同季 + 在读 + 非本班科目）
        co_teachers = {}
        for _key, _line in subj_json.items():
            if not isinstance(_line, dict):
                continue
            _line_season = (_line.get('season') or '').strip()
            _line_status = (_line.get('status') or '').strip()
            _line_teacher = (_line.get('teacher') or '').strip()
            _line_subj = get_line_subject(_line, _key)
            if (_line_subj != target_subject and
                _line_season == target_season and
                '在读' in _line_status and
                _line_teacher and
                _line_teacher not in ('-', '—')):
                co_teachers[_line_subj] = _line_teacher

        students_in_class.append({
            'uid': s['uid'],
            'name': s['name'],
            'teaching_point': pt,
            'advisor': s.get('advisor', ''),
            'status': line_status,
            'continue_fall': cf_in_class,
            'renewal_class': cf_cls,
            'grade': line_grade,
            'pre_test_score': (manual.get('pre_test_score') or '') if isinstance(manual, dict) else '',
            'co_teachers': co_teachers,
            'is_denom': is_denom_line,
            'is_renewed_lock': is_ren_lock,
        })

    # ── 搭班老师 ──
    # 已改为按学员+学季计算，保留空字典以保持 API 结构兼容
    co_teachers = {}

    # 计算续报率：分子/分母均只统计「在读」学员；先续报后退费者既不进分子也不进分母，确保续报率不超100%
    active_count = sum(1 for st in students_in_class
                       if '在读' in (st.get('status') or ''))
    renewed_count = sum(1 for st in students_in_class
                        if '在读' in (st.get('status') or '')
                        and is_continue_fall(st.get('continue_fall', '')))
    pre_count = sum(1 for st in students_in_class
                    if '在读' in (st.get('status') or '')
                    and st.get('renewal_class') == 'pre')
    new_count = sum(1 for st in students_in_class
                    if '在读' in (st.get('status') or '')
                    and st.get('renewal_class') == 'new')
    # 锁定分母口径
    denom = sum(1 for st in students_in_class
                if '在读' in (st.get('status') or '')
                and st.get('is_denom'))
    renewed_lock = sum(1 for st in students_in_class
                       if '在读' in (st.get('status') or '')
                       and st.get('is_renewed_lock'))
    renewal_rate = round(renewed_lock / denom * 100, 1) if denom > 0 else 0

    total = len(students_in_class)
    refund_count = sum(1 for st in students_in_class
                       if '退' in (st.get('status') or ''))
    refund_rate = round(refund_count / total * 100, 1) if total > 0 else 0

    return {
        'class_id': class_id,
        'subject': target_subject,
        'teacher': target_teacher,
        'period': target_period,
        'time_slot': target_time_slot,
        'class_type': target_class_type,
        'course_type': target_course_type,
        'room': target_room,
        'teaching_point': target_pt,
        'season': target_season,
        'grade': target_grade,
        'start_date': target_start_date,
        'end_date': target_end_date,
        'week_cycle': target_week_cycle,
        'co_teachers': co_teachers,
        'all_subjects_in_class': sorted(all_subjects_in_class),
        'total': total,
        'active_count': active_count,
        'renewed_count': renewed_count,
        'pre_count': pre_count,
        'new_count': new_count,
        'renewal_rate': renewal_rate,
        'denom': denom,
        'renewed_lock': renewed_lock,
        'refund_count': refund_count,
        'refund_rate': refund_rate,
        'students': students_in_class,
    }


def get_student_detail_enhanced(run_id: str, uid: str, season: str = '') -> Dict:
    """学员报班明细 — 增强版（含各科详情、续报分类、搭班老师）

    season: 学季作用域。传入时仅返回该学季下"在读"的班级行，避免跨学季混排错乱。
    """
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM student_snapshots WHERE run_id = ? AND uid = ?',
        (run_id, uid)
    ).fetchone()
    if not row:
        conn.close()
        return None
    student = dict(row)
    try:
        raw_subjects = json.loads(student.get('subjects_json', '{}'))
    except Exception:
        raw_subjects = {}
    # ── 按学季作用域过滤（班级卡片/班级详情下钻时传入 season）──
    # 保留：在读行 + 退费行（不能只保留在读——会让纯退费学员详情为空）
    # 跨学季混排：仅排除 season 不匹配且 status=在读的行；退费行因显示"出班"信息应保留
    if season:
        scoped = {}
        for key, line in raw_subjects.items():
            if not isinstance(line, dict):
                continue
            line_season = (line.get('season') or '').strip()
            line_status = (line.get('status') or '').strip()
            is_active = '在读' in line_status
            is_refund = bool(line.get('pre_refund') or line.get('post_refund') or (line.get('valid_refund') == '是'))
            # 退费行：始终保留（不区分 season，体现"出班"信息）
            if is_refund:
                scoped[key] = line
                continue
            # 在读行：仅当 season 匹配时保留
            if is_active and line_season == season:
                scoped[key] = line
        # BUG 修复：过季后为空（如纯退费学员）→ 回退到原 raw_subjects，确保退费行可见
        if not scoped:
            scoped = dict(raw_subjects)
        raw_subjects = scoped
    try:
        student['subjects'] = display_subjects(raw_subjects)
    except:
        student['subjects'] = {}
    try:
        student['manual'] = json.loads(student.get('manual_json', '{}'))
    except:
        student['manual'] = {}
    conn.close()

    # ── 原始班级行（未折叠）：{真实学科: [line, ...]}，用于学员详情展示多班 ──
    subjects_raw = defaultdict(list)
    for key, line in raw_subjects.items():
        if not isinstance(line, dict):
            continue
        subj = get_line_subject(line, key)
        if not subj:
            continue
        subjects_raw[subj].append(line)
    student['subjects_raw'] = dict(subjects_raw)

    # ── 丰富各科目数据（同时应用到折叠视图和原始班级行列表）──
    def _enrich_line(sd):
        if not isinstance(sd, dict):
            return
        fpt = sd.get('fall_pay_time', '')
        period = (sd.get('period') or '').split('/')[0].strip()
        sd['renewal_class'] = classify_renewal_by_pay_time(
            fpt, period, start_date=sd.get('start_date', '')) if is_renewed_by_source(sd) else ''
        sd['renewal_label'] = _renewal_label(sd, sd.get('renewal_class', ''), sd.get('course_type', ''))

    for sd in student.get('subjects', {}).values():
        _enrich_line(sd)
    for lines in student.get('subjects_raw', {}).values():
        for sd in lines:
            _enrich_line(sd)

    # ── 搭班老师 ──
    co_map = {
        '雪球思维': [('悦读创作', '语文老师'), ('双语素养', '英语老师')],
        '悦读创作': [('雪球思维', '数学老师'), ('双语素养', '英语老师')],
        '双语素养': [('雪球思维', '数学老师'), ('悦读创作', '语文老师')],
    }
    co_teachers = {}
    for subj, pairs in co_map.items():
        for other_subj, label in pairs:
            other_sd = student['subjects'].get(other_subj, {})
            if isinstance(other_sd, dict) and other_sd.get('teacher'):
                co_teachers[label] = other_sd.get('teacher', '')

    student['co_teachers'] = co_teachers
    student['scope_season'] = season
    return student


def _renewal_label(sd: dict, cls: str, course_type: str = '') -> str:
    """续报标签文本。
    仅特惠课存在「开课前续报/当期转化」细分；系统课（及未知）一律归并：
    续报→已续报，未续报→未续报。
    """
    if not is_renewed_by_source(sd):
        return '未续报'
    if course_type == '特惠课':
        if cls == 'pre':
            return '课前续'
        if cls == 'new':
            return '当期转化'
    return '已续报'


# ═══════════════════════════════════════════════════════════════
# 拉新×续报转化月度分析
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# 拉新×续报转化月度分析（新口径）
# ═══════════════════════════════════════════════════════════════

_SEASON_CYCLE = ['寒假', '春季', '暑假', '秋季']


def _season_index(s):
    try:
        return _SEASON_CYCLE.index(s)
    except ValueError:
        return None


def _is_prior_season(target, candidate):
    """判断 candidate 是否在学季循环中早于 target（同一年周期）"""
    ti = _season_index(target)
    ci = _season_index(candidate)
    if ti is None or ci is None:
        return False
    return ci < ti


def _next_season(s):
    try:
        i = _SEASON_CYCLE.index(s)
    except ValueError:
        return ''
    return _SEASON_CYCLE[(i + 1) % len(_SEASON_CYCLE)]


def _split_filter(s):
    return set(x.strip() for x in s.split(',') if x.strip())


def _parse_pay_time(val):
    """解析支付时间为 datetime；失败返回 None"""
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        return dt_datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S',
                '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M',
                '%Y-%m-%d', '%Y/%m/%d']:
        try:
            return dt_datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _resolve_target_season(season_filter, rows):
    """确定拉新分析的目标学季：优先用筛选器单选/多选第一个；未选则取在读最多的学季"""
    if len(season_filter) == 1:
        return next(iter(season_filter))
    if len(season_filter) > 1:
        for s in _SEASON_CYCLE:
            if s in season_filter:
                return s
        return next(iter(season_filter))
    # 未选：从数据中推断
    counts = Counter()
    for r in rows:
        try:
            subs = json.loads(r['subjects_json'] or '{}')
        except Exception:
            continue
        for line in subs.values():
            if '在读' in (line.get('status') or ''):
                counts[line.get('season', '')] += 1
    return counts.most_common(1)[0][0] if counts else None



# ═══════════════════════════════════════════════════════════════
# 拉新×续报转化月度分析（新口径）
# ═══════════════════════════════════════════════════════════════

_SEASON_CYCLE = ['寒假', '春季', '暑假', '秋季']


def _season_index(s):
    try:
        return _SEASON_CYCLE.index(s)
    except ValueError:
        return None


def _is_prior_season(target, candidate):
    """判断 candidate 是否在学季循环中早于 target（同一年周期）"""
    ti = _season_index(target)
    ci = _season_index(candidate)
    if ti is None or ci is None:
        return False
    return ci < ti


def _next_season(s):
    try:
        i = _SEASON_CYCLE.index(s)
    except ValueError:
        return ''
    return _SEASON_CYCLE[(i + 1) % len(_SEASON_CYCLE)]


def _split_filter(s):
    return set(x.strip() for x in s.split(',') if x.strip())


def _parse_pay_time(val):
    """解析支付时间为 datetime；失败返回 None"""
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        return dt_datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S',
                '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M',
                '%Y-%m-%d', '%Y/%m/%d']:
        try:
            return dt_datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _resolve_target_season(season_filter, rows):
    """确定拉新分析的目标学季：优先用筛选器单选/多选第一个；未选则取在读最多的学季"""
    if len(season_filter) == 1:
        return next(iter(season_filter))
    if len(season_filter) > 1:
        for s in _SEASON_CYCLE:
            if s in season_filter:
                return s
        return next(iter(season_filter))
    # 未选：从数据中推断
    counts = Counter()
    for r in rows:
        try:
            subs = json.loads(r['subjects_json'] or '{}')
        except Exception:
            continue
        for line in subs.values():
            if '在读' in (line.get('status') or ''):
                counts[line.get('season', '')] += 1
    return counts.most_common(1)[0][0] if counts else None


def get_acquisition_trends(periods: str = '', teaching_point: str = '', subject: str = '',
                           teacher: str = '', branch: str = '', grade: str = '', season: str = '',
                           year: str = '', course_type: str = '', product_type: str = '',
                           class_mode: str = '') -> Dict:
    """
    拉新×续报转化月度分析（B 方案：以源表「订单来源」标签为准）

    核心逻辑：
    1. 以全局筛选中的「学季」定位要分析的拉新学季 S（如暑假）。
    2. 纯拉新判定直接采用源表 BS 列「订单来源[新绩效类型]」逐行标签 = 拉新。
       （不再用「跨学季 prior-season 在读」推导老生，因春暑秋联报等场景下源表已准确标注。）
    3. 在 S 内、满足其他行级筛选、且「在班状态=在读」+「订单来源=拉新」的订单计入纯拉新。
    4. 月份归属：
       - PV 口径 = 该订单自身支付时间所在月份。
       - UV 口径 = 该学员在 S 内所有拉新在读订单的最早支付时间所在月份（一人只归属一个月）。
    5. 续报判定优先取行内原生 `renew_next`（AT 列「是否续下一学季」），缺失时回退到
       跨学季 enrichment 后的 `continue_fall`。
    6. 输出动态月份数组，供前端生成月份 chips 与标题；`non_laxin_excluded` 反馈
       在 S 有在读订单但订单来源均非「拉新」的学员数（不计入拉新）。
    """
    latest = get_latest_run()
    if latest is None:
        return {'months': [], 'total_acquired': 0, 'total_active': 0,
                'total_renewed': 0, 'total_conv_rate': 0,
                'total_active_pv': 0, 'total_renewed_pv': 0,
                'total_not_renewed_pv': 0, 'total_conv_rate_pv': 0,
                'student_total': 0, 'season': '', 'next_season': ''}

    run_id = latest['run']['run_id']

    # ── 解析筛选器 ──
    branch_filter = _split_filter(branch)
    grade_filter = _split_filter(grade)
    season_filter = _split_filter(season)
    period_filter = _split_filter(periods)
    pt_filter = _split_filter(teaching_point)
    tch_filter = _split_filter(teacher)
    year_filter = _split_filter(year)
    ct_filter = _split_filter(course_type)
    prod_filter = _split_filter(product_type)
    cm_filter = _split_filter(class_mode)

    # 学科：前端传显示标签，转回数据库键
    subj_filter = set()
    if subject:
        for s in subject.split(','):
            s = s.strip()
            if not s:
                continue
            if s in _LABEL_TO_SUBJECT:
                subj_filter.add(_LABEL_TO_SUBJECT[s])
            elif s in SUBJECTS:
                subj_filter.add(s)
            else:
                subj_filter.add(s)

    # ── 读取学员快照 ──
    conn = get_db()
    rows = conn.execute(
        'SELECT uid, branch, grade, subjects_json FROM student_snapshots WHERE run_id = ?',
        (run_id,)
    ).fetchall()
    conn.close()

    # 分校筛选在学员层级（UID 跨分校唯一）
    if branch_filter:
        rows = [r for r in rows if (r['branch'] or '').strip() in branch_filter]

    # 确定目标拉新学季
    target_season = _resolve_target_season(season_filter, rows)
    if not target_season:
        return {'months': [], 'student_total': 0, 'season': '', 'next_season': '',
                'hint': '未能在数据中定位拉新学季，请先选择学季筛选'}
    next_season = _next_season(target_season)

    # ── Step1：B 方案 —— 纯拉新以源表「订单来源=拉新」逐行标签为准 ──
    # 不再用 prior-season 在读推导老生；订单来源非「拉新」(续报扩科/老生) 的订单不计入拉新。
    # 统计：在目标学季 S 有在读订单、但订单来源均非「拉新」的学员数（仅用于口径提示）。
    non_laxin_excluded = 0
    for r in rows:
        try:
            subs = json.loads(r['subjects_json'] or '{}')
        except Exception:
            continue
        has_reading = False
        has_laxin = False
        for line in subs.values():
            if line.get('season', '') != target_season:
                continue
            if '在读' not in (line.get('status') or ''):
                continue
            has_reading = True
            if (line.get('order_origin') or '') == '拉新':
                has_laxin = True
        if has_reading and not has_laxin:
            non_laxin_excluded += 1

    # ── Step2：在目标学季 S 内按行级筛选聚合 ──
    month_records = {}   # month -> {month_label, acquired_uids, renewed_uids, active_pv, renewed_pv}
    student_total = 0

    for r in rows:
        uid = r['uid']
        try:
            subs = json.loads(r['subjects_json'] or '{}')
        except Exception:
            continue

        # 收集该学员在目标学季 S 内、且满足其他行级筛选的在读订单
        matched_lines = []
        for line in subs.values():
            if line.get('season', '') != target_season:
                continue
            if '在读' not in (line.get('status') or ''):
                continue
            # B 方案：仅订单来源=拉新 计入纯拉新
            if (line.get('order_origin') or '') != '拉新':
                continue
            # 行级筛选
            if period_filter and line.get('period', '') not in period_filter:
                continue
            if pt_filter and line.get('teaching_point', '') not in pt_filter:
                continue
            if subj_filter and line.get('subject', '') not in subj_filter:
                continue
            if tch_filter and line.get('teacher', '') not in tch_filter:
                continue
            if grade_filter and line.get('grade', '') not in grade_filter:
                continue
            if year_filter and line.get('year', '') not in year_filter:
                continue
            if ct_filter and line.get('course_type', '') not in ct_filter:
                continue
            if prod_filter and line.get('product_type', '') not in prod_filter:
                continue
            if cm_filter and norm_class_mode(line.get('class_mode', '')) not in cm_filter:
                continue
            matched_lines.append(line)

        if not matched_lines:
            continue
        student_total += 1

        # 判断该学员是否有任一订单续报（UV 口径：任一在读订单续报即视为续报学员）
        has_renewed_any = False
        for line in matched_lines:
            rn = (line.get('renew_next') or '').strip()
            if rn:
                renewed = rn in ('是', '1', 'true', 'True', 'Y', 'y')
            else:
                renewed = is_renewed_by_source(line)
            if renewed:
                has_renewed_any = True
                break

        # PV 口径：按每行自身支付时间归属月份
        for line in matched_lines:
            pay_time = _parse_pay_time(line.get('pay_time', ''))
            if not pay_time:
                continue
            month = f'{pay_time.year}-{pay_time.month:02d}'
            month_label = f'{pay_time.month:02d}月'
            rec = month_records.setdefault(month, {
                'month_label': month_label,
                'acquired_uids': set(),
                'renewed_uids': set(),
                'active_pv': 0,
                'renewed_pv': 0,
            })
            rec['active_pv'] += 1
            rn = (line.get('renew_next') or '').strip()
            if rn:
                renewed = rn in ('是', '1', 'true', 'True', 'Y', 'y')
            else:
                renewed = is_renewed_by_source(line)
            if renewed:
                rec['renewed_pv'] += 1

        # UV 口径：学员归属到目标学季内最早支付时间的月份
        pay_entries = [(line, _parse_pay_time(line.get('pay_time', ''))) for line in matched_lines]
        pay_entries = [x for x in pay_entries if x[1] is not None]
        if pay_entries:
            earliest_line, earliest_dt = min(pay_entries, key=lambda x: x[1])
            month = f'{earliest_dt.year}-{earliest_dt.month:02d}'
            month_label = f'{earliest_dt.month:02d}月'
            rec = month_records.setdefault(month, {
                'month_label': month_label,
                'acquired_uids': set(),
                'renewed_uids': set(),
                'active_pv': 0,
                'renewed_pv': 0,
            })
            rec['acquired_uids'].add(uid)
            if has_renewed_any:
                rec['renewed_uids'].add(uid)

    # ── Step3：构建连续月份数组（含零值月份）──
    if month_records:
        months_sorted = sorted(month_records.keys())
        min_y, min_m = int(months_sorted[0][:4]), int(months_sorted[0][5:])
        max_y, max_m = int(months_sorted[-1][:4]), int(months_sorted[-1][5:])
        all_months = []
        cy, cm = min_y, min_m
        while (cy, cm) <= (max_y, max_m):
            all_months.append(f'{cy}-{cm:02d}')
            cm += 1
            if cm > 12:
                cm = 1
                cy += 1
    else:
        all_months = []

    months_data = []
    for m in all_months:
        rec = month_records.get(m)
        if rec is None:
            label = f"{int(m[5:]):02d}月"
            months_data.append({
                'month': m, 'month_label': label,
                'acquired': 0, 'active_acquired': 0, 'renewed_acquired': 0,
                'not_renewed': 0, 'conv_rate': 0,
                'active_pv': 0, 'renewed_pv': 0, 'not_renewed_pv': 0, 'conv_rate_pv': 0,
            })
        else:
            acquired_uv = len(rec['acquired_uids'])
            renewed_uv = len(rec['renewed_uids'])
            not_renewed_uv = acquired_uv - renewed_uv
            active_pv = rec['active_pv']
            renewed_pv = rec['renewed_pv']
            not_renewed_pv = active_pv - renewed_pv
            conv_rate = round(renewed_uv / acquired_uv * 100, 1) if acquired_uv > 0 else 0
            conv_rate_pv = round(renewed_pv / active_pv * 100, 1) if active_pv > 0 else 0
            months_data.append({
                'month': m,
                'month_label': rec['month_label'],
                'acquired': acquired_uv,
                'active_acquired': acquired_uv,
                'renewed_acquired': renewed_uv,
                'not_renewed': not_renewed_uv,
                'conv_rate': conv_rate,
                'active_pv': active_pv,
                'renewed_pv': renewed_pv,
                'not_renewed_pv': not_renewed_pv,
                'conv_rate_pv': conv_rate_pv,
            })

    # ── 合计 ──
    total_acquired = sum(m['acquired'] for m in months_data)
    total_active = sum(m['active_acquired'] for m in months_data)
    total_renewed = sum(m['renewed_acquired'] for m in months_data)
    total_not_renewed = sum(m['not_renewed'] for m in months_data)
    total_conv_rate = round(total_renewed / total_active * 100, 1) if total_active > 0 else 0
    total_active_pv = sum(m['active_pv'] for m in months_data)
    total_renewed_pv = sum(m['renewed_pv'] for m in months_data)
    total_not_renewed_pv = sum(m['not_renewed_pv'] for m in months_data)
    total_conv_rate_pv = round(total_renewed_pv / total_active_pv * 100, 1) if total_active_pv > 0 else 0

    return {
        'months': months_data,
        'total_acquired': total_acquired,
        'total_active': total_active,
        'total_renewed': total_renewed,
        'total_not_renewed': total_not_renewed,
        'total_conv_rate': total_conv_rate,
        'total_active_pv': total_active_pv,
        'total_renewed_pv': total_renewed_pv,
        'total_not_renewed_pv': total_not_renewed_pv,
        'total_conv_rate_pv': total_conv_rate_pv,
        'student_total': student_total,
        'season': target_season,
        'next_season': next_season,
        'season_label': target_season,
        'next_season_label': next_season,
        'non_laxin_excluded': non_laxin_excluded,
        'data_source': 'UV台帐数据库',
        'period_filter': list(period_filter) if period_filter else [],
    }
