"""资格引擎：三态输出 + 逐条规则依据。未知 ≠ 符合。"""

from __future__ import annotations

import json
from typing import Any

from app.core.state import EligibilityState
from app.core.timeutils import ensure_aware_utc, utc_now
from app.models import CampaignRound, Profile
from app.schemas.common import EligibilityResultModel, RuleCheck


def _known(value: Any) -> bool:
    return value is not None and value != ""


def evaluate_eligibility(
    round_: CampaignRound,
    profile: Profile,
) -> EligibilityResultModel:
    """硬限制逐条检查；任一已知不满足 → ineligible；全过 → eligible；否则 needs_review。"""
    checks: list[RuleCheck] = []
    reasons: list[str] = []

    # 购买要求
    if round_.purchase_required is True:
        checks.append(
            RuleCheck(
                code="PURCHASE_REQUIRED",
                outcome="unknown",
                profile_value_known=True,
                official_rule_known=True,
                note="官方要求先购买；本系统不自动付费",
            )
        )
        reasons.append("PURCHASE_REQUIRED")
    elif round_.purchase_required is False:
        checks.append(
            RuleCheck(
                code="PURCHASE_REQUIRED",
                outcome="pass",
                profile_value_known=True,
                official_rule_known=True,
                note="官方确认无需购买",
            )
        )
    else:
        checks.append(
            RuleCheck(
                code="PURCHASE_REQUIRED",
                outcome="unknown",
                profile_value_known=True,
                official_rule_known=False,
                note="购买要求未知",
            )
        )
        reasons.append("PURCHASE_RULE_UNKNOWN")

    # 居住国：仅当档案与规则都明确时判断
    # 注：rules 未结构化存储居住国字段时保持 unknown
    residency_known_in_rules = bool(getattr(round_, "residency_required_countries", None))
    profile_res = profile.country_of_residence
    if residency_known_in_rules and _known(profile_res):
        allowed = getattr(round_, "residency_required_countries", None) or []
        if isinstance(allowed, str):
            allowed = json.loads(allowed)
        if profile_res in allowed:
            checks.append(
                RuleCheck(
                    code="RESIDENCY",
                    outcome="pass",
                    profile_value_known=True,
                    official_rule_known=True,
                )
            )
        else:
            checks.append(
                RuleCheck(
                    code="RESIDENCY",
                    outcome="fail",
                    profile_value_known=True,
                    official_rule_known=True,
                )
            )
            reasons.append("RESIDENCY_NOT_ALLOWED")
    else:
        checks.append(
            RuleCheck(
                code="RESIDENCY",
                outcome="unknown",
                profile_value_known=_known(profile_res),
                official_rule_known=residency_known_in_rules,
                note="「未找到限制」不是「明确不限」",
            )
        )
        if not residency_known_in_rules:
            reasons.append("RESIDENCY_RULE_UNKNOWN")
        if not _known(profile_res):
            reasons.append("PROFILE_INFO_MISSING")

    # 年龄
    if _known(profile.date_of_birth):
        checks.append(
            RuleCheck(
                code="AGE",
                outcome="unknown",
                profile_value_known=True,
                official_rule_known=False,
                note="官方最低年龄规则尚未结构化提取",
            )
        )
    else:
        checks.append(
            RuleCheck(
                code="AGE",
                outcome="unknown",
                profile_value_known=False,
                official_rule_known=False,
            )
        )
        reasons.append("PROFILE_INFO_MISSING")

    # 报名期是否已过期（SQLite 可能返回 naive，统一 UTC 后再比）
    now = utc_now()
    closes = ensure_aware_utc(round_.entry_closes_at_utc)
    opens = ensure_aware_utc(round_.entry_opens_at_utc)
    if closes and closes < now:
        checks.append(
            RuleCheck(
                code="ENTRY_WINDOW",
                outcome="fail",
                profile_value_known=True,
                official_rule_known=True,
                note="报名期已结束",
            )
        )
        reasons.append("ENTRY_CLOSED")
    elif opens and opens > now:
        checks.append(
            RuleCheck(
                code="ENTRY_WINDOW",
                outcome="unknown",
                profile_value_known=True,
                official_rule_known=True,
                note="报名尚未开始",
            )
        )
        reasons.append("ENTRY_NOT_OPEN")
    else:
        checks.append(
            RuleCheck(
                code="ENTRY_WINDOW",
                outcome="pass",
                profile_value_known=True,
                official_rule_known=True,
            )
        )

    fails = [c for c in checks if c.outcome == "fail"]
    unknowns = [c for c in checks if c.outcome == "unknown"]

    if fails:
        state = EligibilityState.INELIGIBLE
    elif unknowns:
        state = EligibilityState.NEEDS_REVIEW
    else:
        state = EligibilityState.ELIGIBLE

    rules_hash = round_.rules_version_hash or ""
    return EligibilityResultModel(
        round_id=round_.id,
        profile_id=profile.id,
        state=state.value,
        reason_codes=list(dict.fromkeys(reasons)),
        rule_checks=checks,
        evaluated_at_utc=now,
        rules_version_hash=rules_hash,
    )
