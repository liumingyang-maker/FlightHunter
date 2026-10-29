"""Trip 服务测试。"""

from __future__ import annotations

from datetime import date

import pydantic
import pytest
from app.config import Settings
from app.core.errors import TripDateInvalid
from app.models import TripScanSubscription
from app.schemas.domain import BenefitOfferCreate, TripCreate, TripSegmentIn, TripUpdate
from app.services.benefits.service import create_benefit_offer
from app.services.trips.service import create_trip, rematch_trip_benefits, update_trip
from sqlalchemy import select


def test_create_trip_rejects_invalid_dates(db, settings: Settings):
    with pytest.raises((TripDateInvalid, pydantic.ValidationError)):
        create_trip(
            db,
            settings,
            TripCreate(
                label="坏行程",
                destination_country_code="JP",
                local_start_date=date(2027, 5, 20),
                local_end_date=date(2027, 5, 10),
                timezone="Asia/Tokyo",
            ),
        )


def test_create_trip_registers_scans(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="日本行程",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=False,
            segments=[
                TripSegmentIn(
                    country_code="JP",
                    city_code="TYO",
                    start_date=date(2027, 5, 10),
                    end_date=date(2027, 5, 15),
                    timezone="Asia/Tokyo",
                )
            ],
        ),
    )
    db.commit()
    assert trip.scan_registered is True
    subs = db.scalars(
        select(TripScanSubscription).where(TripScanSubscription.trip_id == trip.id)
    ).all()
    types = {s.task_type for s in subs}
    assert "benefit_discovery" in types
    assert "fare_monitor" in types
    assert all(s.enabled for s in subs)


def test_rematch_does_not_wipe_claims(db, settings: Settings):
    from app.models import BenefitClaim

    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="匹配行程",
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
            organizer_name="商店",
            title="全国券",
            category="shopping_discount",
            official_url="https://example.org/o",
            country_codes=["JP"],
            date_certainty="unconfirmed",
        ),
    )
    from app.core.ids import new_id

    claim = BenefitClaim(
        id=new_id(),
        offer_id=offer.id,
        account_scope_key="local",
        profile_scope="p1",
        issuance_period_key="once",
        idempotency_key="k1",
        status="claimed",
        receipt_reference="R1",
    )
    db.add(claim)
    db.flush()
    matches = rematch_trip_benefits(db, trip)
    db.commit()
    assert len(matches) >= 1
    still = db.get(BenefitClaim, claim.id)
    assert still is not None
    assert still.status == "claimed"


def test_update_trip_rematches(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="可变行程",
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
            organizer_name="大阪商店",
            title="大阪限定券",
            category="shopping_discount",
            country_codes=["JP"],
            city_codes=["OSA"],
            date_certainty="unconfirmed",
        ),
    )
    db.flush()
    update_trip(
        db,
        settings,
        trip.id,
        TripUpdate(
            segments=[
                TripSegmentIn(
                    country_code="JP",
                    city_code="OSA",
                    start_date=date(2027, 5, 16),
                    end_date=date(2027, 5, 20),
                    timezone="Asia/Tokyo",
                )
            ]
        ),
    )
    db.commit()
    from app.models import TripBenefitMatch

    m = db.scalar(
        select(TripBenefitMatch).where(
            TripBenefitMatch.trip_id == trip.id,
            TripBenefitMatch.offer_id == offer.id,
        )
    )
    assert m is not None
    assert m.state in ("usable", "maybe_usable", "not_usable")
