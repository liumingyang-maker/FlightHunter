"""调度接入真实发现 + RSS 机票过滤 + min_spend 结构化。"""

from __future__ import annotations

import json
from datetime import date

from app.config import Settings
from app.core.ids import new_id
from app.db.session import ensure_default_sources
from app.models import Source
from app.scheduler.jobs import run_due_scans
from app.schemas.domain import TripCreate
from app.services.trips.service import create_trip
from sqlalchemy import select


def test_scheduler_uses_discovery_by_default(db, settings: Settings, monkeypatch):
    """到期扫描默认调用 run_discovery（不访问外网时用 fake adapter）。"""
    from app.adapters.base import FetchResult, ParsedSignal, SourceAdapter

    class Fake(SourceAdapter):
        async def fetch(self, url: str) -> FetchResult:
            return FetchResult(
                ok=True,
                url=url,
                status_code=200,
                text="<html><a href='/d'>特价机票 CKG NRT 999元</a></html>",
                content_hash="h",
                final_url=url,
            )

        def parse(self, text: str, *, url: str):
            return [
                ParsedSignal(
                    title="特价机票 CKG NRT 999元",
                    raw_claim_text="特价机票 CKG NRT 999元",
                    url="https://example.org/d",
                    origin_airport="CKG",
                    destination_airport="NRT",
                    reported_total=999,
                    deal_types=["flash_sale"],
                    confidence="low",
                )
            ]

    monkeypatch.setattr("app.services.discovery.service.adapter_for", lambda s, st: Fake())
    ensure_default_sources(db, settings)
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="sched",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=False,
        ),
    )
    db.commit()
    # 强制到期
    from app.models import TripScanSubscription

    for sub in db.scalars(
        select(TripScanSubscription).where(TripScanSubscription.trip_id == trip.id)
    ).all():
        sub.next_run_at = None
        sub.task_type = "fare_monitor" if sub.task_type == "fare_monitor" else sub.task_type
    db.commit()

    runs = run_due_scans(db, settings, dry_run=False, limit=10)
    db.commit()
    assert runs
    # 至少一个 completed/partial 的真实发现
    assert any(r.status in ("completed", "partial") for r in runs)
    from app.models import FareDealSignal

    assert db.scalars(select(FareDealSignal)).first() is not None


def test_rss_fare_filters_news(monkeypatch):
    class E:
        def __init__(self, title, summary, link):
            self.title = title
            self.summary = summary
            self.link = link

    class Feed:
        entries = [
            E("美股收盘快讯", "市场", "https://x/1"),
            E("重庆东京特价机票 999元", "机票促销 CKG NRT", "https://x/2"),
        ]

    monkeypatch.setattr("app.adapters.rss.feedparser.parse", lambda t: Feed())
    from app.adapters.rss import RssAdapter
    from app.config import Settings as S

    items = RssAdapter(S()).parse("<feed/>", url="https://example.org/rss")
    assert all("美股" not in s.title for s in items)
    assert any("999" in (s.raw_claim_text or "") or s.reported_total for s in items)


def test_min_spend_structured(db):
    from app.adapters.html_fetcher import parse_trip_label
    from app.services.discovery.service import materialize_trip_offer

    sig = parse_trip_label("满100元减20元优惠券", page_url="https://example.org/c")
    assert sig is not None
    src = Source(
        id=new_id(),
        name="s",
        base_url="https://example.org/",
        kind="community",
        module="trip",
        status="active",
    )
    db.add(src)
    db.flush()
    offer = materialize_trip_offer(db, src, sig, country_code="JP")
    db.commit()
    assert offer is not None
    cond = json.loads(offer.conditions or "{}")
    assert cond.get("minimum_spend") == 100.0
    assert offer.face_value_min == 20.0
