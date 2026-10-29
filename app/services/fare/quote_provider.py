"""可插拔实时报价供应商接口。

无配置供应商时 quote_provider_enabled=False；绝不虚构库存。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class QuoteRequest:
    origin: str
    destination: str
    depart_date: date
    return_date: date | None
    adults: int
    currency: str = "CNY"


@dataclass
class QuoteResponse:
    ok: bool
    provider: str
    total_price: float | None
    currency: str
    taxes_included: bool | None
    baggage_included: bool | None
    availability_confirmed: bool
    expires_at: datetime | None
    message: str
    booking_deeplink: str | None = None


class FareQuoteProvider(ABC):
    name: str = "base"

    @abstractmethod
    def quote(self, req: QuoteRequest) -> QuoteResponse:
        """同步查询；未授权/未配置时 ok=False。"""


class NullFareQuoteProvider(FareQuoteProvider):
    name = "null"

    def quote(self, req: QuoteRequest) -> QuoteResponse:
        return QuoteResponse(
            ok=False,
            provider=self.name,
            total_price=None,
            currency=req.currency,
            taxes_included=None,
            baggage_included=None,
            availability_confirmed=False,
            expires_at=None,
            message="未配置实时报价供应商；保持情报模式",
        )


def get_quote_provider(settings) -> FareQuoteProvider:
    name = (settings.airfare_radar.quote_provider_name or "").lower()
    if settings.airfare_radar.quote_provider_enabled and name == "demo":
        return DemoFareQuoteProvider()
    return NullFareQuoteProvider()


class DemoFareQuoteProvider(FareQuoteProvider):
    """演示适配器：仅在显式配置 provider=demo 时启用；返回未确认库存。"""

    name = "demo"

    def quote(self, req: QuoteRequest) -> QuoteResponse:
        # 不生成虚假“可买库存”；仅回显请求用于联调
        return QuoteResponse(
            ok=False,
            provider=self.name,
            total_price=None,
            currency=req.currency,
            taxes_included=None,
            baggage_included=None,
            availability_confirmed=False,
            expires_at=None,
            message="demo 适配器已加载，但不返回虚构可购价；请配置真实授权供应商",
        )
