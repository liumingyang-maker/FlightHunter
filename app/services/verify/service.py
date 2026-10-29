"""活动核实服务：candidate → verifying → verified/needs_review。

安全不变量（审核 P0-01 修订）：
- 仅凭标题 + 购买关键词 **不得** 标记 verified。
- verified 必须同时满足：
  1) source_url 与 official_url 同源（或明确 authorized_host）
  2) 存在购买要求证据（明确 true/false，非 unknown）
  3) 存在报名截止日期线索
- CAPTCHA **不** 否定官方真实性；仅影响 automation_policy / 预填模式
  （由 browser 侧处理，不进入 verified 门槛）。
否则一律 needs_review。
"""

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.state import (
    CAMPAIGN_VERIFY_TRANSITIONS,
    CampaignVerifyStatus,
    assert_transition,
)
from app.models import CampaignRound, Evidence
from app.services.extract.service import build_evidence_rows, extract_official_fields


def _host(url: str | None) -> str:
    if not url:
        return ""
    return (urlparse(url).hostname or "").lower()


def _same_site(a: str | None, b: str | None) -> bool:
    ha, hb = _host(a), _host(b)
    if not ha or not hb:
        return False
    if ha == hb:
        return True
    return ha.endswith("." + hb) or hb.endswith("." + ha)


def begin_verify(session: Session, round_: CampaignRound) -> CampaignRound:
    assert_transition(
        "campaign_round",
        CampaignVerifyStatus(round_.verify_status),
        CampaignVerifyStatus.VERIFYING,
        CAMPAIGN_VERIFY_TRANSITIONS,
    )
    round_.verify_status = CampaignVerifyStatus.VERIFYING.value
    session.flush()
    return round_


def complete_verify_from_html(
    session: Session,
    round_: CampaignRound,
    html: str,
    *,
    source_url: str | None = None,
) -> CampaignRound:
    """用官方 HTML 完成一轮核实；缺关键证据则 needs_review，绝不虚构 verified。"""
    url = source_url or round_.official_url
    result = extract_official_fields(html, source_url=url)
    rows = build_evidence_rows("campaign_round", round_.id, result)
    for row in rows:
        session.add(Evidence(**row))

    if round_.verify_status != CampaignVerifyStatus.VERIFYING.value:
        begin_verify(session, round_)

    # CAPTCHA：只影响自动化许可，不影响真实性核实
    if "HUMAN_CHALLENGE" in result.warnings:
        round_.has_captcha = True
        if round_.automation_policy == "allowed":
            round_.automation_policy = "forbidden"

    purchase_fields = [r for r in rows if r["field_path"] == "purchase_required"]
    has_purchase = len(purchase_fields) > 0 and all(r.get("quote") for r in purchase_fields)
    has_date = any(r["field_path"] == "dates.clue" for r in rows)
    same_site = _same_site(url, round_.official_url)

    # 严格门槛：同源 + 购买要求证据 + 日期线索（与 CAPTCHA 无关）
    can_verify = bool(same_site and has_purchase and has_date and result.title)

    target = CampaignVerifyStatus.VERIFIED if can_verify else CampaignVerifyStatus.NEEDS_REVIEW

    assert_transition(
        "campaign_round",
        CampaignVerifyStatus.VERIFYING,
        target,
        CAMPAIGN_VERIFY_TRANSITIONS,
    )
    round_.verify_status = target.value
    round_.rules_version_hash = result.content_hash
    session.flush()
    return round_


def mark_expired(session: Session, round_: CampaignRound) -> CampaignRound:
    assert_transition(
        "campaign_round",
        CampaignVerifyStatus(round_.verify_status),
        CampaignVerifyStatus.EXPIRED,
        CAMPAIGN_VERIFY_TRANSITIONS,
    )
    round_.verify_status = CampaignVerifyStatus.EXPIRED.value
    session.flush()
    return round_


def reject(session: Session, round_: CampaignRound) -> CampaignRound:
    current = CampaignVerifyStatus(round_.verify_status)
    if current == CampaignVerifyStatus.REJECTED:
        return round_
    assert_transition(
        "campaign_round",
        current,
        CampaignVerifyStatus.REJECTED,
        CAMPAIGN_VERIFY_TRANSITIONS,
    )
    round_.verify_status = CampaignVerifyStatus.REJECTED.value
    session.flush()
    return round_
