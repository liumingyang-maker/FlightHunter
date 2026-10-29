"""浏览器报名助手：默认预填+人工确认；禁止绕过验证码/敏感操作。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.url_safety import assert_public_http_url
from app.models import CampaignRound, Profile

# assert_public_http_url 来自 app.core.url_safety（覆盖私网/链路本地/元数据）


@dataclass
class PrefillField:
    field_name: str
    value: str
    source: str  # profile | user | derived_official


@dataclass
class PrefillPlan:
    target_url: str
    mode: str  # PREFILL_AND_REVIEW | MANUAL_ONLY | AUTO_ALLOWED
    fields: list[PrefillField] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_human: list[str] = field(default_factory=list)


def build_prefill_plan(
    round_: CampaignRound,
    profile: Profile,
    *,
    user_approved_fields: dict[str, str] | None = None,
) -> PrefillPlan:
    """生成预填计划。营销勾选默认跳过；验证码/支付/证件要求人工。"""
    assert_public_http_url(round_.official_url)

    mode = round_.automation_policy
    if mode == "forbidden":
        plan_mode = "MANUAL_ONLY"
    elif mode == "allowed":
        plan_mode = "PREFILL_AND_REVIEW"  # 即使站点允许，仍默认人工确认
    else:
        plan_mode = "PREFILL_AND_REVIEW"

    plan = PrefillPlan(target_url=round_.official_url, mode=plan_mode)

    if round_.has_captcha is True:
        plan.requires_human.append("CAPTCHA：系统不绕过，请人工完成")
        plan.mode = "MANUAL_ONLY"

    if round_.marketing_consent_required is True:
        plan.skipped.append(
            {
                "field": "marketing_consent",
                "reason": "营销授权必须由你本人决定，不自动勾选",
            }
        )
        plan.requires_human.append("请自行决定是否勾选营销同意")

    # 仅预填真实档案中已知字段；禁止编造
    if profile.display_name:
        plan.fields.append(PrefillField("full_name", profile.display_name, source="profile"))
    if profile.country_of_residence:
        plan.fields.append(
            PrefillField(
                "country_of_residence",
                profile.country_of_residence,
                source="profile",
            )
        )
    if profile.nationality:
        plan.fields.append(PrefillField("nationality", profile.nationality, source="profile"))
    if profile.date_of_birth:
        plan.fields.append(PrefillField("date_of_birth", profile.date_of_birth, source="profile"))

    if not profile.country_of_residence:
        plan.warnings.append("PROFILE_INFO_MISSING：居住国未填写，相关字段保持空白")

    for k, v in (user_approved_fields or {}).items():
        plan.fields.append(PrefillField(k, v, source="user"))

    plan.warnings.append("提交前请核对目标域名与已填字段；营销项默认不勾选")
    plan.warnings.append("不会自动处理验证码、登录、支付或证件上传")
    return plan


def plan_to_dict(plan: PrefillPlan) -> dict[str, Any]:
    return {
        "target_url": plan.target_url,
        "mode": plan.mode,
        "fields": [f.__dict__ for f in plan.fields],
        "skipped": plan.skipped,
        "warnings": plan.warnings,
        "requires_human": plan.requires_human,
        "note": "本计划仅预填；最终提交由用户完成（除非站点+用户双重授权的受限自动提交）",
    }
