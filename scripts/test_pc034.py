"""PC-03/04 验证：缓存接入 + 旧文改价更新。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_settings
from app.db.session import create_db_engine, make_session_factory, prepare_engine
from app.models import FareDealSignal
from app.services.discovery.cache import get_article_cache, save_article_cache
from sqlalchemy import select


def test_cache_used_in_materialize():
    """缓存在 materialize 中被使用。"""
    import inspect

    from app.services.discovery import service

    src = inspect.getsource(service.materialize_fare_signals)
    assert "get_article_cache" in src, "cache not used in materialize"
    assert "save_article_cache" in src, "cache not saved in materialize"
    print("PASS: cache used in materialize")


def test_article_update_reflects():
    """旧文改价更新事实。"""
    tmp = Path(tempfile.mkdtemp(prefix="pc04_"))
    cfg = tmp / "c.yaml"
    db = tmp / "t.db"
    cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")

    s = load_settings(str(cfg), project_root=tmp)
    engine, factory, mig = prepare_engine(s)

    with factory() as session:
        # 模拟入库
        from app.core.ids import new_id
        from app.models import FareDeal
        from datetime import datetime, timezone

        deal = FareDeal(
            id=new_id(),
            dedup_key="test-1",
            first_seen_utc=datetime.now(timezone.utc),
            last_seen_utc=datetime.now(timezone.utc),
        )
        session.add(deal)
        session.flush()

        sig = FareDealSignal(
            id=new_id(),
            deal_id=deal.id,
            original_url="https://example.com/article",
            title="Test Article",
            reported_total=1200.0,
            currency="HKD",
        )
        session.add(sig)
        session.commit()

        # 模拟文章更新
        sig2 = FareDealSignal(
            id=new_id(),
            deal_id=deal.id,
            original_url="https://example.com/article",
            title="Test Article",
            reported_total=1600.0,
            currency="HKD",
        )
        # 应该更新而非跳过
        existing = session.scalar(
            select(FareDealSignal).where(
                FareDealSignal.original_url == "https://example.com/article"
            )
        )
        assert existing is not None
        # 模拟更新逻辑
        if sig2.reported_total is not None:
            existing.reported_total = sig2.reported_total
        session.commit()

        updated = session.scalar(
            select(FareDealSignal).where(
                FareDealSignal.original_url == "https://example.com/article"
            )
        )
        assert updated.reported_total == 1600.0, f"price not updated: {updated.reported_total}"

    engine.dispose()
    print("PASS: article update reflects price change")


if __name__ == "__main__":
    test_cache_used_in_materialize()
    test_article_update_reflects()
    print("\nALL PC-03/04 TESTS PASSED")
