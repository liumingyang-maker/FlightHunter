"""生成 72h 运行报告（从 JSONL 采样汇总）。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="data/daily_usage/logs/72h_samples.jsonl")
    ap.add_argument("--out", default="docs/72H_RUN_REPORT.md")
    args = ap.parse_args()

    log_path = ROOT / args.log
    if not log_path.exists():
        print(f"no samples: {log_path}")
        raise SystemExit(1)

    rows = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if not rows:
        print("empty log")
        raise SystemExit(1)

    first, last = rows[0], rows[-1]
    t0 = first.get("ts")
    t1 = last.get("ts")
    dur_h = None
    try:
        dur_h = (
            datetime.fromisoformat(str(t1).replace("Z", "+00:00"))
            - datetime.fromisoformat(str(t0).replace("Z", "+00:00"))
        ).total_seconds() / 3600
    except Exception:
        pass

    hb_changes = sum(1 for r in rows[1:] if (r.get("worker") or {}).get("heartbeat_at") != (rows[0].get("worker") or {}).get("heartbeat_at"))
    errors = [r for r in rows if r.get("worker_error") or r.get("db_error")]
    rounds = [(r.get("worker") or {}).get("rounds") for r in rows if (r.get("worker") or {}).get("rounds") is not None]
    lock_pids = {str((r.get("worker") or {}).get("pid") or (r.get("worker") or {}).get("lock", {}).get("pid")) for r in rows}

    sh = last.get("source_health") or {}
    counters = sh.get("counters") or {}

    dur_s = f"{dur_h:.1f} 小时" if dur_h is not None else "未知"
    md = f"""# 72 小时连续运行报告（自动汇总）

- **样本数：** {len(rows)}
- **采样窗口：** `{t0}` → `{t1}`（约 {dur_s}）
- **观测起点（只读）：** `{(first.get('observation') or {}).get('started_utc')}`
- **Worker PID 集合：** {', '.join(sorted(x for x in lock_pids if x and x != 'None'))}
- **心跳变化次数：** {hb_changes}
- **采样错误：** {len(errors)}

## Worker

| 项 | 首次 | 末次 |
|---|---|---|
| rounds | {(first.get('worker') or {}).get('rounds')} | {(last.get('worker') or {}).get('rounds')} |
| last_run_at | {(first.get('worker') or {}).get('last_run_at')} | {(last.get('worker') or {}).get('last_run_at')} |
| heartbeat_at | {(first.get('worker') or {}).get('heartbeat_at')} | {(last.get('worker') or {}).get('heartbeat_at')} |

## 来源健康（末次 24h 窗口）

```json
{json.dumps(counters, ensure_ascii=False, indent=2)}
```

## 诚实边界

- 本报告由 **采样 JSONL** 汇总，不代表 104 项验收。
- 未覆盖：真实桌面 toast、断网/恢复实验（需人工操作）、公网。
- 若 `duration` < 72h，**不得**声称 72h 达标。

## 原始样本

`{log_path.relative_to(ROOT)}`
"""
    out = ROOT / args.out
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out} rows={len(rows)} dur_h={dur_h}")


if __name__ == "__main__":
    main()
