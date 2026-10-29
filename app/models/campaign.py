"""抽奖活动三层模型：Campaign / CampaignRound / EntryAttempt 等。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class Organizer(Base, UUIDPk, TimestampMixin):
    __tablename__ = "organizers"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    official_domain: Mapped[str | None] = mapped_column(String(300))
    website_url: Mapped[str | None] = mapped_column(String(2000))
    trust_notes: Mapped[str | None] = mapped_column(Text)


class Campaign(Base, UUIDPk, TimestampMixin):
    """活动品牌/系列（可跨年重复）。"""

    __tablename__ = "campaigns"
    __table_args__ = (UniqueConstraint("organizer_id", "program_key", name="uq_campaign_program"),)

    organizer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizers.id"), nullable=False, index=True
    )
    program_key: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="flight_giveaway")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    legacy_seed: Mapped[bool] = mapped_column(Boolean, default=False)


class CampaignRound(Base, UUIDPk, TimestampMixin):
    """一届/一次具体报名期。"""

    __tablename__ = "campaign_rounds"
    __table_args__ = (UniqueConstraint("campaign_id", "edition_key", name="uq_round_edition"),)

    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    edition_key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    organizer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    official_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    prize_summary: Mapped[str | None] = mapped_column(Text)
    prize_value_min: Mapped[float | None] = mapped_column(Float)
    prize_value_max: Mapped[float | None] = mapped_column(Float)
    prize_currency: Mapped[str | None] = mapped_column(String(8))
    entry_opens_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry_closes_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry_timezone: Mapped[str | None] = mapped_column(String(60))
    entry_closes_date_only: Mapped[bool] = mapped_column(Boolean, default=False)
    draw_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verify_status: Mapped[str] = mapped_column(String(40), default="candidate", index=True)
    automation_policy: Mapped[str] = mapped_column(String(20), default="unknown")
    submission_channel: Mapped[str] = mapped_column(String(30), default="webform")
    purchase_required: Mapped[bool | None] = mapped_column(Boolean)
    has_captcha: Mapped[bool | None] = mapped_column(Boolean)
    need_login: Mapped[bool | None] = mapped_column(Boolean)
    marketing_consent_required: Mapped[bool | None] = mapped_column(Boolean)
    max_entries: Mapped[int | None] = mapped_column(Integer)
    frequency: Mapped[str] = mapped_column(String(40), default="unknown")
    limit_scope: Mapped[str] = mapped_column(String(40), default="unknown")
    allows_multi_participant_entries: Mapped[bool | None] = mapped_column(Boolean)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    demo_only: Mapped[bool] = mapped_column(Boolean, default=True)
    rules_version_hash: Mapped[str | None] = mapped_column(String(64))

    campaign = relationship("Campaign", lazy="selectin", foreign_keys=[campaign_id])


class EligibilityResult(Base, UUIDPk, TimestampMixin):
    __tablename__ = "eligibility_results"
    __table_args__ = (
        UniqueConstraint("round_id", "profile_id", name="uq_eligibility_round_profile"),
    )

    round_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaign_rounds.id"), nullable=False, index=True
    )
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("profiles.id"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(30), default="needs_review", index=True)
    reason_codes: Mapped[str] = mapped_column(Text, default="[]")
    rule_checks: Mapped[str] = mapped_column(Text, default="[]")
    rules_version_hash: Mapped[str | None] = mapped_column(String(64))
    evaluated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EntryAttempt(Base, UUIDPk, TimestampMixin):
    __tablename__ = "entry_attempts"
    __table_args__ = (
        UniqueConstraint(
            "round_id",
            "participant_scope_key",
            "period_key",
            name="uq_entry_scope_period",
        ),
    )

    round_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaign_rounds.id"), nullable=False, index=True
    )
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("profiles.id"), nullable=False, index=True
    )
    household_scope: Mapped[str | None] = mapped_column(String(36))
    participant_scope_key: Mapped[str] = mapped_column(String(80), nullable=False)
    period_key: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    automation_mode: Mapped[str] = mapped_column(String(40), default="PREFILL_AND_REVIEW")
    status: Mapped[str] = mapped_column(String(40), default="not_started", index=True)
    last_submitted_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipt_id: Mapped[str | None] = mapped_column(String(36))
    manual_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)


class EntryEvent(Base, UUIDPk, TimestampMixin):
    __tablename__ = "entry_events"

    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entry_attempts.id"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    actor: Mapped[str] = mapped_column(String(40), default="system")
    detail: Mapped[str | None] = mapped_column(Text)


class Receipt(Base, UUIDPk, TimestampMixin):
    __tablename__ = "receipts"

    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entry_attempts.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), default="confirmation_page")
    reference_code: Mapped[str | None] = mapped_column(String(200))
    evidence_url: Mapped[str | None] = mapped_column(String(2000))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)


class WinningCheck(Base, UUIDPk, TimestampMixin):
    __tablename__ = "winning_checks"
    __table_args__ = (UniqueConstraint("round_id", "profile_id", name="uq_winning_round_profile"),)

    round_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaign_rounds.id"), nullable=False, index=True
    )
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("profiles.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="not_announced")
    announced_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reply_deadline_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class ClaimTask(Base, UUIDPk, TimestampMixin):
    __tablename__ = "claim_tasks"

    winning_check_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("winning_checks.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="not_started")
    official_claim_url: Mapped[str | None] = mapped_column(String(2000))
    materials_needed: Mapped[str] = mapped_column(Text, default="[]")
    deadline_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
