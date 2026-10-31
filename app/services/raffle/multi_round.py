"""VISITKOREA 等官方详情页：同页多活动/多期拆分规则（禁止跨期拼接奖品与日期）。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now(now: datetime | None) -> datetime:
    n = now or datetime.now(UTC)
    return n.replace(tzinfo=None) if n.tzinfo else n


@dataclass
class EventRoundRules:
    round_label: str
    edition_key: str
    title: str
    organizer_name: str | None = None
    prize_summary: str | None = None
    prize_is_flight: bool = False
    prize_is_gift_or_other: bool = False
    winners_count: int | None = None
    tickets_per_winner: int | None = None
    opens_raw: str | None = None
    closes_raw: str | None = None
    opens_iso: str | None = None
    closes_iso: str | None = None
    free_entry: bool | None = None
    purchase_required: bool | None = None
    residency_restriction: str | None = None
    nationality_restriction: str | None = None
    entry_channel: str | None = None
    notification_text: str | None = None
    prize_terms: str | None = None
    active_now: bool | None = None
    # open | closed | pending_verification | unknown —— 日期未知 ≠ closed
    open_status: str = "unknown"
    requires_login_to_enter: bool = False
    is_current_phase: bool | None = None
    evidence_quote: str | None = None
    blocked_notes: list[str] = field(default_factory=list)
    tags: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MultiRoundParseResult:
    page_url: str
    page_fetched: bool
    page_title: str | None
    rounds: list[EventRoundRules] = field(default_factory=list)
    cross_contamination_guard: str = "each_round_dates_bound_to_own_prize_only"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_url": self.page_url,
            "page_fetched": self.page_fetched,
            "page_title": self.page_title,
            "rounds": [r.to_dict() for r in self.rounds],
            "cross_contamination_guard": self.cross_contamination_guard,
            "notes": self.notes,
            "open_flight_rounds": [
                r.round_label
                for r in self.rounds
                if r.prize_is_flight and r.open_status == "open"
            ],
            "pending_verification_flight_rounds": [
                r.round_label
                for r in self.rounds
                if r.prize_is_flight and r.open_status == "pending_verification"
            ],
            "ended_or_inactive_flight_rounds": [
                r.round_label
                for r in self.rounds
                if r.prize_is_flight and r.open_status == "closed"
            ],
        }


_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _safe_dt(y: int, mo: int, d: int) -> datetime | None:
    try:
        return datetime(y, mo, d)
    except ValueError:
        return None


def _parse_date_flexible(s: str | None, *, default_year: int = 2026) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    # 2026-07-20 / 07/20/2026 / July 20, 2026 / July 20 – August 19, 2026 handled by caller split
    m = re.match(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", s)
    if m:
        return _safe_dt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return _safe_dt(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    m = re.match(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})",
        s,
        re.I,
    )
    if m:
        return datetime(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    m = re.match(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})", s, re.I)
    if m:
        return _safe_dt(default_year, _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    return None


def _status_for_range(opens: datetime | None, closes: datetime | None, now: datetime) -> bool | None:
    if opens and closes:
        return opens <= now <= closes
    if closes:
        return now <= closes
    if opens:
        return now >= opens
    return None


def open_status_from_dates(
    opens: datetime | None,
    closes: datetime | None,
    now: datetime,
    *,
    requires_login: bool = False,
    page_has_visible_join: bool = False,
) -> str:
    """开放状态：仅日期证据可判 open/closed；否则 pending/unknown。"""
    if opens and closes:
        if now < opens:
            return "pending_verification"  # 尚未开始报名窗口，不记 closed
        if now > closes:
            return "closed"
        return "open"
    if closes:
        return "open" if now <= closes else "closed"
    # 无完整日期
    if requires_login or page_has_visible_join:
        return "pending_verification"
    return "unknown"


def parse_multi_round_event_html(
    html: str,
    *,
    page_url: str,
    now: datetime | None = None,
    poster_facts: dict[str, Any] | None = None,
    auto_extract: dict[str, Any] | None = None,
) -> MultiRoundParseResult:
    """把同页 Event1/Event2/Period 拆成独立轮次；禁止把 A 轮机票与 B 轮礼券日期拼接。"""
    from bs4 import BeautifulSoup

    from app.core.url_safety import assert_public_http_url

    now_n = _now(now)
    out = MultiRoundParseResult(page_url=page_url, page_fetched=bool(html), page_title=None)
    try:
        assert_public_http_url(page_url)
    except Exception as exc:
        out.notes.append(f"unsafe_url:{exc}")
        return out

    soup = BeautifulSoup(html, "html.parser")
    out.page_title = soup.title.get_text(strip=True) if soup.title else None
    text = soup.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # 检测是否像 VISITKOREA 详情（含中文美食活动文案）；有 auto_extract 时也可继续
    if not auto_extract and not re.search(
        r"event|period|prize|winner|机票|活动|专栏|quiz|giveaway|sweep", text, re.I
    ):
        out.notes.append("no_event_markers")
        return out

    rounds: list[EventRoundRules] = []
    organizer = "Korea Tourism Organization / VISITKOREA" if "visitkorea" in page_url else None

    # --- Case A style: single survey with flight prize ---
    if re.search(r"enter to win round-trip flights|round-trip flights to Korea|K-SPICY", text, re.I):
        join_visible = bool(re.search(r"Join Now", text))
        r0 = EventRoundRules(
            round_label="survey_roundtrip",
            edition_key="survey_roundtrip",
            title=out.page_title or "VISITKOREA survey round-trip",
            organizer_name=organizer,
            prize_summary="round-trip flights to Korea (survey)",
            prize_is_flight=True,
            entry_channel="survey_quiz",
            free_entry=True,
            purchase_required=False,
            open_status="pending_verification" if join_visible else "unknown",
            requires_login_to_enter=True,
            residency_restriction="open exclusively to non-residents of Korea"
            if re.search(r"non-residents of Korea", text, re.I)
            else None,
        )
        m = re.search(
            r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\s*[–\-—to]+\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4}\s*[–\-—to]+\s*\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{1,2}-\d{1,2}\s*[–\-—to]+\s*\d{4}-\d{1,2}-\d{1,2})",
            text,
        )
        if m:
            r0.opens_raw = r0.closes_raw = m.group(1)
            r0.blocked_notes.append("range_not_split_in_survey_page")
        else:
            r0.blocked_notes.append("dates_unparsed")
        r0.active_now = None
        if r0.open_status == "pending_verification":
            r0.blocked_notes.append("open_state_pending_verification_not_closed")
        rounds.append(r0)

    # --- Explicit Event N / Previous event / Current event / Period N ---
    # Find segments
    prev_idx = next((i for i, ln in enumerate(lines) if re.fullmatch(r"Previous event", ln, re.I)), None)
    curr_idx = next((i for i, ln in enumerate(lines) if re.fullmatch(r"Current event", ln, re.I)), None)
    period_idxs = [i for i, ln in enumerate(lines) if re.match(r"Period\s*\d+\s*:", ln, re.I)]

    def _segment_text(start: int, end: int) -> str:
        return "\n".join(lines[start:end])

    def _build_round(
        label: str,
        edition: str,
        seg: str,
        *,
        is_current: bool | None,
    ) -> EventRoundRules:
        prize_flight = bool(
            re.search(r"round-trip ticket|round-trip flight|air ticket|airfare", seg, re.I)
        )
        gift = bool(re.search(r"gift card|gift voucher|egift|e-gift|voucher", seg, re.I)) and not prize_flight
        # 奖品描述仅取本段
        prize_m = re.search(
            r"(Round-trip Ticket to Korea|Round-trip flight[^\n]{0,80}|Gift Card|Gift Voucher|eGift Card|\$[\d,]+ Amazon[^\n]{0,40})",
            seg,
            re.I,
        )
        date_m = re.search(
            r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\s*[–\-—]\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4}\s*[–\-—]\s*\d{1,2}/\d{1,2}/\d{4})",
            seg,
        )
        opens = closes = None
        opens_raw = closes_raw = None
        if date_m:
            raw = date_m.group(1)
            opens_raw = closes_raw = raw
            parts = re.split(r"\s*[–\-—]\s*", raw)
            if len(parts) >= 2:
                left, right = parts[0].strip(), parts[-1].strip()
                # 若右侧缺年份，从左侧借
                if not re.search(r"\d{4}", right) and re.search(r"\d{4}", left):
                    ym = re.search(r"(\d{4})", left)
                    right = f"{right} {ym.group(1)}" if ym else right
                opens = _parse_date_flexible(left)
                closes = _parse_date_flexible(right, default_year=opens.year if opens else 2026)
        # Period N: September 1 – 30, 2026 form
        if not opens:
            pm = re.search(
                r"(Period\s*\d+\s*:\s*)([A-Za-z]+\s+\d{1,2})\s*[–\-—]\s*(\d{1,2},?\s*\d{4})",
                seg,
                re.I,
            )
            if pm:
                opens_raw = f"{pm.group(2)}"
                closes_raw = f"{pm.group(2).split()[0]} {pm.group(3)}"
                opens = _parse_date_flexible(opens_raw)
                closes = _parse_date_flexible(
                    f"{pm.group(2).split()[0]} {pm.group(3)}",
                    default_year=opens.year if opens else 2026,
                )
        # Month day - day, year for food hunters: August 27 (Thu) - October 6 (Tue)
        if not opens:
            pm = re.search(
                r"([A-Za-z]+\s+\d{1,2})(?:\s*\([^)]+\))?\s*[–\-—]\s*([A-Za-z]+\s+\d{1,2})(?:\s*\([^)]+\))?(?:,\s*(\d{4}))?",
                seg,
            )
            if pm:
                year = int(pm.group(3)) if pm.group(3) else 2026
                opens = _parse_date_flexible(pm.group(1), default_year=year)
                closes = _parse_date_flexible(pm.group(2), default_year=year)
                opens_raw = pm.group(1)
                closes_raw = pm.group(2) + (f", {pm.group(3)}" if pm.group(3) else "")

        winners_m = re.search(r"\((\d+)\s*Winners?", seg, re.I)
        tickets_m = re.search(r"two tickets per|(\d+)\s*tickets? per", seg, re.I)
        residency = None
        nm = re.search(r"(limited to non-Korean citizens only|do not reside in Korea|foreign nationals[^\n]{0,80})", seg, re.I)
        if nm:
            residency = nm.group(1)
        notification = None
        if re.search(r"email", seg, re.I):
            n_m = re.search(r"(Winners will be[^\n]{0,160}email[^\n]{0,80}|announced[^\n]{0,80}via[^\n]{0,80})", seg, re.I)
            notification = n_m.group(1) if n_m else "email notification mentioned"

        # 中文/海报日期：2026.10.26(周一) ~ 2026.11.22(周日) 或 2026/10/26
        if not opens:
            pm = re.search(
                r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})[^\d]{0,12}(?:~|–|-|至|到)\s*(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})",
                seg,
            )
            if pm:
                try:
                    opens = datetime(int(pm.group(1)), int(pm.group(2)), int(pm.group(3)))
                    closes = datetime(int(pm.group(4)), int(pm.group(5)), int(pm.group(6)))
                except ValueError:
                    opens = closes = None
                opens_raw = f"{pm.group(1)}.{pm.group(2)}.{pm.group(3)}"
                closes_raw = f"{pm.group(4)}.{pm.group(5)}.{pm.group(6)}"
        active = _status_for_range(opens, closes, now_n)
        status = open_status_from_dates(
            opens,
            closes,
            now_n,
            requires_login=bool(re.search(r"Join Now|Log in to unlock", seg, re.I)),
            page_has_visible_join=bool(re.search(r"Join Now", seg)),
        )
        if opens is None and closes is None and re.search(r"Join Now", seg, re.I):
            status = "pending_verification"
        if active is None and status == "unknown" and re.search(r"Join Now|Log in", seg, re.I):
            status = "pending_verification"
        rr = EventRoundRules(
            round_label=label,
            edition_key=edition,
            title=(prize_m.group(1) if prize_m else label)[:200],
            organizer_name=organizer,
            prize_summary=(prize_m.group(1) if prize_m else ("flight prize" if prize_flight else "other prize"))[:200],
            prize_is_flight=prize_flight,
            prize_is_gift_or_other=gift and not prize_flight,
            winners_count=int(winners_m.group(1)) if winners_m else None,
            tickets_per_winner=2 if tickets_m else None,
            opens_raw=opens_raw,
            closes_raw=closes_raw,
            opens_iso=opens.isoformat() if opens else None,
            closes_iso=closes.isoformat() if closes else None,
            free_entry=True if prize_flight or gift else None,
            purchase_required=False if prize_flight or gift else None,
            residency_restriction=residency,
            nationality_restriction=residency if residency and "citizen" in residency.lower() else None,
            entry_channel="online_event" if "event" in seg.lower() else None,
            notification_text=notification,
            prize_terms=None,
            active_now=active if status in {"open", "closed"} else (active if active is not None else None),
            open_status=status,
            requires_login_to_enter=bool(re.search(r"Join Now|signin\.do|Log in to unlock", seg, re.I)),
            is_current_phase=is_current,
            evidence_quote=seg[:800],
            tags={"source": "multi_round_split", "open_status": status},
        )
        # open_status 与 active_now 对齐
        if status == "open":
            rr.active_now = True
        elif status == "closed":
            rr.active_now = False
        else:
            rr.active_now = None
        if prize_flight and not opens:
            rr.blocked_notes.append("flight_prize_without_parsed_dates")
        if status == "pending_verification":
            rr.blocked_notes.append("open_state_pending_verification_not_closed")
        return rr
        if prize_flight and not opens:
            rr.blocked_notes.append("flight_prize_without_parsed_dates")
        return rr

    if prev_idx is not None or curr_idx is not None:
        # Previous Event 1 block
        if prev_idx is not None:
            end = curr_idx if curr_idx is not None else min(len(lines), prev_idx + 80)
            seg = _segment_text(prev_idx, end)
            rounds.append(_build_round("previous_event_flight", "prev_flight", seg, is_current=False))
        if curr_idx is not None:
            # Before first Period: general current header
            # Build each Period separately
            if period_idxs:
                # header without periods
                first_p = period_idxs[0]
                header = _segment_text(curr_idx, first_p)
                # Periods
                for i, pidx in enumerate(period_idxs):
                    pend = period_idxs[i + 1] if i + 1 < len(period_idxs) else min(len(lines), pidx + 60)
                    # stop at Event Prize Notice / Disclaimer if present in range
                    for stop_word in ("Event Prize Notice", "Event Disclaimer", "Airfare Prize Terms"):
                        try:
                            j = next(
                                k
                                for k in range(pidx, pend)
                                if stop_word.lower() in lines[k].lower()
                            )
                            pend = j
                            break
                        except StopIteration:
                            pass
                    seg = _segment_text(pidx, pend)
                    # attach header context for prize names if needed
                    combined = header + "\n" + seg
                    rounds.append(
                        _build_round(
                            f"current_period_{i+1}",
                            f"cur_p{i+1}",
                            combined,
                            is_current=True,
                        )
                    )
            else:
                end = len(lines)
                seg = _segment_text(curr_idx, end)
                rounds.append(_build_round("current_event", "current", seg, is_current=True))

    # --- Case C style: single event period with flight ---
    if not rounds or all(not r.prize_is_flight for r in rounds):
        if re.search(r"round-trip (?:flight|ticket)", text, re.I) and re.search(
            r"Event Period", text, re.I
        ):
            m = re.search(
                r"Event Period\s*([A-Za-z]+\s+\d{1,2}(?:\s*\([^)]+\))?\s*[–\-—]\s*[A-Za-z]+\s+\d{1,2}(?:\s*\([^)]+\))?(?:,\s*\d{4})?)",
                text,
                re.I,
            )
            seg = text
            if m:
                seg = m.group(0) + "\n" + text[max(0, m.start() - 200) : m.end() + 800]
            rounds.append(_build_round("single_flight_event", "single_flight", seg, is_current=True))

    # 页面级免责声明适用于全部轮次（若单轮未写明）
    page_res = None
    nm = re.search(
        r"(limited to non-Korean citizens only|open to foreign nationals who do not reside in Korea)",
        text,
        re.I,
    )
    if nm:
        page_res = nm.group(1)
    for r in rounds:
        if not r.residency_restriction and page_res:
            r.residency_restriction = page_res
            r.nationality_restriction = page_res

    # 自动证据提取结果（OCR/HTML，非人工 poster_facts）
    if auto_extract:
        opens = _parse_date_flexible(str(auto_extract.get("opens") or auto_extract.get("opens_iso") or ""))
        closes = _parse_date_flexible(str(auto_extract.get("closes") or auto_extract.get("closes_iso") or ""))
        status = auto_extract.get("open_status") or open_status_from_dates(opens, closes, now_n)
        if status not in {"open", "closed", "pending_verification", "unknown"}:
            status = "unknown"
        # 无关闭日期禁止 closed
        if status == "closed" and not closes:
            status = "pending_verification"
        pr = EventRoundRules(
            round_label="auto_extracted_event",
            edition_key="auto_extract",
            title=str(auto_extract.get("title") or "auto extracted event")[:200],
            organizer_name=organizer,
            prize_summary=str(auto_extract.get("prize_summary") or "auto extracted")[:200],
            prize_is_flight=bool(auto_extract.get("prize_is_flight")),
            prize_is_gift_or_other=auto_extract.get("prize_is_flight") is False,
            winners_count=int(auto_extract["winners_count"])
            if str(auto_extract.get("winners_count") or "").isdigit()
            else None,
            tickets_per_winner=int(auto_extract["tickets_per_winner"])
            if str(auto_extract.get("tickets_per_winner") or "").isdigit()
            else None,
            opens_raw=str(auto_extract.get("opens") or auto_extract.get("opens_iso") or ""),
            closes_raw=str(auto_extract.get("closes") or auto_extract.get("closes_iso") or ""),
            opens_iso=opens.isoformat() if opens else None,
            closes_iso=closes.isoformat() if closes else None,
            free_entry=auto_extract.get("free_entry"),
            purchase_required=False if auto_extract.get("free_entry") else None,
            residency_restriction=auto_extract.get("residency_text"),
            entry_channel=auto_extract.get("entry_channel"),
            open_status=status,
            active_now=True if status == "open" else (False if status == "closed" else None),
            requires_login_to_enter=bool(auto_extract.get("requires_login")),
            evidence_quote=str(auto_extract.get("evidence_quote") or "auto evidence extract")[:800],
            tags={
                "source": "automated_evidence_extract",
                "human_review_required": bool(auto_extract.get("human_review_required", True)),
                "confidence": auto_extract.get("confidence", "medium"),
            },
            blocked_notes=[]
            if status == "open"
            else ["auto_extract_not_open"],
        )
        if auto_extract.get("human_review_required"):
            pr.blocked_notes.append("human_review_required")
        updated = False
        for r in rounds:
            if r.prize_is_flight and not r.opens_iso and pr.opens_iso:
                r.opens_raw = pr.opens_raw
                r.closes_raw = pr.closes_raw
                r.opens_iso = pr.opens_iso
                r.closes_iso = pr.closes_iso
                r.open_status = pr.open_status
                r.active_now = pr.active_now
                r.blocked_notes.append("dates_from_automated_extract")
                updated = True
        if not updated and not any(
            r.prize_is_flight and r.open_status in {"open", "pending_verification"} for r in rounds
        ):
            rounds.append(pr)
        out.notes.append("auto_extract_applied")

    # 海报证据（仅操作员从官方海报读出的日期/奖品；非注入活动 URL）
    if poster_facts:
        opens = _parse_date_flexible(str(poster_facts.get("opens") or ""))
        closes = _parse_date_flexible(str(poster_facts.get("closes") or ""))
        status = open_status_from_dates(opens, closes, now_n)
        pr = EventRoundRules(
            round_label="poster_flight_event",
            edition_key="poster_flight",
            title=str(poster_facts.get("title") or "poster flight event")[:200],
            organizer_name=organizer,
            prize_summary=str(
                poster_facts.get("prize_summary")
                or "round-trip tickets (poster)"
            )[:200],
            prize_is_flight=True,
            winners_count=int(poster_facts["winners"]) if poster_facts.get("winners") else None,
            tickets_per_winner=int(poster_facts["tickets"])
            if poster_facts.get("tickets")
            else None,
            opens_raw=str(poster_facts.get("opens") or ""),
            closes_raw=str(poster_facts.get("closes") or ""),
            opens_iso=opens.isoformat() if opens else None,
            closes_iso=closes.isoformat() if closes else None,
            free_entry=bool(poster_facts.get("free_entry", True)),
            purchase_required=False,
            residency_restriction=poster_facts.get("residency_restriction"),
            entry_channel="quiz_event",
            open_status=status,
            active_now=True if status == "open" else (False if status == "closed" else None),
            evidence_quote=str(poster_facts.get("evidence") or "official poster facts")[:800],
            tags={"source": "official_poster_facts"},
            blocked_notes=[]
            if status == "open"
            else ["poster_facts_not_open"],
        )
        # 若正文已有同主题轮次则更新其日期，否则追加
        updated = False
        for r in rounds:
            if r.prize_is_flight and (not r.opens_iso):
                r.opens_raw = pr.opens_raw
                r.closes_raw = pr.closes_raw
                r.opens_iso = pr.opens_iso
                r.closes_iso = pr.closes_iso
                r.open_status = pr.open_status
                r.active_now = pr.active_now
                r.winners_count = pr.winners_count
                r.tickets_per_winner = pr.tickets_per_winner
                r.blocked_notes.append("dates_from_official_poster_facts")
                updated = True
        if not updated and not any(r.prize_is_flight and r.open_status == "open" for r in rounds):
            rounds.append(pr)
        out.notes.append("poster_facts_applied")

    # 拆分防护：若某段同时含 flight 与 Gift Card 且日期来自 Period，flight 标记仅当本段命中
    for r in rounds:
        if r.prize_is_flight and r.prize_is_gift_or_other:
            r.blocked_notes.append("mixed_prize_keywords_in_segment")
        if r.prize_is_flight and r.open_status == "open" and not r.closes_iso:
            r.blocked_notes.append("open_flight_missing_close_date")

    out.rounds = rounds
    out.notes.append(f"rounds={len(rounds)}")
    return out


def eligibility_with_synthetic_profile(
    rules: EventRoundRules,
    *,
    nationality: str | None,
    residence: str | None,
    age: int | None = None,
) -> dict[str, Any]:
    """三态资格；缺关键限制字段→unknown；有明确 restriction 且档案可知→pass/fail。"""
    checks: list[dict[str, Any]] = []
    state = "unknown"
    reasons: list[str] = []

    # 购买
    if rules.purchase_required is False:
        checks.append({"code": "PURCHASE_REQUIRED", "outcome": "pass", "note": "官方文本显示免费/无需购买"})
    elif rules.purchase_required is True:
        checks.append({"code": "PURCHASE_REQUIRED", "outcome": "ineligible", "note": "需购买"})
        state = "ineligible"
        reasons.append("PURCHASE_REQUIRED")
    else:
        checks.append({"code": "PURCHASE_REQUIRED", "outcome": "unknown", "note": "未解析到购买要求"})
        reasons.append("PURCHASE_RULE_UNKNOWN")

    res_text = (rules.residency_restriction or "").lower()
    needs_non_kr = any(
        k in res_text
        for k in ("non-korean citizens", "do not reside in korea", "non-residents of korea")
    )
    if needs_non_kr:
        if nationality is None or residence is None:
            checks.append(
                {
                    "code": "RESIDENCY_OR_NATIONALITY",
                    "outcome": "unknown",
                    "note": f"规则限制存在；档案 nationality={nationality!r} residence={residence!r} 缺一不可判",
                }
            )
            reasons.append("USER_NATIONALITY_OR_RESIDENCE_INCOMPLETE")
        else:
            nat = nationality.upper()
            res = residence.upper()
            conflict = nat in {"KR", "KOREA", "SOUTH KOREA", "韩国"} or res in {
                "KR",
                "KOREA",
                "SOUTH KOREA",
                "韩国",
            }
            if conflict:
                checks.append(
                    {
                        "code": "RESIDENCY_OR_NATIONALITY",
                        "outcome": "ineligible",
                        "note": "官方限制与档案冲突",
                    }
                )
                state = "ineligible"
                reasons.append("NATIONALITY_OR_RESIDENCE_CONFLICT")
            else:
                checks.append(
                    {
                        "code": "RESIDENCY_OR_NATIONALITY",
                        "outcome": "pass",
                        "note": "档案均非韩国公民/居住且与限制不冲突",
                    }
                )
    else:
        checks.append(
            {
                "code": "RESIDENCY_OR_NATIONALITY",
                "outcome": "unknown",
                "note": "未解析到明确居住/国籍限制",
            }
        )
        reasons.append("RESIDENCY_RULE_UNKNOWN")

    if age is None:
        checks.append({"code": "AGE", "outcome": "unknown", "note": "年龄未知（不得假定 18+）"})
        reasons.append("AGE_UNKNOWN")
    else:
        # 此规则模型尚未保存官方年龄限制，不能自行假设 18 岁门槛。
        checks.append({"code": "AGE", "outcome": "unknown", "note": "官方年龄规则尚未结构化"})
        reasons.append("AGE_RULE_UNKNOWN")

    if state != "ineligible":
        if any(c["outcome"] == "unknown" for c in checks):
            state = "unknown"
        elif all(c["outcome"] == "pass" for c in checks):
            state = "eligible"

    return {
        "state": state,
        "reasons": reasons,
        "checks": checks,
        "note": "有效 ≠ eligible；eligible ≠ 已报名；合成档案仅测规则",
    }
