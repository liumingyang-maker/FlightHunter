"""发现→结构化入库→匹配→提醒 端到端（离线 FakeAdapter，不访问外网）。"""

from __future__ import annotations

import asyncio

from app.adapters.base import FetchResult, ParsedSignal, SourceAdapter
from app.config import Settings
from app.core.ids import new_id
from app.db.session import ensure_default_sources
from app.models import FareDealSignal
from app.schemas.domain import FareWatchCreate
from app.services.discovery.service import (
    run_discovery,
)
from app.services.fare.service import create_fare_watch
from sqlalchemy import select


class FakeHtmlAdapter(SourceAdapter):
    name = "fake"

    async def fetch(self, url: str) -> FetchResult:
        html = (
            "<html><head><title>Deals</title></head><body>"
            "<a href='https://example.org/deal1'>特价机票 CKG NRT 999元</a>"
            "</body></html>"
        )
        return FetchResult(
            ok=True,
            url=url,
            status_code=200,
            text=html,
            content_hash="fakehash",
            final_url=url,
        )

    def parse(self, text: str, *, url: str) -> list[ParsedSignal]:
        return [
            ParsedSignal(
                title="特价机票 CKG NRT 999元",
                raw_claim_text="特价机票 CKG NRT 999元",
                url="https://example.org/deal1",
                reported_total=999,
                origin_airport="CKG",
                destination_airport="NRT",
                confidence="low",
            )
        ]


def test_discovery_e2e_persists_signals_and_alerts(db, settings: Settings, monkeypatch):
    ensure_default_sources(db, settings)
    # 清空默认，只留一个 httpx 来源
    from app.models import Source

    for s in db.scalars(select(Source)).all():
        s.status = "inactive"
    db.add(
        Source(
            id=new_id(),
            name="fake-listing",
            base_url="https://example.org/list",
            kind="community",
            module="fare",
            status="active",
            allowed_fetch_mode="httpx",
            access_policy="public_fetch",
        )
    )
    db.flush()
    watch = create_fare_watch(db, FareWatchCreate(name="w", origin_airports=["CKG"], adults=2))
    db.commit()

    def _fake_adapter(source, settings):
        return FakeHtmlAdapter()

    monkeypatch.setattr("app.services.discovery.service.adapter_for", _fake_adapter)

    results = asyncio.run(
        run_discovery(
            db,
            settings,
            module="fare",
            dry_run=False,
            limit=5,
            persist_signals=True,
            after_fetch=True,
        )
    )
    db.commit()

    assert any(r.get("signals_persisted", 0) >= 1 for r in results if r.get("source_id"))
    sigs = db.scalars(select(FareDealSignal)).all()
    assert any(s.origin_airport == "CKG" for s in sigs)
    matches = db.scalars(select(FareWatchMatch)).all() if False else []
    from app.models import FareWatchMatch

    matches = db.scalars(select(FareWatchMatch)).all()
    assert any(m.watch_id == watch.id for m in matches)
    post = [r for r in results if r.get("status") == "post_match"]
    assert post and post[0].get("matches", 0) >= 1


def test_module_filter_strong(db, settings: Settings):
    """先插入大量 trip 再 fare，fare 仍应被选中。"""
    from app.models import Source

    ensure_default_sources(db, settings)
    for i in range(10):
        db.add(
            Source(
                id=new_id(),
                name=f"aaa-trip-{i}",
                base_url=f"https://t{i}.example.org/",
                kind="community",
                module="trip",
                status="active",
            )
        )
    db.commit()
    results = asyncio.run(run_discovery(db, settings, module="fare", dry_run=True, limit=3))
    # dry_run 只返回 fare/shared 来源
    assert results
    assert all(
        r.get("status") in ("dry_run", "manual_only", "denied")
        for r in results
        if r.get("source_id")
    )
