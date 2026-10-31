"""网络故障注入（应用层）：socket 解析失败 → 来源 failed → 恢复 ok。

不断整机网；不需管理员；向日葵不受影响。
信任边界：信任 httpx/env 的反面是 trust_env=False，故用 socket 层注入。
"""

from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "daily_usage" / "logs" / "net_sim_test.jsonl"


def main() -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from app.adapters.html_fetcher import HttpxFetchAdapter
    from app.config import load_settings
    from app.db.session import create_db_engine, make_session_factory
    from app.services.ops.source_health import source_health_report

    settings = load_settings("data/daily_usage/config.yaml", project_root=ROOT)
    eng = create_db_engine(settings)
    factory = make_session_factory(eng)

    def counters() -> dict:
        with factory() as s:
            return source_health_report(s, window_hours=24).get("counters") or {}

    def log(phase: str, **kw) -> None:
        rec = {"phase": phase, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **kw}
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(json.dumps(rec, ensure_ascii=False))

    adapter = HttpxFetchAdapter(settings)

    async def fetch(url: str):
        return await adapter.fetch(url)

    import asyncio

    # 0) 基线
    log("before", counters=counters())

    # 1) 注入 DNS 失败（模拟断网）
    real_gai = socket.getaddrinfo

    def blocked_gai(*a, **k):
        raise socket.gaierror("SIMULATED_NETWORK_DOWN")

    socket.getaddrinfo = blocked_gai
    try:
        r1 = asyncio.run(fetch("https://flynext.hk/"))
        log(
            "blocked",
            fetch_ok=bool(getattr(r1, "ok", False)),
            error=getattr(r1, "error_code", None) or getattr(r1, "message", "")[:120],
            counters=counters(),
        )
    finally:
        socket.getaddrinfo = real_gai

    # 2) 恢复后应能成功（若外网可达）
    try:
        r2 = asyncio.run(fetch("https://flynext.hk/"))
        log(
            "recovered",
            fetch_ok=bool(getattr(r2, "ok", False)),
            error=getattr(r2, "error_code", None),
            status=getattr(r2, "status_code", None),
            counters=counters(),
        )
    except Exception as exc:
        log("recovered_error", error=str(exc)[:200], counters=counters())

    eng.dispose()
    print("DONE")


if __name__ == "__main__":
    main()
