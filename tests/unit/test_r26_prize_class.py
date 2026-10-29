"""R26：奖品类别、聚合主办方。"""

from __future__ import annotations

from app.adapters.html_fetcher import parse_raffle_label
from app.core.ids import new_id
from app.models import Campaign, Organizer, Source
from app.services.discovery.service import materialize_raffle_candidates
from sqlalchemy import select


def test_non_travel_prize_not_flight_giveaway():
    sig = parse_raffle_label(
        "Win a new iPhone 15 Pro Giveaway",
        page_url="https://example.org/c1",
    )
    assert sig is not None
    assert "flight_giveaway" not in sig.deal_types
    assert "prize_other" in sig.deal_types


def test_travel_prize_is_flight_giveaway():
    sig = parse_raffle_label(
        "Win a free trip to Tokyo vacation package",
        page_url="https://example.org/c2",
    )
    assert sig is not None
    assert "flight_giveaway" in sig.deal_types


def test_aggregator_organizer_has_no_official_domain(db):
    src = Source(
        id=new_id(),
        name="某聚合站",
        base_url="https://agg.example.org/",
        kind="community",
        module="raffle",
        status="active",
    )
    db.add(src)
    db.flush()
    from app.adapters.base import ParsedSignal

    n = materialize_raffle_candidates(
        db,
        src,
        [
            ParsedSignal(
                title="Win a free trip to Tokyo",
                raw_claim_text="Win a free trip to Tokyo",
                url="https://agg.example.org/x",
                deal_types=["flight_giveaway"],
                confidence="low",
            )
        ],
    )
    db.commit()
    assert n == 1
    org = db.scalar(select(Organizer).where(Organizer.name.like("聚合线索%")))
    assert org is not None
    assert org.official_domain is None
    camp = db.scalar(select(Campaign).order_by(Campaign.created_at_utc.desc()).limit(1))
    assert camp is not None
    assert camp.category == "flight_giveaway"
