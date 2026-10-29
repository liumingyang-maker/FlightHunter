"""审核 P0/P1 回归测试：修复前必须失败，修复后必须通过。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from app.config import Settings
from app.core.errors import ErrorCode, FlightHunterError
from app.core.ids import new_id
from app.core.url_safety import assert_public_http_url, is_blocked_hostname
from app.models import (
    Campaign,
    CampaignRound,
    Organizer,
    Trip,
)
from app.scheduler.jobs import claim_due_subscriptions, run_due_scans
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
from sqlalchemy import select

# ---------- P0-01 ----------


def _round(db, official_url="https://example.org/campaign") -> CampaignRound:
    org = Organizer(id=new_id(), name="O")
    db.add(org)
    db.flush()
    camp = Campaign(id=new_id(), organizer_id=org.id, program_key=f"k{new_id()[:8]}", name="C")
    db.add(camp)
    db.flush()
    r = CampaignRound(
        id=new_id(),
        campaign_id=camp.id,
        edition_key="e",
        title="T",
        organizer_name="O",
        official_url=official_url,
        verify_status="candidate",
    )
    db.add(r)
    db.flush()
    return r


def test_p001_cannot_verify_from_official_url_when_html_is_other_site(db):
    r = _round(db, official_url="https://official-airline.example.org/campaign")
    html = (
        "<html><head><title>Win a trip Official Looking</title></head>"
        "<body><p>No purchase necessary. Closes 2027-03-01.</p></body></html>"
    )
    # source_url 与 official 不同源
    complete_verify_from_html(db, r, html, source_url="https://totally-different.example.com/x")
    db.commit()
    assert r.verify_status == "needs_review"


def test_p001_cannot_verify_without_date_clue(db):
    r = _round(db)
    html = (
        "<html><head><title>Official Giveaway</title></head>"
        "<body><p>No purchase necessary to enter this promotion.</p></body></html>"
    )
    complete_verify_from_html(db, r, html)
    db.commit()
    assert r.verify_status == "needs_review"


def test_p001_can_verify_same_site_with_purchase_and_date(db):
    r = _round(db, official_url="https://example.org/campaign")
    html = (
        "<html><head><title>Official Flight Giveaway</title></head>"
        "<body><p>No purchase necessary. Entry closes 2027-03-01.</p></body></html>"
    )
    complete_verify_from_html(db, r, html, source_url="https://example.org/campaign")
    db.commit()
    assert r.verify_status == "verified"


def test_p001_captcha_does_not_block_official_verified(db):
    """CAPTCHA 影响自动化，不影响官方真实性核实（审核修订）。"""
    r = _round(db, official_url="https://example.org/campaign")
    html = (
        "<html><head><title>Official Flight Giveaway</title></head>"
        "<body><p>No purchase necessary. Entry closes 2027-03-01.</p>"
        "<p>Please complete the captcha to continue.</p></body></html>"
    )
    complete_verify_from_html(db, r, html, source_url="https://example.org/campaign")
    db.commit()
    assert r.verify_status == "verified"
    assert r.has_captcha is True


def test_p001_captcha_downgrades_auto_policy(db):
    r = _round(db, official_url="https://example.org/campaign")
    r.automation_policy = "allowed"
    db.flush()
    html = (
        "<html><head><title>Official Flight Giveaway</title></head>"
        "<body><p>No purchase necessary. Entry closes 2027-03-01.</p>"
        "<div>captcha</div></body></html>"
    )
    complete_verify_from_html(db, r, html, source_url="https://example.org/campaign")
    db.commit()
    assert r.verify_status == "verified"
    assert r.automation_policy == "forbidden"


# ---------- P0-02 ----------


def test_p002_untrusted_quote_not_urgent_verified(db):
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="爆料",
            raw_claim_text="x",
            origin_airport="CKG",
            destination_airport="NRT",
            reported_total=999,
            party_size=2,
            deal_types=["flash_sale"],
        ),
    )
    db.flush()
    watch = create_fare_watch(db, FareWatchCreate(name="w", origin_airports=["CKG"], adults=2))
    db.flush()
    # 过期 + 人数不符 + 非授权 provider
    record_quote(
        db,
        deal_id=deal.id,
        watch_id=watch.id,
        provider="community",
        party_size=1,
        total_price=999,
        origin="CKG",
        destination="NRT",
        quote_expiry_utc=datetime.now(UTC) - timedelta(hours=1),
    )
    db.flush()
    matches = match_watch_to_deals(db, watch)
    db.flush()
    alert = evaluate_alerts_for_match(db, matches[0], watch=watch)
    db.commit()
    assert alert is not None
    assert alert.alert_level != "urgent_verified"


def test_p002_trusted_fresh_matching_quote_can_be_urgent(db):
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="报价",
            raw_claim_text="x",
            origin_airport="CKG",
            destination_airport="HND",
            reported_total=1500,
            party_size=2,
            deal_types=["flash_sale"],
        ),
    )
    db.flush()
    watch = create_fare_watch(db, FareWatchCreate(name="w2", origin_airports=["CKG"], adults=2))
    db.flush()
    record_quote(
        db,
        deal_id=deal.id,
        watch_id=watch.id,
        provider="authorized_provider",
        party_size=2,
        total_price=3200,
        origin="CKG",
        destination="HND",
        quote_expiry_utc=datetime.now(UTC) + timedelta(hours=6),
    )
    db.flush()
    matches = match_watch_to_deals(db, watch)
    db.flush()
    alert = evaluate_alerts_for_match(db, matches[0], watch=watch)
    db.commit()
    assert alert is not None
    assert alert.alert_level == "urgent_verified"


# ---------- P0-03 ----------


def test_p003_sqlite_naive_datetime_compare(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="时区行程",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=False,
        ),
    )
    db.commit()
    from app.models import TripScanSubscription

    sub = db.scalars(
        select(TripScanSubscription).where(TripScanSubscription.trip_id == trip.id)
    ).first()
    assert sub is not None
    # 模拟 SQLite 读回 naive
    sub.next_run_at = datetime(2020, 1, 1)  # naive past
    db.commit()
    # 重新从 DB 读
    db.expire_all()
    sub2 = db.get(TripScanSubscription, sub.id)
    assert sub2 is not None
    ready = claim_due_subscriptions(db)
    assert any(s.id == sub2.id for s in ready)


# ---------- P0-04 ----------


def test_p004_no_adapter_is_blocked_not_completed(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="无适配器",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=False,
        ),
    )
    db.commit()
    runs = run_due_scans(db, settings, dry_run=False, limit=5)
    db.commit()
    assert runs
    assert all(r.status == "blocked" for r in runs)
    db.expire_all()
    refreshed = db.get(Trip, trip.id)
    assert refreshed is not None
    assert refreshed.last_benefit_scan_at is None
    assert refreshed.scan_status == "degraded"


# ---------- P1 URL ----------


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.1/enter",
        "http://10.0.0.1/x",
        "http://169.254.169.254/latest/meta-data",
        "http://127.0.0.1/x",
        "http://[::1]/x",
        "http://localhost/x",
        "http://metadata.google.internal/x",
        "http://foo.local/x",
    ],
)
def test_p1_private_urls_blocked(url: str):
    with pytest.raises(FlightHunterError) as ei:
        assert_public_http_url(url)
    assert ei.value.code == ErrorCode.URL_NOT_PUBLIC


def test_p1_hostname_blocklist():
    assert is_blocked_hostname("192.168.0.10")
    assert is_blocked_hostname("169.254.169.254")
    assert not is_blocked_hostname("www.smzdm.com")


# ---------- P1 trip dates ----------


def test_p1_claim_month_differs_from_use_month(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="五月行程",
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
            title="五月领六月用",
            category="shopping_discount",
            country_codes=["JP"],
            date_certainty="confirmed_for_dates",
            claim_window=LocalWindow(
                opens_at_local=datetime(2027, 5, 1),
                closes_at_local=datetime(2027, 5, 20),
                timezone="Asia/Tokyo",
            ),
            redemption_window=LocalWindow(
                starts_at_local=datetime(2027, 6, 1),
                ends_at_local=datetime(2027, 6, 30),
                timezone="Asia/Tokyo",
            ),
        ),
    )
    db.flush()
    matches = rematch_trip_benefits(db, trip)
    db.commit()
    m = next(x for x in matches if x.offer_id == offer.id)
    assert m.state != "usable"
    # 可提前领但不可在行程中使用
    assert m.state in ("maybe_usable", "not_usable")


# ---------- P1 cost ----------


def test_p1_optional_cost_unknown_no_upper_bound():
    from app.services.fare.service import compute_cost_breakdown

    b = compute_cost_breakdown(base_ticket_total=2000, taxes=300, positioning=500, baggage=0)
    assert b.total_min == 2800
    assert b.total_max is None
