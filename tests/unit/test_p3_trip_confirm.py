"""P3 行程确认门槛。"""

from __future__ import annotations

from datetime import date

from app.config import Settings
from app.schemas.domain import TripCreate
from app.services.trips.service import cancel_trip_scans, confirm_trip, create_trip


def test_unconfirmed_real_trip_does_not_register_scans(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="未确认日本",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 20),
            timezone="Asia/Tokyo",
            demo_only=False,
            confirmed=False,
        ),
    )
    db.commit()
    assert trip.confirmed is False
    assert trip.scan_registered is False


def test_confirm_trip_starts_scans_and_cancel_stops(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="确认日本",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 20),
            timezone="Asia/Tokyo",
            demo_only=False,
            confirmed=True,
        ),
    )
    db.commit()
    assert trip.confirmed is True
    assert trip.scan_registered is True
    n = cancel_trip_scans(db, trip.id)
    db.commit()
    assert n >= 1
    db.refresh(trip)
    assert trip.archived is True
