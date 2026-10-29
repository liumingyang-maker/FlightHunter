"""Export machine metrics and human-readable outcomes, without secrets/claims of true verification."""
from __future__ import annotations
import argparse
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from monitor import counts, scrub, connect_readonly


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir',type=Path,required=True)
    args=ap.parse_args()
    run_dir=args.run_dir.resolve()
    db=run_dir/'snapshot'/'data'/'flighthunter-live-test.db'
    report=run_dir/'RESULTS.md'
    c=counts(db)
    rows=['# FlightHunter 第一轮实机运行结果', '', f'- 报告生成 UTC：{datetime.now(timezone.utc).isoformat()}',
          '- 注意：结果来自本机数据库与日志，HTTP 成功不等于官方核实/资格通过/券码已领取。',
          '- 所有数据仅存本机；发送给 AI 前必须检查并脱敏。','', '## 结构化计数', '', '```json',json.dumps(c,indent=2,ensure_ascii=False),'```','','## 来源记录（不包含完整 URL）','']
    if db.exists():
        try:
            with connect_readonly(db) as conn:
                tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'sources' in tables:
                    for name,mod,status,fail,last in conn.execute('SELECT name,module,status,consecutive_failures,last_fetch_at FROM sources ORDER BY module,name'):
                        rows.append(f'- {scrub(str(mod))} | {scrub(str(name))} | status={scrub(str(status))}, failures={fail}, last_fetch={scrub(str(last))}')
                rows+=['','## 真实候选样本（仅显示标题、状态，不显示隐私或凭据）','']
                checks=[('campaign_rounds','SELECT title, verify_status FROM campaign_rounds WHERE demo_only=0 ORDER BY created_at_utc DESC LIMIT 12'),
                        ('benefit_offers','SELECT title, date_certainty FROM benefit_offers WHERE demo_only=0 ORDER BY created_at_utc DESC LIMIT 12'),
                        ('fare_deal_signals','SELECT title, signal_status FROM fare_deal_signals ORDER BY created_at_utc DESC LIMIT 12')]
                for table,query in checks:
                    rows.append(f'### {table}')
                    if table in tables:
                        for title,status in conn.execute(query):
                            rows.append(f'- {scrub(str(title))} | {scrub(str(status))}')
                    else: rows.append('- 尚无数据表')
        except Exception as e:
            rows.append(f'- DB read error: {scrub(str(e))}')
    issues=run_dir/'alerts.jsonl'
    rows+=['','## 自动监控异常','']
    if issues.exists():
        for line in issues.read_text(encoding='utf-8',errors='replace').splitlines()[:60]:
            try:
                item=json.loads(line)
                rows.append(f"- [{item['severity']}] {item['rule']}: {scrub(item['message'])}")
            except Exception: pass
    else: rows.append('- 暂无监控记录')
    rows+=['','## 人工验收（请在 FlightHunter Web 检查）','',
           '- [ ] 抽奖：从公开来源发现了真实条目；能点开线索并追到主办方规则；资格未知不虚构通过',
           '- [ ] 日本：发现真实活动与正确城市日期；中文指南指出未核实字段；不存在伪领取成功',
           '- [ ] 机票：实际信号与爆料价分离；不能确认供应商实时报价时不得标 urgent_verified',
           '- [ ] 重扫：候选与证据不无界增长；没有 unique/IntegrityError',
           '- [ ] 停止：PC 离线/站点拒绝/数据库错误时状态如实显示；无自动表单提交或付款',
           '']
    report.write_text('\n'.join(rows),encoding='utf-8')
    print(f'[REPORT] {report}')

if __name__=='__main__':main()
