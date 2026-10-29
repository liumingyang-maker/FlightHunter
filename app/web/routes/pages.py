"""页面路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from app.core.timeutils import utc_now_iso
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
from app.web.deps import DbDep, SettingsDep

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: DbDep, settings: SettingsDep):
    templates = request.app.state.templates
    trip_count = db.scalar(select(func.count()).select_from(Trip).where(not Trip.demo_only)) or 0
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
    deals = db.scalars(select(FareDeal).order_by(FareDeal.last_seen_utc.desc()).limit(50)).all()
    watches = db.scalars(select(FareWatch).where(FareWatch.enabled == True)).all()  # noqa: E712
    return templates.TemplateResponse(
        request,
        "fare.html",
        {
            "deals": deals,
            "watches": watches,
            "note": "社区爆料 ≠ 实时可买价；无合法报价源时价格为未知",
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
    rounds = db.scalars(
        select(CampaignRound).order_by(CampaignRound.updated_at_utc.desc()).limit(50)
    ).all()
    return templates.TemplateResponse(
        request,
        "campaigns.html",
        {"rounds": rounds, "app_name": settings.app.name},
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
