"""通用官方活动证据管道：HTML 资产发现 + 图片 OCR + PDF/规则链接 + 结构化字段。

不硬编码任何具体活动 ID/URL/日期；字段均带来源定位与可信状态。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from app.core.url_safety import assert_public_http_url


@dataclass
class EvidenceItem:
    field_path: str
    value: str | None
    source_url: str
    locator: str
    raw_excerpt: str
    method: str  # html_text | image_ocr | pdf_text | link_href
    confidence: str  # high | medium | low | pending
    retrieved_at_utc: str
    content_hash: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RuleExtractResult:
    page_url: str
    page_fetched: bool
    assets: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    opens_raw: str | None = None
    closes_raw: str | None = None
    opens_iso: str | None = None
    closes_iso: str | None = None
    prize_summary: str | None = None
    prize_is_flight: bool | None = None
    winners_count: int | None = None
    tickets_per_winner: int | None = None
    free_entry: bool | None = None
    residency_text: str | None = None
    entry_channel: str | None = None
    contact_text: str | None = None
    open_status: str = "unknown"
    human_review_required: bool = True
    conflict_notes: list[str] = field(default_factory=list)
    ocr_text_sample: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence"] = [e.to_dict() if isinstance(e, EvidenceItem) else e for e in self.evidence]
        return d


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def discover_page_assets(html: str, page_url: str) -> list[dict[str, Any]]:
    """从公开详情页识别正文图、海报、规则/PDF 链接。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    assets: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(kind: str, url: str, locator: str, label: str = "") -> None:
        if not url or url.startswith("data:"):
            return
        abs_u = urljoin(page_url, url.replace("&amp;", "&"))
        if abs_u in seen:
            return
        try:
            assert_public_http_url(abs_u)
        except Exception:
            return
        host = (urlparse(abs_u).hostname or "").lower()
        if any(x in host for x in ("facebook.com", "googletagmanager", "doubleclick", "google-analytics")):
            return
        seen.add(abs_u)
        assets.append(
            {
                "kind": kind,
                "url": abs_u,
                "locator": locator,
                "label": label[:200],
                "same_site": host.endswith(urlparse(page_url).hostname or "")
                or (urlparse(page_url).hostname or "").endswith(host),
            }
        )

    for i, img in enumerate(soup.find_all("img")):
        src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
        alt = (img.get("alt") or "").strip()
        # 优先内容图（非 logo/icon）
        low = (src + " " + alt).lower()
        if any(x in low for x in ("logo", "icon", "favicon", "banner_ad", "quick_banner", "ttalk", "wechat")):
            continue
        if "/public/images/" in src or "poster" in low or len(alt) >= 4:
            kind = "poster_image" if ("/public/images/" in src or "poster" in low or "活动" in alt or "机票" in alt) else "content_image"
            add(kind, src, f"img[{i}] src", alt)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        label = a.get_text(" ", strip=True)
        low_href = href.lower()
        low_label = label.lower()
        if any(x in low_href for x in (".pdf", "download", "rule", "terms", "guideline", "notice", "faq")) or any(
            x in low_label for x in ("规则", "条款", "terms", "rule", "细则", "notice", "guide")
        ):
            add("rule_link", href, f"a[{label[:40]}]", label)
        if href.lower().startswith("javascript:"):
            m = re.search(r"https?://[^'\"]+\.(?:pdf|PDF)(?:[^'\"]*)?", href)
            if m:
                add("rule_link", m.group(0), f"a.js[{label[:40]}]", label)
            m2 = re.search(r"https?://[^'\"]*contentsView\.do\?[^'\"]+", href)
            if m2:
                add("related_page", m2.group(0), f"a.js[{label[:40]}]", label)

    # 文本中裸 PDF
    for m in re.finditer(r"https?://[^\s\"'<>]+\.pdf", html, re.I):
        add("rule_link", m.group(0), "text_pdf", "")

    assets.sort(key=lambda x: (0 if x["kind"] == "poster_image" else 1, 0 if x["same_site"] else 1))
    return assets[:30]


def _ocr_image_bytes(data: bytes, *, langs: str = "eng") -> tuple[str, str]:
    """返回 (text, method)。视觉/OCR 失败则抛给调用方处理。"""
    import io

    import pytesseract
    from PIL import Image

    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    img = Image.open(io.BytesIO(data))
    # 过大时缩放以加速
    max_w = 1800
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)))
    # 尝试多语言
    candidates = [langs, "eng", "osd"]
    last_err = ""
    for lang in candidates:
        try:
            text = pytesseract.image_to_string(img, lang=lang)
            if text and text.strip():
                return text, f"tesseract:{lang}"
        except Exception as exc:
            last_err = str(exc)
    raise RuntimeError(f"ocr_failed:{last_err}")


def _ocr_image_url(url: str, *, timeout: float = 40.0) -> tuple[str, str]:
    import httpx

    headers = {"User-Agent": "FlightHunter-Bot/1.0 (evidence extract)"}
    r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return _ocr_image_bytes(r.content)


def _parse_date_flexible(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    m = re.match(r"(\d{4})[./年-](\d{1,2})[./月-](\d{1,2})", s)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    return None


_DATE_RANGE = re.compile(
    r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})\s*[^0-9]{0,16}?(?:~|–|-|至|到)\s*(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})",
    re.I,
)
_DATE_RANGE_SLASH = re.compile(
    r"(\d{1,2})/(\d{1,2})/(\d{4})\s*(?:~|–|-|to)\s*(\d{1,2})/(\d{1,2})/(\d{4})",
    re.I,
)


def parse_rules_from_text(
    text: str,
    *,
    source_url: str,
    locator: str,
    method: str,
    confidence: str = "medium",
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    now = _now_iso()
    if not text:
        return items

    def add(path: str, value: str | None, excerpt: str, conf: str | None = None, notes: list[str] | None = None):
        if value is None:
            return
        items.append(
            EvidenceItem(
                field_path=path,
                value=value[:500],
                source_url=source_url,
                locator=locator,
                raw_excerpt=excerpt[:800],
                method=method,
                confidence=conf or confidence,
                retrieved_at_utc=now,
                content_hash=_hash(value + locator + source_url),
                notes=notes or [],
            )
        )

    m = _DATE_RANGE.search(text)
    if m:
        raw = f"{m.group(1)}.{m.group(2)}.{m.group(3)} ~ {m.group(4)}.{m.group(5)}.{m.group(6)}"
        add("entry_period", raw, m.group(0), "high")
        add("opens", f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", m.group(0), "high")
        add("closes", f"{m.group(4)}-{int(m.group(5)):02d}-{int(m.group(6)):02d}", m.group(0), "high")
    else:
        m2 = _DATE_RANGE_SLASH.search(text)
        if m2:
            raw = m2.group(0)
            add("entry_period", raw, raw, "high")
            add("opens", f"{m2.group(3)}-{int(m2.group(1)):02d}-{int(m2.group(2)):02d}", raw, "high")
            add("closes", f"{m2.group(6)}-{int(m2.group(4)):02d}-{int(m2.group(5)):02d}", raw, "high")

    # 奖品
    if re.search(r"round[\s-]?trip|往返机票|air ticket|airfare", text, re.I):
        add("prize_is_flight", "true", "round-trip/往返/airfare", "high")
        add("prize_summary", "round-trip flights/tickets", "flight prize text", "medium")
    elif re.search(r"gift card|礼品卡|voucher|礼券", text, re.I):
        add("prize_is_flight", "false", "gift/voucher", "medium")
        add("prize_summary", "gift card/voucher", "gift prize text", "medium")

    wm = re.search(r"(\d+)\s*(?:名|winners?| Winners)", text, re.I)
    if wm:
        add("winners_count", wm.group(1), wm.group(0), "medium")
    tm = re.search(r"(\d+)\s*张|two tickets|tickets per", text, re.I)
    if tm and re.search(r"ticket|机票|张", text, re.I):
        if re.search(r"two tickets|每人\s*2|2\s*张", text, re.I):
            add("tickets_per_winner", "2", "tickets per winner", "medium")

    if re.search(r"free\s+entry|免费|无需购买|no purchase", text, re.I):
        add("free_entry", "true", "free entry text", "medium")
    if re.search(r"non-residents? of Korea|不居住韩国|foreign nationals who do not reside", text, re.I):
        add("residency_text", "non-residents of Korea / foreign nationals not residing in Korea", "residency restriction", "high")
    if re.search(r"survey|quiz|问卷|答题|参与活动", text, re.I):
        add("entry_channel", "quiz_or_survey", "entry channel text", "medium")
    cm = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    if cm:
        add("contact_text", cm.group(0), "email on page", "medium")

    return items


def open_status_from_extract(
    opens: datetime | None,
    closes: datetime | None,
    now: datetime | None = None,
    *,
    requires_login: bool = False,
) -> str:
    n = now or datetime.now(UTC).replace(tzinfo=None)
    if opens and closes:
        if n > closes:
            return "closed"
        if n < opens:
            return "pending_verification"
        return "open"
    if closes:
        return "open" if n <= closes else "closed"
    if requires_login:
        return "pending_verification"
    return "unknown"


async def extract_official_evidence(
    html: str,
    *,
    page_url: str,
    fetch_bytes=None,
    now: datetime | None = None,
    max_posters: int = 3,
) -> RuleExtractResult:
    """从详情页自动提取规则证据。fetch_bytes: async (url)->bytes。"""
    out = RuleExtractResult(page_url=page_url, page_fetched=bool(html))
    if not html:
        out.conflict_notes.append("empty_html")
        return out

    # HTML 正文证据
    from bs4 import BeautifulSoup

    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    html_items = parse_rules_from_text(text, source_url=page_url, locator="body_text", method="html_text", confidence="medium")
    out.evidence.extend(html_items)
    out.assets = discover_page_assets(html, page_url)

    # 图片 OCR（海报）
    poster_assets = [a for a in out.assets if a["kind"] in {"poster_image", "content_image"}]
    ocr_notes: list[str] = []
    for asset in poster_assets[:max_posters]:
        try:
            if fetch_bytes is not None:
                data = await fetch_bytes(asset["url"])
                ocr_text, method = _ocr_image_bytes(data)
            else:
                ocr_text, method = _ocr_image_url(asset["url"])
            out.ocr_text_sample = (out.ocr_text_sample or "") + "\n" + ocr_text[:2000]
            items = parse_rules_from_text(
                ocr_text,
                source_url=asset["url"],
                locator=asset["locator"],
                method=f"image_ocr:{method}",
                confidence="medium",
            )
            # OCR 日期通常更可信（海报专载活动时间）
            for it in items:
                if it.field_path in {"opens", "closes", "entry_period"}:
                    it.confidence = "high"
                    it.notes.append("from_poster_ocr")
            out.evidence.extend(items)
            ocr_notes.append(f"ocr_ok:{asset['locator']}")
        except Exception as exc:
            ocr_notes.append(f"ocr_fail:{asset['locator']}:{type(exc).__name__}")
            out.conflict_notes.append(f"ocr_failed:{asset['locator']}")

    # 规则链接（只记录，不自动登录/提交）
    for a in out.assets:
        if a["kind"] == "rule_link":
            out.evidence.append(
                EvidenceItem(
                    field_path="rule_link",
                    value=a["url"],
                    source_url=page_url,
                    locator=a["locator"],
                    raw_excerpt=a.get("label") or a["url"],
                    method="link_href",
                    confidence="low",
                    retrieved_at_utc=_now_iso(),
                    content_hash=_hash(a["url"]),
                    notes=["not_fetched_full_rules_yet"],
                )
            )

    # 汇总字段（冲突则 pending）
    def best(path: str) -> EvidenceItem | None:
        cands = [e for e in out.evidence if e.field_path == path and e.value]
        if not cands:
            return None
        order = {"high": 0, "medium": 1, "low": 2, "pending": 3}
        cands.sort(key=lambda e: order.get(e.confidence, 9))
        return cands[0]

    opens_e = best("opens")
    closes_e = best("closes")
    if opens_e:
        out.opens_raw = opens_e.value
        d = _parse_date_flexible(opens_e.value or "")
        out.opens_iso = d.isoformat() if d else None
    if closes_e:
        out.closes_raw = closes_e.value
        d = _parse_date_flexible(closes_e.value or "")
        out.closes_iso = d.isoformat() if d else None

    # 冲突：多个不同 closes
    closes_vals = {e.value for e in out.evidence if e.field_path == "closes" and e.value}
    if len(closes_vals) > 1:
        out.conflict_notes.append(f"multiple_closes:{sorted(closes_vals)}")
        out.human_review_required = True

    prize = best("prize_summary")
    if prize:
        out.prize_summary = prize.value
    pf = best("prize_is_flight")
    if pf:
        out.prize_is_flight = pf.value == "true"
    wc = best("winners_count")
    if wc and wc.value and wc.value.isdigit():
        out.winners_count = int(wc.value)
    tp = best("tickets_per_winner")
    if tp and tp.value and tp.value.isdigit():
        out.tickets_per_winner = int(tp.value)
    fe = best("free_entry")
    if fe:
        out.free_entry = fe.value == "true"
    rs = best("residency_text")
    if rs:
        out.residency_text = rs.value
    ch = best("entry_channel")
    if ch:
        out.entry_channel = ch.value
    ct = best("contact_text")
    if ct:
        out.contact_text = ct.value

    opens = _parse_date_flexible(out.opens_raw or "") if out.opens_raw else (
        datetime.fromisoformat(out.opens_iso) if out.opens_iso else None
    )
    closes = _parse_date_flexible(out.closes_raw or "") if out.closes_raw else (
        datetime.fromisoformat(out.closes_iso) if out.closes_iso else None
    )
    requires_login = bool(re.search(r"Join Now|Log in|登录", text, re.I))
    out.open_status = open_status_from_extract(opens, closes, now, requires_login=requires_login)

    # 关键字段缺失 → 待核实
    if not out.opens_iso or not out.closes_iso:
        out.human_review_required = True
        if out.open_status == "unknown":
            out.conflict_notes.append("dates_incomplete")
    if out.prize_is_flight is None:
        out.human_review_required = True
    if ocr_notes and all(n.startswith("ocr_fail") for n in ocr_notes) and not any(
        e.field_path == "opens" for e in out.evidence
    ):
        out.conflict_notes.append("no_ocr_and_no_html_dates")

    # 与 HTML/OCR 均无日期且非 open → 保持 unknown/pending，禁止 closed
    if out.open_status == "closed" and not out.closes_iso:
        out.open_status = "pending_verification"
        out.conflict_notes.append("closed_without_close_date_reverted")

    return out
