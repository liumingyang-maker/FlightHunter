"""统一错误码与领域异常。

来源：设计包《06_领域数据契约与状态机.md》。
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """跨模块统一错误码。"""

    # 来源 / 抓取
    SOURCE_FETCH_DENIED = "SOURCE_FETCH_DENIED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    URL_NOT_PUBLIC = "URL_NOT_PUBLIC"

    # 证据 / 规则
    OFFICIAL_EVIDENCE_MISSING = "OFFICIAL_EVIDENCE_MISSING"
    RULE_CONFLICT = "RULE_CONFLICT"
    TIMEZONE_UNKNOWN = "TIMEZONE_UNKNOWN"

    # 资格
    PROFILE_INFO_MISSING = "PROFILE_INFO_MISSING"
    ELIGIBILITY_FAILED = "ELIGIBILITY_FAILED"

    # 报名
    PURCHASE_REQUIRED = "PURCHASE_REQUIRED"
    SITE_AUTOMATION_FORBIDDEN = "SITE_AUTOMATION_FORBIDDEN"
    FORM_TEMPLATE_CHANGED = "FORM_TEMPLATE_CHANGED"
    HUMAN_CHALLENGE = "HUMAN_CHALLENGE"
    SENSITIVE_ACTION_REQUIRED = "SENSITIVE_ACTION_REQUIRED"
    ENTRY_QUOTA_EXCEEDED = "ENTRY_QUOTA_EXCEEDED"
    SUBMIT_OUTCOME_UNKNOWN = "SUBMIT_OUTCOME_UNKNOWN"
    RECEIPT_NOT_VERIFIED = "RECEIPT_NOT_VERIFIED"

    # AI / 邮件
    AI_BUDGET_EXCEEDED = "AI_BUDGET_EXCEEDED"
    MAIL_ACCESS_REVOKED = "MAIL_ACCESS_REVOKED"
    POSSIBLE_PHISHING = "POSSIBLE_PHISHING"

    # 行程福利（R2）
    TRIP_DATE_INVALID = "TRIP_DATE_INVALID"
    TRIP_CITY_UNKNOWN = "TRIP_CITY_UNKNOWN"
    BENEFIT_DATES_UNCONFIRMED = "BENEFIT_DATES_UNCONFIRMED"
    BENEFIT_TIME_NOT_MATCHED = "BENEFIT_TIME_NOT_MATCHED"
    BENEFIT_ELIGIBILITY_UNKNOWN = "BENEFIT_ELIGIBILITY_UNKNOWN"
    BENEFIT_PAYMENT_REQUIRED = "BENEFIT_PAYMENT_REQUIRED"
    BENEFIT_AUTOMATION_FORBIDDEN = "BENEFIT_AUTOMATION_FORBIDDEN"
    BENEFIT_DYNAMIC_APP_ONLY = "BENEFIT_DYNAMIC_APP_ONLY"
    BENEFIT_CLAIM_QUOTA_EXCEEDED = "BENEFIT_CLAIM_QUOTA_EXCEEDED"
    BENEFIT_CLAIM_OUTCOME_UNKNOWN = "BENEFIT_CLAIM_OUTCOME_UNKNOWN"
    BENEFIT_GUIDE_STALE = "BENEFIT_GUIDE_STALE"
    BENEFIT_REVOKED = "BENEFIT_REVOKED"

    # 机票雷达（R3）
    FARE_SIGNAL_UNPARSEABLE = "FARE_SIGNAL_UNPARSEABLE"
    FARE_QUOTE_PROVIDER_MISSING = "FARE_QUOTE_PROVIDER_MISSING"
    FARE_QUOTE_STALE = "FARE_QUOTE_STALE"
    FARE_RISK_HIGH = "FARE_RISK_HIGH"
    FARE_PARTY_SIZE_MISMATCH = "FARE_PARTY_SIZE_MISMATCH"
    FARE_INVENTORY_UNCONFIRMED = "FARE_INVENTORY_UNCONFIRMED"

    # 任务 / 运行时
    SCHEDULER_LOCKED = "SCHEDULER_LOCKED"
    TASK_ALREADY_RUNNING = "TASK_ALREADY_RUNNING"
    CONFIG_INVALID = "CONFIG_INVALID"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class FlightHunterError(Exception):
    """领域异常基类。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"code": self.code.value, "message": self.message, "details": self.details}


class ValidationError(FlightHunterError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(ErrorCode.VALIDATION_FAILED, message, details=details)


class NotFoundError(FlightHunterError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(ErrorCode.NOT_FOUND, message, details=details)


class TripDateInvalid(FlightHunterError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(ErrorCode.TRIP_DATE_INVALID, message, details=details)


class EligibilityError(FlightHunterError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(ErrorCode.ELIGIBILITY_FAILED, message, details=details)


class EntryQuotaExceeded(FlightHunterError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(ErrorCode.ENTRY_QUOTA_EXCEEDED, message, details=details)


class SubmitOutcomeUnknown(FlightHunterError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(ErrorCode.SUBMIT_OUTCOME_UNKNOWN, message, details=details)


class BenefitClaimOutcomeUnknown(FlightHunterError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(ErrorCode.BENEFIT_CLAIM_OUTCOME_UNKNOWN, message, details=details)


class FareQuoteProviderMissing(FlightHunterError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(ErrorCode.FARE_QUOTE_PROVIDER_MISSING, message, details=details)


class BudgetExceeded(FlightHunterError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(ErrorCode.AI_BUDGET_EXCEEDED, message, details=details)
