"""Trip Benefits 与旅行卡包模型。"""

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk


class Trip(Base, UUIDPk, TimestampMixin):
    """用户真实计划（本地优先）。demo_only 永不写入用户真实行程。"""

    __tablename__ = "trips"

    label: Mapped[str] = mapped_column(String(200), nullable=False)
    destination_country_code: Mapped[str] = mapped_column(String(8), nullable=False)
    local_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    local_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(60), nullable=False)
    traveler_profile_ids: Mapped[str] = mapped_column(Text, default="[]")
    interests: Mapped[str] = mapped_column(Text, default="[]")
    created_from: Mapped[str] = mapped_column(String(40), default="user_action")
    demo_only: Mapped[bool] = mapped_column(Boolean, default=False)
    # 用户确认真实行程后才启动正式优惠扫描（P3）
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_policy: Mapped[str] = mapped_column(String(40), default="digest_and_urgent")
    allow_unannounced_watch: Mapped[bool] = mapped_column(Boolean, default=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    scan_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    last_benefit_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_fare_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_status: Mapped[str] = mapped_column(String(40), default="idle")
    scan_message: Mapped[str | None] = mapped_column(Text)

    segments = relationship("TripSegment", back_populates="trip", cascade="all, delete-orphan")


class TripSegment(Base, UUIDPk, TimestampMixin):
    __tablename__ = "trip_segments"
    __table_args__ = (
        UniqueConstraint("trip_id", "start_date", "city_code", name="uq_segment_trip_city_start"),
    )

    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    country_code: Mapped[str] = mapped_column(String(8), nullable=False)
    city_code: Mapped[str | None] = mapped_column(String(20))
    city_name: Mapped[str | None] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(60), nullable=False)

    trip = relationship("Trip", back_populates="segments")


class TripScanSubscription(Base, UUIDPk, TimestampMixin):
    """可恢复周期扫描订阅。幂等键见 unique。"""

    __tablename__ = "trip_scan_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "trip_id",
            "source_group",
            "task_type",
            "policy_hash",
            name="uq_trip_scan_sub",
        ),
    )

    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_group: Mapped[str] = mapped_column(String(80), nullable=False)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str] = mapped_column(String(40), default="idle")
    last_message: Mapped[str | None] = mapped_column(Text)
    paused_reason: Mapped[str | None] = mapped_column(String(200))


class BenefitOrganizer(Base, UUIDPk, TimestampMixin):
    __tablename__ = "benefit_organizers"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    official_domain: Mapped[str | None] = mapped_column(String(300))
    website_url: Mapped[str | None] = mapped_column(String(2000))
    country_code: Mapped[str | None] = mapped_column(String(8))


class BenefitOffer(Base, UUIDPk, TimestampMixin):
    """公开优惠/活动实例。与行程匹配是独立概念。"""

    __tablename__ = "benefit_offers"

    organizer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("benefit_organizers.id")
    )
    organizer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    claim_method: Mapped[str] = mapped_column(String(40), default="PUBLIC_DISPLAY")
    official_url: Mapped[str | None] = mapped_column(String(2000))
    country_codes: Mapped[str] = mapped_column(Text, default="[]")
    city_codes: Mapped[str] = mapped_column(Text, default="[]")
    claim_opens_at_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_closes_at_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    booking_opens_at_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    booking_closes_at_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redeem_starts_at_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redeem_ends_at_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_starts_at_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_ends_at_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_timezone: Mapped[str | None] = mapped_column(String(60))
    date_certainty: Mapped[str] = mapped_column(String(40), default="unconfirmed")
    conditions: Mapped[str] = mapped_column(Text, default="{}")
    face_value_min: Mapped[float | None] = mapped_column(Float)
    face_value_max: Mapped[float | None] = mapped_column(Float)
    face_value_currency: Mapped[str | None] = mapped_column(String(8))
    offer_status: Mapped[str] = mapped_column(String(40), default="candidate", index=True)
    source_id: Mapped[str | None] = mapped_column(String(36))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    demo_only: Mapped[bool] = mapped_column(Boolean, default=True)
    rules_version_hash: Mapped[str | None] = mapped_column(String(64))
    stale_guide: Mapped[bool] = mapped_column(Boolean, default=False)


class TripBenefitMatch(Base, UUIDPk, TimestampMixin):
    __tablename__ = "trip_benefit_matches"
    __table_args__ = (UniqueConstraint("trip_id", "offer_id", name="uq_trip_offer_match"),)

    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("benefit_offers.id"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(30), default="unassessed")
    match_category: Mapped[str] = mapped_column(
        String(40), default="sustained_watch"
    )  # claimable | wallet | local_event | sustained_watch
    eligibility_state: Mapped[str] = mapped_column(String(30), default="needs_review")
    reason_codes: Mapped[str] = mapped_column(Text, default="[]")
    estimated_savings_note: Mapped[str | None] = mapped_column(Text)
    evaluated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BenefitClaim(Base, UUIDPk, TimestampMixin):
    __tablename__ = "benefit_claims"
    __table_args__ = (
        UniqueConstraint(
            "offer_id",
            "account_scope_key",
            "profile_scope",
            "issuance_period_key",
            name="uq_benefit_claim_scope",
        ),
    )

    offer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("benefit_offers.id"), nullable=False, index=True
    )
    profile_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("profiles.id"))
    account_scope_key: Mapped[str] = mapped_column(String(80), default="local")
    profile_scope: Mapped[str] = mapped_column(String(80), default="default")
    issuance_period_key: Mapped[str] = mapped_column(String(80), default="once")
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    automation_mode: Mapped[str] = mapped_column(String(40), default="PREFILL_AND_REVIEW")
    status: Mapped[str] = mapped_column(String(40), default="not_started", index=True)
    last_submitted_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipt_reference: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(80))
    manual_review_required: Mapped[bool] = mapped_column(Boolean, default=True)


class WalletItem(Base, UUIDPk, TimestampMixin):
    """旅行卡包。saved ≠ claimed ≠ used。"""

    __tablename__ = "wallet_items"
    __table_args__ = (UniqueConstraint("offer_id", "claim_id", name="uq_wallet_offer_claim"),)

    offer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("benefit_offers.id"), nullable=False, index=True
    )
    claim_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("benefit_claims.id"))
    state: Mapped[str] = mapped_column(String(40), default="saved", index=True)
    official_url: Mapped[str | None] = mapped_column(String(2000))
    guide_summary: Mapped[str | None] = mapped_column(Text)
    expires_at_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redemption_state: Mapped[str] = mapped_column(String(40), default="not_used")
    private_code_encrypted: Mapped[str | None] = mapped_column(Text)
    dynamic_app_link: Mapped[str | None] = mapped_column(String(2000))
    notes: Mapped[str | None] = mapped_column(Text)


class RedemptionGuide(Base, UUIDPk, TimestampMixin):
    __tablename__ = "redemption_guides"

    offer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("benefit_offers.id"), nullable=False, index=True
    )
    language: Mapped[str] = mapped_column(String(20), default="zh-CN")
    verified_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_version_hash: Mapped[str | None] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    unknown_fields: Mapped[str] = mapped_column(Text, default="[]")


class BenefitReminder(Base, UUIDPk, TimestampMixin):
    __tablename__ = "benefit_reminders"

    offer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("benefit_offers.id"), nullable=False, index=True
    )
    trip_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("trips.id"))
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    fire_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fired: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
