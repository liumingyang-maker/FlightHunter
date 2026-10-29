"""Trip 领域服务：创建/更新/重匹配/扫描注册。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import NotFoundError, TripDateInvalid
from app.core.ids import new_id, sha256_text
from app.core.state import TripMatchState
from app.core.timeutils import ensure_valid_date_range, overlaps
from app.models import (
    BenefitOffer,
    BenefitReminder,
    Trip,
    TripBenefitMatch,
    TripScanSubscription,
    TripSegment,
)
from app.schemas.domain import TripCreate, TripSegmentIn, TripUpdate


def _segment_to_model(trip_id: str, seg: TripSegmentIn) -> TripSegment:
    return TripSegment(
        id=new_id(),
        trip_id=trip_id,
        country_code=seg.country_code.upper(),
        city_code=seg.city_code.upper() if seg.city_code else None,
        city_name=seg.city_name,
        start_date=seg.start_date,
        end_date=seg.end_date,
        timezone=seg.timezone,
    )


def create_trip(session: Session, settings: Settings, payload: TripCreate) -> Trip:
    try:
        ensure_valid_date_range(payload.local_start_date, payload.local_end_date)
    except ValueError as exc:
        raise TripDateInvalid(str(exc)) from exc

    for seg in payload.segments:
        if seg.end_date < seg.start_date:
            raise TripDateInvalid(f"分段日期无效: {seg.start_date} ~ {seg.end_date}")
        # 分段应落在行程总日期内（允许等于）
        if seg.end_date < payload.local_start_date or seg.start_date > payload.local_end_date:
            raise TripDateInvalid(
                f"分段 {seg.start_date}~{seg.end_date} 超出行程范围",
                details={
                    "trip": [
                        payload.local_start_date.isoformat(),
                        payload.local_end_date.isoformat(),
                    ]
                },
            )

    trip = Trip(
        id=new_id(),
        label=payload.label,
        destination_country_code=payload.destination_country_code.upper(),
        local_start_date=payload.local_start_date,
        local_end_date=payload.local_end_date,
        timezone=payload.timezone,
        traveler_profile_ids=json.dumps(payload.traveler_profile_ids),
        interests=json.dumps(payload.interests),
        created_from=payload.created_from,
        demo_only=payload.demo_only,
        notification_policy=payload.notification_policy,
        allow_unannounced_watch=payload.allow_unannounced_watch,
        scan_registered=False,
    )
    session.add(trip)
    session.flush()
    for seg in payload.segments:
        session.add(_segment_to_model(trip.id, seg))

    if settings.trip_monitoring.auto_register_on_trip_save and not payload.demo_only:
        register_trip_scans(session, settings, trip)
    elif payload.demo_only:
        # demo 行程也登记订阅但不自动执行真实抓取
        register_trip_scans(session, settings, trip, enabled=False)

    session.flush()
    rematch_trip_benefits(session, trip)
    session.flush()
    return trip


def register_trip_scans(
    session: Session,
    settings: Settings,
    trip: Trip,
    *,
    enabled: bool | None = None,
) -> list[TripScanSubscription]:
    """按 Trip 创建可恢复订阅；幂等。"""
    active = settings.trip_monitoring.enabled and (enabled if enabled is not None else True)
    groups = [trip.destination_country_code]
    # 分段中的额外国家
    segs = session.scalars(select(TripSegment).where(TripSegment.trip_id == trip.id)).all()
    for seg in segs:
        if seg.country_code not in groups:
            groups.append(seg.country_code)

    created: list[TripScanSubscription] = []
    for group in groups:
        for task_type, interval in (
            ("benefit_discovery", settings.trip_benefits.daily_discovery_interval_hours),
            (
                "fare_monitor",
                max(1, settings.airfare_radar.publicly_shared_deals_scan_minutes // 60),
            ),
        ):
            policy_hash = sha256_text(f"{group}|{task_type}|v1")
            existing = session.scalar(
                select(TripScanSubscription).where(
                    TripScanSubscription.trip_id == trip.id,
                    TripScanSubscription.source_group == group,
                    TripScanSubscription.task_type == task_type,
                    TripScanSubscription.policy_hash == policy_hash,
                )
            )
            if existing is None:
                sub = TripScanSubscription(
                    id=new_id(),
                    trip_id=trip.id,
                    source_group=group,
                    task_type=task_type,
                    policy_hash=policy_hash,
                    enabled=active
                    and (
                        task_type != "fare_monitor"
                        or settings.trip_monitoring.auto_attach_fare_watch_to_new_trip
                    ),
                    interval_hours=interval,
                )
                session.add(sub)
                created.append(sub)
    trip.scan_registered = True
    trip.scan_status = "idle" if active else "paused"
    session.flush()
    return created


def update_trip(session: Session, settings: Settings, trip_id: str, payload: TripUpdate) -> Trip:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在", details={"trip_id": trip_id})

    if payload.label is not None:
        trip.label = payload.label
    if payload.timezone is not None:
        trip.timezone = payload.timezone
    if payload.traveler_profile_ids is not None:
        trip.traveler_profile_ids = json.dumps(payload.traveler_profile_ids)
    if payload.interests is not None:
        trip.interests = json.dumps(payload.interests)
    if payload.archived is not None:
        trip.archived = payload.archived

    start = payload.local_start_date or trip.local_start_date
    end = payload.local_end_date or trip.local_end_date
    try:
        ensure_valid_date_range(start, end)
    except ValueError as exc:
        raise TripDateInvalid(str(exc)) from exc
    trip.local_start_date = start
    trip.local_end_date = end

    if payload.segments is not None:
        session.query(TripSegment).filter(TripSegment.trip_id == trip.id).delete()
        for seg in payload.segments:
            session.add(_segment_to_model(trip.id, seg))
        session.flush()

    if settings.trip_monitoring.auto_scan_on_trip_change:
        register_trip_scans(session, settings, trip)

    session.flush()
    rematch_trip_benefits(session, trip)
    # 变更行程只改变匹配，不清空领取记录
    session.flush()
    return trip


def rematch_trip_benefits(session: Session, trip: Trip) -> list[TripBenefitMatch]:
    """根据行程日期/国家/城市重算 BenefitOffer 匹配。"""
    offers = session.scalars(
        select(BenefitOffer).where(BenefitOffer.offer_status != "withdrawn")
    ).all()

    segments = session.scalars(select(TripSegment).where(TripSegment.trip_id == trip.id)).all()

    results: list[TripBenefitMatch] = []
    for offer in offers:
        countries = json.loads(offer.country_codes or "[]")
        cities = json.loads(offer.city_codes or "[]")

        # 国家匹配
        country_ok = (
            not countries
            or trip.destination_country_code in countries
            or any(s.country_code in countries for s in segments)
        )

        # 城市匹配：有城市限制时，需分段城市命中；无城市则 maybe
        city_match = "unknown"
        if cities:
            seg_cities = {s.city_code for s in segments if s.city_code}
            if seg_cities & set(cities):
                city_match = "match"
            elif not seg_cities:
                city_match = "unknown_city"
            else:
                city_match = "no_match"
        else:
            city_match = "nationwide"

        # 日期匹配：使用期/领取期/活动期任一覆盖行程
        date_match = _date_overlap(trip, offer)

        if not country_ok or city_match == "no_match":
            state = TripMatchState.NOT_USABLE
            reasons = []
            if not country_ok:
                reasons.append("COUNTRY_NOT_MATCHED")
            if city_match == "no_match":
                reasons.append("CITY_NOT_MATCHED")
            category = "sustained_watch"
        elif date_match == "confirmed":
            if city_match == "unknown_city":
                state = TripMatchState.MAYBE_USABLE
                reasons = ["CITY_UNKNOWN"]
            else:
                state = TripMatchState.USABLE
                reasons = []
            category = "claimable"
        elif date_match == "unconfirmed":
            state = TripMatchState.MAYBE_USABLE
            reasons = ["BENEFIT_DATES_UNCONFIRMED"]
            category = "sustained_watch"
        else:
            state = TripMatchState.NOT_USABLE
            reasons = ["BENEFIT_TIME_NOT_MATCHED"]
            category = "wallet" if offer.claim_method == "PUBLIC_DISPLAY" else "sustained_watch"

        if offer.claim_method == "PUBLIC_DISPLAY" and state != TripMatchState.NOT_USABLE:
            category = "wallet"

        existing = session.scalar(
            select(TripBenefitMatch).where(
                TripBenefitMatch.trip_id == trip.id,
                TripBenefitMatch.offer_id == offer.id,
            )
        )
        now = datetime.now(UTC)
        if existing:
            existing.state = state.value
            existing.match_category = category
            existing.reason_codes = json.dumps(reasons)
            existing.evaluated_at_utc = now
            results.append(existing)
        else:
            m = TripBenefitMatch(
                id=new_id(),
                trip_id=trip.id,
                offer_id=offer.id,
                state=state.value,
                match_category=category,
                eligibility_state="needs_review",
                reason_codes=json.dumps(reasons),
                evaluated_at_utc=now,
            )
            session.add(m)
            results.append(m)
    session.flush()
    return results


def _date_overlap(trip: Trip, offer: BenefitOffer) -> str:
    """返回 confirmed / unconfirmed / none。null 窗口 = unconfirmed。"""
    windows = [
        (offer.redeem_starts_at_local, offer.redeem_ends_at_local),
        (offer.event_starts_at_local, offer.event_ends_at_local),
        (offer.claim_opens_at_local, offer.claim_closes_at_local),
        (offer.booking_opens_at_local, offer.booking_closes_at_local),
    ]
    known_any = False
    for start, end in windows:
        if start is None and end is None:
            continue
        known_any = True
        s = start.date() if start else trip.local_start_date
        e = end.date() if end else trip.local_end_date
        if overlaps(trip.local_start_date, trip.local_end_date, s, e):
            return "confirmed"
    if not known_any and offer.date_certainty in (
        "unconfirmed",
        "not_yet_announced",
        "historical_reference",
    ):
        return "unconfirmed"
    if offer.date_certainty == "confirmed_for_dates" and not known_any:
        return "unconfirmed"
    return "none"


def create_reminder(
    session: Session,
    *,
    offer_id: str,
    kind: str,
    fire_at_utc: datetime,
    trip_id: str | None = None,
) -> BenefitReminder:
    content_hash = sha256_text(f"{offer_id}|{kind}|{fire_at_utc.isoformat()}|{trip_id}")
    existing = session.scalar(
        select(BenefitReminder).where(
            BenefitReminder.offer_id == offer_id,
            BenefitReminder.content_hash == content_hash,
            BenefitReminder.cancelled == False,  # noqa: E712
        )
    )
    if existing:
        return existing
    r = BenefitReminder(
        id=new_id(),
        offer_id=offer_id,
        trip_id=trip_id,
        kind=kind,
        fire_at_utc=fire_at_utc,
        content_hash=content_hash,
    )
    session.add(r)
    session.flush()
    return r
