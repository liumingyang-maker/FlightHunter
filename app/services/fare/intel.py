"""P1 国际特价机票情报：过滤、排序、用户反馈（情报模式，不依赖实时报价）。"""

from __future__ import annotations

import json
import re
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


def _norm_title_key(title: str) -> str:
    """跨来源去重键：去标点/空白/常见噪声词，保留航线与航司线索。"""
    t = (title or "").lower()
    for ch in "，。！？、·|-—–|/\\()[]{}\"'“”‘’!?,.;:":
        t = t.replace(ch, " ")
    t = re.sub(r"\s+", " ", t).strip()
    # 去掉常见前后缀噪声
    for noise in (
        "每日机票推荐",
        "什么值得买",
        "特价机票",
        "促销",
        "sale",
        "deal",
        "from ",
        "的",
    ):
        t = t.replace(noise, " ")
    t = re.sub(r"\s+", "", t).strip()
    return t[:80]


def merge_intel_signals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一活动多来源合并；保留全部 source 链接；不误合并不同航线。"""
    groups: dict[str, dict[str, Any]] = {}
    for item in rows:
        key_parts = [
            item.get("origin_airport") or "",
            item.get("destination_airport") or "",
            _norm_title_key(item.get("title") or ""),
        ]
        key = "|".join(key_parts)
        if key in groups:
            g = groups[key]
            g.setdefault("source_urls", [])
            if item.get("source_url") and item["source_url"] not in g["source_urls"]:
                g["source_urls"].append(item["source_url"])
            g["sources"].append(
                {
                    "name": item.get("source_name"),
                    "url": item.get("source_url"),
                    "found_at": item.get("found_at"),
                }
            )
            # 保留更高优先级分类
            if item.get("priority", 0) < g.get("priority", 0):
                g["priority"] = item["priority"]
                g["category"] = item.get("category", g.get("category"))
            if not g.get("source_url") and item.get("source_url"):
                g["source_url"] = item["source_url"]
        else:
            item = dict(item)
            item["source_urls"] = [item["source_url"]] if item.get("source_url") else []
            item["sources"] = [
                {
                    "name": item.get("source_name"),
                    "url": item.get("source_url"),
                    "found_at": item.get("found_at"),
                }
            ]
            item["is_merged"] = False
            groups[key] = item
    out = list(groups.values())
    for g in out:
        g["is_merged"] = len(g.get("sources") or []) > 1
        g["source_count"] = len(g.get("sources") or [])
    out.sort(key=lambda x: (x.get("priority", 0), x.get("found_at") or ""))
    return out


_CN_CITY_TO_IATA = {
    "重庆": "CKG",
    "成都": "TFU",
    "北京": "PEK",
    "上海": "PVG",
    "广州": "CAN",
    "深圳": "SZX",
    "杭州": "HGH",
    "武汉": "WUH",
    "昆明": "KMG",
    "西安": "XIY",
    "长沙": "CSX",
    "青岛": "TAO",
    "南京": "NKG",
    "厦门": "XMN",
    "天津": "TSN",
    "郑州": "CGO",
    "三亚": "SYX",
    "哈尔滨": "HRB",
    "沈阳": "SHE",
    "大连": "DLC",
    "济南": "TNA",
    "福州": "FOC",
    "南宁": "NNG",
    "贵阳": "KWE",
    "温州": "WNZ",
    "宁波": "NGB",
    "无锡": "WUX",
    "珠海": "ZUH",
    "海口": "HAK",
    "银川": "INC",  # 国内
    "西宁": "XNN",
    "兰州": "LHW",
    "乌鲁木齐": "URC",
    "拉萨": "LXA",
    "桂林": "KWL",
    "丽江": "LJG",
    "西双版纳": "JHG",
    "北海": "BHY",
    "张家界": "DYG",
    "敦煌": "DNH",
    "井冈山": "JGS",
    "喀什": "KHG",
    "呼和浩特": "HET",
    "太原": "TYN",
    "石家庄": "SJW",
    "合肥": "HFE",
    "南昌": "KHN",
    "长春": "CGQ",
}


def _maybe_fill_origin_from_title(signal: FareDealSignal) -> None:
    """从标题提取中国出发城市 IATA；仅在无 origin 时填充。"""
    if signal.origin_airport:
        return
    title = signal.title or ""
    for city, iata in _CN_CITY_TO_IATA.items():
        if city in title:
            signal.origin_airport = iata
            return


_NOISE_INTEL = (
    "credit card",
    "points &",
    "review:",
    "review：",
    "card review",
    "membership",
    "信用卡",
    "里程卡",
    "酒店测评",
)


def _looks_noise_intel(title: str) -> bool:
    low = (title or "").lower()
    return any(n in low for n in _NOISE_INTEL)


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
        if _looks_noise_intel(s.title or ""):
            continue
        # 无价格/无机场/无目的地的“怎么买机票”类建议不进情报
        title_l = (s.title or "")
        if (
            s.reported_total is None
            and not s.origin_airport
            and not s.destination_airport
            and any(k in title_l for k in ("怎么买", "避坑", "有坑", "维权", "如何买", "哪里订"))
        ):
            continue
        _maybe_fill_origin_from_title(s)
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
        # 明确支持该城市：标题含城市名且 origin 匹配，或 origin 精确
        # 多城市/全国：origin 为空但标题含「全国/多地」或匹配 preferred 中任一城市中文名
        city_match_level = "origin_unknown"
        title = s.title or ""
        if s.origin_airport and s.origin_airport.upper() in filt.preferred_origins:
            city_match_level = "explicit_city"
        elif not s.origin_airport and any(
            k in title
            for k in ("全国", "多地", "北上广", "全国多地", "China-wide", "nationwide")
        ):
            city_match_level = "national_multi_city_pending"
        elif not s.origin_airport and any(
            c in title
            for c in ("重庆", "成都", "上海", "北京", "广州", "深圳", "杭州", "武汉", "昆明")
        ):
            city_match_level = "city_named_in_title_pending_iata"
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
                "city_match_level": city_match_level,
                "note": "报道/社区价格，请点击来源自行核实并购买",
            }
        )
    out.sort(key=lambda x: (x["priority"], x["found_at"] or ""))
    merged = merge_intel_signals(out)
    return merged[:limit]


def _zh_summary(s: FareDealSignal) -> str:
    bits = [f"情报分类={classify_signal(s)}"]
    if s.origin_airport or s.destination_airport:
        bits.append(f"航线={s.origin_airport or '?'}→{s.destination_airport or '?'}")
    if s.reported_total is not None:
        bits.append(f"报道价 {s.reported_total}{s.currency or ''}（非实时可买）")
    bits.append("请打开来源链接自行查价")
    return "；".join(bits)


def intel_quality_stats(
    session: Session,
    filt: IntelFilter | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """质量统计：新发现/城市匹配/全国待核实/过期/重复/链接（不自动点外链时 link_checked=None）。"""
    import httpx

    from app.services.airports.china import expand_origin_selection

    now_n = now or datetime.now(UTC)
    filt = filt or IntelFilter(
        preferred_origins=expand_origin_selection(multi=["CKG", "TFU", "CTU"])
    )
    all_rows = session.scalars(
        select(FareDealSignal).order_by(FareDealSignal.created_at_utc.desc()).limit(100)
    ).all()
    day_ago = now_n - timedelta(hours=24)
    expired = 0
    for s in all_rows:
        if _is_expired(s, now_n):
            expired += 1
    view = build_intel_view(session, filt, limit=50)
    by_level: dict[str, int] = {}
    for v in view:
        lvl = v.get("city_match_level") or "origin_unknown"
        by_level[lvl] = by_level.get(lvl, 0) + 1
    merged = sum(1 for v in view if v.get("is_merged"))

    def _naive(dt) -> datetime | None:
        if not dt:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(UTC).replace(tzinfo=None)
        return dt

    new_24h = sum(
        1
        for s in all_rows
        if _naive(s.created_at_utc) and _naive(s.created_at_utc) >= day_ago
    )
    # 抽样检查链接（最多 8 条，避免打爆）
    link_checked = 0
    link_ok = 0
    link_bad = 0
    headers = {"User-Agent": "FlightHunter-Bot/1.0 (quality stats)"}
    for v in view[:8]:
        url = v.get("source_url")
        if not url:
            continue
        link_checked += 1
        try:
            r = httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
            if r.status_code < 400:
                link_ok += 1
            else:
                link_bad += 1
        except Exception:
            link_bad += 1
    return {
        "generated_at": now_n.isoformat(),
        "signals_total_sampled": len(all_rows),
        "signals_new_24h": new_24h,
        "expired_flagged": expired,
        "intel_view_count": len(view),
        "city_match_levels": by_level,
        "merged_duplicate_groups": merged,
        "link_sample_checked": link_checked,
        "link_sample_ok": link_ok,
        "link_sample_bad": link_bad,
        "note": "HTTP 200 ≠ 优惠仍有效；过期/重复单列",
    }


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
