"""API v1 路由。"""

from __future__ import annotations

import json
import re

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
        "confirmed": getattr(t, "confirmed", False),
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


@router.get("/ops/source-health")
def ops_source_health(
    db: DbDep,
    module: str = Query("fare"),
    window_hours: int = Query(24, ge=1, le=720),
):
    from app.services.ops.source_health import source_health_report

    return _ok(source_health_report(db, module=module or None, window_hours=window_hours))


@router.get("/ops/status")
def ops_status(db: DbDep):
    from app.services.ops.status import system_status

    return _ok(system_status(db))


@router.get("/mail/eml-scan")
def mail_eml_scan(
    db: DbDep,
    settings: SettingsDep,
    dir: str = Query(..., description="本地 .eml 目录绝对路径"),
):
    from pathlib import Path

    from app.services.entry.browser_pipeline import mail_candidates_to_notifications
    from app.services.mail.eml_scan import scan_eml_dir

    result = scan_eml_dir(Path(dir))
    n = 0
    if result.get("candidates"):
        n = mail_candidates_to_notifications(db, settings, result)  # type: ignore[arg-type]
    db.commit()
    return _ok({**result, "notifications_created": n})


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


@router.get("/fare/intel")
def fare_intel(
    db: DbDep,
    limit: int = Query(40, le=100),
    origins: str | None = Query(None, description="comma IATA like CKG,TFU"),
    mode: str = Query("specific", description="specific|china_all|all"),
    include_hkg: bool = False,
    include_mfm: bool = False,
    hide_expired: bool = True,
    channel: str = Query(
        "my_origin",
        description="my_origin|china_mainland|hk_mo|global_error",
    ),
    destination: str | None = Query(None, description="IATA or destination city (not airline brand)"),
    category: str | None = Query(None, description="suspected_bug_fare|official_or_flash_promo|..."),
    date_from: str | None = Query(None, description="YYYY-MM-DD lower bound"),
    date_to: str | None = Query(None, description="YYYY-MM-DD upper bound"),
    feedback: str | None = Query(None, description="bookmarked|useful|ignore"),
    time_field: str = Query("auto", description="auto|travel|published|found"),
):
    """P1 四频道情报（统一库；无实时报价依赖）。"""
    from app.services.airports.china import expand_origin_selection
    from app.services.fare.channels import filter_for_channel
    from app.services.fare.intel import IntelFilter, build_intel_view

    codes = [x.strip().upper() for x in (origins or "").split(",") if x.strip()]
    # 频道视图：港澳/全球错价不强制绑定用户偏好机场过滤结果
    if channel == "global_error":
        # D-004：除非用户显式传入 origins，否则全球错价不过滤出发地
        prefs = (
            expand_origin_selection(multi=codes, include_hkg=True, include_mfm=True)
            if codes
            else []
        )
    elif channel == "hk_mo":
        prefs = expand_origin_selection(multi=codes, include_hkg=True, include_mfm=True)
    elif mode == "china_all" or channel == "china_mainland":
        prefs = expand_origin_selection(china_mainland_all=True, multi=codes)
    else:
        prefs = expand_origin_selection(
            multi=codes or ["CKG", "TFU", "CTU"],
            include_hkg=include_hkg,
            include_mfm=include_mfm,
        )
    filt = IntelFilter(
        preferred_origins=prefs,
        include_hkg=include_hkg or channel == "hk_mo",
        include_mfm=include_mfm or channel == "hk_mo",
        hide_expired=hide_expired,
        exclude_domestic=channel != "global_error",
    )
    # 全球错价：不过滤城市匹配
    rows = build_intel_view(db, filt, limit=max(limit, 80))
    routed = filter_for_channel(
        rows,
        channel,
        prefs,
    )
    primary = routed["primary"]
    folded = routed["folded"]
    # N-018：目的地 / 类别 / 时间 / 反馈筛选（未知项不会被误当作已匹配）
    primary = _apply_intel_filters(
        primary,
        destination=destination,
        category=category,
        date_from=date_from,
        date_to=date_to,
        feedback=feedback,
        time_field=time_field,
    )
    folded = _apply_intel_filters(
        folded,
        destination=destination,
        category=category,
        date_from=date_from,
        date_to=date_to,
        feedback=feedback,
        time_field=time_field,
    )
    primary = primary[:limit]
    folded = folded[:20]
    return _ok(
        {
            "channel": channel,
            "origins": prefs if mode != "china_all" else ["(china_mainland_all)", *codes],
            "mode_flag": mode,
            "include_hkg": include_hkg or channel == "hk_mo",
            "include_mfm": include_mfm or channel == "hk_mo",
            "primary_count": len(primary),
            "folded_count": len(folded),
            "items": primary,
            "folded": folded,
            "mode": "intel_no_live_quote",
            "same_signal_id_across_channels": True,
            "filters": {
                "destination": destination,
                "category": category,
                "date_from": date_from,
                "date_to": date_to,
                "feedback": feedback,
                "time_field": time_field,
            },
        }
    )


def _apply_intel_filters(
    rows: list[dict],
    *,
    destination: str | None,
    category: str | None,
    date_from: str | None,
    date_to: str | None,
    feedback: str | None,
    time_field: str | None = None,
) -> list[dict]:
    """结构化筛选：缺失字段在指定过滤时排除（不误作匹配）。

    R-007：反馈用 user_feedback（与 signal_status 同源）。
    R-009：目的地只匹配结构化 destination_airport / 明确目的地城市，不把航司名当目的地。
    """
    from datetime import datetime

    # 目的地城市别名 → IATA（仅目的地语境，不含航司品牌）
    dest_alias = {
        "香港": "HKG",
        "HK": "HKG",
        "澳门": "MFM",
        "澳門": "MFM",
        "大阪": "KIX",
        "东京": "NRT",
        "首尔": "ICN",
        "台北": "TPE",
        "台湾": None,  # 台湾非单一机场
        "上海": "PVG",
        "北京": "PEK",
        "成都": "TFU",
    }

    out = rows
    if destination:
        d = destination.strip().upper()
        alias = dest_alias.get(destination.strip())
        if alias is None and destination.strip() in dest_alias:
            # 台湾等：仅结构化字段或明确目的地词在 dest 位
            alias = ""

        def dest_match(it: dict) -> bool:
            code = (it.get("destination_airport") or "").upper()
            if d and code == d:
                return True
            if alias and code == alias:
                return True
            # 明确「→城市」目的语境，不匹配航司名/出发语境
            title = it.get("title") or ""
            if destination.strip() and re.search(
                r"(?:→|->|至|飞|to)\s*" + re.escape(destination.strip()), title, re.I
            ):
                return True
            # dest 字段城市名
            dest_city = (it.get("destination_city") or "") or ""
            return bool(dest_city and dest_city == destination.strip())

        out = [it for it in out if dest_match(it)]
    if category:
        cat = category.strip()
        out = [it for it in out if (it.get("category") or "") == cat]
    if feedback:
        fb = feedback.strip()
        out = [
            it
            for it in out
            if (it.get("user_feedback") or it.get("signal_status") or "") == fb
        ]

    def _parse_dt(s: str | None):
        if not s:
            return None
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except Exception:
            return None

    dfrom = _parse_dt(date_from)
    dto = _parse_dt(date_to)
    if dfrom or dto:
        field = (time_field or "auto").strip()

        def pick_time(it: dict):
            if field == "travel":
                # 出行时间：travel_date_hint / travel 窗口
                for k in ("travel_date_hint", "travel_window_start", "travel_date"):
                    if it.get(k):
                        raw = it.get(k)
                        if isinstance(raw, str) and len(raw) >= 10:
                            return _parse_dt(raw[:10])
                        return _parse_dt(str(raw))
                return None
            if field == "published":
                return _parse_dt(it.get("published_at") if isinstance(it.get("published_at"), str) else None)
            if field == "found":
                return _parse_dt(it.get("found_at") if isinstance(it.get("found_at"), str) else None)
            # 默认界面筛选发布/发现时间；出行日期需显式选择 travel。
            for k in ("published_at", "found_at"):
                raw = it.get(k)
                if not raw:
                    continue
                if isinstance(raw, str) and len(raw) >= 10:
                    dt = _parse_dt(raw[:10] if k == "travel_date_hint" else raw)
                    if dt:
                        return dt
            return None

        def time_ok(it: dict) -> bool:
            if field == "travel":
                start = _parse_dt(it.get("travel_window_start"))
                end = _parse_dt(it.get("travel_window_end"))
                if start and end:
                    return not (
                        (dfrom and end.date() < dfrom.date())
                        or (dto and start.date() > dto.date())
                    )
            dt = pick_time(it)
            if dt is None:
                return False
            if dfrom and dt.date() < dfrom.date():
                return False
            return not (dto and dt.date() > dto.date())

        out = [it for it in out if time_ok(it)]
    return out


@router.post("/fare/intel/{signal_id}/feedback")
def fare_intel_feedback(
    signal_id: str,
    db: DbDep,
    feedback: str = Query(..., description="bookmarked|read|not_interested|expired_reported|price_mismatch_reported"),
):
    from app.services.fare.intel import apply_user_feedback

    try:
        s = apply_user_feedback(db, signal_id, feedback)
        db.commit()
        return _ok({"id": s.id, "signal_status": s.signal_status})
    except Exception as exc:
        db.rollback()
        from app.core.errors import FlightHunterError

        if isinstance(exc, FlightHunterError):
            raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
def list_rounds(
    db: DbDep,
    status: str | None = None,
    limit: int = Query(50, le=200),
    open_only: bool = False,
    flight_only: bool = False,
    pending_only: bool = False,
):
    stmt = select(CampaignRound).order_by(CampaignRound.updated_at_utc.desc()).limit(limit * 3)
    if status:
        stmt = stmt.where(CampaignRound.verify_status == status)
    rows = db.scalars(stmt).all()
    import json as _json
    from datetime import UTC, datetime

    now = datetime.now(UTC).replace(tzinfo=None)

    def _tags(r: CampaignRound) -> dict:
        if not r.tags:
            return {}
        try:
            data = _json.loads(r.tags)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _source_list(r: CampaignRound) -> str | None:
        return _tags(r).get("source_list_url")

    def _open_status(r: CampaignRound) -> str:
        t = _tags(r)
        if t.get("open_status") in {"open", "closed", "pending_verification", "unknown"}:
            return str(t["open_status"])
        if t.get("active_now") is True:
            return "open"
        if t.get("active_now") is False:
            return "closed"
        closes = r.entry_closes_at_utc
        if closes is not None:
            c = closes.replace(tzinfo=None) if closes.tzinfo else closes
            return "open" if c >= now else "closed"
        # 无证据日期 → 未知/待核实，绝不当 closed
        return "pending_verification" if t.get("requires_login_to_enter") else "unknown"

    def _is_open(r: CampaignRound) -> bool:
        return _open_status(r) == "open"

    def _is_flight(r: CampaignRound) -> bool:
        t = _tags(r)
        if "prize_is_flight" in t:
            return t.get("prize_is_flight") is True
        try:
            cat = r.campaign.category if r.campaign else ""
        except Exception:
            cat = ""
        return cat == "flight_giveaway"

    filtered = []
    for r in rows:
        st = _open_status(r)
        if open_only and st != "open":
            continue
        if pending_only and st != "pending_verification":
            continue
        if flight_only and not _is_flight(r):
            continue
        filtered.append(r)
        if len(filtered) >= limit:
            break
    return _ok(
        [
            {
                "id": r.id,
                "title": r.title,
                "organizer_name": r.organizer_name,
                "official_url": r.official_url,
                "source_list_url": _source_list(r),
                "verify_status": r.verify_status,
                "demo_only": r.demo_only,
                "open_status": _open_status(r),
                "open_now": _open_status(r) == "open",
                "prize_is_flight": _is_flight(r),
                "entry_timezone": r.entry_timezone,
                "entry_closes_at_utc": r.entry_closes_at_utc.isoformat()
                if r.entry_closes_at_utc
                else None,
            }
            for r in filtered
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


class PrefillExecuteIn(BaseModel):
    round_id: str
    profile_id: str
    file_url: str | None = None
    submit: bool = False
    explicit_submit_consent: bool = False
    user_approved_fields: dict[str, str] | None = None


@router.post("/entries/prefill-execute")
def prefill_execute(payload: PrefillExecuteIn, db: DbDep, settings: SettingsDep):
    """执行浏览器预填管道；默认不自动提交。file_url 用于本地模拟站 E2E。"""
    from app.services.entry.browser_pipeline import execute_browser_entry

    round_ = db.get(CampaignRound, payload.round_id)
    profile = db.get(Profile, payload.profile_id)
    if round_ is None or profile is None:
        raise HTTPException(status_code=404, detail="round or profile not found")
    try:
        result = execute_browser_entry(
            db,  # type: ignore[arg-type]
            settings,  # type: ignore[arg-type]
            round_,
            profile,
            file_url=payload.file_url,
            submit=payload.submit,
            explicit_submit_consent=payload.explicit_submit_consent,
            user_approved_fields=payload.user_approved_fields,
        )
        db.commit()
    except FlightHunterError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    return _ok(
        {
            "attempt_id": result.attempt_id,
            "status": result.status,
            "receipt_code": result.receipt_code,
            "browser_ok": result.browser_ok,
            "message": result.message,
            "warnings": result.warnings,
            "requires_human": result.requires_human,
        }
    )


@router.post("/wallet/{wallet_item_id}/private-code")
def wallet_private_code(
    wallet_item_id: str,
    payload: dict,
    db: DbDep,
    settings: SettingsDep,
):
    """加密保存卡包私密码；响应不回显明文。"""
    from app.services.entry.browser_pipeline import wallet_store_and_notify

    code = (payload or {}).get("code") or ""
    if not code:
        raise HTTPException(status_code=400, detail="code required")
    try:
        out = wallet_store_and_notify(
            db,  # type: ignore[arg-type]
            settings,  # type: ignore[arg-type]
            wallet_item_id=wallet_item_id,
            plaintext_code=str(code),
        )
        db.commit()
    except FlightHunterError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    return _ok(out)


@router.get("/mail/candidates")
def mail_candidates(db: DbDep, settings: SettingsDep):
    """扫描授权邮箱候选（未配置则 blocked）。"""
    from app.services.entry.browser_pipeline import mail_candidates_to_notifications
    from app.services.mail.imap_scan import scan_inbox_imap

    cfg = {
        "enabled": bool(settings.notifications.email_integration_enabled),  # type: ignore[attr-defined]
        "host": settings.notifications.email_host,  # type: ignore[attr-defined]
        "user": settings.notifications.email_user,  # type: ignore[attr-defined]
        "password": settings.notifications.email_password,  # type: ignore[attr-defined]
    }
    if not cfg["enabled"] or not cfg["host"] or not cfg["user"]:
        return _ok(
            {
                "status": "blocked",
                "message": "未启用邮件集成或缺少 IMAP host/user；请在本地配置 notifications.email_* 后使用",
            }
        )
    result = scan_inbox_imap(
        settings,  # type: ignore[arg-type]
        host=str(cfg["host"]),
        username=str(cfg["user"] or ""),
        password=str(cfg["password"] or ""),
    )
    n = mail_candidates_to_notifications(db, settings, result)  # type: ignore[arg-type]
    db.commit()
    return _ok({**result, "notifications_created": n})


@router.get("/entries/center")
def entry_center(db: DbDep):
    from app.services.entry.center import entry_center_view

    return _ok(entry_center_view(db))


@router.get("/entries/attempts")
def list_attempts(db: DbDep, limit: int = Query(30, le=200)):
    from app.services.entry.detail import list_attempts_for_ui

    return _ok(list_attempts_for_ui(db, limit=limit))


@router.get("/entries/attempts/{attempt_id}")
def get_attempt(attempt_id: str, db: DbDep):
    from app.services.entry.detail import attempt_detail

    detail = attempt_detail(db, attempt_id)
    if detail.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="attempt not found")
    return _ok(detail)


@router.post("/entries/reconcile-stuck")
def reconcile_stuck(db: DbDep):
    from app.services.entry.detail import reconcile_all_stuck

    n = reconcile_all_stuck(db)
    db.commit()
    return _ok({"reconciled_to_unknown": n})


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


@router.post("/scheduler/run-due")
def scheduler_run_due(db: DbDep, settings: SettingsDep, limit: int = Query(10, le=50)):
    """真实执行到期扫描（仍遵守来源策略与 dry/execute 幂等分离）。"""
    from app.scheduler.jobs import run_due_scans

    runs = run_due_scans(
        db, settings, dry_run=False, limit=limit, include_raffle_pipeline=True
    )  # type: ignore[arg-type]
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
