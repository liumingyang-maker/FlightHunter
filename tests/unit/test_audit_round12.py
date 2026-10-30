"""第十二轮：dry/execute 幂等分离、到期过滤、千分位。"""

from __future__ import annotations

from datetime import date, timedelta

from app.adapters.html_fetcher import parse_trip_label
from app.config import Settings
from app.core.timeutils import utc_now
from app.models import TripScanSubscription
from app.scheduler.jobs import claim_due_subscriptions, run_subscription_scan
from app.schemas.domain import TripCreate
from app.services.trips.service import create_trip
from sqlalchemy import select


def test_dry_run_does_not_block_execute(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="t",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=False, confirmed=True,
        ),
    )
    db.commit()
    sub = db.scalars(
        select(TripScanSubscription).where(TripScanSubscription.trip_id == trip.id)
    ).first()
    assert sub is not None
    sub.next_run_at = None
    db.commit()

    def _blocked_fetch(s):
        return {"status": "blocked", "message": "no adapter"}

    dry = run_subscription_scan(db, settings, sub, dry_run=True, fetch_fn=_blocked_fetch)
    db.commit()
    assert dry.dry_run is True

    # dry 后 execute 仍应执行（不同幂等键）
    exe = run_subscription_scan(db, settings, sub, dry_run=False, fetch_fn=_blocked_fetch)
    db.commit()
    assert exe.dry_run is False
    assert exe.id != dry.id


def test_due_filter_before_starving(db, settings: Settings):
    """未到期订阅不应挡住已到期订阅被选中。"""
    t1 = create_trip(
        db,
        settings,
        TripCreate(
            label="due",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=False, confirmed=True,
        ),
    )
    t2 = create_trip(
        db,
        settings,
        TripCreate(
            label="future",
            destination_country_code="FR",
            local_start_date=date(2027, 6, 1),
            local_end_date=date(2027, 6, 10),
            timezone="Europe/Paris",
            demo_only=False, confirmed=True,
        ),
    )
    db.commit()
    subs = db.scalars(select(TripScanSubscription)).all()
    future = [s for s in subs if s.trip_id == t2.id]
    due = [s for s in subs if s.trip_id == t1.id]
    for s in future:
        s.next_run_at = utc_now() + timedelta(hours=48)
    for s in due:
        s.next_run_at = None
    db.commit()
    ready = claim_due_subscriptions(db, limit=1)
    assert ready
    assert all(s.trip_id == t1.id for s in ready)


def test_thousand_separator_min_spend():
    sig = parse_trip_label("满1,000元减100元", page_url="https://example.org/x")
    assert sig is not None
    assert sig.reported_total == 100.0
    assert "min_spend=1000" in sig.raw_claim_text

