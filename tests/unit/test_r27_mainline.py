"""R27：奖品细分、官方溯源、日本优惠扫描。"""

from __future__ import annotations

from app.adapters.html_fetcher import parse_raffle_label
from app.core.ids import new_id
from app.models import Organizer
from app.services.raffle.provenance import attempt_official_evidence


def test_hotel_not_flight_giveaway():
    sig = parse_raffle_label(
        "Win a luxury hotel stay weekend getaway",
        page_url="https://example.org/h",
    )
    assert sig is not None
    assert "flight_giveaway" not in sig.deal_types
    assert "lodging_or_cruise" in sig.deal_types


def test_airfare_keyword_is_flight():
    sig = parse_raffle_label(
        "Win round-trip airfare to Paris",
        page_url="https://example.org/f",
    )
    assert sig is not None
    assert "flight_giveaway" in sig.deal_types


def test_official_evidence_snapshot(db, settings):
    from app.models import Campaign, CampaignRound

    org = Organizer(id=new_id(), name="O", official_domain=None)
    db.add(org)
    db.flush()
    camp = Campaign(id=new_id(), organizer_id=org.id, program_key="k", name="C")
    db.add(camp)
    db.flush()
    r = CampaignRound(
        id=new_id(),
        campaign_id=camp.id,
        edition_key="e",
        title="Win trip",
        organizer_name="O",
        official_url="https://example.org/nope-unsafe",
        verify_status="candidate",
    )
    db.add(r)
    db.flush()
    import asyncio

    res = asyncio.run(attempt_official_evidence(db, settings, r))
    assert res["ok"] is False
    assert res["reason"] in ("unsafe_url", "fetch_failed", "no_url")
