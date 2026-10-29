"""机票雷达：信号导入、去重、匹配、成本、风险。"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, date, datetime
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.ids import new_id, sha256_text, stable_json_hash
from app.core.state import (
    FareDealStatus,
    FareDealSubtype,
    FareQuoteStatus,
    FareRiskCode,
    FareRiskTier,
    FareSignalStatus,
)
from app.models import (
    FareAlert,
    FareDeal,
    FareDealSignal,
    FarePriceHistory,
    FareQuote,
    FareRiskEvidence,
    FareWatch,
    FareWatchMatch,
)
from app.schemas.domain import (
    FareCostBreakdown,
    FareSignalImport,
    FareWatchCreate,
)


def _parse_subtypes(types: Iterable[str]) -> list[str]:
    allowed = {m.value for m in FareDealSubtype}
    out = []
    for t in types:
        if t in allowed:
            out.append(t)
        elif t:
            out.append(FareDealSubtype.UNCLASSIFIED.value)
    return out or [FareDealSubtype.UNCLASSIFIED.value]


def _risk_tier_for_subtypes(subtypes: list[str]) -> tuple[str, list[str]]:
    """高风险独立分栏；由低价不能掩盖风险。"""
    risk_codes: list[str] = []
    high = False
    review = False
    if FareDealSubtype.ERROR_FARE.value in subtypes:
        risk_codes.append(FareRiskCode.ERROR_FARE.value)
        risk_codes.append(FareRiskCode.MISPRICE_WITHDRAWAL.value)
        review = True
    if FareDealSubtype.FUEL_SURCHARGE_ANOMALY.value in subtypes:
        risk_codes.append(FareRiskCode.FUEL_ANOMALY.value)
        review = True
    if FareDealSubtype.HIDDEN_CITY.value in subtypes:
        risk_codes.append(FareRiskCode.HIDDEN_CITY.value)
        risk_codes.append(FareRiskCode.TERMS_VIOLATION_RISK.value)
        high = True
    if FareDealSubtype.AWARD_SPACE.value in subtypes or FareDealSubtype.WAITLIST.value in subtypes:
        risk_codes.append(FareRiskCode.COMMUNITY_UNVERIFIED.value)
        review = True
    if high:
        return FareRiskTier.HIGH_RISK.value, risk_codes
    if review:
        return FareRiskTier.NEEDS_REVIEW.value, risk_codes
    return FareRiskTier.STANDARD.value, risk_codes


def _dedup_key(origin: str | None, dest: str | None, window: str, airline: str | None) -> str:
    return sha256_text(f"{origin or '?'}|{dest or '?'}|{window or 'flex'}|{airline or '?'}")[:32]


def import_signal(session: Session, payload: FareSignalImport) -> tuple[FareDeal, FareDealSignal]:
    """导入社区爆料。标记为信号，绝不直接写成可买报价。"""
    if not payload.title.strip():
        raise ValidationError("爆料标题不能为空")

    window = None
    if payload.travel_window_start or payload.travel_window_end:
        window = f"{payload.travel_window_start}~{payload.travel_window_end}"

    subtypes = _parse_subtypes(payload.deal_types)
    dedup = _dedup_key(payload.origin_airport, payload.destination_airport, window, payload.airline)

    deal = session.scalar(select(FareDeal).where(FareDeal.dedup_key == dedup))
    now = datetime.now(UTC)
    if deal is None:
        tier, risk_codes = _risk_tier_for_subtypes(subtypes)
        deal = FareDeal(
            id=new_id(),
            dedup_key=dedup,
            origin=payload.origin_airport,
            destination=payload.destination_airport,
            travel_date_hint=window,
            travel_window_start=payload.travel_window_start,
            travel_window_end=payload.travel_window_end,
            airline=payload.airline,
            offer_subtypes=json.dumps(subtypes),
            status=FareDealStatus.PRICE_UNCONFIRMED.value,
            risk_tier=tier,
            first_seen_utc=now,
            last_seen_utc=now,
            link=payload.original_url,
        )
        session.add(deal)
        session.flush()
        for code in risk_codes:
            session.add(
                FareRiskEvidence(
                    id=new_id(),
                    deal_id=deal.id,
                    risk_code=code,
                    cited_url=payload.original_url,
                    original_statement=payload.raw_claim_text[:2000],
                    retrieved_at=now,
                    review_state="pending",
                )
            )
    else:
        deal.last_seen_utc = now
        existing_subtypes = set(json.loads(deal.offer_subtypes or "[]"))
        existing_subtypes.update(subtypes)
        deal.offer_subtypes = json.dumps(sorted(existing_subtypes))
        tier, risk_codes = _risk_tier_for_subtypes(sorted(existing_subtypes))
        deal.risk_tier = tier

    evidence_hash = sha256_text(payload.evidence_text or payload.raw_claim_text)
    signal = FareDealSignal(
        id=new_id(),
        deal_id=deal.id,
        source_id=payload.source_id,
        original_url=payload.original_url,
        title=payload.title,
        raw_claim_text=payload.raw_claim_text,
        published_at_utc=payload.published_at_utc,
        reported_total=payload.reported_total,
        currency=payload.currency,
        party_size=payload.party_size,
        taxes_included=payload.taxes_included,
        origin_airport=payload.origin_airport,
        destination_airport=payload.destination_airport,
        airline=payload.airline,
        deal_types=json.dumps(subtypes),
        evidence_text=payload.evidence_text,
        text_evidence_hash=evidence_hash,
        source_type="user_supplied" if payload.user_supplied else "community",
        signal_status=FareSignalStatus.PARSED.value,
        confidence="low" if payload.user_supplied else "medium",
        user_supplied=payload.user_supplied,
    )
    session.add(signal)
    session.flush()
    return deal, signal


def create_fare_watch(session: Session, payload: FareWatchCreate) -> FareWatch:
    watch = FareWatch(
        id=new_id(),
        name=payload.name,
        owner_profile_id=payload.owner_profile_id,
        trip_id=payload.trip_id,
        origin_airports=json.dumps(payload.origin_airports),
        destination_scope=payload.destination_scope,
        destination_airports=json.dumps(payload.destination_airports),
        destination_countries=json.dumps(payload.destination_countries),
        exclude_destination_countries=json.dumps(payload.exclude_destination_countries),
        depart_window_start=payload.depart_window_start,
        depart_window_end=payload.depart_window_end,
        stay_days_min=payload.stay_days_min,
        stay_days_max=payload.stay_days_max,
        trip_type=payload.trip_type,
        cabins=json.dumps(payload.cabins),
        adults=payload.adults,
        children=payload.children,
        require_checked_baggage=payload.require_checked_baggage,
        max_total_cost_cny=payload.max_total_cost_cny,
        min_discount_vs_median=payload.min_discount_vs_median,
        max_positioning_cost_cny=payload.max_positioning_cost_cny,
        accept_error_fares=payload.accept_error_fares,
        accept_hidden_city=payload.accept_hidden_city,
        accept_fuel_anomaly=payload.accept_fuel_anomaly,
        enabled=payload.enabled,
        scan_status="idle",
    )
    session.add(watch)
    session.flush()
    return watch


def match_watch_to_deals(session: Session, watch: FareWatch) -> list[FareWatchMatch]:
    """硬约束匹配：目的地/日期/风险偏好；输出可解释 reason_codes。"""
    origins = set(json.loads(watch.origin_airports or "[]"))
    dest_scope = watch.destination_scope
    dest_airports = set(json.loads(watch.destination_airports or "[]"))
    dest_countries = set(json.loads(watch.destination_countries or "[]"))
    exclude = set(json.loads(watch.exclude_destination_countries or "[]"))
    accept_error = watch.accept_error_fares
    accept_hidden = watch.accept_hidden_city
    accept_fuel = watch.accept_fuel_anomaly

    deals = session.scalars(
        select(FareDeal).where(FareDeal.status != FareDealStatus.WITHDRAWN.value)
    ).all()

    matches: list[FareWatchMatch] = []
    now = datetime.now(UTC)
    for deal in deals:
        reasons: list[str] = []
        # 出发：信号可能无 origin，标 unknown
        if deal.origin and origins and deal.origin not in origins:
            continue
        if deal.origin is None:
            reasons.append("ORIGIN_UNKNOWN")

        # 目的地
        if dest_scope == "explicit":
            if (
                deal.destination
                and dest_airports
                and deal.destination not in dest_airports
                and not dest_countries
            ):
                continue
            if (
                deal.destination
                and dest_airports
                and deal.destination not in dest_airports
                and dest_countries
            ):
                reasons.append("DEST_COUNTRY_UNVERIFIED")
        # 排除国家（机场码无法直接映射时保留检查）
        if deal.destination and deal.destination in exclude:
            continue

        # 日期
        date_match = "unknown"
        if watch.depart_window_start and watch.depart_window_end:
            if deal.travel_window_start and deal.travel_window_end:
                if (
                    deal.travel_window_end >= watch.depart_window_start
                    and deal.travel_window_start <= watch.depart_window_end
                ):
                    date_match = "match"
                else:
                    continue
            elif deal.travel_date_hint:
                date_match = "partial"
            else:
                date_match = "unknown"
                reasons.append("DEPART_WINDOW_UNKNOWN")
        else:
            date_match = "any"

        # 风险偏好
        subtypes = set(json.loads(deal.offer_subtypes or "[]"))
        risk_match = "standard"
        if (
            FareDealSubtype.HIDDEN_CITY.value in subtypes
            and not accept_hidden
            and deal.risk_tier == FareRiskTier.HIGH_RISK.value
        ):
            continue
        if FareDealSubtype.ERROR_FARE.value in subtypes and not accept_error:
            reasons.append("ERROR_FARE_NEEDS_OPT_IN")
            risk_match = "needs_review"
        if FareDealSubtype.FUEL_SURCHARGE_ANOMALY.value in subtypes and not accept_fuel:
            reasons.append("FUEL_ANOMALY_NEEDS_OPT_IN")
            risk_match = "needs_review"
        if deal.risk_tier == FareRiskTier.HIGH_RISK.value:
            risk_match = "high_risk"
            reasons.append("HIGH_RISK_SEPARATE")

        # 人数：社区爆料 party_size 与 watch.adults 不一致时提示
        passenger_match = "unknown"
        signals = session.scalars(
            select(FareDealSignal).where(FareDealSignal.deal_id == deal.id)
        ).all()
        party_sizes = [s.party_size for s in signals if s.party_size]
        if party_sizes:
            if any(p != watch.adults for p in party_sizes):
                passenger_match = "mismatch"
                reasons.append("PARTY_SIZE_MISMATCH")
            else:
                passenger_match = "match"
        else:
            reasons.append("PARTY_SIZE_UNKNOWN")

        # 价格状态：仅社区爆料 → not_queried
        latest_quote = session.scalar(
            select(FareQuote)
            .where(FareQuote.deal_id == deal.id)
            .order_by(FareQuote.observed_at_utc.desc())
            .limit(1)
        )
        trusted = (
            _is_trusted_quote(latest_quote, watch_adults=watch.adults, deal=deal, watch=watch)
            if latest_quote
            else None
        )
        if latest_quote and trusted:
            price_status = FareQuoteStatus.OBSERVED.value
        elif latest_quote:
            price_status = latest_quote.quote_status or FareQuoteStatus.PROVIDER_UNKNOWN.value
            reasons.append("QUOTE_NOT_TRUSTED_FOR_VERIFIED")
            if not latest_quote.availability_confirmed:
                reasons.append("QUOTE_INVENTORY_UNCONFIRMED")
            if latest_quote.depart_date is None:
                reasons.append("QUOTE_DATE_MISSING")
            elif (
                watch.depart_window_start and latest_quote.depart_date < watch.depart_window_start
            ) or (watch.depart_window_end and latest_quote.depart_date > watch.depart_window_end):
                reasons.append("QUOTE_OUTSIDE_WATCH_WINDOW")
            if (latest_quote.currency or "").upper() != "CNY":
                reasons.append("QUOTE_CURRENCY_MISMATCH")
            if latest_quote.tax_included is None:
                reasons.append("QUOTE_TAX_UNKNOWN")
        else:
            price_status = FareQuoteStatus.NOT_QUERIED.value
            reasons.append("NO_AUTHORIZED_QUOTE")

        net_min = None
        net_max = None
        if latest_quote and latest_quote.total_price is not None and trusted:
            net_min = latest_quote.total_price
            net_max = latest_quote.total_price
        else:
            for s in signals:
                if s.reported_total is not None:
                    net_min = (
                        s.reported_total if net_min is None else min(net_min, s.reported_total)
                    )
                    net_max = (
                        s.reported_total if net_max is None else max(net_max, s.reported_total)
                    )
            if net_min is not None:
                reasons.append("PRICE_FROM_COMMUNITY_ONLY")

        if (
            watch.max_total_cost_cny is not None
            and net_max is not None
            and net_max > watch.max_total_cost_cny
        ):
            reasons.append("OVER_BUDGET")

        existing = session.scalar(
            select(FareWatchMatch).where(
                FareWatchMatch.watch_id == watch.id,
                FareWatchMatch.deal_id == deal.id,
            )
        )
        if existing:
            existing.price_status = price_status
            existing.date_match = date_match
            existing.passenger_match = passenger_match
            existing.risk_match = risk_match
            existing.net_cost_min = net_min
            existing.net_cost_max = net_max
            existing.reason_codes = json.dumps(reasons)
            existing.evaluated_at_utc = now
            matches.append(existing)
        else:
            m = FareWatchMatch(
                id=new_id(),
                watch_id=watch.id,
                deal_id=deal.id,
                price_status=price_status,
                date_match=date_match,
                passenger_match=passenger_match,
                risk_match=risk_match,
                net_cost_min=net_min,
                net_cost_max=net_max,
                reason_codes=json.dumps(reasons),
                evaluated_at_utc=now,
            )
            session.add(m)
            matches.append(m)
    session.flush()
    watch.last_scanned_at = now
    watch.scan_status = "idle"
    return matches


def compute_cost_breakdown(
    *,
    base_ticket_total: float | None = None,
    taxes: float | None = None,
    positioning: float | None = None,
    baggage: float | None = None,
    overnight: float | None = None,
    other: float | None = None,
    currency: str = "CNY",
) -> FareCostBreakdown:
    """完整出行成本；未知字段不假精确。"""
    unknown: list[str] = []
    known_sum = 0.0
    critical = {
        "base_ticket_total": base_ticket_total,
        "required_taxes_and_fees": taxes,
        "positioning": positioning,
        "baggage": baggage,
    }
    for name, value in critical.items():
        if value is None:
            unknown.append(name)
        else:
            known_sum += value
    # 可选费用：有值则计入；无值仅备注，不阻断上界
    optional_unknown: list[str] = []
    for name, value in (
        ("unavoidable_overnight", overnight),
        ("other_required_cost", other),
    ):
        if value is None:
            optional_unknown.append(name)
        else:
            known_sum += value

    if unknown:
        total_min = known_sum if base_ticket_total is not None else None
        total_max = None
        notes = ["未含未知关键费用，不给出确定上界"]
    else:
        total_min = known_sum
        total_max = known_sum
        notes = []
    # 可选费用未知时：上界仍不可假精确（审核 I7）
    if optional_unknown:
        total_max = None
        notes.append("可选必要费用未知，上界未知")

    return FareCostBreakdown(
        base_ticket_total=base_ticket_total,
        required_taxes_and_fees=taxes,
        positioning=positioning,
        baggage=baggage,
        unavoidable_overnight=overnight,
        other_required_cost=other,
        currency=currency,
        total_min=total_min,
        total_max=total_max,
        unknown_fields=unknown + optional_unknown,
        notes=notes,
    )


def historical_median_for_route(
    session: Session,
    origin: str,
    destination: str,
    *,
    min_samples: int = 5,
) -> tuple[float | None, int]:
    """样本不足返回 (None, n)，禁止假“历史最低”。"""
    rows = session.scalars(
        select(FarePriceHistory).where(
            FarePriceHistory.origin == origin.upper(),
            FarePriceHistory.destination == destination.upper(),
        )
    ).all()
    if len(rows) < min_samples:
        return None, len(rows)
    return median(r.total_price for r in rows), len(rows)


_BANNED_TRUSTED_PROVIDER = frozenset(
    {
        "community",
        "user_supplied",
        "manual_share",
        "totally_unregistered_provider",
        "unknown",
        "anonymous",
    }
)


def _provider_whitelist(settings=None) -> set[str]:
    """白名单：优先注入的 Settings；否则 load_settings。空集 = 禁止 urgent_verified。"""
    try:
        if settings is not None:
            return {p.lower() for p in settings.airfare_radar.trusted_quote_providers}
        from app.config import load_settings

        s = load_settings()
        return {p.lower() for p in s.airfare_radar.trusted_quote_providers}
    except Exception:
        return set()


def _is_trusted_quote(
    quote: FareQuote,
    *,
    watch_adults: int,
    deal: FareDeal | None = None,
    whitelist: set[str] | None = None,
    settings=None,
    expected_currency: str = "CNY",
    watch: FareWatch | None = None,
) -> bool:
    """可信可购报价全链门槛：
    白名单 + TTL + 库存确认 + 出发日 + 人数 + 航线 + 币种 + **出发日落在 watch 窗口**。
    """
    if quote is None or quote.total_price is None:
        return False
    provider = (quote.provider or "").lower().strip()
    if not provider or provider in _BANNED_TRUSTED_PROVIDER:
        return False
    if "community" in provider or "user" in provider:
        return False
    allowed = _provider_whitelist(settings) if whitelist is None else whitelist
    if provider not in allowed:
        return False
    if not quote.availability_confirmed:
        return False
    if quote.depart_date is None:
        return False
    if (quote.currency or "").upper() != expected_currency.upper():
        return False
    if quote.tax_included is None:
        return False
    from app.core.timeutils import ensure_aware_utc, utc_now

    if quote.quote_expiry_utc is None:
        return False
    exp = ensure_aware_utc(quote.quote_expiry_utc)
    if exp is None or exp < utc_now():
        return False
    if quote.pax_count != watch_adults:
        return False
    if watch is not None:
        if watch.depart_window_start and quote.depart_date < watch.depart_window_start:
            return False
        if watch.depart_window_end and quote.depart_date > watch.depart_window_end:
            return False
    if deal is not None:
        if not quote.origin or not quote.destination:
            return False
        if quote.origin.upper() != (deal.origin or "").upper():
            return False
        if quote.destination.upper() != (deal.destination or "").upper():
            return False
    return quote.quote_status not in (
        FareQuoteStatus.EXPIRED.value,
        FareQuoteStatus.UNAVAILABLE.value,
        FareQuoteStatus.PROVIDER_UNKNOWN.value,
    )


# 禁止 urgent_verified 的 reason codes
_BLOCK_URGENT_VERIFIED = frozenset(
    {
        "OVER_BUDGET",
        "PARTY_SIZE_MISMATCH",
        "PARTY_SIZE_UNKNOWN",
        "QUOTE_NOT_TRUSTED_FOR_VERIFIED",
        "NO_AUTHORIZED_QUOTE",
        "PRICE_FROM_COMMUNITY_ONLY",
        "HIGH_RISK_SEPARATE",
        "QUOTE_ROUTE_MISMATCH",
        "QUOTE_TTL_MISSING",
        "QUOTE_INVENTORY_UNCONFIRMED",
        "QUOTE_DATE_MISSING",
        "QUOTE_CURRENCY_MISMATCH",
        "QUOTE_TAX_UNKNOWN",
        "QUOTE_OUTSIDE_WATCH_WINDOW",
    }
)


def evaluate_alerts_for_match(
    session: Session, match: FareWatchMatch, *, watch: FareWatch
) -> FareAlert | None:
    """三级提醒；仅白名单可信报价且无阻断 reason 可 urgent_verified。"""
    deal = session.get(FareDeal, match.deal_id)
    if deal is None:
        return None
    reasons = json.loads(match.reason_codes or "[]")

    quote = None
    if match.price_status == FareQuoteStatus.OBSERVED.value:
        quote = session.scalar(
            select(FareQuote)
            .where(FareQuote.deal_id == deal.id)
            .order_by(FareQuote.observed_at_utc.desc())
            .limit(1)
        )
    trusted = bool(
        quote
        and _is_trusted_quote(
            quote,
            watch_adults=watch.adults,
            deal=deal,
            whitelist=_provider_whitelist(),
            watch=watch,
        )
    )
    high_risk = match.risk_match == FareRiskTier.HIGH_RISK.value
    blocked = bool(set(reasons) & _BLOCK_URGENT_VERIFIED)
    # 预算：watch 有上限且报价超限
    if (
        watch.max_total_cost_cny is not None
        and quote is not None
        and quote.total_price is not None
        and quote.total_price > watch.max_total_cost_cny
    ):
        blocked = True
        if "OVER_BUDGET" not in reasons:
            reasons.append("OVER_BUDGET")

    if high_risk:
        level = "digest"
        suppression = "high_risk_separate"
    elif trusted and not blocked and match.risk_match == "standard":
        level = "urgent_verified"
        suppression = None
    elif trusted:
        level = "digest"
        suppression = "trusted_quote_but_blocked_reasons"
    else:
        level = "urgent_unverified"
        suppression = (
            "community_only" if "PRICE_FROM_COMMUNITY_ONLY" in reasons else "no_trusted_quote"
        )

    body_parts = [
        f"航线：{deal.origin or '?'} → {deal.destination or '?'}",
        f"风险：{deal.risk_tier}",
        f"价格状态：{match.price_status}",
    ]
    if match.net_cost_min is not None:
        body_parts.append(f"参考成本区间：{match.net_cost_min} ~ {match.net_cost_max}")
    body_parts.append("报价≠成交价；请到正规出票平台自行核验并支付。")

    title = f"{'报价更新' if trusted else '神价线索'} {deal.origin or ''}-{deal.destination or ''}"
    content_hash = stable_json_hash(
        {
            "deal": deal.id,
            "watch": watch.id,
            "price_status": match.price_status,
            "net_min": match.net_cost_min,
            "tier": deal.risk_tier,
        }
    )
    existing = session.scalar(
        select(FareAlert).where(
            FareAlert.watch_id == watch.id,
            FareAlert.deal_id == deal.id,
            FareAlert.content_hash == content_hash,
        )
    )
    if existing:
        return existing

    alert = FareAlert(
        id=new_id(),
        watch_id=watch.id,
        deal_id=deal.id,
        alert_level=level,
        content_hash=content_hash,
        delivery_status="pending",
        title=title,
        body="\n".join(body_parts),
        suppression_reason=suppression,
    )
    session.add(alert)
    session.flush()
    return alert


def record_quote(
    session: Session,
    *,
    deal_id: str | None,
    watch_id: str | None,
    provider: str,
    party_size: int,
    total_price: float | None,
    currency: str = "CNY",
    taxes_included: bool | None = None,
    baggage_included: bool | None = None,
    origin: str | None = None,
    destination: str | None = None,
    depart_date: date | None = None,
    return_date: date | None = None,
    booking_deeplink: str | None = None,
    availability_confirmed: bool = False,
    quote_expiry_utc: datetime | None = None,
) -> FareQuote:
    """记录合法报价快照。availability_confirmed 仅在源明确证实时 true。"""
    if total_price is None and not availability_confirmed:
        status = FareQuoteStatus.UNAVAILABLE.value
    else:
        status = FareQuoteStatus.OBSERVED.value

    quote = FareQuote(
        id=new_id(),
        deal_id=deal_id,
        watch_id=watch_id,
        provider=provider,
        booking_deeplink=booking_deeplink,
        observed_at_utc=datetime.now(UTC),
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        return_date=return_date,
        pax_count=party_size,
        total_price=total_price,
        currency=currency,
        tax_included=taxes_included,
        baggage_included=baggage_included,
        availability_confirmed=availability_confirmed,
        quote_expiry_utc=quote_expiry_utc,
        quote_status=status,
    )
    session.add(quote)

    if origin and destination and total_price is not None:
        session.add(
            FarePriceHistory(
                id=new_id(),
                route_key=f"{origin.upper()}-{destination.upper()}",
                origin=origin.upper(),
                destination=destination.upper(),
                depart_date=depart_date,
                pax_count=party_size,
                total_price=total_price,
                currency=currency,
                provider=provider,
                observed_at_utc=quote.observed_at_utc,
            )
        )
    session.flush()
    return quote


def mark_booked(session: Session, deal_id: str, *, method: str = "user_reported") -> FareDeal:
    deal = session.get(FareDeal, deal_id)
    if deal is None:
        raise NotFoundError("机会不存在")
    if method not in (
        "user_reported",
        "confirmed_from_authorized_source",
        "unknown",
        "canceled_by_user",
        "not_booked",
    ):
        raise ValidationError("非法购票状态")
    deal.booking_status = method
    session.flush()
    return deal
