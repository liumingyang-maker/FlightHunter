"""活动核实服务（第三轮：证据型官方核实）。

自动 verified 必须同时满足：
1) official_url 与 source_url 同源
2) Organizer.official_domain 与 official_url 同源（主办方注册域）
3) HTML 中存在**指向同源细则页的 <a href>**（不是正文出现 “Official Rules” 字样即可）
4) 购买要求证据 + 报名截止日期线索 + 活动语义
缺任一 → needs_review。
CAPTCHA 只影响 automation_policy。
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.core.state import (
    CAMPAIGN_VERIFY_TRANSITIONS,
    CampaignVerifyStatus,
    assert_transition,
)
from app.models import CampaignRound, Evidence
from app.services.extract.service import build_evidence_rows, extract_official_fields

_CAMPAIGN_HINTS = re.compile(
    r"(giveaway|sweepstake|contest|enter to win|win a trip|win flights|"
    r"抽奖|赠票|机票抽奖|报名赢|参赛)",
    re.I,
)
_RULES_LINK_TEXT = re.compile(
    r"(official\s+rules|terms\s+and\s+conditions|official\s+terms|"
    r"活动细则|官方规则|官方条款|参赛规则|contest\s+rules)",
    re.I,
)
_INDEX_LIKE = re.compile(
    r"(news index|homepage|newsletter|订阅|首页|目录|archive)",
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


def _organizer_domain_ok(session: Session, round_: CampaignRound) -> bool:
    """Campaign → Organizer.official_domain 必须与 official_url 同源。"""
    campaign = round_.campaign
    if campaign is None:
        return False
    organizer = campaign.organizer
    if organizer is None or not organizer.official_domain:
        return False
    domain = organizer.official_domain
    # 允许 official_domain 为 example.org 或 https://example.org
    if "://" in domain:
        return _same_site(domain, round_.official_url)
    return _same_site(f"https://{domain}", round_.official_url)


def _has_same_site_rules_link(html: str, page_url: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if not text or not _RULES_LINK_TEXT.search(text):
            continue
        href = a["href"].strip()
        if href.startswith("//"):
            return False
        if href.startswith("/"):
            # 站内相对链接视为同源
            return True
        if href.startswith("http") and _same_site(href, page_url):
            return True
    return False


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


def _has_rules_body(html: str) -> bool:
    """细则正文：去掉超链接后仍含规则语义；拒绝 TBD/占位。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a"):
        a.extract()
    text = soup.get_text(" ", strip=True)
    if re.search(
        r"(eligibility\s*[:：]\s*(tbd|tbc|待定|coming\s*soon)|"
        r"rules\s*[:：]\s*(tbd|tbc|待定))",
        text,
        re.I,
    ):
        return False
    has_rules_heading = bool(
        re.search(
            r"(official\s+rules|活动细则|官方规则|official\s+terms)",
            text,
            re.I,
        )
    )
    # 资格：不能只是 TBD，需有实质描述
    has_eligibility = bool(
        re.search(
            r"(eligib(?:le|ility)\s+(?:applies|open|is|are|must|shall|must be)|"
            r"eligib(?:le|ility)\s*[:：]\s*(?!tbd|tbc|待定|coming)\S|"
            r"参赛资格[^。]{0,40}|"
            r"open to (residents|residing|entrants|legal))",
            text,
            re.I,
        )
    )
    return has_rules_heading and has_eligibility


def complete_verify_from_html(
    session: Session,
    round_: CampaignRound,
    html: str,
    *,
    source_url: str | None = None,
    rules_html: str | None = None,
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

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    purchase_fields = [r for r in rows if r["field_path"] == "purchase_required"]
    has_purchase = len(purchase_fields) > 0 and all(r.get("quote") for r in purchase_fields)
    has_date = any(r["field_path"] == "dates.clue" for r in rows)
    same_site = _same_site(url, round_.official_url)
    organizer_ok = _organizer_domain_ok(session, round_)
    # 链接存在 ≠ 正文已核实；需 rules_html 或页面内细则正文
    rules_link_ok = _has_same_site_rules_link(html, url)
    if rules_html:
        rules_body_ok = _has_rules_body(rules_html) or _has_same_site_rules_link(rules_html, url)
        # rules_html 已提供时，要求其中有规则正文语义
        rules_body_ok = _has_rules_body(rules_html)
    else:
        rules_body_ok = _has_rules_body(html)
    rules_ok = rules_link_ok and rules_body_ok
    has_campaign_semantics = bool(
        _CAMPAIGN_HINTS.search(text) or _CAMPAIGN_HINTS.search(result.title or "")
    )
    index_like = bool(_INDEX_LIKE.search(result.title or ""))

    can_verify = bool(
        same_site
        and organizer_ok
        and rules_ok
        and has_purchase
        and has_date
        and result.title
        and has_campaign_semantics
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
