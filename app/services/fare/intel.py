"""P1 国际特价机票情报：过滤、排序、用户反馈（情报模式，不依赖实时报价）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FareDealSignal, Source
from app.services.airports.china import match_signal_origins

# 用户反馈写入 signal_status（避免重迁移）；预留未来独立反馈表
FEEDBACK_STATES = {
    "bookmarked",
    "read",
    "not_interested",
    "expired_reported",
    "price_mismatch_reported",
}
CONTENT_STATES = {"discovered", "parsed", "intel_active", "intel_expired"}


@dataclass
class IntelFilter:
    preferred_origins: list[str]
    include_hkg: bool = False
    include_mfm: bool = False
    exclude_domestic: bool = True
    hide_expired: bool = True
    categories: list[str] | None = None  # None = all
    max_age_days: int | None = 30


def _deal_types(signal: FareDealSignal) -> list[str]:
    try:
        d = json.loads(signal.deal_types or "[]")
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _is_expired(signal: FareDealSignal, now: datetime) -> bool:
    st = (signal.signal_status or "").lower()
    if st in {"intel_expired", "expired_reported"}:
        return True
    title = signal.title or ""
    if "过期" in title or "expired" in title.lower():
        return True
    if signal.published_at_utc:
        pub = signal.published_at_utc
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=UTC)
        if now - pub > timedelta(days=60):
            return True
    return False


def classify_signal(signal: FareDealSignal) -> str:
    types = set(_deal_types(signal))
    if "error_fare" in types:
        return "suspected_bug_fare"
    if "fuel_surcharge_anomaly" in types:
        return "fuel_anomaly"
    if "hidden_city" in types:
        return "hidden_city"
    if "award_space" in types or "mileage" in types:
        return "mileage_promo"
    if "flash_sale" in types:
        return "official_or_flash_promo"
    if signal.source_type == "community":
        return "community_deal_tip"
    return "other_intl_deal"


def build_intel_view(
    session: Session,
    filt: IntelFilter,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """组装 P1 情报列表：国际过滤 + 出发地匹配 + 排序 + 过期。"""
    now_n = now or datetime.now(UTC)
    rows = session.scalars(
        select(FareDealSignal).order_by(FareDealSignal.created_at_utc.desc()).limit(limit * 3)
    ).all()
    out: list[dict[str, Any]] = []
    for s in rows:
        expired = _is_expired(s, now_n)
        if filt.hide_expired and expired:
            continue
        intl = None
        if s.origin_airport and s.destination_airport:
            from app.services.airports.china import is_international_pair

            intl = is_international_pair(s.origin_airport, s.destination_airport)
            if filt.exclude_domestic and intl is False:
                continue
        cat = classify_signal(s)
        if filt.categories and cat not in filt.categories:
            continue
        match = match_signal_origins(
            s.origin_airport,
            filt.preferred_origins,
            signal_dest=s.destination_airport,
            require_international=filt.exclude_domestic,
        )
        # 无机场但标题像国际机票：保留为可能匹配
        if not s.origin_airport and not match.get("match"):
            continue
        if not match.get("match") and s.origin_airport:
            continue
        age_score = 0
        if s.published_at_utc:
            pub = s.published_at_utc
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=UTC)
            age_score = max(0, (now_n - pub).days)
        priority = 0
        if cat == "suspected_bug_fare":
            priority -= 50
        if cat == "fuel_anomaly":
            priority -= 30
        if match.get("reason") == "exact_iata":
            priority -= 20
        if s.reported_total:
            priority -= 5
        priority += age_score * 2
        if (s.signal_status or "") in FEEDBACK_STATES:
            priority += 100  # 已处理降权
        src = session.get(Source, s.source_id) if s.source_id else None
        out.append(
            {
                "signal_id": s.id,
                "title": s.title,
                "summary_zh": _zh_summary(s),
                "airline": s.airline,
                "origin_airport": s.origin_airport,
                "destination_airport": s.destination_airport,
                "reported_total": s.reported_total,
                "currency": s.currency,
                "category": cat,
                "deal_types": _deal_types(s),
                "source_url": s.original_url,
                "source_name": src.name if src else None,
                "published_at": s.published_at_utc.isoformat() if s.published_at_utc else None,
                "found_at": s.created_at_utc.isoformat() if s.created_at_utc else None,
                "expired": expired,
                "international": intl,
                "confidence": s.confidence,
                "signal_status": s.signal_status,
                "priority": priority,
                "is_live_bookable_price": False,  # 情报模式硬约束
                "note": "报道/社区价格，请点击来源自行核实并购买",
            }
        )
    out.sort(key=lambda x: (x["priority"], x["found_at"] or ""))
    return out[:limit]


def _zh_summary(s: FareDealSignal) -> str:
    bits = [f"情报分类={classify_signal(s)}"]
    if s.origin_airport or s.destination_airport:
        bits.append(f"航线={s.origin_airport or '?'}→{s.destination_airport or '?'}")
    if s.reported_total is not None:
        bits.append(f"报道价 {s.reported_total}{s.currency or ''}（非实时可买）")
    bits.append("请打开来源链接自行查价")
    return "；".join(bits)


def apply_user_feedback(
    session: Session,
    signal_id: str,
    feedback: str,
) -> FareDealSignal:
    if feedback not in FEEDBACK_STATES:
        from app.core.errors import ValidationError

        raise ValidationError(f"不支持的反馈: {feedback}")
    s = session.get(FareDealSignal, signal_id)
    if s is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("信号不存在")
    s.signal_status = feedback
    session.flush()
    return s


def mark_sources_intel(session: Session) -> dict[str, int]:
    """补充 Secret Flying / Fly4Free 等公开情报源种子。"""
    from app.core.ids import new_id

    defaults = [
        {
            "name": "Secret Flying",
            "base_url": "https://www.secretflying.com/",
            "kind": "community",
            "language": "en",
            "module": "fare",
            "notes": "国际特价机票情报；非实时可买价；遵守站点条款",
        },
        {
            "name": "Fly4Free",
            "base_url": "https://www.fly4free.com/",
            "kind": "community",
            "language": "en",
            "module": "fare",
            "notes": "国际优惠机票情报；社区爆料≠官方可购",
        },
    ]
    created = 0
    for item in defaults:
        exists = session.scalar(select(Source).where(Source.base_url == item["base_url"]))
        if exists:
            continue
        session.add(
            Source(
                id=new_id(),
                base_url=item["base_url"],
                kind=item["kind"],
                language=item["language"],
                country_code=None,
                access_policy="public_fetch",
                allowed_fetch_mode="httpx",
                module=item["module"],
                status="active",
                name=item["name"],
                notes=item["notes"],
            )
        )
        created += 1
    session.flush()
    return {"created": created}
