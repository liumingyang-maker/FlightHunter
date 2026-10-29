"""第四轮审核边界回归（I5/I9/I10）。"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from app.config import Settings
from app.core.ids import new_id
from app.models import Campaign, CampaignRound, Organizer, TripSegment
from app.schemas.common import LocalWindow
from app.schemas.domain import (
    BenefitOfferCreate,
    FareSignalImport,
    FareWatchCreate,
    TripCreate,
)
from app.services.benefits.service import create_benefit_offer
from app.services.fare.service import (
    create_fare_watch,
    evaluate_alerts_for_match,
    import_signal,
    match_watch_to_deals,
    record_quote,
)
from app.services.trips.service import create_trip, rematch_trip_benefits
from app.services.verify.service import complete_verify_from_html


def _trusted_full_quote(db, watch, deal, *, depart: date, monkeypatch):
    monkeypatch.setattr(
        "app.services.fare.service._provider_whitelist",
        lambda settings=None: {"authorized_provider"},
    )
    record_quote(
        db,
        deal_id=deal.id,
        watch_id=watch.id,
        provider="authorized_provider",
        party_size=watch.adults,
        total_price=2000,
        origin=deal.origin,
        destination=deal.destination,
        depart_date=depart,
        taxes_included=True,
        baggage_included=True,
        quote_expiry_utc=datetime.now(UTC) + timedelta(hours=6),
        availability_confirmed=True,
    )
    db.flush()


def test_quote_outside_watch_window_not_urgent(db, monkeypatch):
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="t",
            raw_claim_text="c",
            origin_airport="CKG",
            destination_airport="NRT",
            party_size=2,
            deal_types=["flash_sale"],
            travel_window_start=date(2027, 5, 1),
            travel_window_end=date(2027, 5, 31),
        ),
    )
    db.flush()
    watch = create_fare_watch(
        db,
        FareWatchCreate(
            name="may",
            origin_airports=["CKG"],
            adults=2,
            depart_window_start=date(2027, 5, 10),
            depart_window_end=date(2027, 5, 30),
        ),
    )
    db.flush()
    _trusted_full_quote(db, watch, deal, depart=date(2027, 6, 20), monkeypatch=monkeypatch)
    matches = match_watch_to_deals(db, watch)
    db.flush()
    alert = evaluate_alerts_for_match(db, matches[0], watch=watch)
    db.commit()
    assert alert.alert_level != "urgent_verified"
    reasons = json.loads(matches[0].reason_codes or "[]")
    assert "QUOTE_OUTSIDE_WATCH_WINDOW" in reasons


def test_city_before_arrival_not_usable(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="jp",
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
            title="大阪活动",
            category="event",
            country_codes=["JP"],
            city_codes=["KIX"],
            date_certainty="confirmed_for_dates",
            event_window=LocalWindow(
                starts_at_local=datetime(2027, 5, 15),
                ends_at_local=datetime(2027, 5, 15),
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


def test_rules_label_without_body_not_verified(db):
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
        '<a href="/page-that-is-not-terms">Official Rules</a></p></body></html>'
    )
    complete_verify_from_html(db, r, html, source_url="https://example.org/campaign")
    db.commit()
    assert r.verify_status == "needs_review"


def test_redirect_dns_private_not_requested(monkeypatch):
    import asyncio
    import socket

    from app.adapters.html_fetcher import HttpxFetchAdapter

    adapter = HttpxFetchAdapter(Settings())
    called: list[str] = []

    class Ok:
        status_code = 200
        text = "User-agent: *\nAllow: /\n"
        content = b"User-agent: *\nAllow: /\n"
        headers: dict = {}

    class Redir:
        status_code = 302
        headers = {"location": "https://evil-rebind.example/admin"}
        content = b""

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kwargs):
            called.append(url)
            if "evil-rebind" in url:
                raise AssertionError("must not request private rebind host: " + url)
            if url.endswith("/robots.txt"):
                return Ok()
            return Redir()

    def fake_gai(host, *a, **k):
        if "evil-rebind" in host:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_gai)
    monkeypatch.setattr("app.adapters.html_fetcher.httpx.AsyncClient", lambda **k: FakeClient())
    result = asyncio.run(adapter.fetch("https://example.org/campaign"))
    assert result.ok is False
    assert result.error_code == "URL_NOT_PUBLIC"
    assert all("evil-rebind" not in u for u in called)
