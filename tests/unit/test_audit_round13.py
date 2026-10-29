"""第十三轮：公平到期、国家证据、源冷却。"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from app.config import Settings
from app.core.timeutils import utc_now
from app.db.session import ensure_default_sources
from app.models import Source, TripScanSubscription
from app.scheduler.jobs import claim_due_subscriptions
from app.schemas.domain import TripCreate
from app.services.trips.service import create_trip
from sqlalchemy import select


def test_200_plus_due_not_starved(db, settings: Settings):
    """208 条订阅中仅最后一条到期时仍能被 claim 到。"""
    t = create_trip(
        db,
        settings,
        TripCreate(
            label="many",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=False,
        ),
    )
    db.commit()
    base = db.scalars(
        select(TripScanSubscription).where(TripScanSubscription.trip_id == t.id)
    ).all()
    assert base
    fut = utc_now() + timedelta(hours=99)
    # 复制大量未到期
    for i in range(207):
        s = TripScanSubscription(
            id=f"00000000-0000-0000-0000-{i:012d}"[:36],
            trip_id=t.id,
            source_group="JP",
            task_type="fare_monitor",
            policy_hash=f"p{i}",
            enabled=True,
            next_run_at=fut,
        )
        # id 必须 uuid 格式
        from app.core.ids import new_id

        s.id = new_id()
        db.add(s)
    for s in base:
        s.next_run_at = None
    db.commit()
    ready = claim_due_subscriptions(db, limit=1)
    assert ready
    assert all(s.next_run_at is None or s.next_run_at <= utc_now() for s in ready)


def test_shared_source_not_forced_country(db, settings: Settings):
    ensure_default_sources(db, settings)
    from app.services.discovery.service import run_discovery

    # 共享源 country_code=None
    results = asyncio.run(
        run_discovery(db, settings, module="fare", dry_run=True, limit=5, country_code="JP")
    )
    # dry_run 不写 offer；仅验证无异常
    assert results


def test_source_cooldown_skips_recent(db, settings: Settings, monkeypatch):
    ensure_default_sources(db, settings)
    src = db.scalars(select(Source)).first()
    assert src is not None
    src.last_fetch_at = utc_now()
    src.fetch_interval_hours = 24
    db.commit()
    fetched: list[str] = []

    async def _fake_fetch(session, settings, source, **kwargs):
        fetched.append(source.id)
        return {"source_id": source.id, "status": "ok"}

    monkeypatch.setattr("app.services.discovery.service.fetch_source", _fake_fetch)
    from app.services.discovery.service import run_discovery

    asyncio.run(
        run_discovery(
            db,
            settings,
            module="fare",
            dry_run=False,
            limit=10,
            enforce_cooldown=True,
            after_fetch=False,
            persist_signals=False,
        )
    )
    assert src.id not in fetched
