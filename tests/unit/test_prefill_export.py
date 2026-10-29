"""预填守卫与导出测试。"""

from __future__ import annotations

from datetime import date

import pytest
from app.config import Settings
from app.core.errors import ErrorCode, FlightHunterError, NotFoundError
from app.core.ids import new_id
from app.models import Campaign, CampaignRound, Organizer, Profile
from app.schemas.domain import TripCreate
from app.services.browser.prefill import (
    assert_public_http_url,
    build_prefill_plan,
    plan_to_dict,
)
from app.services.export.service import trip_to_export_dict, trip_to_ics
from app.services.trips.service import create_trip


def test_block_private_url():
    with pytest.raises(FlightHunterError) as ei:
        assert_public_http_url("http://127.0.0.1/enter")
    assert ei.value.code == ErrorCode.URL_NOT_PUBLIC


def test_block_non_http():
    with pytest.raises(FlightHunterError):
        assert_public_http_url("javascript:alert(1)")


def test_prefill_skips_marketing_and_flags_captcha(db):
    org = Organizer(id=new_id(), name="O")
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
        organizer_name="O",
        official_url="https://example.org/enter",
        verify_status="verified",
        automation_policy="unknown",
        has_captcha=True,
        marketing_consent_required=True,
    )
    p = Profile(
        id=new_id(),
        display_name="张三",
        country_of_residence=None,
    )
    db.add(r)
    db.add(p)
    db.flush()
    plan = build_prefill_plan(r, p)
    assert plan.mode == "MANUAL_ONLY"
    assert any("CAPTCHA" in h for h in plan.requires_human)
    assert any(s["field"] == "marketing_consent" for s in plan.skipped)
    d = plan_to_dict(plan)
    assert d["note"]


def test_export_json_and_ics_no_codes(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="导出行程",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=True,
        ),
    )
    db.commit()
    data = trip_to_export_dict(db, trip.id)
    assert data["contains_private_codes"] is False
    assert "private_code_encrypted" not in str(data)
    ics = trip_to_ics(db, trip.id)
    assert "BEGIN:VCALENDAR" in ics
    assert "BEGIN:VEVENT" in ics
    assert "private_code" not in ics


def test_export_missing_trip(db):
    with pytest.raises(NotFoundError):
        trip_to_export_dict(db, "missing-id")
