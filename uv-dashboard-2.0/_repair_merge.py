"""
一次性修复脚本：将当前共享库中「最新广州 run」+「最新深圳 run」合并为一个
新的 merged run，并正确标注 branch/grade/season。
前置：repository.init_db 已完成迁移 + 历史广州回填。
"""
import os, sys, json, sqlite3
from datetime import datetime

sys.path.insert(0, '/Users/wangboning/WorkBuddy/2026-06-29-13-19-59/uv-dashboard-2.0')
import repository as repo

BASE = '/Users/wangboning/WorkBuddy/2026-06-29-13-19-59/uv-dashboard-2.0'
shared_dir = os.path.join(os.path.dirname(BASE), 'uv-dashboard')
repo.set_data_dir(shared_dir)
repo.init_db()

conn = repo.get_db()

# 深圳特征教学点（用于区分城市）
SZ_MARKS = ('南山', '宝安', '深圳', '福田', '罗湖', '龙华', '龙岗', '盐田', '坪山', '光明')

def classify_run(run_id):
    rows = conn.execute(
        "SELECT teaching_point FROM student_snapshots WHERE run_id=?", (run_id,)
    ).fetchall()
    for r in rows:
        tp = (r['teaching_point'] or '')
        if any(m in tp for m in SZ_MARKS):
            return '深圳'
    return '广州'

runs = conn.execute(
    "SELECT run_id, run_time, total_students FROM calibration_runs ORDER BY run_time DESC"
).fetchall()

gz_runs, sz_runs = [], []
for r in runs:
    city = classify_run(r['run_id'])
    (sz_runs if city == '深圳' else gz_runs).append(r)

print("广州 runs:", [r['run_id'] for r in gz_runs][:5], "...共", len(gz_runs))
print("深圳 runs:", [r['run_id'] for r in sz_runs][:5], "...共", len(sz_runs))

if not gz_runs or not sz_runs:
    print("缺少广州或深圳 run，无法合并。退出。")
    conn.close()
    sys.exit(1)

latest_gz = gz_runs[0]['run_id']   # run_time DESC，首个即最新
latest_sz = sz_runs[0]['run_id']

# 确保 branch/grade/season 正确
conn.execute("UPDATE student_snapshots SET branch='广州', grade='初一', season='暑假' WHERE run_id=?", (latest_gz,))
conn.execute("UPDATE student_snapshots SET branch='深圳', grade='初一', season='暑假' WHERE run_id=?", (latest_sz,))
conn.commit()

# 取两 run 的快照行
gz_rows = conn.execute("SELECT * FROM student_snapshots WHERE run_id=?", (latest_gz,)).fetchall()
sz_rows = conn.execute("SELECT * FROM student_snapshots WHERE run_id=?", (latest_sz,)).fetchall()
print(f"广州 run({latest_gz}) 学员: {len(gz_rows)} | 深圳 run({latest_sz}) 学员: {len(sz_rows)}")

cols = ['run_id','uid','name','teaching_point','advisor','channel','status',
        'period_combined','branch','grade','season','subjects_json','manual_json']
new_run_id = datetime.now().strftime('%Y%m%d_%H%M%S') + '_merge'

merged = []
for r in list(gz_rows) + list(sz_rows):
    d = dict(r)
    d['run_id'] = new_run_id
    merged.append(d)

# 写入新 run 的快照
for d in merged:
    conn.execute(f'''
        INSERT INTO student_snapshots
        ({','.join(cols)})
        VALUES ({','.join('?' for _ in cols)})
    ''', tuple(d.get(c) for c in cols))

total = len(merged)
active = sum(1 for d in merged if '在读' in (d.get('status') or ''))
refund = sum(1 for d in merged if (d.get('status') or '') == '退费')

stats = {
    'total_students': total, 'active_students': active,
    'refund_students': refund, 'new_students': 0, 'changes_count': 0,
}
conn.execute('''
    INSERT OR REPLACE INTO calibration_runs
    (run_id, run_time, total_students, active_students, refund_students,
     new_students, changes_count, stats_json, students_json, student_changes_json,
     ledger_path, report_path, enrollment_file, old_ledger_file)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (
    new_run_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    total, active, refund, 0, 0,
    json.dumps(stats, ensure_ascii=False),
    json.dumps([dict(d) for d in merged], ensure_ascii=False, default=str),
    json.dumps([], ensure_ascii=False),
    '', '', '广州+深圳合并(修复)', '广州+深圳合并(修复)',
))
conn.commit()
conn.close()
print(f"\n✅ 已写入合并 run: {new_run_id}")
print(f"   总学员={total} 在读={active} 退费={refund}")
print("   分校分布:")
from collections import Counter
print("  ", dict(Counter(d.get('branch') for d in merged)))
