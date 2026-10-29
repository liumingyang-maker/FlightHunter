"""活动核实服务。

FH-AUDIT-P0-01：同源 HTML + “无需购买” + 任意日期 **不足以** verified。
必须同时具备：
1) source_url 与 official_url 同源
2) 页面含明确活动/报名语义（giveaway/sweepstake/抽奖/报名/获胜行程等）
3) 购买要求证据
4) 报名截止日期线索
5) 存在官方细则/条款链接或 rules 关键词（Official Rules / 活动细则 / terms）
新闻订阅页、首页索引即使有日期和 no purchase 也保持 needs_review。
CAPTCHA 不否定 verified，只影响 automation_policy。
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.state import (
    CAMPAIGN_VERIFY_TRANSITIONS,
    CampaignVerifyStatus,
    assert_transition,
)
from app.models import CampaignRound, Evidence
from app.services.extract.service import build_evidence_rows, extract_official_fields

_CAMPAIGN_HINTS = re.compile(
    r"(giveaway|sweepstake|contest|enter to win|win a|official rules|"
    r"抽奖|赠票|机票 giveaway|报名|中奖|活动细则|官方规则|参赛|eligibility)",
    re.I,
)
_RULES_HINTS = re.compile(
    r"(official rules|terms and conditions|terms of|rules|"
    r"细则|条款|规则|eligibility|参赛资格|官方活动)",
    re.I,
)


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
    url = source_url or round_.official_url
    result = extract_official_fields(html, source_url=url)
    rows = build_evidence_rows("campaign_round", round_.id, result)
    for row in rows:
        session.add(Evidence(**row))

    if round_.verify_status != CampaignVerifyStatus.VERIFYING.value:
        begin_verify(session, round_)

    if "HUMAN_CHALLENGE" in result.warnings:
        round_.has_captcha = True
        if round_.automation_policy == "allowed":
            round_.automation_policy = "forbidden"

    from bs4 import BeautifulSoup

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)

    purchase_fields = [r for r in rows if r["field_path"] == "purchase_required"]
    has_purchase = len(purchase_fields) > 0 and all(r.get("quote") for r in purchase_fields)
    has_date = any(r["field_path"] == "dates.clue" for r in rows)
    same_site = _same_site(url, round_.official_url)
    has_campaign_semantics = bool(
        _CAMPAIGN_HINTS.search(text) or _CAMPAIGN_HINTS.search(result.title or "")
    )
    has_rules_signal = bool(_RULES_HINTS.search(text))

    # 标题像新闻索引 / 订阅页 → 拒绝 verified
    title = (result.title or "").lower()
    index_like = bool(
        re.search(r"(news index|homepage|newsletter|订阅|首页|目录|archive)", title, re.I)
    )

    can_verify = bool(
        same_site
        and has_purchase
        and has_date
        and result.title
        and has_campaign_semantics
        and has_rules_signal
        and not index_like
    )

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
