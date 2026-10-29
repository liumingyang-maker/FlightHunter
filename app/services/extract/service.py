"""规则/证据提取：保守解析，无证据保持未知。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from app.core.ids import content_hash_of_html, new_id, sha256_text
from app.core.timeutils import utc_now

# 常见日期模式（不猜时区，仅提取原文线索）
_DATE_PATTERNS = [
    re.compile(
        r"(?P<y>20\d{2})[-/年.](?P<m>\d{1,2})[-/月.](?P<d>\d{1,2})日?",
        re.I,
    ),
    re.compile(
        r"(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>20\d{2})",
        re.I,
    ),
]


@dataclass
class ExtractedField:
    field_path: str
    value: str | None
    quote: str | None
    confidence: str  # high | medium | low | none
    source_url: str


@dataclass
class ExtractionResult:
    title: str | None
    fields: list[ExtractedField]
    content_hash: str
    warnings: list[str]


def extract_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()[:300]
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(" ", strip=True)[:300]
    return None


def find_date_clues(html: str, *, source_url: str) -> list[ExtractedField]:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    out: list[ExtractedField] = []
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            snippet = text[max(0, m.start() - 40) : m.end() + 40]
            out.append(
                ExtractedField(
                    field_path="dates.clue",
                    value=m.group(0),
                    quote=snippet,
                    confidence="medium",
                    source_url=source_url,
                )
            )
            if len(out) >= 10:
                return out
    return out


def detect_purchase_requirement(html: str, *, source_url: str) -> ExtractedField:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    lower = text.lower()
    if any(k in text for k in ("无需购买", "免费参加", "无需消费", "no purchase")) or (
        "no purchase" in lower
    ):
        return ExtractedField(
            field_path="purchase_required",
            value="false",
            quote=_snippet(text, ["无需购买", "免费参加", "no purchase"]),
            confidence="medium",
            source_url=source_url,
        )
    if any(k in text for k in ("必须购买", "需先购票", "purchase required", "需消费")):
        return ExtractedField(
            field_path="purchase_required",
            value="true",
            quote=_snippet(text, ["必须购买", "purchase required", "需消费"]),
            confidence="medium",
            source_url=source_url,
        )
    return ExtractedField(
        field_path="purchase_required",
        value=None,
        quote=None,
        confidence="none",
        source_url=source_url,
    )


def _snippet(text: str, keys: list[str]) -> str | None:
    lower = text.lower()
    for k in keys:
        i = text.find(k)
        if i < 0:
            i = lower.find(k.lower())
            if i >= 0:
                return text[max(0, i - 30) : i + len(k) + 40]
            continue
        return text[max(0, i - 30) : i + len(k) + 40]
    return None


def extract_official_fields(html: str, *, source_url: str) -> ExtractionResult:
    """从官方页面提取字段级线索；识别不出 = value None。"""
    warnings: list[str] = []
    fields: list[ExtractedField] = []
    title = extract_title(html)
    fields.extend(find_date_clues(html, source_url=source_url))
    fields.append(detect_purchase_requirement(html, source_url=source_url))

    # CAPTCHA 迹象
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
    if "captcha" in text or "人机验证" in text:
        warnings.append("HUMAN_CHALLENGE")
        fields.append(
            ExtractedField(
                field_path="has_captcha",
                value="true",
                quote="页面包含 captcha/人机验证字样",
                confidence="medium",
                source_url=source_url,
            )
        )

    return ExtractionResult(
        title=title,
        fields=fields,
        content_hash=content_hash_of_html(html),
        warnings=warnings,
    )


def build_evidence_rows(
    entity_type: str,
    entity_id: str,
    result: ExtractionResult,
    *,
    source_kind: str = "official_page",
    retrieved_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """转换为可入库的证据 dict 列表。"""
    now = retrieved_at or utc_now()
    rows = []
    for f in result.fields:
        if f.confidence == "none" or not f.quote:
            continue
        rows.append(
            {
                "id": new_id(),
                "entity_type": entity_type,
                "entity_id": entity_id,
                "field_path": f.field_path,
                "source_url": f.source_url,
                "source_kind": source_kind,
                "quote": f.quote,
                "retrieved_at_utc": now,
                "content_hash": sha256_text(f.quote),
                "extraction_method": "rule_based",
                "verification_method": "pending_human",
            }
        )
    return rows
