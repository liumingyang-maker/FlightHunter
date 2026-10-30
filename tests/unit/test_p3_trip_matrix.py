"""P3 行程状态机矩阵：confirm/edit/cancel + 开关组合。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Trip, TripScanSubscription
from app.services.trips import service as tripsvc
from app.schemas.domain import TripCreate, TripSegmentIn, TripUpdate


def _settings(**over):
    from app.config import Settings

    s = Settings()
    for k, v in over.items():
        if hasattr(s.trip_monitoring, k):
            setattr(s.trip_monitoring, k, v)
    s.trip_monitoring.enabled = True
    return s


def _mk_trip(session, confirmed=False, demo=False):
    payload = TripCreate(
        label="t",
        local_start_date=date(2027, 1, 1),
        local_end_date=date(2027, 1, 10),
        destination_country_code="JP",
        timezone="Asia/Tokyo",
        segments=[
            TripSegmentIn(
                start_date=date(2027, 1, 1),
                end_date=date(2027, 1, 10),
                timezone="Asia/Tokyo",
                country_code="JP",
                city_code="OSA",
            )
        ],
        confirmed=confirmed,
        demo_only=demo,
    )
    trip = tripsvc.create_trip(session, _settings(), payload)
    return trip


def _subs(session, trip_id):
    return session.scalars(
        select(TripScanSubscription).where(TripScanSubscription.trip_id == trip_id)
    ).all()


def test_unconfirmed_edit_keeps_subs_disabled():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    s = S()
    settings = _settings()
    trip = _mk_trip(s, confirmed=False)
    tripsvc.register_trip_scans(s, settings, trip, enabled=False)
    s.flush()
    tripsvc.update_trip(s, settings, trip.id, TripUpdate(label="renamed"))
    assert all(not x.enabled for x in _subs(s, trip.id))


def test_confirmed_edit_rescan_off_keeps_enabled():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    s = S()
    settings = _settings(auto_scan_on_trip_change=False, auto_attach_fare_watch_to_new_trip=True)
    trip = _mk_trip(s, confirmed=True)
    tripsvc.register_trip_scans(s, settings, trip)
    s.flush()
    assert any(x.enabled for x in _subs(s, trip.id))
    tripsvc.update_trip(s, settings, trip.id, TripUpdate(label="renamed2"))
    # N-007/R-016：关闭重扫不得禁用已启用订阅
    assert any(x.enabled for x in _subs(s, trip.id))


def test_confirm_respects_fare_watch_off():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    s = S()
    settings = _settings(auto_attach_fare_watch_to_new_trip=False)
    trip = _mk_trip(s, confirmed=False)
    tripsvc.register_trip_scans(s, settings, trip, enabled=False)
    s.flush()
    tripsvc.confirm_trip(s, settings, trip.id)
    subs = _subs(s, trip.id)
    fare = [x for x in subs if x.task_type == "fare_monitor"]
    benefit = [x for x in subs if x.task_type == "benefit_discovery"]
    assert all(not x.enabled for x in fare)
    assert any(x.enabled for x in benefit)


def test_confirm_restores_trip_not_confirmed():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    s = S()
    settings = _settings()
    trip = _mk_trip(s, confirmed=False)
    tripsvc.register_trip_scans(s, settings, trip)
    s.flush()
    for sub in _subs(s, trip.id):
        sub.enabled = False
        sub.paused_reason = "trip_not_confirmed"
    s.flush()
    tripsvc.confirm_trip(s, settings, trip.id)
    assert any(x.enabled and x.paused_reason is None for x in _subs(s, trip.id))


def test_cancel_disables_all():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    s = S()
    settings = _settings()
    trip = _mk_trip(s, confirmed=True)
    tripsvc.register_trip_scans(s, settings, trip)
    s.flush()
    tripsvc.cancel_trip_scans(s, trip.id)
    assert all(not x.enabled for x in _subs(s, trip.id))


def test_demo_cannot_confirm():
    import pytest

    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    s = S()
    settings = _settings()
    trip = _mk_trip(s, demo=True)
    with pytest.raises(ValueError):
        tripsvc.confirm_trip(s, settings, trip.id)
