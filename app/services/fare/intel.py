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
        now_cmp = now if now.tzinfo else now.replace(tzinfo=UTC)
        if now_cmp - pub > timedelta(days=60):
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
    for extra in ("機票優惠", "机票优惠", "起"):
        t = t.replace(extra, "")
    return t[:90]


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
    "银川": "INC",
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
    "北上广": "MULTI",  # 占位多城
}

_DEST_CITY = {
    "东京": "NRT",
    "大阪": "KIX",
    "名古屋": "NGO",
    "冲绳": "OKA",
    "首尔": "ICN",
    "釜山": "PUS",
    "曼谷": "BKK",
    "普吉": "HKT",
    "清迈": "CNX",
    "吉隆坡": "KUL",
    "新加坡": "SIN",
    "巴厘岛": "DPS",
    "河内": "HAN",
    "胡志明": "SGN",
    "香港": "HKG",
    "台北": "TPE",
    "澳门": "MFM",
    "赫尔辛基": "HEL",
    "伦敦": "LHR",
    "巴黎": "CDG",
    "法兰克福": "FRA",
    "阿姆斯特丹": "AMS",
    "洛杉矶": "LAX",
    "旧金山": "SFO",
    "纽约": "JFK",
    "温哥华": "YVR",
    "悉尼": "SYD",
    "墨尔本": "MEL",
    "奥克兰": "AKL",
    "迪拜": "DXB",
    "伊斯坦布尔": "IST",
    "贝尔格莱德": "BEG",
}

_AIRLINE_HINTS = {
    "国航": "Air China",
    "中国国际航空": "Air China",
    "东航": "China Eastern",
    "中国东方": "China Eastern",
    "南航": "China Southern",
    "中国南方": "China Southern",
    "海航": "Hainan Airlines",
    "海南航空": "Hainan Airlines",
    "川航": "Sichuan Airlines",
    "四川航空": "Sichuan Airlines",
    "厦航": "Xiamen Airlines",
    "首都航空": "Capital Airlines",
    "春秋": "Spring Airlines",
    "吉祥": "Juneyao Airlines",
    "全日空": "ANA",
    "ANA": "ANA",
    "日航": "JAL",
    "JAL": "JAL",
    "大韩": "Korean Air",
    "韩亚": "Asiana",
    "新加坡航空": "Singapore Airlines",
    "国泰": "Cathay Pacific",
    "阿联酋": "Emirates",
    "阿提哈德": "Etihad",
    "卡塔尔": "Qatar Airways",
    "美联": "United",
    "达美": "Delta",
    "美国航空": "American Airlines",
    "加拿大航空": "Air Canada",
}


_HK_MO_ORIGIN = {
    "香港": "HKG",
    "香港來回": "HKG",
    "香港往返": "HKG",
    "Hong Kong": "HKG",
    "澳门": "MFM",
    "澳門": "MFM",
    "Macau": "MFM",
    "Macao": "MFM",
}


def _strip_airline_names(title: str) -> str:
    t = title or ""
    for name in _AIRLINE_HINTS:
        t = t.replace(name, " ")
    # 常见港澳航司英文/中文
    for name in (
        "HK Express",
        "Hong Kong Express",
        "香港航空",
        "Hong Kong Airlines",
        "Cathay Pacific",
        "國泰",
        "国泰",
        "Air Hong Kong",
        "澳门航空",
        "Air Macau",
        "Peach",
        "樂桃",
        "乐桃",
    ):
        t = t.replace(name, " ")
    return t


def extract_origin_iatas_from_title(title: str) -> list[str]:
    """提取出发地；先剥航司名，再优先显式出发模式，避免目的/航司误判。"""
    t = title or ""
    body = _strip_airline_names(t)
    found: list[str] = []

    def add(code: str) -> None:
        if code and code not in found:
            found.append(code)

    # 显式：X出发 / X→Y / X -> Y / from X
    m = re.search(
        r"(重庆|成都|北京|上海|广州|深圳|杭州|武汉|昆明|香港|澳門|澳门|Hong\s*Kong|Macau|Macao)[^\dA-Za-z]{0,4}(?:出发|起飞|→|->|至|飞|來回|往返|from)",
        body,
        re.I,
    )
    if m:
        city = m.group(1)
        mapping = {
            "重庆": "CKG",
            "成都": "TFU",
            "北京": "PEK",
            "上海": "PVG",
            "广州": "CAN",
            "深圳": "SZX",
            "杭州": "HGH",
            "武汉": "WUH",
            "昆明": "KMG",
            "香港": "HKG",
            "澳門": "MFM",
            "澳门": "MFM",
        }
        if city.lower().startswith("hong"):
            add("HKG")
        elif city.lower().startswith("mac"):
            add("MFM")
        else:
            add(mapping.get(city, "HKG" if "港" in city else None))

    # 显式 IATA 对：ABC-DEF 或 ABC→DEF（两端 3 字母）
    m2 = re.findall(r"\b([A-Z]{3})\b\s*(?:→|->|-|–)\s*\b([A-Z]{3})\b", body)
    if m2:
        add(m2[0][0])

    # 北上广
    # 港澳航司品牌 → 出发地启发（无内地出发词时）
    brand_hk = bool(re.search(r"HK Express|Hong Kong Airlines|國泰|国泰|Cathay|Peach|樂桃|乐桃", t, re.I))
    if brand_hk and not re.search(
        r"(上海|北京|成都|重庆|广州|深圳|杭州|武汉|昆明).{0,6}(出发|起飞|from)", body, re.I
    ):
        add("HKG")
    if "北上广" in body:
        add("PEK")
        add("PVG")
        add("CAN")
        # 北上广/成都 等并列
        for city, iata in _CN_CITY_TO_IATA.items():
            if city == "北上广":
                continue
            if city in body:
                add(iata)
    if not found:
        # 无显式出发/品牌出发时，才把正文内地城市当出发（全国多城促销）
        for city, iata in _CN_CITY_TO_IATA.items():
            if city == "北上广":
                continue
            if city in body:
                add(iata)
                break
    if not re.search(r"(上海|北京|成都|重庆|广州|深圳|杭州|武汉|昆明).{0,6}(出发|起飞|from)", body, re.I):
        if re.search(r"(香港|HKG|Hong\s*Kong)", body, re.I) and re.search(
            r"(優惠|优惠|促銷|促销|機票|机票|來回|往返|周年|週年|sale|offer)", body, re.I
        ):
            add("HKG")
        if re.search(r"(澳門|澳门|MFM|Macau)", body, re.I) and re.search(
            r"(優惠|优惠|促銷|促销|機票|机票|來回|往返)", body, re.I
        ):
            add("MFM")
    return found

    if not found:
        if re.search(r"(香港|HKG).{0,16}(優惠|优惠|促銷|促销|機票|机票|來回|往返|出发)", body, re.I):
            add("HKG")
        if re.search(r"(澳門|澳门|MFM).{0,16}(優惠|优惠|促銷|促销|機票|机票|來回|往返|出发)", body, re.I):
            add("MFM")
    return found


def extract_dest_iata(title: str) -> str | None:
    t = title or ""
    # 显式目的：→/至/飞/to 后的城市
    m = re.search(
        r"(?:→|->|至|飞|to)\s*(东京|大阪|名古屋|冲绳|首尔|釜山|曼谷|普吉|清迈|吉隆坡|新加坡|巴厘岛|河内|胡志明|台北|赫尔辛基|伦敦|巴黎|法兰克福|阿姆斯特丹|洛杉矶|旧金山|纽约|温哥华|悉尼|墨尔本|奥克兰|迪拜|伊斯坦布尔|贝尔格莱德|香港|澳门)",
        t,
        re.I,
    )
    if m:
        return _DEST_CITY.get(m.group(1), _HK_MO_ORIGIN.get(m.group(1)))
    for city, iata in _DEST_CITY.items():
        if city in t:
            # 香港在出发语境时不作为目的
            if city in ("香港",) and re.search(r"香港.{0,8}(出发|來回|往返|优惠|促銷|促销)", t, re.I):
                continue
            return iata
    return None


def extract_airline(title: str) -> str | None:
    t = title or ""
    for k, v in _AIRLINE_HINTS.items():
        if k in t:
            return v
    return None


def _maybe_fill_origin_from_title(signal: FareDealSignal) -> None:
    """从标题提取出发城市；优先填 origin_airport（首个），另存全部到 tags 不可用时仅 DB 字段。"""
    if signal.origin_airport:
        return
    iatas = extract_origin_iatas_from_title(signal.title or "")
    if iatas:
        # 多城时优先用户常用 CKG/TFU
        for pref in ("CKG", "TFU", "CTU"):
            if pref in iatas:
                signal.origin_airport = pref
                return
        signal.origin_airport = iatas[0]
    if not signal.destination_airport:
        d = extract_dest_iata(signal.title or "")
        if d:
            signal.destination_airport = d
    if not signal.airline:
        a = extract_airline(signal.title or "")
        if a:
            signal.airline = a[:120]


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
    title_l = (signal.title or "").lower()
    if "error_fare" in types or any(
        k in title_l for k in ("bug fare", "error fare", "mistake fare", "错价")
    ):
        return "suspected_bug_fare"
    if "fuel_surcharge_anomaly" in types or "fuel dump" in title_l or "漏油" in title_l:
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
        title = s.title or ""
        all_origins = extract_origin_iatas_from_title(title)
        if s.origin_airport and s.origin_airport.upper() not in all_origins:
            all_origins = [s.origin_airport.upper(), *all_origins]
        # 目的/航司补全
        if not s.destination_airport:
            s.destination_airport = extract_dest_iata(title)
            # 国内目的地城市名（如银川）→ 填 IATA 便于国际过滤
            if not s.destination_airport:
                for city, iata in _CN_CITY_TO_IATA.items():
                    if city in title and city not in ("北上广",) and city != "成都":
                        # 启发式：目的地在最后一个“-”之后
                        parts = re.split(r"[-—–至到]", title)
                        if len(parts) >= 2 and city in parts[-1]:
                            s.destination_airport = iata
                            break
        if not s.airline:
            s.airline = extract_airline(title)

        # 国际判定：任一出发地→目的地为国际；或全国促销无机场
        from app.services.airports.china import is_international_pair

        intl = None
        for o in all_origins or ([s.origin_airport] if s.origin_airport else []):
            pair = is_international_pair(o, s.destination_airport) if o else None
            if pair is True:
                intl = True
                break
            if pair is False and filt.exclude_domestic:
                # 若标题还有其他国际目的地线索则保留
                if not s.destination_airport:
                    continue
        if filt.exclude_domestic and s.destination_airport:
            from app.services.airports.china import is_china_mainland_airport

            if is_china_mainland_airport(s.destination_airport):
                continue
        if filt.exclude_domestic and intl is False and s.destination_airport:
            continue

        cat = classify_signal(s)
        if filt.categories and cat not in filt.categories:
            continue

        # 匹配：标题中任一 preferred 城市 OR origin 精确 OR 全国/多城待核实 OR 无机场全国促销
        preferred = {x.upper() for x in (filt.preferred_origins or [])}
        pref_in_title = [x for x in all_origins if x in preferred]
        national = any(
            k in title
            for k in ("全国", "多地", "北上广", "全国多地", "China-wide", "nationwide", "全国多城")
        )
        if pref_in_title:
            city_match_level = "explicit_city"
            match = {"match": True, "reason": "preferred_city_in_title", "international": intl}
        elif all_origins and not pref_in_title and preferred:
            # 有明确出发城市但不含偏好城市 → 不匹配
            if not national:
                continue
            city_match_level = "national_multi_city_pending"
            match = {"match": True, "reason": "national_overrides_specific_other_city", "international": intl}
        elif national and preferred:
            city_match_level = "national_multi_city_pending"
            match = {"match": True, "reason": "national_multi_pending", "international": intl}
        elif not all_origins and not s.origin_airport:
            # 无机场：可能全国促销
            if national or not preferred:
                city_match_level = "national_multi_city_pending" if national else "origin_unknown"
                match = {"match": True, "reason": "unknown_origin_keep", "international": intl}
            else:
                # 默认偏好下无城市信息：保留为 origin_unknown 展示但降权
                city_match_level = "origin_unknown"
                match = {"match": True, "reason": "no_origin_show_low_priority", "international": intl}
        else:
            # origin 存在但未匹配 preferred 且非全国
            m2 = match_signal_origins(
                s.origin_airport,
                filt.preferred_origins,
                signal_dest=s.destination_airport,
                require_international=filt.exclude_domestic,
            )
            if not m2.get("match"):
                continue
            city_match_level = (
                "explicit_city" if s.origin_airport.upper() in preferred else "origin_unknown"
            )
            match = m2

        if not match.get("match"):
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
        if match.get("reason") in {"exact_iata", "preferred_city_in_title"} or city_match_level == "explicit_city":
            priority -= 30
        if city_match_level == "national_multi_city_pending":
            priority -= 10
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

    now_n = now or datetime.now(UTC).replace(tzinfo=None)
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
