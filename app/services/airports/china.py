"""中国内地/港澳出发机场识别（基于 airportsdata，不手写残缺列表）。"""

from __future__ import annotations

from functools import lru_cache

# 中国内地省级行政区（ISO 3166-2 前缀 CN-）粗分；HKG/MFM 单独
_MAINLAND_COUNTRY = "CN"
_HK_MO_IATA = frozenset({"HKG", "MFM"})  # 香港、澳门 — 独立可选，不并入“内地全国”


@lru_cache(maxsize=1)
def _airport_db() -> dict[str, dict]:
    """iata -> airport dict（airportsdata.load）。"""
    try:
        import airportsdata

        db = airportsdata.load("IATA")
        return db or {}
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _china_mainland_iatas() -> frozenset[str]:
    """中国内地机场 IATA 集合（排除 HKG/MFM）。"""
    db = _airport_db()
    out: set[str] = set()
    for iata, info in db.items():
        if iata in _HK_MO_IATA:
            continue
        country = str(info.get("country") or info.get("country_code") or "")
        cu = country.upper()
        if cu in {"CN", "CHINA"} or cu.startswith("CN-") or "CHINA" in cu:
            # 排除港/澳名称
            if any(x in cu for x in ("HONG KONG", "MACAO", "MACAU")):
                continue
            out.add(iata.upper())
    # 常见内地枢纽保底
    out.update(
        {"CKG", "TFU", "CTU", "PEK", "PKX", "SHA", "PVG", "CAN", "SZX", "HGH", "WUH", "KMG", "XIY", "CSX", "TAO", "DLC"}
    )
    return frozenset(out)


def is_china_mainland_airport(iata: str | None) -> bool:
    if not iata:
        return False
    code = iata.upper().strip()
    if code in _HK_MO_IATA:
        return False
    return code in _china_mainland_iatas()


def is_hk_mo_airport(iata: str | None) -> bool:
    return bool(iata) and iata.upper().strip() in _HK_MO_IATA


def is_international_pair(origin: str | None, dest: str | None) -> bool | None:
    """国际/跨境判定；未知返回 None。

    规则：
    - 内地机场 ↔ 非内地（含 HKG/MFM/外国） → True
    - 内地机场 ↔ 内地机场 → False（纯国内，情报雷达应排除）
    - HKG/MFM ↔ 任何非同系机场 → True（用户显式选择港澳出发时）
    - 任一端未知 → None
    """
    if not origin or not dest:
        return None
    o, d = origin.upper().strip(), dest.upper().strip()
    o_main, d_main = is_china_mainland_airport(o), is_china_mainland_airport(d)
    o_hm, d_hm = is_hk_mo_airport(o), is_hk_mo_airport(d)
    if o_main and d_main:
        return False
    if o_main and not d_main:
        return True
    if d_main and not o_main:
        return True
    if o_hm or d_hm:
        # 港澳与内地/外国
        if o_hm and d_hm:
            return False  # HKG-MFM 视作特殊，非国际长途默认
        return True
    # 两端均非中国体系（假设国际）
    if o != d:
        return True
    return False


def expand_origin_selection(
    *,
    single: str | None = None,
    multi: list[str] | None = None,
    china_mainland_all: bool = False,
    include_hkg: bool = False,
    include_mfm: bool = False,
    extra: list[str] | None = None,
) -> list[str]:
    """展开用户出发地选择 → IATA 列表（去重、大写）。"""
    codes: list[str] = []

    def add(c: str | None) -> None:
        if c:
            codes.append(c.upper().strip())

    if single:
        add(single)
    for c in multi or []:
        add(c)
    if china_mainland_all:
        codes.extend(sorted(_china_mainland_iatas()))
    if include_hkg:
        add("HKG")
    if include_mfm:
        add("MFM")
    for c in extra or []:
        add(c)
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def match_signal_origins(
    signal_origin: str | None,
    preferred: list[str],
    *,
    signal_dest: str | None = None,
    require_international: bool = True,
) -> dict:
    """信号出发地是否匹配用户偏好；并判定是否国际。"""
    intl = is_international_pair(signal_origin, signal_dest) if require_international else None
    if require_international and intl is False:
        return {
            "match": False,
            "reason": "domestic_china_route_excluded",
            "international": False,
        }
    if require_international and intl is None and not signal_origin:
        # 无机场但可能是全国性国际促销
        return {
            "match": True,
            "reason": "national_or_unknown_origin_intl_possible",
            "international": None,
        }
    if not preferred:
        return {"match": True, "reason": "no_origin_filter", "international": intl}
    if signal_origin and signal_origin.upper() in preferred:
        return {"match": True, "reason": "exact_iata", "international": intl}
    # 全国模式：信号为内地任一机场且用户含内地全国（通过 preferred 很大）
    if signal_origin and is_china_mainland_airport(signal_origin) and len(preferred) >= 20:
        return {"match": True, "reason": "mainland_all", "international": intl}
    if not signal_origin:
        return {"match": True, "reason": "unknown_origin_keep", "international": intl}
    return {"match": False, "reason": "origin_not_in_preference", "international": intl}
