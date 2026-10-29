"""全球低价机票雷达模型。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPk


class FareWatch(Base, UUIDPk, TimestampMixin):
    """航线愿望单。可无 Trip 独立运行。"""

    __tablename__ = "fare_watches"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("profiles.id"), index=True
    )
    trip_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="SET NULL"), index=True
    )
    origin_airports: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    destination_scope: Mapped[str] = mapped_column(String(20), default="any")
    destination_airports: Mapped[str] = mapped_column(Text, default="[]")
    destination_countries: Mapped[str] = mapped_column(Text, default="[]")
    exclude_destination_countries: Mapped[str] = mapped_column(Text, default="[]")
    depart_window_start: Mapped[date | None] = mapped_column(Date)
    depart_window_end: Mapped[date | None] = mapped_column(Date)
    stay_days_min: Mapped[int | None] = mapped_column(Integer)
    stay_days_max: Mapped[int | None] = mapped_column(Integer)
    trip_type: Mapped[str] = mapped_column(String(20), default="round_trip")
    cabins: Mapped[str] = mapped_column(Text, default='["economy"]')
    adults: Mapped[int] = mapped_column(Integer, default=2)
    children: Mapped[int] = mapped_column(Integer, default=0)
    require_checked_baggage: Mapped[bool] = mapped_column(Boolean, default=False)
    max_total_cost_cny: Mapped[float | None] = mapped_column(Float)
    min_discount_vs_median: Mapped[float | None] = mapped_column(Float)
    max_positioning_cost_cny: Mapped[float | None] = mapped_column(Float)
    accept_error_fares: Mapped[bool] = mapped_column(Boolean, default=False)
    accept_hidden_city: Mapped[bool] = mapped_column(Boolean, default=False)
    accept_fuel_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_status: Mapped[str] = mapped_column(String(40), default="idle")
    scan_message: Mapped[str | None] = mapped_column(Text)


class FareDeal(Base, UUIDPk, TimestampMixin):
    """去重后的优惠机会。"""

    __tablename__ = "fare_deals"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_fare_deal_dedup"),)

    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str | None] = mapped_column(String(12), index=True)
    destination: Mapped[str | None] = mapped_column(String(12), index=True)
    travel_date_hint: Mapped[str | None] = mapped_column(String(80))
    travel_window_start: Mapped[date | None] = mapped_column(Date)
    travel_window_end: Mapped[date | None] = mapped_column(Date)
    airline: Mapped[str | None] = mapped_column(String(120))
    cabin: Mapped[str | None] = mapped_column(String(40))
    offer_subtypes: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    risk_tier: Mapped[str] = mapped_column(String(30), default="standard", index=True)
    booking_status: Mapped[str] = mapped_column(String(50), default="not_booked")
    first_seen_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    link: Mapped[str | None] = mapped_column(String(2000))


class FareDealSignal(Base, UUIDPk, TimestampMixin):
    """社区爆料 / 官方促销信号。≠ 实时报价。"""

    __tablename__ = "fare_deal_signals"

    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fare_deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sources.id"))
    original_url: Mapped[str | None] = mapped_column(String(2000))
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    raw_claim_text: Mapped[str] = mapped_column(Text, default="")
    published_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reported_total: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    party_size: Mapped[int | None] = mapped_column(Integer)
    taxes_included: Mapped[bool | None] = mapped_column(Boolean)
    origin_airport: Mapped[str | None] = mapped_column(String(12))
    destination_airport: Mapped[str | None] = mapped_column(String(12))
    airline: Mapped[str | None] = mapped_column(String(120))
    deal_types: Mapped[str] = mapped_column(Text, default="[]")
    evidence_text: Mapped[str | None] = mapped_column(Text)
    text_evidence_hash: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(40), default="community")
    signal_status: Mapped[str] = mapped_column(String(30), default="discovered", index=True)
    confidence: Mapped[str] = mapped_column(String(20), default="low")
    user_supplied: Mapped[bool] = mapped_column(Boolean, default=False)


class FareQuote(Base, UUIDPk, TimestampMixin):
    """合法报价快照，append-only 历史。"""

    __tablename__ = "fare_quotes"

    deal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("fare_deals.id", ondelete="SET NULL"), index=True
    )
    watch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("fare_watches.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_quote_id: Mapped[str | None] = mapped_column(String(200))
    booking_deeplink: Mapped[str | None] = mapped_column(String(2000))
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    origin: Mapped[str | None] = mapped_column(String(12))
    destination: Mapped[str | None] = mapped_column(String(12))
    depart_date: Mapped[date | None] = mapped_column(Date)
    return_date: Mapped[date | None] = mapped_column(Date)
    pax_count: Mapped[int] = mapped_column(Integer, default=1)
    total_price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    tax_included: Mapped[bool | None] = mapped_column(Boolean)
    baggage_included: Mapped[bool | None] = mapped_column(Boolean)
    booking_class: Mapped[str | None] = mapped_column(String(40))
    availability_confidence: Mapped[str] = mapped_column(String(30), default="unconfirmed")
    availability_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    quote_expiry_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quote_status: Mapped[str] = mapped_column(String(30), default="observed", index=True)


class FareWatchMatch(Base, UUIDPk, TimestampMixin):
    __tablename__ = "fare_watch_matches"
    __table_args__ = (UniqueConstraint("watch_id", "deal_id", name="uq_fare_watch_deal"),)

    watch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fare_watches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fare_deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_status: Mapped[str] = mapped_column(String(30), default="not_queried")
    date_match: Mapped[str] = mapped_column(String(20), default="unknown")
    passenger_match: Mapped[str] = mapped_column(String(20), default="unknown")
    risk_match: Mapped[str] = mapped_column(String(20), default="unknown")
    net_cost_min: Mapped[float | None] = mapped_column(Float)
    net_cost_max: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    score: Mapped[float | None] = mapped_column(Float)
    reason_codes: Mapped[str] = mapped_column(Text, default="[]")
    evaluated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FareAlert(Base, UUIDPk, TimestampMixin):
    __tablename__ = "fare_alerts"
    __table_args__ = (
        UniqueConstraint("watch_id", "deal_id", "content_hash", name="uq_fare_alert_dedup"),
    )

    watch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fare_watches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fare_deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_level: Mapped[str] = mapped_column(String(30), default="digest")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    latest_quote_id: Mapped[str | None] = mapped_column(String(36))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_status: Mapped[str] = mapped_column(String(30), default="pending")
    delivered_channels: Mapped[str] = mapped_column(Text, default="[]")
    suppression_reason: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)


class FareRiskEvidence(Base, UUIDPk, TimestampMixin):
    __tablename__ = "fare_risk_evidence"

    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fare_deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    cited_url: Mapped[str | None] = mapped_column(String(2000))
    original_statement: Mapped[str] = mapped_column(Text, default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_state: Mapped[str] = mapped_column(String(30), default="pending")


class FarePriceHistory(Base, UUIDPk):
    """同航线历史价格样本，用于中位数（样本不足不用假历史最低）。"""

    __tablename__ = "fare_price_history"
    __table_args__ = (
        UniqueConstraint(
            "route_key",
            "depart_date",
            "provider",
            "observed_at_utc",
            name="uq_price_history_sample",
        ),
    )

    route_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    origin: Mapped[str] = mapped_column(String(12), nullable=False)
    destination: Mapped[str] = mapped_column(String(12), nullable=False)
    depart_date: Mapped[date | None] = mapped_column(Date)
    pax_count: Mapped[int] = mapped_column(Integer, default=1)
    cabin: Mapped[str | None] = mapped_column(String(40))
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
