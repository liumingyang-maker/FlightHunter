"""机票雷达：信号、匹配、成本、风险、报价分层。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.models import FareRiskEvidence
from app.schemas.domain import FareSignalImport, FareWatchCreate
from app.services.fare.service import (
    compute_cost_breakdown,
    create_fare_watch,
    evaluate_alerts_for_match,
    historical_median_for_route,
    import_signal,
    mark_booked,
    match_watch_to_deals,
    record_quote,
)
from sqlalchemy import select


def test_import_signal_does_not_create_quote(db):
    deal, signal = import_signal(
        db,
        FareSignalImport(
            title="神价爆料",
            raw_claim_text="CKG NRT 999元起",
            origin_airport="CKG",
            destination_airport="NRT",
            reported_total=999,
            currency="CNY",
            party_size=2,
            taxes_included=True,
            deal_types=["flash_sale"],
            original_url="https://example.org/s/1",
        ),
    )
    db.commit()
    assert deal.status == "price_unconfirmed"
    assert signal.signal_status == "parsed"
    from app.models import FareQuote

    quotes = db.scalars(select(FareQuote).where(FareQuote.deal_id == deal.id)).all()
    assert quotes == []


def test_hidden_city_is_high_risk(db):
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="甩尾票",
            raw_claim_text="hidden city",
            origin_airport="PVG",
            destination_airport="LHR",
            deal_types=["hidden_city"],
        ),
    )
    db.commit()
    assert deal.risk_tier == "high_risk"
    risks = db.scalars(select(FareRiskEvidence).where(FareRiskEvidence.deal_id == deal.id)).all()
    codes = {r.risk_code for r in risks}
    assert "HIDDEN_CITY" in codes


def test_watch_match_requires_opt_in_for_error_fare(db):
    import_signal(
        db,
        FareSignalImport(
            title="BUG票",
            raw_claim_text="error fare",
            origin_airport="CKG",
            destination_airport="BKK",
            travel_window_start=date(2027, 5, 1),
            travel_window_end=date(2027, 5, 10),
            deal_types=["error_fare"],
            reported_total=50,
            party_size=2,
        ),
    )
    db.flush()
    watch = create_fare_watch(
        db,
        FareWatchCreate(
            name="不接受错价",
            origin_airports=["CKG"],
            destination_scope="any",
            depart_window_start=date(2027, 5, 1),
            depart_window_end=date(2027, 5, 31),
            adults=2,
            accept_error_fares=False,
        ),
    )
    db.flush()
    matches = match_watch_to_deals(db, watch)
    db.commit()
    # 可以匹配但 reason 应提示需 opt-in，且 risk_match 标注
    target = [m for m in matches]
    assert len(target) >= 1
    reasons = set()
    for m in target:
        reasons.update(__import__("json").loads(m.reason_codes or "[]"))
    assert "ERROR_FARE_NEEDS_OPT_IN" in reasons


def test_party_size_mismatch_reason(db):
    import_signal(
        db,
        FareSignalImport(
            title="单人价爆料",
            raw_claim_text="1人",
            origin_airport="TFU",
            destination_airport="ICN",
            party_size=1,
            reported_total=800,
            currency="CNY",
            deal_types=["flash_sale"],
        ),
    )
    db.flush()
    watch = create_fare_watch(
        db,
        FareWatchCreate(
            name="双人",
            origin_airports=["TFU"],
            destination_scope="any",
            adults=2,
        ),
    )
    db.flush()
    matches = match_watch_to_deals(db, watch)
    db.commit()
    codes = set()
    for m in matches:
        codes.update(__import__("json").loads(m.reason_codes or "[]"))
    assert "PARTY_SIZE_MISMATCH" in codes


def test_alert_never_verified_without_quote(db):
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="仅爆料",
            raw_claim_text="x",
            origin_airport="CKG",
            destination_airport="KIX",
            reported_total=1200,
            party_size=2,
            deal_types=["flash_sale"],
        ),
    )
    db.flush()
    watch = create_fare_watch(
        db,
        FareWatchCreate(name="w", origin_airports=["CKG"], adults=2),
    )
    db.flush()
    matches = match_watch_to_deals(db, watch)
    db.flush()
    alert = evaluate_alerts_for_match(db, matches[0], watch=watch)
    db.commit()
    assert alert is not None
    assert alert.alert_level != "urgent_verified"


def test_cost_breakdown_unknown_fields():
    b = compute_cost_breakdown(base_ticket_total=2000, taxes=300)
    assert b.total_min == 2300
    assert "positioning" in b.unknown_fields
    assert b.total_max is None  # 未知项存在时不给假精确上界
    b2 = compute_cost_breakdown(
        base_ticket_total=2000,
        taxes=300,
        positioning=500,
        baggage=0,
        overnight=0,
        other=0,
    )
    assert b2.total_min == 2800
    assert b2.total_max == 2800


def test_history_median_insufficient_samples(db):
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="样本不足",
            raw_claim_text="x",
            origin_airport="CKG",
            destination_airport="NRT",
        ),
    )
    db.flush()
    median, n = historical_median_for_route(db, "CKG", "NRT", min_samples=5)
    assert median is None
    assert n == 0

    for i in range(6):
        record_quote(
            db,
            deal_id=deal.id,
            watch_id=None,
            provider="test_provider",
            party_size=2,
            total_price=1000 + i * 10,
            origin="CKG",
            destination="NRT",
        )
    db.flush()
    median, n = historical_median_for_route(db, "CKG", "NRT", min_samples=5)
    assert n == 6
    assert median is not None


def test_mark_booked_user_reported(db):
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="t", raw_claim_text="c", origin_airport="CKG", destination_airport="SIN"
        ),
    )
    db.commit()
    mark_booked(db, deal.id, method="user_reported")
    db.commit()
    assert db.get(type(deal), deal.id).booking_status == "user_reported"


def test_quote_observed_vs_signal(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.fare.service._provider_whitelist",
        lambda: {"authorized_demo"},
    )
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="有报价",
            raw_claim_text="c",
            origin_airport="CKG",
            destination_airport="HND",
            reported_total=1500,
            party_size=2,
        ),
    )
    db.flush()
    watch = create_fare_watch(db, FareWatchCreate(name="w2", origin_airports=["CKG"], adults=2))
    db.flush()
    record_quote(
        db,
        deal_id=deal.id,
        watch_id=watch.id,
        provider="authorized_demo",
        party_size=2,
        total_price=3200,
        origin="CKG",
        destination="HND",
        taxes_included=True,
        baggage_included=False,
        quote_expiry_utc=datetime.now(UTC) + timedelta(hours=12),
    )
    db.flush()
    matches = match_watch_to_deals(db, watch)
    db.commit()
    m = matches[0]
    assert m.price_status == "observed"
    assert m.net_cost_min == 3200
