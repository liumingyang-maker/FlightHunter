"""发现管道：来源 → RawCandidate → 解析 → **结构化业务实体** → 匹配提醒。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import FetchResult, ParsedSignal, SourceAdapter
from app.adapters.html_fetcher import HttpxFetchAdapter
from app.adapters.rss import RssAdapter
from app.config import Settings
from app.core.errors import ErrorCode
from app.core.ids import content_hash_of_html, new_id
from app.core.timeutils import utc_now
from app.models import (
    BenefitOffer,
    FareDeal,
    FareDealSignal,
    FareWatch,
    RawCandidate,
    Source,
)


def adapter_for(source: Source, settings: Settings) -> SourceAdapter | None:
    if source.allowed_fetch_mode == "rss":
        return RssAdapter(settings)
    if source.allowed_fetch_mode == "httpx":
        return HttpxFetchAdapter(settings)
    return None


def ingest_fetch_result(
    session: Session,
    source: Source,
    result: FetchResult,
    *,
    module: str = "fare",
    title: str | None = None,
) -> RawCandidate | None:
    now = utc_now()
    if not result.ok:
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        if result.error_code == ErrorCode.SOURCE_FETCH_DENIED.value:
            source.status = "manual_only"
        session.flush()
        return None

    existing = session.scalar(
        select(RawCandidate).where(
            RawCandidate.source_id == source.id,
            RawCandidate.url == (result.final_url or result.url),
        )
    )
    ch = result.content_hash or content_hash_of_html(result.text or "")
    if existing:
        existing.raw_content_hash = ch
        existing.discovered_at_utc = now
        existing.payload_excerpt = (
            (result.text or "")[:4000] if result.text else existing.payload_excerpt
        )
        session.flush()
        return existing

    cand = RawCandidate(
        id=new_id(),
        source_id=source.id,
        url=result.final_url or result.url,
        title=title or ((result.text or "")[:200] if result.text else None),
        discovered_at_utc=now,
        content_type=result.content_type or "text/html",
        raw_content_hash=ch,
        status="parsed",
        module=module,
        payload_excerpt=(result.text or "")[:4000] if result.text else None,
    )
    session.add(cand)
    source.last_seen_at = now
    source.consecutive_failures = 0
    session.flush()
    return cand


def _risk_tier_for_subtypes(subtypes: list[str]) -> str:
    high = {"hidden_city"}
    review = {"error_fare", "fuel_surcharge_anomaly", "unclassified"}
    if any(t in high for t in subtypes):
        return "high_risk"
    if any(t in review for t in subtypes):
        return "needs_review"
    return "standard"


def materialize_fare_signals(
    session: Session,
    source: Source,
    parsed: list[ParsedSignal],
    *,
    candidate_url: str | None = None,
    limit: int = 20,
) -> list[FareDealSignal]:
    """把解析结果写成 FareDeal + FareDealSignal；子类型与风险写入主记录。"""
    created: list[FareDealSignal] = []
    now = utc_now()
    for s in parsed[:limit]:
        origin = (s.origin_airport or "").upper() or None
        dest = (s.destination_airport or "").upper() or None
        window = "flex"
        subtypes = list(s.deal_types or ["unclassified"])
        if (
            "hidden_city" in subtypes
            or "error_fare" in subtypes
            or "fuel_surcharge_anomaly" in subtypes
        ):
            dedup = f"src:{source.id}:{s.title[:80]}:{origin}-{dest}:{window}"
        else:
            dedup = f"src:{source.id}:{s.title[:80]}:{origin}-{dest}:{window}"
        deal = session.scalar(select(FareDeal).where(FareDeal.dedup_key == dedup))
        risk = _risk_tier_for_subtypes(subtypes)
        if deal is None:
            deal = FareDeal(
                id=new_id(),
                dedup_key=dedup,
                origin=origin,
                destination=dest,
                travel_date_hint=window,
                offer_subtypes=json.dumps(subtypes),
                status="price_unconfirmed",
                risk_tier=risk,
                first_seen_utc=now,
                last_seen_utc=now,
                link=s.url or candidate_url,
            )
            session.add(deal)
            session.flush()
        else:
            deal.last_seen_utc = now
            merged = set(json.loads(deal.offer_subtypes or "[]")) | set(subtypes)
            deal.offer_subtypes = json.dumps(sorted(merged))
            deal.risk_tier = _risk_tier_for_subtypes(sorted(merged))

        sig_url = s.url or candidate_url
        existing_sig = session.scalar(
            select(FareDealSignal).where(
                FareDealSignal.deal_id == deal.id,
                FareDealSignal.original_url == sig_url,
                FareDealSignal.title == s.title[:400],
            )
        )
        if existing_sig:
            continue
        sig = FareDealSignal(
            id=new_id(),
            deal_id=deal.id,
            source_id=source.id,
            original_url=s.url or candidate_url,
            title=s.title[:400],
            raw_claim_text=s.raw_claim_text[:2000],
            published_at_utc=s.published_at,
            reported_total=s.reported_total,
            currency=s.currency,
            party_size=s.party_size,
            origin_airport=origin,
            destination_airport=dest,
            airline=s.airline,
            deal_types=json.dumps(subtypes),
            source_type="community",
            signal_status="parsed",
            confidence=s.confidence,
            user_supplied=False,
        )
        session.add(sig)
        created.append(sig)
    session.flush()
    return created


def materialize_trip_offer(
    session: Session,
    source: Source,
    parsed: ParsedSignal,
    *,
    country_code: str | None = None,
) -> BenefitOffer | None:
    """行程线索 → BenefitOffer 候选；社区帖不得写成已核实 official_url。"""
    existing = session.scalar(
        select(BenefitOffer).where(
            BenefitOffer.title == parsed.title[:400],
            BenefitOffer.source_id == source.id,
        )
    )
    if existing:
        return existing
    conditions = {"raw_claim": parsed.raw_claim_text[:500]}
    if "min_spend=" in (parsed.raw_claim_text or ""):
        import re

        m = re.search(r"min_spend=([\d,]+(?:\.\d+)?)", parsed.raw_claim_text)
        if m:
            conditions["minimum_spend"] = float(m.group(1).replace(",", ""))
    offer = BenefitOffer(
        id=new_id(),
        organizer_name=source.name,
        title=parsed.title[:400],
        category="travel_deal",
        claim_method="PUBLIC_DISPLAY",
        official_url=None,
        country_codes=json.dumps([country_code.upper()] if country_code else []),
        date_certainty="unconfirmed",
        conditions=json.dumps(conditions, ensure_ascii=False),
        face_value_min=parsed.reported_total,
        face_value_max=parsed.reported_total,
        face_value_currency=parsed.currency,
        offer_status="candidate",
        source_id=source.id,
        source_url=parsed.url or source.base_url,
        demo_only=False,
    )
    session.add(offer)
    session.flush()
    return offer


def match_and_alert_fare(session: Session, *, limit_watches: int = 20) -> dict[str, int]:
    """对启用中的 FareWatch 做匹配并生成提醒；站内+尝试本机外送。"""
    from app.services.fare.service import evaluate_alerts_for_match, match_watch_to_deals
    from app.services.notify.delivery import send_notification

    watches = session.scalars(
        select(FareWatch).where(FareWatch.enabled == True).limit(limit_watches)  # noqa: E712
    ).all()
    matched = 0
    alerted = 0
    for w in watches:
        matches = match_watch_to_deals(session, w)
        matched += len(matches)
        for m in matches:
            alert = evaluate_alerts_for_match(session, m, watch=w)
            if alert:
                alerted += 1
                if alert.delivery_status == "pending":
                    n = send_notification(
                        session,
                        None,
                        kind="fare_alert",
                        title=alert.title or "机票提醒",
                        body=alert.body or "",
                        severity="warning" if alert.alert_level != "digest" else "info",
                        entity_type="fare_alert",
                        entity_id=alert.id,
                    )
                    if n and n.body and "delivered" in (n.body or ""):
                        alert.delivery_status = "delivered"
                    elif n:
                        alert.delivery_status = "recorded"
    session.flush()
    return {"watches": len(watches), "matches": matched, "alerts": alerted}


async def fetch_source(
    session: Session,
    settings: Settings,
    source: Source,
    *,
    module: str = "fare",
    dry_run: bool = False,
    persist_signals: bool = True,
    country_code: str | None = None,
) -> dict[str, Any]:
    """抓取单一来源；dry_run 不访问网络。manual_only 禁止自动抓取。"""
    if source.status == "manual_only" or source.access_policy == "manual_only":
        return {
            "source_id": source.id,
            "status": "manual_only",
            "error_code": "SOURCE_FETCH_DENIED",
            "message": "来源仅限人工导入，不自动抓取",
        }
    if source.access_policy in ("forbidden",) or source.allowed_fetch_mode == "none":
        return {
            "source_id": source.id,
            "status": "denied",
            "error_code": ErrorCode.SOURCE_FETCH_DENIED.value,
            "message": "来源策略禁止自动抓取",
        }
    if dry_run:
        return {
            "source_id": source.id,
            "status": "dry_run",
            "message": "未访问外部网络",
        }

    adapter = adapter_for(source, settings)
    if adapter is None:
        return {
            "source_id": source.id,
            "status": "manual_only",
            "message": "无可用自动抓取适配器；请使用人工粘贴入口",
        }

    result = await adapter.fetch(source.base_url)
    cand = ingest_fetch_result(session, source, result, module=module)
    # 相对链接基准：优先最终 URL（重定向后）
    parse_base = (result.final_url or source.base_url) if result.ok else source.base_url
    parsed: list[ParsedSignal] = []
    if result.ok and result.text:
        effective_module = module if module != "all" else (source.module or "fare")
        if effective_module == "trip" and hasattr(adapter, "parse_trip"):
            parsed = adapter.parse_trip(result.text, url=parse_base)[:20]  # type: ignore[attr-defined]
        else:
            parsed = adapter.parse(result.text, url=parse_base)[:20]

    effective_module = module if module != "all" else (source.module or "fare")
    if cand is not None:
        cand.module = effective_module
    signals_persisted = 0
    offers_persisted = 0
    if persist_signals and parsed:
        if effective_module == "fare":
            sigs = materialize_fare_signals(
                session, source, parsed, candidate_url=cand.url if cand else None
            )
            signals_persisted = len(sigs)
        elif effective_module == "trip":
            cc = country_code or source.country_code
            before = {
                p.title[:400]
                for p in parsed
                if session.scalar(
                    select(BenefitOffer.id).where(
                        BenefitOffer.title == p.title[:400],
                        BenefitOffer.source_id == source.id,
                    )
                )
                is None
            }
            for p in parsed:
                materialize_trip_offer(session, source, p, country_code=cc)
            offers_persisted = len(before)

    source.last_fetch_at = utc_now()
    session.flush()

    preview = [
        {
            "title": s.title,
            "reported_total": s.reported_total,
            "origin": s.origin_airport,
            "destination": s.destination_airport,
            "confidence": s.confidence,
            "deal_types": s.deal_types,
        }
        for s in parsed[:10]
    ]
    return {
        "source_id": source.id,
        "module": effective_module,
        "status": "ok" if result.ok else "failed",
        "candidate_id": cand.id if cand else None,
        "error_code": result.error_code,
        "message": result.message,
        "signal_preview_count": len(parsed),
        "signals_persisted": signals_persisted,
        "offers_persisted": offers_persisted,
        "signals": preview,
    }


async def run_discovery(
    session: Session,
    settings: Settings,
    *,
    module: str = "fare",
    dry_run: bool = True,
    limit: int = 10,
    persist_signals: bool = True,
    after_fetch: bool = True,
    country_code: str | None = None,
    enforce_cooldown: bool = True,
) -> list[dict[str, Any]]:
    """status+module(+国家) → 冷却过滤 → last_fetch 轮询 → 抓取。"""
    from datetime import timedelta as _td

    from app.core.timeutils import ensure_aware_utc

    now = utc_now()
    stmt = select(Source).where(Source.status == "active")
    if module != "all":
        stmt = stmt.where(Source.module.in_((module, "shared")))
    if country_code:
        cc = country_code.upper()
        stmt = stmt.where((Source.country_code == cc) | (Source.country_code.is_(None)))
    stmt = stmt.order_by(Source.last_fetch_at.is_(None).desc(), Source.last_fetch_at, Source.name)
    all_sources = list(session.scalars(stmt).all())
    sources: list[Source] = []
    for s in all_sources:
        if enforce_cooldown and not dry_run and s.last_fetch_at is not None:
            interval_h = max(1, s.fetch_interval_hours or 24)
            last = ensure_aware_utc(s.last_fetch_at)
            if last and (now - last) < _td(hours=interval_h):
                continue
        sources.append(s)
        if len(sources) >= limit:
            break
    out = []
    for s in sources:
        offer_cc = s.country_code
        out.append(
            await fetch_source(
                session,
                settings,
                s,
                module=module,
                dry_run=dry_run,
                persist_signals=persist_signals,
                country_code=offer_cc,
            )
        )
    session.flush()
    if after_fetch and not dry_run:
        if module in ("fare", "all"):
            stats = match_and_alert_fare(session)
            out.append({"source_id": None, "status": "post_match", **stats})
        if module in ("trip", "all"):
            from app.models import Trip
            from app.services.trips.service import rematch_trip_benefits

            trips = session.scalars(select(Trip).where(Trip.archived == False)).all()  # noqa: E712
            for t in trips:
                rematch_trip_benefits(session, t)
            out.append(
                {
                    "source_id": None,
                    "status": "post_trip_rematch",
                    "trips": len(trips),
                }
            )
    return out
