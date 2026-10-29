"""来源适配器基类。遵守 robots / 条款 / 限速；禁止绕过 CAPTCHA。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FetchResult:
    ok: bool
    url: str
    status_code: int | None = None
    content_type: str | None = None
    text: str | None = None
    content_hash: str | None = None
    error_code: str | None = None
    message: str | None = None
    fetched_at: datetime | None = None
    final_url: str | None = None
    robots_disallowed: bool = False


@dataclass
class ParsedSignal:
    title: str
    raw_claim_text: str
    url: str | None = None
    reported_total: float | None = None
    currency: str | None = None
    party_size: int | None = None
    origin_airport: str | None = None
    destination_airport: str | None = None
    airline: str | None = None
    deal_types: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    confidence: str = "low"


class SourceAdapter(ABC):
    """所有来源适配器必须遵守 access_policy。"""

    name: str = "base"

    @abstractmethod
    async def fetch(self, url: str) -> FetchResult:
        """抓取；禁止时返回 ok=False + SOURCE_FETCH_DENIED。"""

    @abstractmethod
    def parse(self, text: str, *, url: str) -> list[ParsedSignal]:
        """解析为信号；识别不出的字段保持 None。"""
