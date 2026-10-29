"""第五轮审核边界：类别时间窗、细则占位、manual_only。"""

from __future__ import annotations

import json
from datetime import date, datetime

from app.config import Settings
from app.core.ids import new_id
from app.db.session import ensure_default_sources
from app.models import Campaign, CampaignRound, Organizer, Source, TripSegment
from app.schemas.common import LocalWindow
from app.schemas.domain import BenefitOfferCreate, TripCreate
from app.services.benefits.service import create_benefit_offer
from app.services.trips.service import create_trip, rematch_trip_benefits
from app.services.verify.service import complete_verify_from_html
from sqlalchemy import select


def test_shopping_redeem_and_event_city_must_use_redeem(db, settings: Settings):
    """购物券：redeem 5/15 + event 5/22，城停 5/20–25 → 不得 usable。"""
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="t",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=True,
        ),
    )
    db.add(
        TripSegment(
            id=new_id(),
            trip_id=trip.id,
            country_code="JP",
            city_code="KIX",
            start_date=date(2027, 5, 20),
            end_date=date(2027, 5, 25),
            timezone="Asia/Tokyo",
        )
    )
    db.flush()
    offer = create_benefit_offer(
        db,
        BenefitOfferCreate(
            organizer_name="店",
            title="购物",
            category="shopping_discount",
            country_codes=["JP"],
            city_codes=["KIX"],
            date_certainty="confirmed_for_dates",
            redemption_window=LocalWindow(
                starts_at_local=datetime(2027, 5, 15),
                ends_at_local=datetime(2027, 5, 15),
                timezone="Asia/Tokyo",
            ),
            event_window=LocalWindow(
                starts_at_local=datetime(2027, 5, 22),
                ends_at_local=datetime(2027, 5, 22),
                timezone="Asia/Tokyo",
            ),
        ),
    )
    db.flush()
    matches = rematch_trip_benefits(db, trip)
    db.commit()
    m = next(x for x in matches if x.offer_id == offer.id)
    assert m.state != "usable"
    assert "CITY_STAY_DATES_MISMATCH" in json.loads(m.reason_codes or "[]")


def test_event_category_ignores_redeem_for_city(db, settings: Settings):
    """活动类：event 5/15 + redeem 5/22，城停 5/20–25 → 不得 usable。"""
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="t2",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=True,
        ),
    )
    db.add(
        TripSegment(
            id=new_id(),
            trip_id=trip.id,
            country_code="JP",
            city_code="KIX",
            start_date=date(2027, 5, 20),
            end_date=date(2027, 5, 25),
            timezone="Asia/Tokyo",
        )
    )
    db.flush()
    offer = create_benefit_offer(
        db,
        BenefitOfferCreate(
            organizer_name="会",
            title="活动",
            category="event",
            country_codes=["JP"],
            city_codes=["KIX"],
            date_certainty="confirmed_for_dates",
            event_window=LocalWindow(
                starts_at_local=datetime(2027, 5, 15),
                ends_at_local=datetime(2027, 5, 15),
                timezone="Asia/Tokyo",
            ),
            redemption_window=LocalWindow(
                starts_at_local=datetime(2027, 5, 22),
                ends_at_local=datetime(2027, 5, 22),
                timezone="Asia/Tokyo",
            ),
        ),
    )
    db.flush()
    matches = rematch_trip_benefits(db, trip)
    db.commit()
    m = next(x for x in matches if x.offer_id == offer.id)
    assert m.state != "usable"


def test_eligibility_tbd_not_verified(db):
    org = Organizer(id=new_id(), name="O", official_domain="example.org")
    db.add(org)
    db.flush()
    camp = Campaign(id=new_id(), organizer_id=org.id, program_key="pk", name="C")
    db.add(camp)
    db.flush()
    r = CampaignRound(
        id=new_id(),
        campaign_id=camp.id,
        edition_key="e",
        title="Win flights",
        organizer_name="O",
        official_url="https://example.org/campaign",
        verify_status="candidate",
    )
    db.add(r)
    db.flush()
    html = (
        "<html><head><title>Win a Trip Giveaway</title></head>"
        "<body><p>Enter to win. No purchase necessary. Closes 2027-03-01. "
        "<h2>Official Rules</h2><p>Eligibility: TBD</p>"
        '<a href="/rules">Official Rules</a></p></body></html>'
    )
    complete_verify_from_html(db, r, html, source_url="https://example.org/campaign")
    db.commit()
    assert r.verify_status == "needs_review"


def test_manual_only_source_not_scheduled(db, settings: Settings):
    ensure_default_sources(db, settings)
    src = db.scalars(select(Source)).first()
    assert src is not None
    src.status = "manual_only"
    db.commit()
    import asyncio

    from app.services.discovery.service import run_discovery

    results = asyncio.run(run_discovery(db, settings, module="fare", dry_run=True, limit=20))
    assert all(r.get("status") != "dry_run" or r.get("source_id") != src.id for r in results)
    assert all(r.get("source_id") != src.id or r.get("status") == "manual_only" for r in results)
