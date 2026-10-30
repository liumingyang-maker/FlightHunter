"""官方活动规则解析（只读 HTML）。区分：读到页面 / 活动真实 / 当前有效 / 用户资格。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class OfficialRulesParse:
    page_fetched: bool = False
    organizer_name: str | None = None
    title: str | None = None
    prize_summary: str | None = None
    prize_is_flight: bool | None = None
    prize_is_cash_or_other: bool | None = None
    entry_opens_raw: str | None = None
    entry_closes_raw: str | None = None
    free_entry: bool | None = None
    purchase_required: bool | None = None
    residency_text: str | None = None
    nationality_text: str | None = None
    companions_allowed: bool | None = None
    travel_dates_raw: str | None = None
    notification_text: str | None = None
    entry_channel: str | None = None
    official_domain_ok: bool | None = None
    active_now: bool | None = None
    blocked_notes: list[str] = field(default_factory=list)
    evidence_quote: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_DATE_PATTERNS = [
    re.compile(
        r"(?P<a>\d{4}[./-]\d{1,2}[./-]\d{1,2})\s*(?:~|–|-|—|to|until|~)\s*(?P<b>\d{4}[./-]\d{1,2}[./-]\d{1,2})"
    ),
    re.compile(
        r"(?P<a>\d{1,2}/\d{1,2}/\d{4})\s*(?:~|–|-|—|to|until)\s*(?P<b>\d{1,2}/\d{1,2}/\d{4})"
    ),
    re.compile(
        r"(?P<a>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\s*(?:-|to|–|—)\s*(?P<b>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})",
        re.I,
    ),
]


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip().replace(".", "-").replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            continue
    return None


def parse_official_rules_html(
    html: str,
    *,
    page_url: str,
    expected_official_hosts: tuple[str, ...] | None = None,
    now: datetime | None = None,
) -> OfficialRulesParse:
    from bs4 import BeautifulSoup

    from app.core.url_safety import assert_public_http_url

    out = OfficialRulesParse(page_fetched=bool(html))
    now = now or datetime.now(UTC).replace(tzinfo=None)
    try:
        assert_public_http_url(page_url)
    except Exception as exc:
        out.blocked_notes.append(f"unsafe_url:{exc}")
        return out

    host = re.sub(r"^www\.", "", (re.sub(r"^https?://", "", page_url).split("/")[0] or "").lower())
    if expected_official_hosts:
        out.official_domain_ok = any(
            host == h or host.endswith("." + h) or h in host for h in expected_official_hosts
        )
    else:
        out.official_domain_ok = True

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    low = text.lower()
    title_tag = soup.find("title")
    out.title = (title_tag.get_text(strip=True) if title_tag else None) or None
    out.evidence_quote = text[:1200]

    for m in re.finditer(
        r"(Korean Tourism Organization|Visit Korea|Korea Tourism Organization|한국관광공사|VISITKOREA)",
        text,
        re.I,
    ):
        out.organizer_name = m.group(1)
        break
    if not out.organizer_name and "visitkorea" in host:
        out.organizer_name = "Korea Tourism Organization / VISITKOREA"

    # 奖品
    if re.search(r"round[\s-]?trip|roundtrip|air ?ticket|flight ticket|airfare|왕복항공", low):
        out.prize_is_flight = True
        out.prize_summary = "含往返机票相关奖品（文本命中）"
    elif re.search(r"cash|gift card|shopping voucher|현금", low) and not re.search(
        r"flight|airfare|air ticket", low
    ):
        out.prize_is_flight = False
        out.prize_is_cash_or_other = True
        out.prize_summary = "现金/礼品卡类奖品"
    if re.search(r"winner.*(?:\d+|\btwo\b|\bfour\b).*prize|prizes?\s*:\s*", low):
        m = re.search(r"(\d+)\s*(?:winner|prize|set|pairs?)", low)
        if m:
            out.prize_summary = (out.prize_summary or "") + f"; 数量文本:{m.group(0)}"

    # 日期
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if m:
            out.entry_opens_raw = m.group("a")
            out.entry_closes_raw = m.group("b")
            break

    # 免费报名
    if re.search(r"free\s+(?:to\s+)?(?:enter|entry|participat)|no purchase necessary|무료참여|무료 응모", low):
        out.free_entry = True
        out.purchase_required = False
    elif re.search(r"purchase required|must purchase|buy to enter", low):
        out.free_entry = False
        out.purchase_required = True

    # 居住/国籍
    m = re.search(
        r"((?:open to|eligible for|residents? of|citizens? of|nationals? of)[^.]{0,200})",
        text,
        re.I,
    )
    if m:
        out.residency_text = m.group(1)[:300]
    m = re.search(r"((?:not open to|excluding|except)[^.]{0,160}(?:country|residents?|citizens?)[^.]{0,80})", text, re.I)
    if m:
        out.nationality_text = (out.nationality_text or "") + " " + m.group(1)[:200]

    # 同行
    if re.search(r"companion|guest|plus one|together with|동반", low):
        out.companions_allowed = True

    # 报名方式
    if re.search(r"survey|questionnaire|quiz|응모\s*폼|surveyIntro", low):
        out.entry_channel = "survey_quiz"
    elif re.search(r"online form|registration form|sign[\s-]?up", low):
        out.entry_channel = "online_form"

    # 通知
    m = re.search(r"((?:winner|notif|announce)[^.]{0,160}(?:email|mail|website|site)[^.]{0,80})", text, re.I)
    if m:
        out.notification_text = m.group(1)[:300]

    # 当前有效
    opens = _parse_date(out.entry_opens_raw)
    closes = _parse_date(out.entry_closes_raw)
    if opens and closes:
        if now < opens:
            out.active_now = False
            out.blocked_notes.append("not_open_yet")
        elif now > closes:
            out.active_now = False
            out.blocked_notes.append("ended")
        else:
            out.active_now = True
    elif closes:
        out.active_now = now <= closes if closes else None
    else:
        out.active_now = None
        out.blocked_notes.append("dates_unparsed")

    if out.official_domain_ok is False:
        out.blocked_notes.append("not_expected_official_host")
    return out


def eligibility_unknown_profile(parse: OfficialRulesParse) -> dict[str, Any]:
    """无可靠用户国籍/居住数据时，资格保持 unknown。"""
    # 即使有 residency 文本，没有用户档案也不判 eligible
    return {
        "state": "unknown",
        "reason": "USER_PROFILE_ABSENT",
        "official_free_entry": parse.free_entry,
        "official_active_now": parse.active_now,
        "residency_text_present": bool(parse.residency_text),
        "note": "官方页面存在 ≠ 用户 eligible；未知国籍/居住不得臆测为符合",
    }
