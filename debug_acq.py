import sqlite3, json

db_path = '/Users/wangboning/WorkBuddy/2026-06-29-13-19-59/uv-dashboard/uv_dashboard.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rid = '20260708_231358'

rows = conn.execute(
    'SELECT uid, name, channel, subjects_json FROM student_snapshots WHERE run_id = ?',
    (rid,)
).fetchall()

period_filter = {'一期'}
spring_old = 0
kept = 0
has_active_count = 0
no_active_kept = 0

for r in rows:
    channel = (r['channel'] or '').strip()
    if channel == '春季在读老生':
        spring_old += 1
        continue

    subs = json.loads(r['subjects_json'] or '{}')
    has_active = False
    any_subject = False
    for subj, sd in subs.items():
        if not isinstance(sd, dict):
            continue
        subj_period = (sd.get('period') or '').strip()
        if period_filter and subj_period not in period_filter:
            continue
        any_subject = True
        status = (sd.get('status') or '').strip()
        if '在读' in status:
            has_active = True

    # 期次筛选后无科目 -> 跳过
    if period_filter and not any_subject:
        continue

    kept += 1
    if has_active:
        has_active_count += 1
    else:
        no_active_kept += 1

print(f'总学员: {len(rows)}')
print(f'春季老生排除: {spring_old}')
print(f'期次筛选后保留: {kept}')
print(f'期次筛选后在读: {has_active_count}')
print(f'期次筛选后退费: {no_active_kept}')
conn.close()
