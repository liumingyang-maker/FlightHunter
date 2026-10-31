"""72h 运行监控：只读采样 Worker/来源健康/通知，写入 JSONL。

**不**重置 OBSERVATION.json，**不**杀 Worker，**不**写正式库。
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sample_once(settings_path: str) -> dict:
    """单次采样。"""
    import sys

    sys.path.insert(0, str(ROOT))
    from app.config import load_settings
    from app.db.session import create_db_engine, make_session_factory
    from app.services.ops.source_health import source_health_report
    from app.services.ops.status import system_status
    from app.services.ops.worker_lock import worker_status

    settings = load_settings(settings_path, project_root=ROOT)
    engine = create_db_engine(settings)
    factory = make_session_factory(engine)
    out: dict = {"ts": _now()}
    try:
        ws = worker_status(settings)
        rec = (ws or {}).get("record") or {}
        out["worker"] = {
            **ws,
            "pid": rec.get("pid"),
            "rounds": rec.get("rounds"),
            "heartbeat_at": rec.get("heartbeat_at"),
            "last_run_at": rec.get("last_run_at"),
            "last_scans": rec.get("last_scans"),
        }
    except Exception as exc:
        out["worker_error"] = str(exc)[:200]
    try:
        with factory() as s:
            out["system"] = system_status(s)
            out["source_health"] = source_health_report(s, window_hours=24)
    except Exception as exc:
        out["db_error"] = str(exc)[:200]
    finally:
        engine.dispose()
    # 观测起点只读
    obs = ROOT / "data" / "daily_usage" / "OBSERVATION.json"
    if obs.exists():
        try:
            out["observation"] = json.loads(obs.read_text(encoding="utf-8"))
        except Exception:
            out["observation"] = None
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="data/daily_usage/config.yaml")
    ap.add_argument("--interval", type=int, default=900, help="采样间隔秒（默认 15min）")
    ap.add_argument("--duration", type=int, default=72 * 3600, help="总时长秒（默认 72h）")
    ap.add_argument("--log", default="data/daily_usage/logs/72h_samples.jsonl")
    args = ap.parse_args()

    log_path = ROOT / args.log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    n = 0
    print(f"[72h-monitor] start={_now()} interval={args.interval}s log={log_path}")
    while time.time() - start < args.duration:
        try:
            rec = sample_once(args.config)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            w = rec.get("worker") or {}
            print(f"[{_now()}] #{n} rounds={w.get('rounds')} hb={w.get('heartbeat_at')}")
        except Exception as exc:
            print(f"[{_now()}] sample_error {exc}")
        time.sleep(args.interval)
    print(f"[72h-monitor] done samples={n}")


if __name__ == "__main__":
    main()
