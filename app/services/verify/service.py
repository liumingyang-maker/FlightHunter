"""活动核实服务：candidate → verifying → verified/needs_review。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.state import (
    CAMPAIGN_VERIFY_TRANSITIONS,
    CampaignVerifyStatus,
    assert_transition,
)
from app.models import CampaignRound, Evidence
from app.services.extract.service import build_evidence_rows, extract_official_fields


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

    # 必须有 title 与至少一条日期/购买线索才可能 verified；否则 needs_review
    has_purchase = any(r["field_path"] == "purchase_required" for r in rows)
    if round_.verify_status != CampaignVerifyStatus.VERIFYING.value:
        begin_verify(session, round_)

    if has_purchase and result.title:
        target = CampaignVerifyStatus.VERIFIED
        note = "已提取标题与购买要求线索；仍需人工复核完整条款"
    else:
        target = CampaignVerifyStatus.NEEDS_REVIEW
        note = "证据不足，保持待核实"

    assert_transition(
        "campaign_round",
        CampaignVerifyStatus.VERIFYING,
        target,
        CAMPAIGN_VERIFY_TRANSITIONS,
    )
    round_.verify_status = target.value
    round_.rules_version_hash = result.content_hash
    session.flush()
    _ = note
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
