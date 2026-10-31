"""模拟断网/恢复：HTTP(S)_PROXY 指向死端口，观察来源失败后恢复。

不断整机网，不需管理员；向日葵不受影响。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
CONFIG = "data/daily_usage/config.yaml"
LOG = ROOT / "data" / "daily_usage" / "logs" / "net_sim_test.jsonl"


def run_cli(extra_env: dict | None = None, timeout: int = 180) -> tuple[int, str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    if extra_env:
        env.update(extra_env)
    r = subprocess.run(
        [str(PY), "-B", "-m", "app.cli", "discover", "--execute", "--module", "fare", "--limit", "2"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out[-2000:]


def health() -> dict:
    r = subprocess.run(
        [str(PY), "-B", "-c",
         "import sys;sys.path.insert(0,'.');"
         "from app.config import load_settings;"
         "from app.db.session import create_db_engine,make_session_factory;"
         "from app.services.ops.source_health import source_health_report;"
         "import json;s=load_settings('data/daily_usage/config.yaml',project_root='.');"
         "e=create_db_engine(s);f=make_session_factory(e);"
         "print(json.dumps(source_health_report(f(),window_hours=24).get('counters'),ensure_ascii=False));e.dispose()"],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    try:
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception:
        return {"raw": (r.stdout or "")[-500:], "err": (r.stderr or "")[-300:]}


def log(rec: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False))


def main() -> None:
    import datetime

    now = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    # 1) 正常
    h0 = health()
    log({"phase": "before", "ts": now, "counters": h0})

    # 2) 断网（死代理）
    dead = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "ALL_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}
    code, out = run_cli(dead, timeout=90)
    h1 = health()
    log({"phase": "blocked", "ts": now, "exit": code, "counters": h1, "cli_tail": out[-500:]})

    # 3) 恢复
    code2, out2 = run_cli(None, timeout=90)
    h2 = health()
    log({"phase": "recovered", "ts": now, "exit": code2, "counters": h2, "cli_tail": out2[-500:]})

    print("DONE", "blocked_failed_delta", (h1.get("round_failed") or 0) - (h0.get("round_failed") or 0))


if __name__ == "__main__":
    main()
