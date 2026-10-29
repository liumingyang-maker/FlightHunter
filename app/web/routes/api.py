"""API v1 路由。"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.core.errors import FlightHunterError
from app.core.ids import new_id
from app.core.timeutils import utc_now
from app.models import (
    BenefitOffer,
    CampaignRound,
    FareDeal,
    FareQuote,
    FareWatch,
    Notification,
    Profile,
    Trip,
    WalletItem,
)
from app.schemas.domain import (
    BenefitClaimStart,
    BenefitOfferCreate,
    FareSignalImport,
    FareWatchCreate,
    ProfileCreate,
    TripCreate,
    TripUpdate,
)
from app.web.deps import DbDep, SettingsDep
from app.web.routes.auth import router as auth_router

router = APIRouter()
router.include_router(auth_router)


def _ok(data, request_id: str | None = None):
    return {
        "ok": True,
        "data": data,
        "request_id": request_id or new_id(),
        "server_time_utc": utc_now().isoformat(),
    }


def _trip_dict(t: Trip) -> dict:
    return {
        "id": t.id,
        "label": t.label,
        "destination_country_code": t.destination_country_code,
        "local_start_date": t.local_start_date.isoformat(),
        "local_end_date": t.local_end_date.isoformat(),
        "timezone": t.timezone,
        "demo_only": t.demo_only,
        "archived": t.archived,
        "scan_registered": t.scan_registered,
        "scan_status": t.scan_status,
        "scan_message": t.scan_message,
        "created_at_utc": t.created_at_utc.isoformat() if t.created_at_utc else None,
    }


# ---- Health ----
@router.get("/health")
def health(settings: SettingsDep):
    return _ok({"status": "up", "demo_mode": settings.app.demo_mode})  # type: ignore[attr-defined]


# ---- Profiles ----
@router.post("/profiles")
def create_profile(payload: ProfileCreate, db: DbDep):
    p = Profile(
        id=new_id(),
        display_name=payload.display_name,
        country_of_residence=payload.country_of_residence,
        nationality=payload.nationality,
        date_of_birth=payload.date_of_birth.isoformat() if payload.date_of_birth else None,
        household_id=payload.household_id,
        preferred_departure_airports=json.dumps(payload.preferred_departure_airports),
        preferred_party_size=payload.preferred_party_size,
        max_relocation_cost_cny=(
            str(payload.max_relocation_cost_cny)
            if payload.max_relocation_cost_cny is not None
            else None
        ),
        payment_networks=json.dumps(payload.payment_networks),
        issuing_regions=json.dumps(payload.issuing_regions),
    )
    db.add(p)
    db.commit()
    return _ok({"id": p.id, "display_name": p.display_name})


@router.get("/profiles")
def list_profiles(db: DbDep):
    rows = db.scalars(select(Profile)).all()
    return _ok(
        [
            {
                "id": r.id,
                "display_name": r.display_name,
                "country_of_residence": r.country_of_residence,
                "nationality": r.nationality,
            }
            for r in rows
        ]
    )


# ---- Trips ----
@router.get("/trips")
def list_trips(db: DbDep, demo_only: bool | None = None):
    stmt = select(Trip).order_by(Trip.created_at_utc.desc())
    if demo_only is not None:
        stmt = stmt.where(Trip.demo_only == demo_only)
    rows = db.scalars(stmt).all()
    return _ok([_trip_dict(t) for t in rows])


@router.post("/trips")
def create_trip(payload: TripCreate, db: DbDep, settings: SettingsDep):
    from app.services.trips.service import create_trip as svc_create

    try:
        trip = svc_create(db, settings, payload)  # type: ignore[arg-type]
        db.commit()
    except FlightHunterError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    return _ok(_trip_dict(trip))


@router.patch("/trips/{trip_id}")
def update_trip(trip_id: str, payload: TripUpdate, db: DbDep, settings: SettingsDep):
    from app.services.trips.service import update_trip as svc_update

    try:
        trip = svc_update(db, settings, trip_id, payload)  # type: ignore[arg-type]
        db.commit()
    except FlightHunterError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    return _ok(_trip_dict(trip))


@router.get("/trips/{trip_id}/matches")
def trip_matches(trip_id: str, db: DbDep):
    from app.models import TripBenefitMatch

    trip = db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    rows = db.scalars(select(TripBenefitMatch).where(TripBenefitMatch.trip_id == trip_id)).all()
    return _ok(
        [
            {
                "offer_id": r.offer_id,
                "state": r.state,
                "match_category": r.match_category,
                "eligibility_state": r.eligibility_state,
                "reason_codes": json.loads(r.reason_codes or "[]"),
            }
            for r in rows
        ]
    )


# ---- Benefits ----
@router.get("/benefits")
def list_benefits(db: DbDep, country: str | None = None, limit: int = Query(50, le=200)):
    stmt = select(BenefitOffer).order_by(BenefitOffer.created_at_utc.desc()).limit(limit)
    rows = db.scalars(stmt).all()
    out = []
    for r in rows:
        countries = json.loads(r.country_codes or "[]")
        if country and country.upper() not in [c.upper() for c in countries]:
            continue
        out.append(
            {
                "id": r.id,
                "title": r.title,
                "category": r.category,
                "claim_method": r.claim_method,
                "country_codes": countries,
                "date_certainty": r.date_certainty,
                "offer_status": r.offer_status,
                "demo_only": r.demo_only,
                "official_url": r.official_url,
            }
        )
    return _ok(out)


@router.post("/benefits")
def create_benefit(payload: BenefitOfferCreate, db: DbDep):
    from app.services.benefits.service import create_benefit_offer

    offer = create_benefit_offer(db, payload)
    db.commit()
    return _ok({"id": offer.id, "offer_status": offer.offer_status})


@router.post("/benefit-claims")
def start_claim(payload: BenefitClaimStart, db: DbDep, settings: SettingsDep):
    from app.services.benefits.service import start_benefit_claim

    try:
        claim = start_benefit_claim(
            db,
            payload,
            allow_auto=bool(getattr(settings.trip_benefits, "auto_claim_globally_enabled", False)),
        )
        db.commit()
    except FlightHunterError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    return _ok({"id": claim.id, "status": claim.status, "automation_mode": claim.automation_mode})


@router.get("/wallet")
def wallet(db: DbDep):
    rows = db.scalars(select(WalletItem)).all()
    return _ok(
        [
            {
                "id": r.id,
                "offer_id": r.offer_id,
                "state": r.state,
                "official_url": r.official_url,
                "redemption_state": r.redemption_state,
            }
            for r in rows
        ]
    )


# ---- Fare ----
@router.get("/fare-watches")
def list_watches(db: DbDep):
    rows = db.scalars(select(FareWatch)).all()
    return _ok(
        [
            {
                "id": r.id,
                "name": r.name,
                "origin_airports": json.loads(r.origin_airports or "[]"),
                "destination_scope": r.destination_scope,
                "adults": r.adults,
                "enabled": r.enabled,
                "trip_id": r.trip_id,
                "scan_status": r.scan_status,
            }
            for r in rows
        ]
    )


@router.post("/fare-watches")
def create_watch(payload: FareWatchCreate, db: DbDep):
    from app.services.fare.service import create_fare_watch

    w = create_fare_watch(db, payload)
    db.commit()
    return _ok({"id": w.id, "name": w.name, "enabled": w.enabled})


@router.post("/fare-watches/{watch_id}/scan")
def scan_watch(watch_id: str, db: DbDep):
    from app.services.fare.service import match_watch_to_deals

    w = db.get(FareWatch, watch_id)
    if not w:
        raise HTTPException(status_code=404, detail="watch not found")
    matches = match_watch_to_deals(db, w)
    db.commit()
    return _ok(
        [
            {
                "deal_id": m.deal_id,
                "price_status": m.price_status,
                "date_match": m.date_match,
                "passenger_match": m.passenger_match,
                "risk_match": m.risk_match,
                "net_cost_min": m.net_cost_min,
                "net_cost_max": m.net_cost_max,
                "reason_codes": json.loads(m.reason_codes or "[]"),
            }
            for m in matches
        ]
    )


@router.get("/fare-deals")
def list_deals(
    db: DbDep,
    risk: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
    limit: int = Query(50, le=200),
):
    stmt = select(FareDeal).order_by(FareDeal.last_seen_utc.desc()).limit(limit)
    if risk:
        stmt = stmt.where(FareDeal.risk_tier == risk)
    if origin:
        stmt = stmt.where(FareDeal.origin == origin.upper())
    if destination:
        stmt = stmt.where(FareDeal.destination == destination.upper())
    rows = db.scalars(stmt).all()
    return _ok(
        [
            {
                "id": r.id,
                "origin": r.origin,
                "destination": r.destination,
                "offer_subtypes": json.loads(r.offer_subtypes or "[]"),
                "status": r.status,
                "risk_tier": r.risk_tier,
                "booking_status": r.booking_status,
                "link": r.link,
            }
            for r in rows
        ]
    )


@router.post("/fare-deals/import-signal")
def import_signal(payload: FareSignalImport, db: DbDep):
    from app.services.fare.service import import_signal as svc_import

    try:
        deal, signal = svc_import(db, payload)
        db.commit()
    except FlightHunterError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    return _ok(
        {
            "deal_id": deal.id,
            "signal_id": signal.id,
            "risk_tier": deal.risk_tier,
            "status": deal.status,
            "note": "已记录社区信号；不代表当前可买价",
        }
    )


@router.get("/fare-deals/{deal_id}/quotes")
def deal_quotes(deal_id: str, db: DbDep):
    rows = db.scalars(
        select(FareQuote)
        .where(FareQuote.deal_id == deal_id)
        .order_by(FareQuote.observed_at_utc.desc())
    ).all()
    return _ok(
        [
            {
                "id": r.id,
                "provider": r.provider,
                "observed_at_utc": r.observed_at_utc.isoformat(),
                "party_size": r.pax_count,
                "total_price": r.total_price,
                "currency": r.currency,
                "taxes_included": r.tax_included,
                "baggage_included": r.baggage_included,
                "availability_confirmed": r.availability_confirmed,
                "quote_status": r.quote_status,
                "booking_deeplink": r.booking_deeplink,
            }
            for r in rows
        ]
    )


@router.post("/fare-deals/{deal_id}/mark-booked")
def mark_booked(deal_id: str, db: DbDep, method: str = Query("user_reported")):
    from app.services.fare.service import mark_booked as svc_mark

    try:
        deal = svc_mark(db, deal_id, method=method)
        db.commit()
    except FlightHunterError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    return _ok({"id": deal.id, "booking_status": deal.booking_status})


# ---- Campaign rounds ----
@router.get("/campaign-rounds")
def list_rounds(db: DbDep, status: str | None = None, limit: int = Query(50, le=200)):
    stmt = select(CampaignRound).order_by(CampaignRound.updated_at_utc.desc()).limit(limit)
    if status:
        stmt = stmt.where(CampaignRound.verify_status == status)
    rows = db.scalars(stmt).all()
    return _ok(
        [
            {
                "id": r.id,
                "title": r.title,
                "organizer_name": r.organizer_name,
                "official_url": r.official_url,
                "verify_status": r.verify_status,
                "demo_only": r.demo_only,
                "entry_timezone": r.entry_timezone,
                "entry_closes_at_utc": r.entry_closes_at_utc.isoformat()
                if r.entry_closes_at_utc
                else None,
            }
            for r in rows
        ]
    )


# ---- Cost estimate ----
class CostIn(BaseModel):
    base_ticket_total: float | None = None
    taxes: float | None = None
    positioning: float | None = None
    baggage: float | None = None
    overnight: float | None = None
    other: float | None = None
    currency: str = "CNY"


@router.post("/fare/cost-breakdown")
def cost_breakdown(payload: CostIn):
    from app.services.fare.service import compute_cost_breakdown

    b = compute_cost_breakdown(
        base_ticket_total=payload.base_ticket_total,
        taxes=payload.taxes,
        positioning=payload.positioning,
        baggage=payload.baggage,
        overnight=payload.overnight,
        other=payload.other,
        currency=payload.currency,
    )
    return _ok(b.model_dump())


# ---- Export / Prefill ----
@router.get("/trips/{trip_id}/export")
def export_trip(trip_id: str, db: DbDep, format: str = Query("json")):
    from app.services.export.service import trip_to_export_dict, trip_to_ics

    try:
        if format == "ics":
            ics = trip_to_ics(db, trip_id)
            return Response(
                content=ics,
                media_type="text/calendar; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="trip-{trip_id}.ics"'},
            )
        data = trip_to_export_dict(db, trip_id)
        return _ok(data)
    except FlightHunterError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc


class PrefillIn(BaseModel):
    round_id: str
    profile_id: str
    user_approved_fields: dict[str, str] | None = None


@router.post("/entries/prefill-plan")
def prefill_plan(payload: PrefillIn, db: DbDep):
    from app.services.browser.prefill import build_prefill_plan, plan_to_dict

    round_ = db.get(CampaignRound, payload.round_id)
    profile = db.get(Profile, payload.profile_id)
    if round_ is None or profile is None:
        raise HTTPException(status_code=404, detail="round or profile not found")
    try:
        plan = build_prefill_plan(
            round_, profile, user_approved_fields=payload.user_approved_fields
        )
    except FlightHunterError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    return _ok(plan_to_dict(plan))


@router.get("/entries/center")
def entry_center(db: DbDep):
    from app.services.entry.center import entry_center_view

    return _ok(entry_center_view(db))


@router.get("/notifications")
def notifications(db: DbDep, unread_only: bool = True, limit: int = Query(50, le=200)):
    from app.services.notify.service import list_unread

    if unread_only:
        rows = list_unread(db, limit=limit)
    else:
        rows = db.scalars(
            select(Notification).order_by(Notification.created_at_utc.desc()).limit(limit)
        ).all()
    return _ok(
        [
            {
                "id": r.id,
                "kind": r.kind,
                "title": r.title,
                "body": r.body,
                "severity": r.severity,
                "read": r.read,
                "suppressed_reason": r.suppressed_reason,
            }
            for r in rows
        ]
    )


@router.post("/scheduler/run-dry")
def scheduler_run_dry(db: DbDep, settings: SettingsDep, limit: int = Query(10, le=50)):
    from app.scheduler.jobs import run_due_scans

    runs = run_due_scans(db, settings, dry_run=True, limit=limit)  # type: ignore[arg-type]
    db.commit()
    return _ok(
        [
            {
                "id": r.id,
                "task_type": r.task_type,
                "status": r.status,
                "dry_run": r.dry_run,
                "result_summary": r.result_summary,
            }
            for r in runs
        ]
    )
