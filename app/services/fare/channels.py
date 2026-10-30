"""四频道情报路由：统一库/去重/通知；前端严格分流。"""

from __future__ import annotations

import json
from typing import Any

from app.services.airports.china import (
    is_china_mainland_airport,
    is_hk_mo_airport,
)

# 错价/漏油关键词（标题或 deal_types）
_ERROR_TYPES = {
    "error_fare",
    "suspected_error_fare",
    "fuel_dump",
    "suspected_fuel_dump",
    "fuel_surcharge_anomaly",
}
_ERROR_TITLE_KW = (
    "bug fare",
    "error fare",
    "mistake fare",
    "fuel dump",
    "漏油",
    "错价",
    "bug价",
    "error-fare",
    "mistake fare",
    "pricing error",
)
_PREMIUM_TITLE_KW = ("business class", "商务舱", "first class", "头等舱", "business-class")


def is_error_fare_item(item: dict[str, Any]) -> bool:
    raw = item.get("deal_types")
    if isinstance(raw, str):
        try:
            types = set(json.loads(raw or "[]"))
        except Exception:
            types = set()
    else:
        types = set(raw or [])
    if types & _ERROR_TYPES:
        return True
    title = (item.get("title") or "").lower()
    return any(k in title for k in _ERROR_TITLE_KW)


def is_premium_cabin_deal(item: dict[str, Any]) -> bool:
    title = (item.get("title") or "").lower()
    return any(k in title for k in _PREMIUM_TITLE_KW) and bool(
        item.get("reported_total") or is_error_fare_item(item)
    )


def origin_region(item: dict[str, Any]) -> str:
    o = (item.get("origin_airport") or "").upper()
    if is_hk_mo_airport(o):
        return "hk_mo"
    if is_china_mainland_airport(o):
        return "china_mainland"
    if not o:
        title = item.get("title") or ""
        if any(k in title for k in ("香港", "澳门", "HKG", "MFM", "Hong Kong", "Macau")):
            return "hk_mo"
        if any(k in title for k in ("全国", "多地", "中国", "China-wide")):
            return "china_mainland"
    return "global"


def route_channels(item: dict[str, Any], preferred: list[str]) -> list[str]:
    """返回该情报所属频道列表（可多频道，同一 signal_id）。"""
    chans: list[str] = []
    pref = {x.upper() for x in preferred or []}
    o = (item.get("origin_airport") or "").upper()
    title = item.get("title") or ""
    all_origins = set()
    if o:
        all_origins.add(o)
    # 标题中的偏好城市
    from app.services.fare.intel import extract_origin_iatas_from_title

    all_origins.update(extract_origin_iatas_from_title(title))
    region = origin_region(item)
    error = is_error_fare_item(item)

    # 频道 A：我的出发地 — 仅 explicit 匹配偏好机场
    explicit = bool(all_origins & pref)
    if explicit:
        chans.append("my_origin")
    # 频道 D：全球错价 — 不限出发地
    if error:
        chans.append("global_error")
    # 频道 B：全国出发 — 内地相关（明确内地机场或全国/内地线索），不含仅港澳
    if region == "china_mainland" or (
        not explicit
        and any(k in title for k in ("全国", "多地", "中国", "China"))
        and region != "hk_mo"
    ):
        if not (is_hk_mo_airport(o) if o else False):
            chans.append("china_mainland")
    # 频道 C：港澳
    if region == "hk_mo" or (o and is_hk_mo_airport(o)) or any(
        k in title for k in ("香港", "澳门", "HKG", "MFM", "Hong Kong", "Macau", "HongKong")
    ):
        chans.append("hk_mo")
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for c in chans:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def filter_for_channel(
    items: list[dict[str, Any]],
    channel: str,
    preferred: list[str],
    *,
    include_pending_in_fold: bool = False,
) -> dict[str, Any]:
    """按频道过滤情报；my_origin 分主列表与折叠区。"""
    primary: list[dict[str, Any]] = []
    folded: list[dict[str, Any]] = []
    for it in items:
        chans = route_channels(it, preferred)
        it = dict(it)
        it["channels"] = chans
        it["is_error_fare"] = is_error_fare_item(it)
        if channel == "my_origin":
            lvl = it.get("city_match_level")
            if "my_origin" in chans and lvl == "explicit_city":
                primary.append(it)
            elif "my_origin" in chans or lvl in {
                "national_multi_city_pending",
                "origin_unknown",
            }:
                # 折叠：全国/未知（即使无 my_origin 标签，因无偏好城市但仍可能适用）
                if lvl == "explicit_city":
                    primary.append(it)
                else:
                    folded.append(it)
        elif channel == "china_mainland":
            if "china_mainland" in chans or (
                it.get("city_match_level") == "national_multi_city_pending"
            ):
                # 港澳机场不进全国
                o = (it.get("origin_airport") or "").upper()
                if o and is_hk_mo_airport(o):
                    continue
                primary.append(it)
        elif channel == "hk_mo":
            if "hk_mo" in chans:
                primary.append(it)
        elif channel == "global_error":
            if it.get("is_error_fare") or "global_error" in chans:
                primary.append(it)
        else:
            primary.append(it)
    return {
        "channel": channel,
        "primary": primary,
        "folded": folded,
        "primary_count": len(primary),
        "folded_count": len(folded),
    }
