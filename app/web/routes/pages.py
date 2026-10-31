"""页面路由。"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from app.core.timeutils import utc_now_iso
from app.core.url_safety import is_safe_local_next
from app.models import (
    BenefitOffer,
    CampaignRound,
    EntryAttempt,
    FareAlert,
    FareDeal,
    FareWatch,
    Notification,
    Profile,
    Trip,
    WalletItem,
)
from app.web.auth import (
    create_session_cookie_value,
    ensure_runtime_secrets,
    token_matches,
)
from app.web.deps import DbDep, SettingsDep

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    templates = request.app.state.templates
    settings = request.app.state.settings
    return templates.TemplateResponse(
        request,
        "login.html",
        {"app_name": settings.app.name, "next_url": next or "/"},
    )


@router.post("/login")
def login_submit(request: Request, token: str = Form(...), next: str = Form("/")):
    settings = request.app.state.settings
    ensure_runtime_secrets(settings)
    if not token_matches(token, settings):
        return RedirectResponse(url="/login?error=1", status_code=303)
    safe_next = is_safe_local_next(next)
    response = RedirectResponse(url=safe_next, status_code=303)
    response.set_cookie(
        key=settings.auth.session_cookie_name,
        value=create_session_cookie_value(settings),
        httponly=True,
        samesite="strict",
        max_age=settings.auth.session_max_age_seconds,
        path="/",
    )
    return response


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: DbDep, settings: SettingsDep):
    templates = request.app.state.templates
    trip_count = (
        db.scalar(select(func.count()).select_from(Trip).where(Trip.demo_only == False))  # noqa: E712
        or 0
    )
    demo_trips = (
        db.scalar(
            select(func.count()).select_from(Trip).where(Trip.demo_only == True)  # noqa: E712
        )
        or 0
    )
    deal_count = db.scalar(select(func.count()).select_from(FareDeal)) or 0
    high_risk = (
        db.scalar(
            select(func.count()).select_from(FareDeal).where(FareDeal.risk_tier == "high_risk")
        )
        or 0
    )
    wallet_count = db.scalar(select(func.count()).select_from(WalletItem)) or 0
    pending_entries = (
        db.scalar(
            select(func.count())
            .select_from(EntryAttempt)
            .where(EntryAttempt.status.in_(["prepared", "awaiting_review", "unknown"]))
        )
        or 0
    )
    offer_count = db.scalar(select(func.count()).select_from(BenefitOffer)) or 0
    watch_count = db.scalar(select(func.count()).select_from(FareWatch)) or 0
    alerts = db.scalars(select(FareAlert).order_by(FareAlert.created_at_utc.desc()).limit(5)).all()
    notes = db.scalars(
        select(Notification).order_by(Notification.created_at_utc.desc()).limit(5)
    ).all()

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "app_name": settings.app.name,
            "demo_mode": settings.app.demo_mode,
            "server_time_utc": utc_now_iso(),
            "stats": {
                "trips": trip_count,
                "demo_trips": demo_trips,
                "deals": deal_count,
                "high_risk": high_risk,
                "wallet": wallet_count,
                "pending_entries": pending_entries,
                "offers": offer_count,
                "watches": watch_count,
            },
            "alerts": alerts,
            "notifications": notes,
            "version": request.app.version,
        },
    )


@router.get("/trips", response_class=HTMLResponse)
def trips_page(request: Request, db: DbDep, settings: SettingsDep):
    templates = request.app.state.templates
    trips = db.scalars(select(Trip).order_by(Trip.created_at_utc.desc())).all()
    return templates.TemplateResponse(
        request,
        "trips.html",
        {"trips": trips, "app_name": settings.app.name},
    )


@router.get("/fare", response_class=HTMLResponse)
def fare_page(request: Request, db: DbDep, settings: SettingsDep):
    templates = request.app.state.templates
    from app.services.airports.china import expand_origin_selection
    from app.services.fare.intel import IntelFilter, build_intel_view

    default_origins = list(settings.profiles.default_preferred_departure_airports)
    intel = build_intel_view(
        db,
        IntelFilter(preferred_origins=default_origins, hide_expired=True),
        limit=30,
    )
    watches = db.scalars(select(FareWatch).where(FareWatch.enabled == True)).all()  # noqa: E712
    return templates.TemplateResponse(
        request,
        "fare.html",
        {
            "intel": intel,
            "watches": watches,
            "default_origins": default_origins,
            "mainland_count": len(expand_origin_selection(china_mainland_all=True)),
            "note": "情报模式：社区/RSS 报道价 ≠ 实时可买价；请点击来源自行查询",
            "app_name": settings.app.name,
        },
    )


@router.get("/wallet", response_class=HTMLResponse)
def wallet_page(request: Request, db: DbDep, settings: SettingsDep):
    templates = request.app.state.templates
    items = db.scalars(select(WalletItem)).all()
    return templates.TemplateResponse(
        request,
        "wallet.html",
        {"items": items, "app_name": settings.app.name},
    )


@router.get("/campaigns", response_class=HTMLResponse)
def campaigns_page(request: Request, db: DbDep, settings: SettingsDep):
    templates = request.app.state.templates
    import json as _json

    rounds = db.scalars(
        select(CampaignRound).order_by(CampaignRound.updated_at_utc.desc()).limit(200)
    ).all()

    from app.services.raffle.campaigns_clean import is_noise_title, is_travel_related

    def _view(r: CampaignRound) -> dict:
        # 视图层兜底去噪（即使库里还有脏数据也不展示）
        if is_noise_title(r.title or ""):
            return {"title": "", "hidden": True}
        if not is_travel_related(r.title or "", r.prize_summary):
            return {"title": "", "hidden": True}
        # 只保留机票/旅行/住宿类奖品
        _tags = _json.loads(r.tags or "{}") if r.tags else {}
        _prizes = set(_tags.get("prize_types") or [])
        _KEEP = {"flight_giveaway", "travel_package_unknown_air", "lodging_or_cruise"}
        if _prizes and not (_KEEP & _prizes):
            return {"title": "", "hidden": True}
        from app.services.raffle.campaigns_clean import safe_core_recommend

        source_list = None
        china_outbound = "unknown"
        tags = {}
        if r.tags:
            try:
                data = _json.loads(r.tags)
                if isinstance(data, dict):
                    tags = data
                    source_list = data.get("source_list_url")
                    china_outbound = data.get("china_outbound_relevance") or "unknown"
            except Exception:
                source_list = None
        # 聚合源/无官方链接 永不 core（安全兜底）
        core_recommend = safe_core_recommend(tags, r.official_url)
        return {
            "title": r.title,
            "organizer_name": r.organizer_name,
            "official_url": r.official_url,
            "source_list_url": source_list,
            "verify_status": r.verify_status,
            "demo_only": r.demo_only,
            "china_outbound": china_outbound,
            "core_recommend": core_recommend,
            "prize_summary": (r.prize_summary or "")[:80],
            "opens": tags.get("opens_iso") or tags.get("opens_raw"),
            "closes": tags.get("closes_iso") or tags.get("closes_raw"),
            "aggregator": tags.get("aggregator", False),
            "prize_types": tags.get("prize_types") or [],
        }

    return templates.TemplateResponse(
        request,
        "campaigns.html",
        {
            "rounds": sorted(
                (x for x in (_view(r) for r in rounds) if not x.get("hidden")),
                key=lambda x: (
                    0 if x.get("verify_status") == "verified" else
                    1 if x.get("verify_status") == "auto_extracted" else
                    2 if x.get("core_recommend") else 3,
                    0 if x.get("closes") else 1,
                    x.get("title") or "",
                ),
            ),
            "app_name": settings.app.name,
        },
    )


@router.get("/entries", response_class=HTMLResponse)
def entries_page(request: Request, db: DbDep, settings: SettingsDep):
    templates = request.app.state.templates
    from app.services.entry.center import entry_center_view
    from app.services.entry.detail import list_attempts_for_ui

    groups = entry_center_view(db)
    view = {}
    for g, items in groups.items():
        view[g] = [
            {
                "round_id": i.get("round_id"),
                "title": i.get("title") or i.get("round_id"),
                "status": i.get("status"),
                "why_stuck": i.get("why_stuck"),
                "next_step": i.get("next_step"),
            }
            for i in items
        ]
    attempts = list_attempts_for_ui(db, limit=20)
    return templates.TemplateResponse(
        request,
        "entries.html",
        {
            "groups": view,
            "attempts": attempts,
            "app_name": settings.app.name,
        },
    )


@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: DbDep, settings: SettingsDep):
    templates = request.app.state.templates
    notes = db.scalars(
        select(Notification).order_by(Notification.created_at_utc.desc()).limit(100)
    ).all()
    return templates.TemplateResponse(
        request,
        "notifications.html",
        {"notes": notes, "app_name": settings.app.name},
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: DbDep, settings: SettingsDep):
    templates = request.app.state.templates
    profiles = db.scalars(select(Profile)).all()
    cfg = {
        "demo_mode": settings.app.demo_mode,
        "ai_enabled": settings.ai.enabled,
        "trip_monitoring": settings.trip_monitoring.enabled,
        "airfare_radar": settings.airfare_radar.enabled,
        "quote_provider": settings.airfare_radar.quote_provider_enabled,
        "origins": settings.airfare_radar.candidate_origin_airports,
        "web": f"{settings.app.web_host}:{settings.app.web_port}",
    }
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"cfg": cfg, "profiles": profiles, "app_name": settings.app.name},
    )
