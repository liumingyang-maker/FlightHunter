"""来源、证据、档案模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPk


class Source(Base, UUIDPk, TimestampMixin):
    """来源注册表。"""

    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="official_page")
    language: Mapped[str | None] = mapped_column(String(20))
    country_code: Mapped[str | None] = mapped_column(String(8))
    access_policy: Mapped[str] = mapped_column(String(40), default="public_fetch")
    allowed_fetch_mode: Mapped[str] = mapped_column(String(40), default="httpx")
    status: Mapped[str] = mapped_column(String(40), default="active")
    fetch_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # last_fetch_at = 最近一次**成功**读取（历史/本轮成功口径）
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_valuable_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_signal_count: Mapped[int] = mapped_column(Integer, default=0)
    last_result: Mapped[str | None] = mapped_column(String(40))  # ok|ok_zero|failed|skipped_cooldown
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    module: Mapped[str] = mapped_column(
        String(40), default="shared"
    )  # shared | raffle | trip | fare


class Evidence(Base, UUIDPk, TimestampMixin):
    """字段级证据。"""

    __tablename__ = "evidences"

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    field_path: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    html_locator: Mapped[str | None] = mapped_column(String(500))
    retrieved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(50), default="rule_based")
    verification_method: Mapped[str] = mapped_column(String(50), default="pending_human")


class Profile(Base, UUIDPk, TimestampMixin):
    """真实参与者档案。不由 IP 推断国籍/居住国。"""

    __tablename__ = "profiles"

    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    country_of_residence: Mapped[str | None] = mapped_column(String(8))
    nationality: Mapped[str | None] = mapped_column(String(8))
    date_of_birth: Mapped[str | None] = mapped_column(String(10))  # YYYY-MM-DD
    household_id: Mapped[str | None] = mapped_column(String(36), index=True)
    preferred_departure_airports: Mapped[str] = mapped_column(
        Text, default="[]"
    )  # JSON array string
    preferred_party_size: Mapped[int] = mapped_column(Integer, default=2)
    max_relocation_cost_cny: Mapped[float | None] = mapped_column(String(32))
    payment_networks: Mapped[str] = mapped_column(Text, default="[]")
    issuing_regions: Mapped[str] = mapped_column(Text, default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RawCandidate(Base, UUIDPk, TimestampMixin):
    """发现的原始候选页面。"""

    __tablename__ = "raw_candidates"
    __table_args__ = (UniqueConstraint("source_id", "url", name="uq_raw_candidate_source_url"),)

    source_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    discovered_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_type: Mapped[str] = mapped_column(String(80), default="text/html")
    source_locale: Mapped[str | None] = mapped_column(String(20))
    related_official_urls: Mapped[str] = mapped_column(Text, default="[]")
    raw_content_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default="candidate")
    module: Mapped[str] = mapped_column(String(40), default="shared")
    payload_excerpt: Mapped[str | None] = mapped_column(Text)


class TaskRun(Base, UUIDPk, TimestampMixin):
    """后台任务运行记录（可恢复扫描）。"""

    __tablename__ = "task_runs"

    task_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str | None] = mapped_column(Text)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    result_summary: Mapped[str | None] = mapped_column(Text)


class Notification(Base, UUIDPk, TimestampMixin):
    """站内提醒。"""

    __tablename__ = "notifications"

    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default="info")
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    suppressed_reason: Mapped[str | None] = mapped_column(String(200))


class NotificationDelivery(Base, UUIDPk, TimestampMixin):
    """R-012/R-013：事件+渠道持久送达状态（跨进程可查）。"""

    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("event_key", "channel", name="uq_notification_delivery_event_channel"),)

    event_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending|toast_delivered|recorded|failed|exhausted
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    notification_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("notifications.id", ondelete="SET NULL"))
