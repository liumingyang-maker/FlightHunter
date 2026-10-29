"""日本行程：真实公开优惠结构化 + 中文指南。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.ids import new_id
from app.models import BenefitOffer, Trip
from app.services.benefits.service import create_benefit_offer, generate_guide
from app.services.discovery.service import adapter_for
from app.services.trips.service import rematch_trip_benefits

JP_TRIP_FIXTURE = {
    "label": "2027 日本旅行（演示测试）",
    "country": "JP",
    "start": date(2027, 5, 10),
    "end": date(2027, 5, 30),
    "tz": "Asia/Tokyo",
}


def ensure_demo_japan_trip(session: Session, settings: Settings) -> Trip:
    existing = session.scalar(select(Trip).where(Trip.label == JP_TRIP_FIXTURE["label"]))
    if existing:
        return existing
    from app.schemas.domain import TripCreate
    from app.services.trips.service import create_trip

    return create_trip(
        session,
        settings,
        TripCreate(
            label=JP_TRIP_FIXTURE["label"],
            destination_country_code="JP",
            local_start_date=JP_TRIP_FIXTURE["start"],
            local_end_date=JP_TRIP_FIXTURE["end"],
            timezone=JP_TRIP_FIXTURE["tz"],
            demo_only=True,
        ),
    )


def upsert_jp_benefit_from_source_text(
    session: Session,
    *,
    title: str,
    source_url: str,
    source_name: str,
    raw_text: str,
    country_code: str = "JP",
) -> BenefitOffer:
    """把公开页面线索结构化为 BenefitOffer（unconfirmed，不伪造领取）。"""
    existing = session.scalar(
        select(BenefitOffer).where(
            BenefitOffer.title == title[:400],
            BenefitOffer.source_url == source_url,
        )
    )
    if existing:
        return existing
    conditions = {
        "raw_evidence": raw_text[:500],
        "source": source_name,
        "claim_window": "待核实",
        "redeem_window": "待核实",
        "min_spend": None,
        "payment": None,
    }
    offer = create_benefit_offer(
        session,
        __import__("app.schemas.domain", fromlist=["BenefitOfferCreate"]).BenefitOfferCreate(
            organizer_name=source_name,
            title=title[:400],
            category="travel_deal",
            claim_method="PUBLIC_DISPLAY",
            official_url=None,
            country_codes=[country_code],
            date_certainty="unconfirmed",
            conditions=conditions,
            source_url=source_url,
            demo_only=False,
        ),
    )
    return offer


async def scan_jp_public_page(
    session: Session,
    settings: Settings,
    trip: Trip,
    *,
    source_url: str = "https://www.timeout.com/tokyo/things-to-do",
    limit: int = 10,
) -> dict:
    """抓取东京公开列表 → BenefitOffer 候选 → 重匹配 → 中文指南。"""
    from app.models import Source

    src = session.scalar(select(Source).where(Source.base_url.contains("timeout.com")))
    if src is None:
        src = Source(
            id=new_id(),
            name="Time Out Tokyo",
            base_url=source_url,
            kind="community",
            language="en",
            country_code="JP",
            access_policy="public_fetch",
            allowed_fetch_mode="httpx",
            module="trip",
            status="active",
        )
        session.add(src)
        session.flush()

    adapter = adapter_for(src, settings)
    if adapter is None:
        return {"ok": False, "reason": "no_adapter"}
    result = await adapter.fetch(src.base_url)
    if not result.ok:
        return {"ok": False, "reason": "fetch_failed", "message": result.message}

    base = result.final_url or src.base_url
    parsed = adapter.parse_trip(result.text or "", url=base)[:limit] if hasattr(adapter, "parse_trip") else []
    created = 0
    for p in parsed:
        upsert_jp_benefit_from_source_text(
            session,
            title=p.title,
            source_url=p.url or base,
            source_name=src.name,
            raw_text=p.raw_claim_text,
            country_code="JP",
        )
        created += 1

    matches = rematch_trip_benefits(session, trip)
    guides = 0
    for m in matches:
        offer = session.get(BenefitOffer, m.offer_id)
        if offer and offer.demo_only is False:
            generate_guide(session, offer.id)
            guides += 1
    session.flush()
    return {
        "ok": True,
        "parsed": len(parsed),
        "offers_touched": created,
        "matches": len(matches),
        "guides_generated": guides,
        "source_url": base,
        "note": "候选均为 unconfirmed；指南含待核实字段，不代表已领取",
    }
