"""PC-01 验证：20 来源 27h 虚拟时钟，经过 run_discovery 真实调用链。"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_run_discovery_27h_virtual():
    """通过 run_discovery 验证冷却不饿死来源。"""
    from app.config import load_settings
    from app.db.session import create_db_engine, make_session_factory, prepare_engine
    from app.models import Source
    from app.services.discovery.service import run_discovery
    from app.core.ids import new_id

    tmp = Path(tempfile.mkdtemp(prefix="pc01_"))
    cfg = tmp / "config.yaml"
    db = tmp / "test.db"
    cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")

    s = load_settings(str(cfg), project_root=tmp)
    engine, factory, mig = prepare_engine(s)

    # 创建 20 个活跃来源
    with factory() as session:
        for i in range(20):
            session.add(
                Source(
                    id=new_id(),
                    name=f"src-{i:02d}",
                    base_url=f"https://example{i}.com/feed",
                    kind="community",
                    module="fare",
                    status="active",
                    allowed_fetch_mode="rss",
                    access_policy="public_fetch",
                    fetch_interval_hours=24,
                )
            )
        session.commit()

    # 模拟时钟：27 小时，30 分钟间隔
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = now + timedelta(hours=27)

    fetches = 0
    checks = 0
    t = now

    # monkeypatch adapter 为 mock
    from app.services.discovery.fetcher_router import FetcherRouter

    class MockAdapter:
        async def fetch(self, url, headers=None):
            from app.adapters.base import FetchResult

            return FetchResult(
                ok=True, url=url, status_code=200, text="<rss></rss>", content_hash="mock", final_url=url
            )

        def parse(self, text, *, url):
            return []

    original_select = FetcherRouter.select_adapter
    FetcherRouter.select_adapter = lambda self, source: MockAdapter()

    try:
        while t < end:
            checks += 1
            with factory() as session:
                # 手动更新 now 以模拟时钟
                import app.services.discovery.service as svc

                old_utc_now = svc.utc_now
                svc.utc_now = lambda: t
                try:
                    results = asyncio.run(
                        run_discovery(
                            session, s, module="fare", dry_run=False, limit=10, persist_signals=False
                        )
                    )
                    fetched = [
                        r
                        for r in results
                        if r.get("status") not in ("skipped", "failed") and r.get("source_id")
                    ]
                    fetches += len(fetched)
                finally:
                    svc.utc_now = old_utc_now
                # 关键：commit 以持久化 last_attempt_at
                session.commit()
            t += timedelta(minutes=30)
    finally:
        FetcherRouter.select_adapter = original_select

    engine.dispose()

    # 20 来源 * 2 次/来源 = 40 次抓取
    expected = 20 * 2
    print(f"checks={checks} fetches={fetches} expected={expected}")
    assert fetches == expected, f"27h 应抓 {expected} 次，实际 {fetches} 次"
    assert checks == 54, f"27h 应检查 54 次，实际 {checks} 次"
    print("PASS: run_discovery 27h virtual clock")


if __name__ == "__main__":
    test_run_discovery_27h_virtual()
    print("\nALL PC-01 TESTS PASSED")
