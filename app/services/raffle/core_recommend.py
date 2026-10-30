"""P2：核心推荐正向闭环 —— 仅官方可核实的内地出境证据。

规则（保守）：
1. prize_is_flight 为真
2. 有官方直链 official_url
3. 标签/正文有明确「中国内地/大陆出发」正向表述
4. 无「不包括/国内航班/domestic」等排除语义
5. verify_status 进入 verified / auto_extracted（非 candidate）

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
        return {
            "core_recommend": False,
            "china_outbound": "prize_unknown",
            "reasons": reasons,
        }
    if _EXCLUDE_RE.search(text) or _DOMESTIC_RE.search(text):
        reasons.append("EXCLUDED_OR_DOMESTIC")
        return {
            "core_recommend": False,
            "china_outbound": "excluded_or_domestic",
            "reasons": reasons,
        }
    if not official_url:
        reasons.append("NO_OFFICIAL_URL")
        return {
            "core_recommend": False,
            "china_outbound": "unknown_origin_pending",
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
    reasons.append("OFFICIAL_FLIGHT_MAINLAND_OUTBOUND_EVIDENCE")
    return {
        "core_recommend": True,
        "china_outbound": "confirmed_mainland_outbound",
        "reasons": reasons,
    }
