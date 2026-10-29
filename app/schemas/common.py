"""Pydantic 公共契约。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceKind = Literal[
    "official_page",
    "official_terms",
    "organizer_social_post",
    "authorized_host",
    "third_party_reporting",
    "user_supplied",
]

ClaimMethod = Literal[
    "PUBLIC_DISPLAY",
    "ACCOUNT_CLAIM",
    "APP_ONLY",
    "BOOKING_REQUIRED",
    "ON_SITE",
    "MANUAL",
]

DateCertainty = Literal[
    "confirmed_for_dates",
    "historical_reference",
    "not_yet_announced",
    "unconfirmed",
]

AutomationPolicy = Literal["allowed", "forbidden", "unknown"]

SubmissionChannel = Literal["webform", "social", "email", "postal", "in_person", "other"]

Frequency = Literal["once_per_edition", "once_per_day", "once_per_week", "limited_n", "unknown"]


class ApiOk(BaseModel):
    ok: Literal[True] = True
    data: Any
    request_id: str
    server_time_utc: datetime


class ApiErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApiError(BaseModel):
    ok: Literal[False] = False
    error: ApiErrorBody
    request_id: str


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class FieldEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    field_path: str
    source_url: str
    source_kind: SourceKind
    quote: str
    html_locator: str | None = None
    retrieved_at_utc: datetime
    content_hash: str
    extraction_method: str = "rule_based"
    verification_method: str = "pending_human"


class MoneyRange(BaseModel):
    """可选金额区间；无可靠数字时用 None，禁止假精确。"""

    min: float | None = None
    max: float | None = None
    currency: str | None = None
    basis: str | None = None
    estimated_at: datetime | None = None


class LocalWindow(BaseModel):
    """当地时区窗口；null 表示未知，不得补成 23:59。"""

    opens_at_local: datetime | None = None
    closes_at_local: datetime | None = None
    starts_at_local: datetime | None = None
    ends_at_local: datetime | None = None
    timezone: str | None = None


class RuleCheck(BaseModel):
    code: str
    outcome: Literal["pass", "fail", "unknown"]
    profile_value_known: bool = False
    official_rule_known: bool = False
    evidence_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class EligibilityResultModel(BaseModel):
    round_id: str
    profile_id: str
    state: Literal["eligible", "ineligible", "needs_review"]
    reason_codes: list[str] = Field(default_factory=list)
    rule_checks: list[RuleCheck] = Field(default_factory=list)
    evaluated_at_utc: datetime
    rules_version_hash: str


class DateOnly(BaseModel):
    """行程日期使用目的地当地自然日 YYYY-MM-DD。"""

    value: date
