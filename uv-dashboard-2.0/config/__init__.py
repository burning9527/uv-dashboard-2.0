"""
UV Dashboard 2.0 — 配置层
集中管理期次、学科、教学点、顾问等业务配置。
修改任何业务参数只需改此文件，无需动引擎/API层。
"""

from datetime import datetime

# ═══════════════════════════════════════════════════════════════
# 期次配置
# ═══════════════════════════════════════════════════════════════

PERIOD_SCHEDULE = {
    '零期': {'start': (6, 29), 'end': (7, 10), 'note': '7/4-5休息'},
    '一期': {'start': (7, 13), 'end': (7, 24), 'note': '7/18-19休息'},
    '二期': {'start': (7, 27), 'end': (8, 7),  'note': '8/1-2休息'},
    '三期': {'start': (8, 10), 'end': (8, 21),  'note': '8/15-16休息'},
    '四期': {'start': (8, 17), 'end': (8, 28),  'note': ''},
}

# 期次显示顺序（按开课日期排序，从 PERIOD_SCHEDULE 动态派生）
PERIOD_ORDER = sorted(PERIOD_SCHEDULE.keys(), key=lambda k: PERIOD_SCHEDULE[k]['start'])

# ── 星期维度（长学期春秋用）──
# 春秋长学期按"周X"开课，无期次之分。week_cycle 字段取值如 "每周六"/"每周日"。
# 规范化为 周一/周二/.../周日 七值。
WEEKDAY_ORDER = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
WEEKDAY_LABELS = {w: w for w in WEEKDAY_ORDER}
# week_cycle 原始值 → 规范化的星期简称
WEEKDAY_NORM = {
    '周一': '周一', '周二': '周二', '周三': '周三', '周四': '周四',
    '周五': '周五', '周六': '周六', '周日': '周日',
    '每周一': '周一', '每周二': '周二', '每周三': '周三', '每周四': '周四',
    '每周五': '周五', '每周六': '周六', '每周日': '周日',
}


def norm_weekday(raw):
    """week_cycle 原始值（'每周X' / '周X' / 'X'）→ '周X' 简称。
    未识别返回 ''。"""
    s = (raw or '').strip()
    if not s:
        return ''
    return WEEKDAY_NORM.get(s, s)


# ── 学期类型判定 ──
SHORT_SEASONS = {'暑假', '寒假'}
LONG_SEASONS = {'春季', '秋季'}


def term_type_for_seasons(seasons):
    """根据学季集合返回学期类型。

    Returns:
        'short_term' - 全部为短学期（寒/暑）
        'long_term'  - 全部为长学期（春/秋）
        'mixed'      - 短+长混合
        'empty'      - 无学季
    """
    if not seasons:
        return 'empty'
    has_short = any(s in SHORT_SEASONS for s in seasons)
    has_long = any(s in LONG_SEASONS for s in seasons)
    if has_short and has_long:
        return 'mixed'
    if has_short:
        return 'short_term'
    if has_long:
        return 'long_term'
    return 'empty'


# ── 期次筛选器全集（含"无"）──
# 底表 I列(期次) 的完整取值域。"无" = 春/秋长学期（无期次之分）。
# 期次矩阵/分期次统计只用 PERIOD_ORDER（不含"无"）；筛选器下拉用 PERIODS_ALL（含"无"）。
NO_PERIOD_LABEL = '无'
PERIODS_ALL = PERIOD_ORDER + [NO_PERIOD_LABEL]

# 期次排序键：零<一<二<三<四<无（其它未知值排最后）
_PERIOD_RANK = {name: i for i, name in enumerate(PERIODS_ALL)}


def period_sort_key(p):
    """期次排序键，用于对期次标签列表排序（零/一/二/三/四/无）。"""
    return _PERIOD_RANK.get((p or '').strip(), 999)

# 期次开课日期（用于退费分类、续报基线判定）
PERIOD_DATES = {
    name: datetime(datetime.now().year, cfg['start'][0], cfg['start'][1])
    for name, cfg in PERIOD_SCHEDULE.items()
}


def get_period_start_str(period_name, year=None):
    """获取期次开课日期字符串 (YYYY-MM-DD)"""
    if year is None:
        year = datetime.now().year
    m, d = PERIOD_SCHEDULE[period_name]['start']
    return f'{year}-{m:02d}-{d:02d}'


def auto_detect_period(dt=None):
    """根据日期自动判定当前期次（基于PERIOD_SCHEDULE动态计算）"""
    if dt is None:
        dt = datetime.now()
    t_md = dt.month * 100 + dt.day
    # 从最晚的期次开始检查
    for p in reversed(PERIOD_ORDER):
        m, d = PERIOD_SCHEDULE[p]['start']
        if t_md >= m * 100 + d:
            return p
    # 早于所有期次 → 返回最早的期次
    return PERIOD_ORDER[0] if PERIOD_ORDER else ''


# ═══════════════════════════════════════════════════════════════
# 学科配置
# ═══════════════════════════════════════════════════════════════

SUBJECTS = ['雪球思维', '悦读创作', '双语素养', '雪球科学']

# 学科简称映射
SUBJECT_SHORT = {
    '雪球思维': '数',
    '悦读创作': '语',
    '双语素养': '英',
    '雪球科学': '物',
}

# 学科标签映射（用于导出等场景）
SUBJECT_LABEL = {
    '雪球思维': '数学',
    '悦读创作': '语文',
    '双语素养': '英语',
    '雪球科学': '物理',
}

# 学科颜色
SUBJECT_COLOR = {
    '雪球思维': '#378ADD',
    '悦读创作': '#639922',
    '双语素养': '#BA7517',
    '雪球科学': '#2BB6A3',
}

# 学科列范围（UV台帐Excel格式）
SUBJECT_COL_RANGES = {
    '雪球思维': (10, 20),
    '悦读创作': (21, 29),
    '双语素养': (30, 38),
}

# 学科列映射（UV台帐Excel列号）
SUBJECT_COL_MAP = {
    '雪球思维': {
        'class_id': 10, 'teacher': 14, 'room': 15,
        'time_slot': 16, 'class_type': 17, 'period': 18, 'status': 19, 'continue_fall': 20,
    },
    '悦读创作': {
        'class_id': 21, 'teacher': 23, 'room': 24,
        'time_slot': 25, 'class_type': 26, 'period': 27, 'status': 28, 'continue_fall': 29,
    },
    '双语素养': {
        'class_id': 30, 'teacher': 32, 'room': 33,
        'time_slot': 34, 'class_type': 35, 'period': 36, 'status': 37, 'continue_fall': 38,
    },
}

# 招生明细订单字段映射: subject → {field_key: (招生明细列名, 台帐列号)}
ORDER_FIELD_MAP = {
    '雪球思维': {
        '班级id':       ('在读班级id', 10),
        '主讲':         ('主讲', 14),
        '教室':         ('教室', 15),
        '上课时段':     ('上课时段', 16),
        '班型':         ('班型', 17),
        '期次':         ('期次', 18),
        '是否在读':     ('在班状态', 19),
        '是否续秋':     (None, 20),
    },
    '悦读创作': {
        '班级id':       ('在读班级id', 21),
        '主讲':         ('主讲', 23),
        '教室':         ('教室', 24),
        '上课时段':     ('上课时段', 25),
        '班型':         ('班型', 26),
        '期次':         ('期次', 27),
        '是否在读':     ('在班状态', 28),
        '是否续秋':     (None, 29),
    },
    '双语素养': {
        '班级id':       ('在读班级id', 30),
        '主讲':         ('主讲', 32),
        '教室':         ('教室', 33),
        '上课时段':     ('上课时段', 34),
        '班型':         ('班型', 35),
        '期次':         ('期次', 36),
        '是否在读':     ('在班状态', 37),
        '是否续秋':     (None, 38),
    },
}

# 变动字段中文标签
CHANGE_LABELS = {
    'class_id': '班级变更',
    'teacher': '主讲变更',
    'room': '教室变更',
    'time_slot': '时段变更',
    'class_type': '班型变更',
    'period': '期次变更',
}


# ═══════════════════════════════════════════════════════════════
# 教学点配置
# ═══════════════════════════════════════════════════════════════

def normalize_teaching_point(raw):
    """标准化教学点名称：去'教学点'后缀；保留'大厦'等完整名称。"""
    if not raw:
        return raw
    name = str(raw).strip()
    name = name.removesuffix('教学点').strip()
    # 统一完整名称：避免出现'新宝利'与'新宝利大厦'并存
    if name == '新宝利':
        name = '新宝利大厦'
    if name == '天成':
        name = '天成大厦'
    return name


# ═══════════════════════════════════════════════════════════════
# 教室→教学点映射（班级ID的教学点归属由教室决定）
# ═══════════════════════════════════════════════════════════════

# 教室名 → 教学点全称（标准化后）
# 规律：01智慧林/02彩虹桥/03识海阁 → 同创汇
#       03品尚 → 天成大厦
#       教室2/教室3/教室4/教室5 → 新宝利大厦
ROOM_POINT_MAP = {
    '01智慧林': '同创汇',
    '02彩虹桥': '同创汇',
    '03识海阁': '同创汇',
    '03品尚': '天成大厦',
    '教室2': '新宝利大厦',
    '教室3': '新宝利大厦',
    '教室4': '新宝利大厦',
    '教室5': '新宝利大厦',
}


def get_room_teaching_point(room_name, fallback=''):
    """从教室名推导教学点归属（班级ID的教学点由教室绑定）。
    未匹配的教室名返回 fallback（默认空字符串），由调用方决定回退策略。
    """
    if not room_name:
        return fallback
    room = str(room_name).strip()
    return ROOM_POINT_MAP.get(room, fallback)


def get_line_subject(sd, key=''):
    """从一条班级行(line/科目子结构)取真实学科名。

    订单行数组模型下 subjects_json 的键为合成唯一 id（无业务含义），
    真实学科存于 sd['subject']；旧 1.0 dict 模型键即学科名，
    此时 sd 无 'subject' 键 → 回退到 key。
    """
    if isinstance(sd, dict):
        s = (sd.get('subject') or '').strip()
        if s:
            return s
    return key


def line_teaching_point(sd, fallback_pt=''):
    """取单条班级行的教学点：优先显式 teaching_point（订单行自带），
    否则由教室推导，再否则 fallback 到学员级注册教学点。"""
    if isinstance(sd, dict):
        tp = (sd.get('teaching_point') or '').strip()
        if tp and tp != '-':
            return normalize_teaching_point(tp)
        room = (sd.get('room') or '').strip()
        if room:
            derived = get_room_teaching_point(room, '')
            if derived and derived != '-':
                return normalize_teaching_point(derived)
    return normalize_teaching_point(fallback_pt) if fallback_pt else ''


def student_teaching_points(subjects, fallback_pt=''):
    """从学员各科目推导其教学点归属集合（班级/教室决定归属）。

    核心判定原则：学员归属默认跟随其各班级所在教学点，
    而非学员级注册教学点。

    - 遍历各班级行，优先取显式 teaching_point（订单行自带），
      否则用 get_room_teaching_point(room, '') 推导；
    - 任一行能映射到教学点即收集（学员可能归属多个教学点）；
    - 若所有行都无法映射到教学点，则 fallback 到学员级注册教学点。
    """
    pts = set()
    if isinstance(subjects, dict):
        for subj, sd in subjects.items():
            if not isinstance(sd, dict):
                continue
            pt = line_teaching_point(sd, '')
            if pt and pt != '-':
                pts.add(pt)
    if not pts and fallback_pt:
        n = normalize_teaching_point(fallback_pt)
        if n:
            pts.add(n)
    return pts


def display_subjects(subjects, current_season: str = ''):
    """把订单行数组模型的 subjects_json（合成键 → line）折叠为
    前端友好的 {真实学科名: line} 字典。

    背景：订单行数组模型下，subjects_json 的键是合成唯一 id
    （如 "雪球思维#0"），前端（uv-modal.js / uv-config.js）却按
    真实学科名（"数学"/"雪球思维"…）查找 subjects['数学']，会全部落空。
    此助手把每个学员对象的 subjects 重键为真实学科名。

    同一学员同一学科可能有多条订单行（重复报名/退费+重报），
    优先保留「在读」的那条 line；若都不在读则保留最后一条。
    旧 1.0 dict 模型键即学科名，直接透传（幂等）。

    BUG 修复：当传入 current_season 时，优先保留匹配该学季的「在读」行。
    否则同一学科可能在读行有「暑假+秋季」两条，display_subjects 会保留后者（秋季），
    但续报判定（continue_fall='是'）是跨学季的（秋季 + 寒假），导致秋季行带续报标签。
    修复后：筛选秋季时只显示秋季行的状态（cf=否、status=在读），不展示跨学季续报。
    """
    if not isinstance(subjects, dict):
        return {}
    out = {}
    for key, sd in subjects.items():
        if not isinstance(sd, dict):
            continue
        subj = get_line_subject(sd, key)
        if not subj:
            continue
        prev = out.get(subj)
        if prev is None:
            out[subj] = sd
            continue
        prev_season = str(prev.get('season') or '').strip()
        cur_season = str(sd.get('season') or '').strip()
        prev_active = prev_season in ('在读', '在班')
        cur_active = cur_season in ('在读', '在班')
        # BUG 修复：传 current_season 时优先匹配学季的行
        if current_season:
            prev_match = prev_season == current_season
            cur_match = cur_season == current_season
            if cur_match and not prev_match:
                out[subj] = sd
            elif cur_match == prev_match:
                # 同匹配度：优先保留在读行
                prev_in_read = str(prev.get('status') or '').strip() in ('在读', '在班')
                cur_in_read = str(sd.get('status') or '').strip() in ('在读', '在班')
                if cur_in_read and not prev_in_read:
                    out[subj] = sd
                elif cur_in_read == prev_in_read:
                    out[subj] = sd  # 同状态取后者
            continue
        # 旧逻辑（无 current_season）
        if cur_active and not prev_active:
            out[subj] = sd
        elif cur_active == prev_active:
            out[subj] = sd  # 同状态取后者（最新一条）
    return out


# ═══════════════════════════════════════════════════════════════
# 顾问标签配置（全称标签，适应全国教学点拓展）
# ═══════════════════════════════════════════════════════════════

# 顾问 → 教学点全称标签（硬编码 fallback，引擎会从学员数据动态构建）
ADVISOR_POINT_TAG = {
    '陈亮延': '天成大厦', '王达04': '天成大厦', '沈思浩': '天成大厦', '龙倩敏': '天成大厦',
    '戎凯01': '同创汇', '王丽': '同创汇', '苏丽婷': '同创汇',
    '杨林33': '新宝利大厦', '林志豪01': '新宝利大厦', '张敏烨': '新宝利大厦',
}

# 教学点全称 → 颜色（主页面用）
POINT_COLOR = {
    '天成大厦': '#f5a623',
    '同创汇': '#1d9e75',
    '新宝利大厦': '#378add',
}

# 教学点全称 → 颜色（分享页面用，稍偏灰）
POINT_COLOR_SHARE = {
    '天成大厦': '#f5a623',
    '同创汇': '#1d9e75',
    '新宝利大厦': '#8c92a3',
}

DEFAULT_POINT_COLOR = '#6b7280'
DEFAULT_POINT_COLOR_SHARE = '#8c92a3'


def get_advisor_tag(advisor_name, dynamic_map=None):
    """获取顾问教学点全称标签。
    优先使用引擎动态构建的映射，fallback 到硬编码配置。
    """
    if dynamic_map and advisor_name in dynamic_map:
        return dynamic_map.get(advisor_name)
    return ADVISOR_POINT_TAG.get(advisor_name)


def get_advisor_tag_color(advisor_name, is_share=False, dynamic_map=None):
    """获取顾问标签颜色（按教学点全称匹配）"""
    tag = get_advisor_tag(advisor_name, dynamic_map)
    if not tag:
        return DEFAULT_POINT_COLOR_SHARE if is_share else DEFAULT_POINT_COLOR
    color_map = POINT_COLOR_SHARE if is_share else POINT_COLOR
    return color_map.get(tag, DEFAULT_POINT_COLOR_SHARE if is_share else DEFAULT_POINT_COLOR)


# ═══════════════════════════════════════════════════════════════
# 续报标记配置
# ═══════════════════════════════════════════════════════════════

CONTINUE_FALL_POSITIVE = {'是', '已续', 't', 'ac', 'al', 'true', 'yes', '1', 'y'}

def is_continue_fall(val):
    """判断续秋标记是否为已续报"""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if not s or s == '-':
        return False
    return s in CONTINUE_FALL_POSITIVE


def is_renewal_denom(sd):
    """续报率锁定分母口径：BW(renew_denom_incl)=1 → 分母行。
    无 BW 字段时回退到旧口径（在读行）。"""
    val = (sd.get('renew_denom_incl') or '').strip()
    if not val:
        return '在读' in (sd.get('status') or '')
    return val == '1'


def is_renewed_by_source(sd):
    """续报率锁定分子口径：BW=1 & AT(renew_next)=是 & BG(valid_refund)≠有效退费。
    无源表字段时回退到旧口径 is_continue_fall。"""
    if not is_renewal_denom(sd):
        return False
    rn = (sd.get('renew_next') or '').strip()
    vr = (sd.get('valid_refund') or '').strip()
    # 无源表字段时回退到旧口径
    if not rn:
        return is_continue_fall(sd.get('continue_fall', ''))
    return rn == '是' and vr != '是'


def classify_renewal_by_pay_time(fall_pay_time_str, period_name, year=None, start_date=None):
    """
    根据订单实际支付时间与开课时间判定续报类别：
    - 支付时间 < 开课日期 → 'pre' (开课前续报)
    - 支付时间 >= 开课日期 → 'new' (当期转化)
    - 无支付时间 → 'pre' (保守归为开课前续报)
    - 若提供了 start_date（班级开始日期），优先以该实际开课日期为准；
      否则回退到期次配置表 PERIOD_SCHEDULE 的期次开课日期。
    """
    if not fall_pay_time_str:
        return 'pre'
    try:
        pay_time = datetime.fromisoformat(str(fall_pay_time_str))
    except (ValueError, TypeError):
        return 'pre'
    # 优先使用实际班级开始日期作为开课时间
    if start_date:
        try:
            sd = datetime.fromisoformat(str(start_date).strip())
            # start_date 多为 YYYY-MM-DD， pay_time 为 datetime；统一按 date 比较
            if pay_time.date() < sd.date():
                return 'pre'
            return 'new'
        except (ValueError, TypeError):
            pass
    # 回退：期次配置表
    if year is None:
        year = datetime.now().year
    schedule = PERIOD_SCHEDULE.get(period_name)
    if not schedule:
        return 'pre'
    m, d = schedule['start']
    period_start = datetime(year, m, d)
    return 'pre' if pay_time < period_start else 'new'


# ═══════════════════════════════════════════════════════════════
# 筛选器体系配置（8项看板筛选器：年份/分校/学科/年级/学季/期次/教学点/主讲）
# ═══════════════════════════════════════════════════════════════

FILTER_CONFIG = {
    'year': {
        'label': '年份', 'enabled': True, 'default': '2026',
        'type': 'multi_select', 'options': ['2025', '2026', '2027'],
    },
    'branch': {
        'label': '分校', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': ['广州', '深圳', '北京', '上海'],
    },
    'subject': {
        'label': '学科', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': [],  # 从 SUBJECTS 动态填充
    },
    'grade': {
        'label': '年级', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': ['一年级', '二年级', '三年级', '四年级',
                                      '五年级', '六年级', '初一', '初二', '初三'],
    },
    'season': {
        'label': '学季', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': ['寒假', '春季', '暑假', '秋季'],
    },
    'period': {
        'label': '期次', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': [],  # 从 PERIOD_ORDER 动态填充
    },
    'teaching_point': {
        'label': '教学点', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': [],  # 从数据动态填充
    },
    'teacher': {
        'label': '主讲', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': [],  # 从数据动态填充
    },
    'advisor': {
        'label': '顾问', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': [],  # 从数据动态填充（仅数据明细板块使用）
    },
    'enrollment_status': {
        'label': '在读状态', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': ['在读', '退费'],
        'glossary': '学员当前就读状态。仅含「在读 / 退费」两态：退费含课前退与课后退（可双标），丢弃「出班 / 结课」口径（数据中出班均属退费）。',
    },
    'course_type': {
        'label': '课程类型', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': [],
        'glossary': '按收费模型区分：特惠课（低价引流课）/ 系统课（正价体系课）。来自订单明细「课程类型(K)」列。',
    },
    'product_type': {
        'label': '产品类型', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': [],
        'glossary': '按转化属性区分：转化品（用于拉新转化）/ 正价品（正式正价产品）。来自订单明细「产品类型(J)」列。',
    },
    'renewal_status': {
        'label': '续报状态', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': ['已续报', '未续报', '课前续', '当期转化'],
    },
    'student_type': {
        'label': '学员归属', 'enabled': True, 'default': '',
        'type': 'multi_select', 'options': ['新生', '老生', '老生拓科'],
        'glossary': '按学员来源渠道区分：新生（首次报名）/ 老生（已有学员续报）/ 老生拓科（老学员新增其他科目）。来自订单明细「学员归属(BS)」列。',
    },
}

# ═══════════════════════════════════════════════════════════════
# 筛选器释意（FIELD_GLOSSARY）— 权威字典 §1~§4 收敛，供前端 tooltip 展示
# 键 = FILTER_CONFIG 的字段名；值 = 一句话释意（鼠标悬停筛选标签可见）
# ═══════════════════════════════════════════════════════════════
FIELD_GLOSSARY = {
    'year': '订单归属学年。默认 2026。空选 = 全部年份并集（面向全国多城市共存）。',
    'branch': '城市分校（归一自「K9XX分校」→城市名：广州/深圳/北京/上海…）。空选 = 全部分校。',
    'subject': '产品原名（雪球思维/双语素养/悦读创作/雪球科学），分别对应数学/英语/语文/物理。空选 = 全部学科。',
    'grade': '报名班级年级（一年级~初三），主年级维度。空选 = 全部年级。',
    'season': '学季：暑/秋/寒/春。寒暑为短学期分期次；春秋为长学期不分期次（期次显示「无」→按学季简称）。',
    'period': '寒暑期次：零/一/二/三/四期；长学期为「无」。前端按学季显示为 春/秋/暑/寒。',
    'teaching_point': '具体教学点（去「教学点」后缀）。学员归属跟随其各班级所在教室推导的教学点。',
    'teacher': '班级主讲。按 uname 聚合、显示用 name。',
    'advisor': '顾问（成单归属人 uname 聚合、name 显示）。',
    'class_type': '拔高班型阶梯：源能<启航<潜能<启能<超能，逐步拔高。',
    'enrollment_status': '学员当前就读状态。仅含「在读 / 退费」两态：退费含课前退与课后退（可双标），丢弃「出班 / 结课」口径（数据中出班均属退费）。',
    'renewal_status': '续报流向：已续报 / 未续报 / 课前续 / 当期转化。',
    'course_type': '按收费模型区分：特惠课（低价引流）/ 系统课（正价体系）。',
    'product_type': '按转化属性区分：转化品（拉新）/ 正价品（正式正价）。',
    'channel': '订单线索二级渠道（AM 列）。一级渠道仅作 UI 分组，不进筛选。',
}

# 前端期次配置（动态渲染，支持不同分校不同期次组合）
PERIOD_CONFIG = {
    'order': PERIOD_ORDER,            # 矩阵/分期次统计用（不含"无"）
    'all': PERIODS_ALL,              # 筛选器下拉全集（含"无"）
    'schedule': PERIOD_SCHEDULE,
    'default': PERIOD_ORDER[0] if PERIOD_ORDER else '',
}

# 默认筛选器值（全国数据首屏默认：2026年 / 广州 / 暑假 / 初一）
# 前端 _setDefaultSet 用这些值初始化各板块 state；用户清空后为空 Set = 全选。
# 后端 FilterSpec.from_params 遇空参数返回空列表 = 全选。
FILTER_DEFAULTS = {
    'year': '2026',
    'season': '暑假',
    'branch': '广州',
    'grade': '初一',
    'class_mode': '班课',   # 矩阵「产品类型」筛选器：取 M 列课程模式，归一为 班课/1v1，默认 班课
}

# 课程模式（M 列 课程模式）归一：k9班课→班课，k9一对一→1v1
# ⚠️ 严格归一：只接受班课/1v1 两类合法值；其他值（脏数据如"潜能班"误填入 M 列）
# 一律视为空，避免污染 class_modes 集合（防止班型(class_type) 混入产品类型(class_mode)）。
def norm_class_mode(v):
    v = (v or '').strip()
    if not v or v == '-':
        return ''
    if '班课' in v:
        return '班课'
    if '1v1' in v or '一对一' in v:
        return '1v1'
    # 非法值（如"潜能班"误填到 M 列 / 空字符串）→ 视为空
    return ''
    return v

# 班型阶梯（依次进阶：源能→启航→潜能→启能→超能），供排序与阶梯 UI 使用
CLASS_TYPE_ORDER = ['源能班', '启航班', '潜能班', '启能班', '超能班']


# ═══════════════════════════════════════════════════════════════
# 搭班配置（讲师学员导出）
# ═══════════════════════════════════════════════════════════════

# 主讲学科 → 搭班学科列名
CO_TEACHER_MAP = {
    '雪球思维': ('搭班语文', '搭班英语', 'chinese_teacher', 'english_teacher'),
    '悦读创作': ('搭班数学', '搭班英语', 'math_teacher', 'english_teacher'),
    '双语素养': ('搭班数学', '搭班语文', 'math_teacher', 'chinese_teacher'),
}


# ═══════════════════════════════════════════════════════════════
# 应用配置
# ═══════════════════════════════════════════════════════════════

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
DEFAULT_PORT = 5200


# ═══════════════════════════════════════════════════════════════
# 分享页辅助函数（移植自 1.0，供本地分享页快照迭代计算使用）
# ═══════════════════════════════════════════════════════════════

def _is_cf(v):
    """判断续秋标记（与 1.0 一致）"""
    if not v:
        return False
    v = str(v).strip()
    return v in ('是', '已续', 'T', 'AC', 'AL', 'true', '1', '√')


def _detect_subj_period(period_val):
    """从跨期字符串中提取主要期次"""
    if not period_val:
        return ''
    parts = [p.strip() for p in period_val.split('/') if p.strip()]
    return parts[0] if parts else ''


def _compute_filtered_new_count(conn, rid, point_filter, subj_filter, period_filter, teacher_filter,
                                branch_filter=None, year_filter=None, season_filter=None,
                                course_type_filter=None, class_mode_filter=None):
    """
    按筛选条件计算某次校准 run 中的新增学员 PV 数（移植自 1.0）。

    新增学员来源：change_records 中 change_type='新增学员' 的 uid + subject 对。
    PV 逻辑：每个新增学员的每个在读科目满足筛选条件时计 1（不去重 uid）。
    支持 branch/year/season/course_type/class_mode 全局筛选行级过滤。
    """
    import json as _j

    # 1. 从 change_records 取出新增学员的 uid + subject 对
    where_sql = 'run_id = ? AND change_type = ?'
    params = [rid, '新增学员']
    if subj_filter:
        where_sql += ' AND subject IN (%s)' % ','.join('?' * len(subj_filter))
        params.extend(subj_filter)

    rows = conn.execute(
        f'SELECT DISTINCT uid, subject FROM change_records WHERE {where_sql}',
        params
    ).fetchall()
    if not rows:
        return 0

    # 构建 uid -> set(subjects) 映射
    uid_subjects = {}
    for r in rows:
        uid_subjects.setdefault(r['uid'], set()).add(r['subject'])

    # 2. 取这些 uid 的 snapshot，按教学点/期次/主讲/全局筛选，计 PV
    uids = list(uid_subjects.keys())
    placeholders = ','.join('?' * len(uids))
    snap_rows = conn.execute(
        f'SELECT uid, teaching_point, branch, subjects_json FROM student_snapshots WHERE run_id = ? AND uid IN ({placeholders})',
        (rid,) + tuple(uids)
    ).fetchall()

    pv_count = 0
    for s in snap_rows:
        pt = (s['teaching_point'] or '').strip()
        if point_filter and pt not in point_filter:
            continue
        s_branch = (s.get('branch') or '').strip()
        if branch_filter and s_branch not in branch_filter:
            continue
        try:
            subs = _j.loads(s['subjects_json'] or '{}')
        except Exception:
            continue
        new_subjects = uid_subjects.get(s['uid'], set())
        for _k, sd in subs.items():
            if not isinstance(sd, dict):
                continue
            subj = get_line_subject(sd, _k)
            # 只统计该学员新增的科目
            if subj not in new_subjects:
                continue
            if subj_filter and subj not in subj_filter:
                continue
            period = (sd.get('period') or '').strip()
            if period_filter:
                plist = [p.strip() for p in period.split('/') if p.strip()]
                if not any(p in period_filter for p in plist):
                    continue
            teacher = (sd.get('teacher') or '').strip()
            if teacher_filter and teacher not in teacher_filter:
                continue
            # 全局筛选行级过滤（与主看板口径一致）
            if year_filter and (sd.get('year', '') or '') not in year_filter:
                continue
            if season_filter and (sd.get('season', '') or '') not in season_filter:
                continue
            if course_type_filter and (sd.get('course_type', '') or '') not in course_type_filter:
                continue
            if class_mode_filter and norm_class_mode(sd.get('class_mode', '') or '') not in class_mode_filter:
                continue
            status = (sd.get('status') or '').strip()
            if '在读' in status:
                pv_count += 1
    return pv_count
