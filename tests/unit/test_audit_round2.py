"""第二轮审核 P0/P1 回归测试（对照 GPT 复现脚本）。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from app.config import Settings
from app.core.errors import ErrorCode, FlightHunterError
from app.core.ids import new_id
from app.core.url_safety import assert_public_http_url, is_safe_local_next
from app.models import Campaign, CampaignRound, EntryAttempt, Organizer
from app.schemas.common import LocalWindow
from app.schemas.domain import (
    BenefitOfferCreate,
    FareSignalImport,
    FareWatchCreate,
    TripCreate,
)
from app.services.benefits.service import create_benefit_offer
from app.services.entry.service import finish_submit_unknown
from app.services.fare.service import (
    create_fare_watch,
    evaluate_alerts_for_match,
    import_signal,
    match_watch_to_deals,
    record_quote,
)
from app.services.trips.service import create_trip, rematch_trip_benefits
from app.services.verify.service import complete_verify_from_html
from app.web.auth import (
    create_session_cookie_value,
    revoke_session_cookie,
    verify_session_cookie,
)


def _round(db, official_url: str = "https://example.org/campaign") -> CampaignRound:
    org = Organizer(id=new_id(), name="O", official_domain="example.org")
    db.add(org)
    db.flush()
    camp = Campaign(id=new_id(), organizer_id=org.id, program_key=f"k{new_id()[:8]}", name="C")
    db.add(camp)
    db.flush()
    r = CampaignRound(
        id=new_id(),
        campaign_id=camp.id,
        edition_key="e",
        title="Win flights",
        organizer_name="O",
        official_url=official_url,
        verify_status="candidate",
    )
    db.add(r)
    db.flush()
    return r


def test_newsletter_index_not_verified(db):
    r = _round(db)
    html = (
        "<html><head><title>Example news index</title></head>"
        "<body><p>No purchase necessary to subscribe to a newsletter. "
        "Updated 2027-03-01.</p></body></html>"
    )
    complete_verify_from_html(db, r, html, source_url="https://example.org/campaign")
    db.commit()
    assert r.verify_status == "needs_review"


def test_campaign_page_with_rules_can_verify(db):
    r = _round(db)
    html = (
        "<html><head><title>Win a Trip Official Giveaway</title></head>"
        "<body><p>Enter to win. No purchase necessary. "
        "Entry closes 2027-03-01. "
        "<h2>Official Rules</h2><p>Eligibility: residents only.</p>"
        '<a href="/official-rules">Official Rules</a></p></body></html>'
    )
    complete_verify_from_html(db, r, html, source_url="https://example.org/campaign")
    db.commit()
    assert r.verify_status == "verified"


def test_fake_provider_quote_not_urgent_verified(db):
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="Sample community lead",
            raw_claim_text="x",
            origin_airport="CKG",
            destination_airport="NRT",
            reported_total=999,
            party_size=2,
            deal_types=["flash_sale"],
        ),
    )
    db.flush()
    watch = create_fare_watch(
        db,
        FareWatchCreate(
            name="w",
            origin_airports=["CKG"],
            adults=2,
            max_total_cost_cny=100,
        ),
    )
    db.flush()
    record_quote(
        db,
        deal_id=deal.id,
        watch_id=watch.id,
        provider="totally_unregistered_provider",
        party_size=2,
        total_price=500,
        origin="LAX",
        destination="JFK",
        quote_expiry_utc=None,
        availability_confirmed=False,
    )
    db.flush()
    matches = match_watch_to_deals(db, watch)
    db.flush()
    alert = evaluate_alerts_for_match(db, matches[0], watch=watch)
    db.commit()
    assert alert is not None
    assert alert.alert_level != "urgent_verified"


def test_over_budget_not_urgent_verified(db, monkeypatch):
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
    watch = create_fare_watch(
        db,
        FareWatchCreate(
            name="cheap",
            origin_airports=["CKG"],
            adults=2,
            max_total_cost_cny=100,
        ),
    )
    db.flush()
    record_quote(
        db,
        deal_id=deal.id,
        watch_id=watch.id,
        provider="authorized_provider",
        party_size=2,
        total_price=500,
        origin="CKG",
        destination="NRT",
        quote_expiry_utc=datetime.now(UTC) + timedelta(hours=6),
        depart_date=date(2027, 5, 15),
        taxes_included=True,
        baggage_included=True,
        availability_confirmed=True,
    )
    db.flush()
    matches = match_watch_to_deals(db, watch)
    db.flush()
    alert = evaluate_alerts_for_match(db, matches[0], watch=watch)
    db.commit()
    assert alert is not None
    assert alert.alert_level != "urgent_verified"


def test_trusted_whitelisted_quote_can_urgent(db, monkeypatch):
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
    watch = create_fare_watch(db, FareWatchCreate(name="ok", origin_airports=["CKG"], adults=2))
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
        depart_date=date(2027, 5, 15),
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
    assert alert is not None
    assert alert.alert_level == "urgent_verified"


@pytest.mark.parametrize(
    "host",
    ["2130706433", "0x7f000001", "0177.0.0.1", "127.1", "127.0.0.1"],
)
def test_ssrf_numeric_localhost_blocked(host: str):
    with pytest.raises(FlightHunterError) as ei:
        assert_public_http_url(f"http://{host}/")
    assert ei.value.code == ErrorCode.URL_NOT_PUBLIC


def test_html_fetch_redirect_blocked_before_request(monkeypatch):
    import asyncio

    from app.adapters.html_fetcher import HttpxFetchAdapter

    adapter = HttpxFetchAdapter(Settings())
    called: list[str] = []

    class FakeResp:
        status_code = 302
        headers = {"location": "http://127.0.0.1/admin"}
        content = b""

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kwargs):
            called.append(url)
            if url.endswith("/robots.txt"):

                class R:
                    status_code = 200
                    text = "User-agent: *\nAllow: /\n"

                return R()
            return FakeResp()

    monkeypatch.setattr("app.adapters.html_fetcher.httpx.AsyncClient", lambda **k: FakeClient())
    import socket

    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    result = asyncio.run(adapter.fetch("https://example.org/campaign"))
    assert result.ok is False
    assert result.error_code == "URL_NOT_PUBLIC"
    assert all("127.0.0.1" not in u for u in called)


def test_historical_reference_never_usable(db, settings: Settings):
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
            title="历史参考券",
            category="shopping_discount",
            country_codes=["JP"],
            date_certainty="historical_reference",
            redemption_window=LocalWindow(
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


def test_next_url_open_redirect_blocked():
    assert is_safe_local_next("https://example.invalid/x") == "/"
    assert is_safe_local_next("//evil.com") == "/"
    assert is_safe_local_next("/trips") == "/trips"


def test_cookie_logout_replay_rejected(settings: Settings):
    value = create_session_cookie_value(settings)
    assert verify_session_cookie(value, settings) is True
    assert revoke_session_cookie(value, settings) is True
    assert verify_session_cookie(value, settings) is False


def test_finish_submit_unknown_requires_submitting(db):
    from app.models import Profile

    org = Organizer(id=new_id(), name="O2")
    db.add(org)
    db.flush()
    camp = Campaign(id=new_id(), organizer_id=org.id, program_key="pk", name="C")
    db.add(camp)
    db.flush()
    r = CampaignRound(
        id=new_id(),
        campaign_id=camp.id,
        edition_key="e",
        title="T",
        organizer_name="O2",
        official_url="https://example.org",
    )
    p = Profile(id=new_id(), display_name="A")
    db.add(r)
    db.add(p)
    db.flush()
    att = EntryAttempt(
        id=new_id(),
        round_id=r.id,
        profile_id=p.id,
        participant_scope_key="person:x",
        period_key="e@UTC",
        idempotency_key="k",
        status="confirmed",
    )
    db.add(att)
    db.flush()
    with pytest.raises(FlightHunterError):
        finish_submit_unknown(db, att)
