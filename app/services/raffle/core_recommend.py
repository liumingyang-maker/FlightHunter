"""P2/C14-03/04：核心推荐正向闭环 —— 官方可核实的**跨境/国际**内地出境证据。

规则（保守）：
1. prize_is_flight 为真
2. official_url 为空或非官方域名 → False
3. source_kind 必须是官方（official_*）
4. 有明确「中国内地/大陆出发」正向表述
5. 有明确**境外目的地**（国际/跨境），排除纯内地航线
6. 无「不包括/国内航班/domestic」等排除语义
7. verify_status 进入 verified / auto_extracted（非 candidate）

候选 materialize 阶段一律 core_recommend=False；本函数供核验后提升。
"""

from __future__ import annotations

import re
from typing import Any

_EXCLUDE_RE = re.compile(
    r"(不包括|不含|排除|exclude[sd]?|except|not\s+(?:valid\s+)?for|"
    r"不适用于|国内航班|国内航线|国内出发|domestic\s+flights?|"
    r"中国大陆出发.{0,8}(不|无|排除))",
    re.I,
)
_DOMESTIC_RE = re.compile(
    r"(国内航班|国内航线|内地航班|domestic\s+flights?|domestic\s+routes?)",
    re.I,
)
_POSITIVE_CN_OUT_RE = re.compile(
    r"(中国内地出发|内地出发|中国大陆出发|from\s+Mainland\s+China|"
    r"mainland\s+China\s+departures|中国出发)",
    re.I,
)
# C14-04：必须有境外目的地（国际/跨境）才算正向
_INTL_DEST_RE = re.compile(
    r"(国际|跨境|出境|overseas|international|abroad|"
    r"东京|大阪|首尔|曼谷|新加坡|台北|东京|London|Paris|Tokyo|Seoul|Bangkok|"
    r"纽约|洛杉矶|悉尼|墨尔本|温哥华|迪拜)",
    re.I,
)
_DOMESTIC_PAIR_RE = re.compile(
    r"(上海.{0,4}北京|北京.{0,4}上海|广州.{0,4}深圳|上海.{0,4}广州|"
    r"中国内地.{0,6}国内|国内.{0,6}航线)",
    re.I,
)
_OFFICIAL_KINDS = {
    "official_tourism_board",
    "official_airline",
    "official_carrier",
    "official_event",
    "official_page",
}


def evaluate_core_recommend(
    *,
    title: str,
    evidence_text: str | None = None,
    prize_is_flight: bool | None = None,
    official_url: str | None = None,
    verify_status: str | None = None,
    source_kind: str | None = None,
) -> dict[str, Any]:
    """返回 {core_recommend, china_outbound, reasons}。未知一律 False/unknown。"""
    text = f"{title or ''}\n{evidence_text or ''}"
    reasons: list[str] = []
    if prize_is_flight is not True:
        reasons.append("PRIZE_NOT_CONFIRMED_FLIGHT")
        return {"core_recommend": False, "china_outbound": "prize_unknown", "reasons": reasons}

    if _EXCLUDE_RE.search(text) or _DOMESTIC_RE.search(text) or _DOMESTIC_PAIR_RE.search(text):
        reasons.append("EXCLUDED_OR_DOMESTIC")
        return {"core_recommend": False, "china_outbound": "excluded_or_domestic", "reasons": reasons}

    # C14-04：必须明确国际/跨境目的地
    if not _INTL_DEST_RE.search(text):
        reasons.append("NO_INTERNATIONAL_DESTINATION")
        return {
            "core_recommend": False,
            "china_outbound": "pending_international_evidence",
            "reasons": reasons,
        }

    if not official_url:
        reasons.append("NO_OFFICIAL_URL")
        return {"core_recommend": False, "china_outbound": "unknown_origin_pending", "reasons": reasons}

    # C14-04：source_kind 必须官方
    if (source_kind or "") not in _OFFICIAL_KINDS:
        reasons.append(f"SOURCE_KIND_NOT_OFFICIAL:{source_kind or 'unknown'}")
        return {
            "core_recommend": False,
            "china_outbound": "source_not_official",
            "reasons": reasons,
        }

    if verify_status not in {"verified", "auto_extracted"}:
        reasons.append(f"VERIFY_STATUS_{(verify_status or 'unknown').upper()}")
        return {
            "core_recommend": False,
            "china_outbound": "pending_official_outbound_evidence",
            "reasons": reasons,
        }

    if not _POSITIVE_CN_OUT_RE.search(text):
        reasons.append("NO_POSITIVE_MAINLAND_OUTBOUND_TEXT")
        return {
            "core_recommend": False,
            "china_outbound": "pending_official_outbound_evidence",
            "reasons": reasons,
        }

    reasons.append("OFFICIAL_FLIGHT_INTERNATIONAL_MAINLAND_OUTBOUND")
    return {
        "core_recommend": True,
        "china_outbound": "confirmed_mainland_outbound",
        "reasons": reasons,
    }
