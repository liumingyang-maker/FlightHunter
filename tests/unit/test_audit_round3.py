"""第三轮审核 P0/P1 回归（ea0650ea 反例）。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from app.config import Settings
from app.core.errors import ErrorCode, FlightHunterError
from app.core.ids import new_id
from app.core.url_safety import resolve_and_assert_public_host
from app.models import Campaign, CampaignRound, Organizer
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


def test_keywords_without_rules_link_not_verified(db):
    """正文出现 Official Rules 字样但无同源细则链接 → needs_review。"""
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
        "Official Rules and eligibility apply.</p></body></html>"
    )
    complete_verify_from_html(db, r, html, source_url="https://example.org/campaign")
    db.commit()
    assert r.verify_status == "needs_review"


def test_missing_organizer_domain_not_verified(db):
    org = Organizer(id=new_id(), name="O")  # 无 official_domain
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
        '<a href="/rules">Official Rules</a></p></body></html>'
    )
    complete_verify_from_html(db, r, html, source_url="https://example.org/campaign")
    db.commit()
    assert r.verify_status == "needs_review"


def test_no_inventory_no_urgent_verified(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.fare.service._provider_whitelist",
        lambda settings=None: {"authorized_provider"},
    )
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="t",
            raw_claim_text="c",
            origin_airport="CKG",
            destination_airport="NRT",
            reported_total=1500,
            party_size=2,
            deal_types=["flash_sale"],
        ),
    )
    db.flush()
    watch = create_fare_watch(db, FareWatchCreate(name="w", origin_airports=["CKG"], adults=2))
    db.flush()
    record_quote(
        db,
        deal_id=deal.id,
        watch_id=watch.id,
        provider="authorized_provider",
        party_size=2,
        total_price=3200,
        origin="CKG",
        destination="NRT",
        depart_date=date(2027, 5, 10),
        taxes_included=True,
        quote_expiry_utc=datetime.now(UTC) + timedelta(hours=6),
        availability_confirmed=False,  # 库存未确认
    )
    db.flush()
    matches = match_watch_to_deals(db, watch)
    db.flush()
    alert = evaluate_alerts_for_match(db, matches[0], watch=watch)
    db.commit()
    assert alert.alert_level != "urgent_verified"


def test_usd_currency_blocks_urgent(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.fare.service._provider_whitelist",
        lambda settings=None: {"authorized_provider"},
    )
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="t",
            raw_claim_text="c",
            origin_airport="CKG",
            destination_airport="NRT",
            party_size=2,
            deal_types=["flash_sale"],
        ),
    )
    db.flush()
    watch = create_fare_watch(db, FareWatchCreate(name="w", origin_airports=["CKG"], adults=2))
    db.flush()
    q = record_quote(
        db,
        deal_id=deal.id,
        watch_id=watch.id,
        provider="authorized_provider",
        party_size=2,
        total_price=400,
        currency="USD",
        origin="CKG",
        destination="NRT",
        depart_date=date(2027, 5, 10),
        taxes_included=True,
        quote_expiry_utc=datetime.now(UTC) + timedelta(hours=6),
        availability_confirmed=True,
    )
    # 强制写 currency（record_quote 默认 CNY）
    q.currency = "USD"
    db.flush()
    matches = match_watch_to_deals(db, watch)
    db.flush()
    alert = evaluate_alerts_for_match(db, matches[0], watch=watch)
    db.commit()
    assert alert.alert_level != "urgent_verified"


def test_full_trusted_quote_urgent(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.fare.service._provider_whitelist",
        lambda settings=None: {"authorized_provider"},
    )
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="t",
            raw_claim_text="c",
            origin_airport="CKG",
            destination_airport="NRT",
            reported_total=1500,
            party_size=2,
            deal_types=["flash_sale"],
        ),
    )
    db.flush()
    watch = create_fare_watch(db, FareWatchCreate(name="w", origin_airports=["CKG"], adults=2))
    db.flush()
    record_quote(
        db,
        deal_id=deal.id,
        watch_id=watch.id,
        provider="authorized_provider",
        party_size=2,
        total_price=3200,
        origin="CKG",
        destination="NRT",
        depart_date=date(2027, 5, 10),
        taxes_included=True,
        baggage_included=True,
        quote_expiry_utc=datetime.now(UTC) + timedelta(hours=6),
        availability_confirmed=True,
    )
    db.flush()
    matches = match_watch_to_deals(db, watch)
    db.flush()
    alert = evaluate_alerts_for_match(db, matches[0], watch=watch)
    db.commit()
    assert alert.alert_level == "urgent_verified"


def test_dns_private_resolution_blocked(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        # 模拟公网域名解析到 127.0.0.1
        import socket

        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("127.0.0.1", 0),
            )
        ]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(FlightHunterError) as ei:
        resolve_and_assert_public_host("evil.example.com")
    assert ei.value.code == ErrorCode.URL_NOT_PUBLIC


def test_shopping_event_cannot_override_redeem(db, settings: Settings):
    """购物券 redeem=6月、event=5月、行程5月 → 不得 usable。"""
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
    offer = create_benefit_offer(
        db,
        BenefitOfferCreate(
            organizer_name="店",
            title="购物券",
            category="shopping_discount",
            country_codes=["JP"],
            date_certainty="confirmed_for_dates",
            redemption_window=LocalWindow(
                starts_at_local=datetime(2027, 6, 1),
                ends_at_local=datetime(2027, 6, 30),
                timezone="Asia/Tokyo",
            ),
            event_window=LocalWindow(
                starts_at_local=datetime(2027, 5, 1),
                ends_at_local=datetime(2027, 5, 31),
                timezone="Asia/Tokyo",
            ),
        ),
    )
    db.flush()
    matches = rematch_trip_benefits(db, trip)
    db.commit()
    m = next(x for x in matches if x.offer_id == offer.id)
    assert m.state != "usable"


def test_robots_403_allow(monkeypatch):
    import asyncio

    from app.adapters.html_fetcher import HttpxFetchAdapter

    adapter = HttpxFetchAdapter(Settings())

    class FakeResp:
        status_code = 403
        headers: dict = {}
        content = b""

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url, **kwargs):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def response():
                yield await self.get(url, **kwargs)

            return response()

        async def get(self, url, **kwargs):
            return FakeResp()

    # 允许 DNS
    import socket

    def fake_gai(*a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_gai)
    monkeypatch.setattr("app.adapters.html_fetcher.httpx.AsyncClient", lambda **k: FakeClient())
    result = asyncio.run(adapter.fetch("https://example.org/campaign"))
    assert result.ok is False
    # 403 robots 不应阻止抓取正文
    assert result.ok or result.error_code != "SOURCE_FETCH_DENIED"
