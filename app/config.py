"""应用配置：YAML 文件 + 环境变量覆盖。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class AuthConfig(BaseModel):
    """本地 API 鉴权。私人数据接口必须认证。"""

    enabled: bool = True
    api_token: str | None = None  # 为空则首次启动自动生成并写入 auth 文件
    session_cookie_name: str = "fh_session"
    session_max_age_seconds: int = 7 * 24 * 3600
    allow_login_with_token: bool = True
    # 测试/隔离环境：显式状态目录（auth.json/sessions.json），避免与正式环境共用
    state_dir: str | None = None


class AppConfig(BaseModel):
    name: str = "FlightHunter"
    locale: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    web_host: str = "127.0.0.1"
    web_port: int = 8765
    mode: str = "local"
    demo_mode: bool = True
    telemetry_enabled: bool = False


class ProfilesConfig(BaseModel):
    max_profiles_default: int = 2
    require_verified_user_input: bool = True
    country_of_residence: str | None = None
    nationality: str | None = None
    household_id: str | None = None
    default_preferred_departure_airports: list[str] = Field(
        default_factory=lambda: ["CKG", "TFU", "CTU"]
    )
    preferred_party_size: int = 2
    max_relocation_cost_cny: float | None = None


class CategoriesConfig(BaseModel):
    prioritize: list[str] = Field(
        default_factory=lambda: ["flight_giveaway", "flight_hotel_package"]
    )
    include: list[str] = Field(
        default_factory=lambda: [
            "free_hotel",
            "airline_miles",
            "official_travel_grant",
            "travel_voucher",
        ]
    )
    conditional_entry_visible_by_default: bool = False
    paid_entry_blocked: bool = True


class SourcesConfig(BaseModel):
    target_verified_seed_count: int = 100
    search_languages: list[str] = Field(
        default_factory=lambda: [
            "zh-Hans",
            "zh-Hant",
            "en",
            "ja",
            "ko",
            "th",
            "id",
            "ms",
            "es",
            "fr",
            "de",
            "pt",
            "ru",
            "ar",
        ]
    )
    discovery_interval_hours: int = 6
    normal_source_interval_hours: int = 24
    active_source_interval_hours: int = 6
    per_domain_concurrency: int = 1
    min_seconds_between_requests_per_domain: int = 10
    obey_robots_and_site_terms: bool = True
    max_redirects: int = 5
    max_html_bytes: int = 5_242_880
    max_pdf_bytes: int = 15_728_640
    max_runtime_seconds_per_page: int = 30


class AIConfig(BaseModel):
    enabled: bool = False
    provider: str = "openai_compatible"
    base_url: str | None = None
    extraction_model: str | None = None
    escalation_model: str | None = None
    never_send_profile_pii: bool = True
    cache_by_content_hash: bool = True
    daily_cost_estimate_limit_cny: float = 5
    monthly_cost_estimate_limit_cny: float = 50
    daily_request_fallback_limit: int = 200
    api_key: str | None = None  # 仅本地，不进 Git


class EntryConfig(BaseModel):
    default_mode: str = "PREFILL_AND_REVIEW"
    auto_submission_globally_enabled: bool = False
    require_site_permission_and_per_campaign_consent: bool = True
    require_fresh_rules_check_hours: int = 24
    never_auto_retry_unknown_submit: bool = True
    never_bypass_captcha_or_2fa: bool = True
    prohibit_paid_or_sensitive_actions: bool = True
    isolate_browser_profiles: bool = True


class NotificationsConfig(BaseModel):
    in_app_enabled: bool = True
    deadline_hours_before: list[int] = Field(default_factory=lambda: [72, 24, 6])
    claim_reply_hours_before: list[int] = Field(default_factory=lambda: [24, 6, 2])
    email_integration_enabled: bool = False
    browser_notifications_enabled: bool = False
    email_host: str | None = None
    email_user: str | None = None
    email_password: str | None = None  # 仅本地，不进 Git


class StorageConfig(BaseModel):
    sqlite_path: str = "./data/flighthunter.db"
    encryption_key_backend: str = "os_keyring"
    backups_encrypted: bool = True
    raw_snapshot_retention_days: int = 90
    browser_receipt_image_retention_days: int = 30
    participation_history_retention_days: int = 730


class CloudConfig(BaseModel):
    public_discovery_enabled: bool = False
    github_actions_schedule_enabled: bool = False
    cloudflare_d1_sync_enabled: bool = False
    upload_private_user_data: bool = False


class TripBenefitsConfig(BaseModel):
    enabled: bool = True
    default_destination_timezone_lookup: bool = True
    trip_creation_requires_user_action: bool = True
    country_only_search_without_cities: bool = True
    country_wide_promotions_preferred_until_cities_known: bool = True
    scan_after_new_trip: bool = True
    daily_discovery_interval_hours: int = 24
    advance_deep_scan_days_before: list[int] = Field(default_factory=lambda: [90, 30, 7])
    benefit_claim_policy: str = "PREFILL_AND_REVIEW"
    auto_claim_globally_enabled: bool = False
    per_site_auto_claim_requires_explicit_authorization: bool = True
    never_auto_pay_or_reserve_paid_ticket: bool = True
    never_copy_dynamic_app_qr_as_static_voucher: bool = True
    include_paid_spend_based_discounts: bool = True
    count_discount_only_if_planned_spend: bool = True
    unconfirmed_next_year_event_as_historical_only: bool = True
    remind_claim_open_hours_before: list[int] = Field(default_factory=lambda: [24, 1])
    remind_use_expiry_days_before: list[int] = Field(default_factory=lambda: [7, 1])
    remind_use_day_local_hour: int = 9
    quiet_hours_local: list[int] = Field(default_factory=lambda: [23, 8])
    trip_wallet_local_only: bool = True
    encrypt_private_codes_and_receipts: bool = True
    scan_email_for_coupon_receipts_only_if_authorized: bool = False
    allow_ics_export_without_private_codes: bool = True


class TripMonitoringConfig(BaseModel):
    enabled: bool = True
    auto_register_on_trip_save: bool = True
    auto_scan_on_trip_change: bool = True
    create_real_trip_from_email_without_confirmation: bool = False
    optional_email_trip_suggestions_enabled: bool = False
    auto_attach_fare_watch_to_new_trip: bool = True
    background_scan_while_app_running: bool = True
    local_offline_reports_actual_status: bool = True
    on_recovery_rescan: bool = True
    stop_or_reduce_scan_when_trip_completed: bool = True


class AirfareRadarConfig(BaseModel):
    enabled: bool = True
    default_watch_enabled: bool = False
    candidate_origin_airports: list[str] = Field(default_factory=lambda: ["CKG", "TFU", "CTU"])
    destinations_mode: str = "any"
    default_party_size: int = 2
    default_currency: str = "CNY"
    default_trip_types: list[str] = Field(default_factory=lambda: ["round_trip", "one_way"])
    allowed_risk_tiers_for_urgent_alerts: list[str] = Field(default_factory=lambda: ["standard"])
    high_risk_deals_separate_and_visible: bool = True
    discover_error_fares_and_hidden_city_for_review: bool = True
    never_automate_hidden_city_booking: bool = True
    no_auto_ticket_payment_booking_changes: bool = True
    prefer_legal_rss_and_public_web_sources: bool = True
    allow_manual_shares_and_screenshots: bool = True
    publicly_shared_deals_scan_minutes: int = 30
    ordinary_fare_quote_interval_hours: int = 24
    quote_provider_enabled: bool = False
    quote_provider_api_key: str | None = None
    quote_provider_name: str | None = None
    trusted_quote_providers: list[str] = Field(default_factory=list)
    quote_max_ttl_hours: int = 48
    compare_total_cost_for_party: bool = True
    require_real_quote_for_urgent_verified: bool = True
    distinguish_reported_price_and_current_quote: bool = True
    include_taxes_fees_baggage_and_positioning_in_cost: bool = True
    notify_urgent_unverified: bool = False
    never_claim_live_inventory_without_authorized_provider: bool = True
    respect_fetch_and_ai_budget_limits: bool = True
    default_community_sources: list[str] = Field(
        default_factory=lambda: [
            "https://www.smzdm.com/fenlei/guowaijipiao/",
            "https://m.smzdm.com/theme/a788l7k/",
            "https://piao.tips/",
        ]
    )


class Settings(BaseSettings):
    """顶层设置。环境变量前缀 FH_。"""

    model_config = {"env_prefix": "FH_", "env_nested_delimiter": "__", "extra": "ignore"}

    app: AppConfig = Field(default_factory=AppConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    profiles: ProfilesConfig = Field(default_factory=ProfilesConfig)
    categories: CategoriesConfig = Field(default_factory=CategoriesConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    entry: EntryConfig = Field(default_factory=EntryConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    trip_benefits: TripBenefitsConfig = Field(default_factory=TripBenefitsConfig)
    trip_monitoring: TripMonitoringConfig = Field(default_factory=TripMonitoringConfig)
    airfare_radar: AirfareRadarConfig = Field(default_factory=AirfareRadarConfig)

    # 运行时
    config_path: str | None = None
    project_root: str = "."


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(
    config_path: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
) -> Settings:
    """从 YAML 加载配置；路径不存在时使用默认值。"""
    root = Path(project_root or Path.cwd()).resolve()
    path = Path(config_path) if config_path else None
    if path is None:
        candidates = [
            root / "config.yaml",
            root / "config.local.yaml",
        ]
        for candidate in candidates:
            if candidate.is_file():
                path = candidate
                break

    data: dict[str, Any] = {}
    if path and path.is_file():
        with path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"配置文件必须是映射: {path}")
        data = loaded

    settings = Settings(**data)
    settings.project_root = str(root)
    settings.config_path = str(path) if path else None
    return settings


def sqlite_path(settings: Settings) -> Path:
    p = Path(settings.storage.sqlite_path)
    if not p.is_absolute():
        p = Path(settings.project_root) / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
