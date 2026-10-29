"""主业务冲刺集成测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.config import Settings
from app.schemas.domain import (
    BenefitOfferCreate,
    FareSignalImport,
    FareWatchCreate,
    TripCreate,
)
from app.services.benefits.service import create_benefit_offer, ensure_wallet_saved, generate_guide
from app.services.discovery.service import match_and_alert_fare
from app.services.fare.service import create_fare_watch, import_signal
from app.services.mail.eml_scan import scan_eml_dir
from app.services.ops.status import system_status
from app.services.trips.service import create_trip, rematch_trip_benefits
from sqlalchemy import select


def test_system_status_shape(db, settings: Settings):
    st = system_status(db)
    assert "db" in st
    assert "tasks_24h" in st["db"]


def test_eml_local_candidate(db, settings: Settings, tmp_path: Path):
    eml = tmp_path / "win.eml"
    eml.write_bytes(
        b"From: a@example.org\r\nTo: b@example.org\r\nSubject: \xe6\x81\xad\xe5\x96\x9c\xe4\xb8\xad\xe5\xa5\x96\r\n\r\nYou won!\r\n"
    )
    r = scan_eml_dir(tmp_path)
    assert r["status"] == "ok"
    assert r["candidates"]
    assert r["candidates"][0]["needs_human"] is True


def test_trip_benefit_wallet_guide_flow(db, settings: Settings):
    from datetime import datetime

    from app.schemas.common import LocalWindow

    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="2027日本演示",
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
            organizer_name="演示商店",
            title="免税95折",
            category="shopping_discount",
            claim_method="PUBLIC_DISPLAY",
            country_codes=["JP"],
            date_certainty="confirmed_for_dates",
            redemption_window=LocalWindow(
                starts_at_local=datetime(2027, 5, 1),
                ends_at_local=datetime(2027, 5, 31),
                timezone="Asia/Tokyo",
            ),
        ),
    )
    db.flush()
    matches = rematch_trip_benefits(db, trip)
    m = next(x for x in matches if x.offer_id == offer.id)
    assert m.state in ("usable", "maybe_usable")
    wallet = ensure_wallet_saved(db, offer, None)
    guide = generate_guide(db, offer.id)
    db.commit()
    assert wallet.state in ("saved", "dynamic_app_required")
    assert guide is not None


def test_fare_signal_to_alert_flow(db, settings: Settings):
    deal, _ = import_signal(
        db,
        FareSignalImport(
            title="重庆东京特价",
            raw_claim_text="CKG NRT 特价机票 999元",
            origin_airport="CKG",
            destination_airport="NRT",
            reported_total=999,
            party_size=2,
            deal_types=["flash_sale"],
            original_url="https://example.org/deal1",
        ),
    )
    db.flush()
    create_fare_watch(
        db, FareWatchCreate(name="ckg", origin_airports=["CKG"], adults=2)
    )
    db.commit()
    stats = match_and_alert_fare(db)
    db.commit()
    assert stats["matches"] >= 1
    from app.models import FareAlert

    assert db.scalars(select(FareAlert)).first() is not None


def test_notification_ui_page_api(db, settings: Settings, app_client):
    r = app_client.get("/notifications")
    assert r.status_code == 200
    r2 = app_client.get("/entries")
    assert r2.status_code == 200
