"""Trip / Benefit / Fare / Campaign 的 Pydantic 输入输出契约。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import (
    ClaimMethod,
    DateCertainty,
    LocalWindow,
    MoneyRange,
)

# ---------- Profile ----------


class ProfileCreate(BaseModel):
    display_name: str
    country_of_residence: str | None = None
    nationality: str | None = None
    date_of_birth: date | None = None
    household_id: str | None = None
    preferred_departure_airports: list[str] = Field(default_factory=list)
    preferred_party_size: int = 2
    max_relocation_cost_cny: float | None = None
    # 仅非敏感卡网络元数据
    payment_networks: list[str] = Field(default_factory=list)
    issuing_regions: list[str] = Field(default_factory=list)


class ProfileOut(ProfileCreate):
    id: str
    created_at_utc: datetime


# ---------- Source ----------


class SourceCreate(BaseModel):
    name: str
    base_url: str
    kind: Literal[
        "official_page",
        "rss",
        "community",
        "search_api",
        "manual",
        "other",
    ] = "official_page"
    language: str | None = None
    country_code: str | None = None
    access_policy: Literal[
        "public_fetch",
        "rss_allowed",
        "manual_only",
        "login_required",
        "forbidden",
    ] = "public_fetch"
    allowed_fetch_mode: Literal["httpx", "rss", "playwright", "manual", "none"] = "httpx"
    notes: str | None = None


class SourceOut(SourceCreate):
    id: str
    status: str = "active"
    last_seen_at: datetime | None = None
    created_at_utc: datetime


# ---------- Campaign（抽奖） ----------


class CampaignRoundCreate(BaseModel):
    campaign_id: str
    edition_key: str
    title: str
    organizer_name: str
    official_url: str
    prize_summary: str | None = None
    prize_value: MoneyRange | None = None
    entry_opens_at_utc: datetime | None = None
    entry_closes_at_utc: datetime | None = None
    entry_timezone: str | None = None
    draw_at_utc: datetime | None = None
    automation_policy: Literal["allowed", "forbidden", "unknown"] = "unknown"
    submission_channel: str = "webform"
    purchase_required: bool | None = None
    has_captcha: bool | None = None
    need_login: bool | None = None
    marketing_consent_required: bool | None = None
    max_entries: int | None = None
    frequency: str = "unknown"
    limit_scope: str = "unknown"
    tags: list[str] = Field(default_factory=list)
    demo_only: bool = True


class CampaignRoundOut(CampaignRoundCreate):
    id: str
    verify_status: str = "candidate"
    created_at_utc: datetime
    updated_at_utc: datetime


# ---------- Trip ----------


class TripSegmentIn(BaseModel):
    country_code: str
    city_code: str | None = None
    city_name: str | None = None
    start_date: date
    end_date: date
    timezone: str

    @model_validator(mode="after")
    def _check_dates(self) -> TripSegmentIn:
        if self.end_date < self.start_date:
            raise ValueError("segment end_date 不能早于 start_date")
        return self


class TripCreate(BaseModel):
    label: str
    destination_country_code: str
    local_start_date: date
    local_end_date: date
    timezone: str
    segments: list[TripSegmentIn] = Field(default_factory=list)
    traveler_profile_ids: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    created_from: str = "user_action"
    demo_only: bool = False
    notification_policy: str = "digest_and_urgent"
    allow_unannounced_watch: bool = True

    @model_validator(mode="after")
    def _check_dates(self) -> TripCreate:
        if self.local_end_date < self.local_start_date:
            raise ValueError("行程结束日期不能早于开始日期")
        if self.local_start_date == self.local_end_date:
            pass  # 单日行程合法
        return self


class TripOut(TripCreate):
    id: str
    created_at_utc: datetime
    updated_at_utc: datetime
    scan_registered: bool = False


class TripUpdate(BaseModel):
    label: str | None = None
    local_start_date: date | None = None
    local_end_date: date | None = None
    timezone: str | None = None
    segments: list[TripSegmentIn] | None = None
    traveler_profile_ids: list[str] | None = None
    interests: list[str] | None = None
    archived: bool | None = None


# ---------- BenefitOffer ----------


class BenefitOfferCreate(BaseModel):
    organizer_name: str
    title: str
    category: str
    claim_method: ClaimMethod = "PUBLIC_DISPLAY"
    official_url: str | None = None
    country_codes: list[str] = Field(default_factory=list)
    city_codes: list[str] = Field(default_factory=list)
    claim_window: LocalWindow | None = None
    booking_window: LocalWindow | None = None
    redemption_window: LocalWindow | None = None
    event_window: LocalWindow | None = None
    date_certainty: DateCertainty = "unconfirmed"
    conditions: dict[str, Any] = Field(default_factory=dict)
    face_value: MoneyRange | None = None
    estimated_net_savings: MoneyRange | None = None
    official_evidence_ids: list[str] = Field(default_factory=list)
    source_id: str | None = None
    source_url: str | None = None
    demo_only: bool = True


class BenefitOfferOut(BenefitOfferCreate):
    id: str
    offer_status: str = "candidate"
    created_at_utc: datetime
    updated_at_utc: datetime


class BenefitClaimStart(BaseModel):
    offer_id: str
    profile_id: str | None = None
    household_scope: str | None = None
    automation_mode: Literal["PREFILL_AND_REVIEW", "MANUAL_ONLY", "AUTO_ALLOWED"] = (
        "PREFILL_AND_REVIEW"
    )


class WalletItemOut(BaseModel):
    id: str
    offer_id: str
    state: str
    official_url: str | None = None
    guide_summary: str | None = None
    expires_at_local: datetime | None = None
    created_at_utc: datetime


class RedemptionGuideOut(BaseModel):
    offer_id: str
    language: str = "zh-CN"
    verified_at_utc: datetime
    claim_steps: list[str] = Field(default_factory=list)
    use_steps: list[str] = Field(default_factory=list)
    validity: str | None = None
    minimum_spend: MoneyRange | None = None
    eligible_payment: list[str] = Field(default_factory=list)
    required_items: list[str] = Field(default_factory=list)
    excluded_items: list[str] = Field(default_factory=list)
    stackability: str | None = None
    special_warnings: list[str] = Field(default_factory=list)
    official_urls: list[str] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)
    stale: bool = False


# ---------- Fare radar ----------


class FareWatchCreate(BaseModel):
    name: str
    origin_airports: list[str] = Field(min_length=1)
    destination_scope: Literal["any", "explicit"] = "any"
    destination_airports: list[str] = Field(default_factory=list)
    destination_countries: list[str] = Field(default_factory=list)
    exclude_destination_countries: list[str] = Field(default_factory=list)
    depart_window_start: date | None = None
    depart_window_end: date | None = None
    stay_days_min: int | None = None
    stay_days_max: int | None = None
    trip_type: Literal["round_trip", "one_way", "multi_city"] = "round_trip"
    cabins: list[str] = Field(default_factory=lambda: ["economy"])
    adults: int = 2
    children: int = 0
    require_checked_baggage: bool = False
    max_total_cost_cny: float | None = None
    min_discount_vs_median: float | None = None
    max_positioning_cost_cny: float | None = None
    accept_error_fares: bool = False
    accept_hidden_city: bool = False
    accept_fuel_anomaly: bool = False
    trip_id: str | None = None
    owner_profile_id: str | None = None
    enabled: bool = True

    @field_validator("origin_airports")
    @classmethod
    def _nonempty_origins(cls, v: list[str]) -> list[str]:
        cleaned = [a.strip().upper() for a in v if a.strip()]
        if not cleaned:
            raise ValueError("至少需要一个出发机场")
        return cleaned

    @model_validator(mode="after")
    def _check_window(self) -> FareWatchCreate:
        if (
            self.depart_window_start
            and self.depart_window_end
            and self.depart_window_end < self.depart_window_start
        ):
            raise ValueError("出发窗口结束不能早于开始")
        if self.destination_scope == "explicit" and not (
            self.destination_airports or self.destination_countries
        ):
            raise ValueError("explicit 目的地模式需提供机场或国家")
        return self


class FareWatchOut(FareWatchCreate):
    id: str
    created_at_utc: datetime
    updated_at_utc: datetime
    last_scanned_at: datetime | None = None
    scan_status: str = "idle"


class FareSignalImport(BaseModel):
    """手动导入社区爆料 / 分享链接。"""

    source_id: str | None = None
    original_url: str | None = None
    title: str
    raw_claim_text: str
    published_at_utc: datetime | None = None
    reported_total: float | None = None
    currency: str | None = None
    party_size: int | None = None
    taxes_included: bool | None = None
    origin_airport: str | None = None
    destination_airport: str | None = None
    travel_window_start: date | None = None
    travel_window_end: date | None = None
    airline: str | None = None
    deal_types: list[str] = Field(default_factory=list)
    evidence_text: str | None = None
    user_supplied: bool = True

    @field_validator("origin_airport", "destination_airport")
    @classmethod
    def _upper_iata(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else None


class FareSignalOut(BaseModel):
    id: str
    deal_id: str
    source_id: str | None
    original_url: str | None
    title: str
    raw_claim_text: str
    published_at_utc: datetime | None
    reported_total: float | None
    currency: str | None
    party_size: int | None
    taxes_included: bool | None
    origin_airport: str | None
    destination_airport: str | None
    deal_types: list[str]
    signal_status: str
    created_at_utc: datetime


class FareQuoteOut(BaseModel):
    id: str
    deal_id: str | None
    watch_id: str | None
    provider: str
    observed_at_utc: datetime
    party_size: int
    total_price: float | None
    currency: str
    taxes_included: bool | None
    baggage_included: bool | None
    booking_deeplink: str | None
    availability_confirmed: bool
    quote_status: str


class FareCostBreakdown(BaseModel):
    """两人/多人完整成本。未知费用保持 None 或区间。"""

    base_ticket_total: float | None = None
    required_taxes_and_fees: float | None = None
    positioning: float | None = None
    baggage: float | None = None
    unavoidable_overnight: float | None = None
    other_required_cost: float | None = None
    currency: str = "CNY"
    total_min: float | None = None
    total_max: float | None = None
    unknown_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FareDealOut(BaseModel):
    id: str
    dedup_key: str
    origin: str | None
    destination: str | None
    travel_date_hint: str | None
    airline: str | None
    cabin: str | None
    offer_subtypes: list[str]
    status: str
    risk_tier: str
    first_seen_utc: datetime
    last_seen_utc: datetime
    link: str | None
    signal_count: int = 0
    quote_count: int = 0
    latest_quote_id: str | None = None
