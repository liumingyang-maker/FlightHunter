"""领域状态机：合法状态与允许的迁移。

严格对应设计包第 3 节与 R2/R3 增补状态机。
非法迁移必须抛出 TransitionError，禁止静默改状态。
"""

from __future__ import annotations

from enum import StrEnum

from app.core.errors import ErrorCode, FlightHunterError


class TransitionError(FlightHunterError):
    def __init__(self, entity: str, current: str, target: str) -> None:
        super().__init__(
            ErrorCode.VALIDATION_FAILED,
            f"非法状态迁移: {entity} {current} -> {target}",
            details={"entity": entity, "current": current, "target": target},
        )


# --- 活动核实 ---
class CampaignVerifyStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    EXPIRED = "expired"


CAMPAIGN_VERIFY_TRANSITIONS: dict[CampaignVerifyStatus, frozenset[CampaignVerifyStatus]] = {
    CampaignVerifyStatus.CANDIDATE: frozenset(
        {CampaignVerifyStatus.VERIFYING, CampaignVerifyStatus.REJECTED}
    ),
    CampaignVerifyStatus.VERIFYING: frozenset(
        {
            CampaignVerifyStatus.VERIFIED,
            CampaignVerifyStatus.NEEDS_REVIEW,
            CampaignVerifyStatus.REJECTED,
        }
    ),
    CampaignVerifyStatus.NEEDS_REVIEW: frozenset(
        {CampaignVerifyStatus.VERIFYING, CampaignVerifyStatus.REJECTED}
    ),
    CampaignVerifyStatus.VERIFIED: frozenset(
        {CampaignVerifyStatus.VERIFYING, CampaignVerifyStatus.EXPIRED}
    ),
    CampaignVerifyStatus.REJECTED: frozenset(),
    CampaignVerifyStatus.EXPIRED: frozenset({CampaignVerifyStatus.VERIFYING}),
}


# --- 每人资格 ---
class EligibilityState(StrEnum):
    NEEDS_REVIEW = "needs_review"
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"


ELIGIBILITY_TRANSITIONS: dict[EligibilityState, frozenset[EligibilityState]] = {
    EligibilityState.NEEDS_REVIEW: frozenset(
        {EligibilityState.ELIGIBLE, EligibilityState.INELIGIBLE}
    ),
    EligibilityState.ELIGIBLE: frozenset({EligibilityState.NEEDS_REVIEW}),
    EligibilityState.INELIGIBLE: frozenset({EligibilityState.NEEDS_REVIEW}),
}


# --- 抽奖报名 ---
class EntryStatus(StrEnum):
    NOT_STARTED = "not_started"
    PREPARED = "prepared"
    AWAITING_REVIEW = "awaiting_review"
    SUBMITTING = "submitting"
    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


ENTRY_TRANSITIONS: dict[EntryStatus, frozenset[EntryStatus]] = {
    EntryStatus.NOT_STARTED: frozenset({EntryStatus.PREPARED, EntryStatus.CANCELLED}),
    EntryStatus.PREPARED: frozenset(
        {EntryStatus.AWAITING_REVIEW, EntryStatus.SUBMITTING, EntryStatus.CANCELLED}
    ),
    EntryStatus.AWAITING_REVIEW: frozenset({EntryStatus.SUBMITTING, EntryStatus.CANCELLED}),
    EntryStatus.SUBMITTING: frozenset(
        {
            EntryStatus.CONFIRMED,
            EntryStatus.UNKNOWN,
            EntryStatus.REJECTED,
            EntryStatus.FAILED,
        }
    ),
    EntryStatus.UNKNOWN: frozenset({EntryStatus.CONFIRMED, EntryStatus.REJECTED}),
    EntryStatus.CONFIRMED: frozenset(),
    EntryStatus.REJECTED: frozenset(),
    EntryStatus.FAILED: frozenset({EntryStatus.PREPARED, EntryStatus.CANCELLED}),
    EntryStatus.CANCELLED: frozenset(),
}

# unknown 禁止自动重试（设计强制）
ENTRY_AUTO_RETRY_FORBIDDEN: frozenset[EntryStatus] = frozenset(
    {EntryStatus.UNKNOWN, EntryStatus.CONFIRMED, EntryStatus.SUBMITTING}
)


# --- 开奖与兑奖 ---
class WinningCheckStatus(StrEnum):
    NOT_ANNOUNCED = "not_announced"
    RESULT_PENDING = "result_pending"
    WON = "won"
    NOT_WON = "not_won"
    RESULT_UNKNOWN = "result_unknown"


class ClaimTaskStatus(StrEnum):
    NOT_STARTED = "not_started"
    CLAIM_PENDING = "claim_pending"
    CLAIMED = "claimed"
    EXPIRED = "expired"


WINNING_TRANSITIONS: dict[WinningCheckStatus, frozenset[WinningCheckStatus]] = {
    WinningCheckStatus.NOT_ANNOUNCED: frozenset(
        {WinningCheckStatus.RESULT_PENDING, WinningCheckStatus.RESULT_UNKNOWN}
    ),
    WinningCheckStatus.RESULT_PENDING: frozenset(
        {
            WinningCheckStatus.WON,
            WinningCheckStatus.NOT_WON,
            WinningCheckStatus.RESULT_UNKNOWN,
        }
    ),
    WinningCheckStatus.RESULT_UNKNOWN: frozenset(
        {WinningCheckStatus.WON, WinningCheckStatus.NOT_WON, WinningCheckStatus.RESULT_PENDING}
    ),
    WinningCheckStatus.WON: frozenset(),
    WinningCheckStatus.NOT_WON: frozenset(),
}


# --- 行程福利 Offer ---
class BenefitOfferStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


BENEFIT_OFFER_TRANSITIONS: dict[BenefitOfferStatus, frozenset[BenefitOfferStatus]] = {
    BenefitOfferStatus.CANDIDATE: frozenset(
        {BenefitOfferStatus.VERIFYING, BenefitOfferStatus.NEEDS_REVIEW}
    ),
    BenefitOfferStatus.VERIFYING: frozenset(
        {
            BenefitOfferStatus.VERIFIED,
            BenefitOfferStatus.NEEDS_REVIEW,
            BenefitOfferStatus.WITHDRAWN,
        }
    ),
    BenefitOfferStatus.NEEDS_REVIEW: frozenset(
        {BenefitOfferStatus.VERIFYING, BenefitOfferStatus.WITHDRAWN}
    ),
    BenefitOfferStatus.VERIFIED: frozenset(
        {
            BenefitOfferStatus.VERIFYING,
            BenefitOfferStatus.WITHDRAWN,
            BenefitOfferStatus.EXPIRED,
        }
    ),
    BenefitOfferStatus.WITHDRAWN: frozenset(),
    BenefitOfferStatus.EXPIRED: frozenset({BenefitOfferStatus.VERIFYING}),
}


class TripMatchState(StrEnum):
    UNASSESSED = "unassessed"
    USABLE = "usable"
    MAYBE_USABLE = "maybe_usable"
    NOT_USABLE = "not_usable"


class BenefitClaimStatus(StrEnum):
    NOT_STARTED = "not_started"
    AVAILABLE = "available"
    PREPARED = "prepared"
    AWAITING_REVIEW = "awaiting_review"
    SUBMITTING = "submitting"
    CLAIMED = "claimed"
    UNKNOWN = "unknown"
    REJECTED = "rejected"
    FAILED_BEFORE_SEND = "failed_before_send"


BENEFIT_CLAIM_TRANSITIONS: dict[BenefitClaimStatus, frozenset[BenefitClaimStatus]] = {
    BenefitClaimStatus.NOT_STARTED: frozenset(
        {BenefitClaimStatus.AVAILABLE, BenefitClaimStatus.PREPARED}
    ),
    BenefitClaimStatus.AVAILABLE: frozenset(
        {BenefitClaimStatus.PREPARED, BenefitClaimStatus.NOT_STARTED}
    ),
    BenefitClaimStatus.PREPARED: frozenset(
        {BenefitClaimStatus.AWAITING_REVIEW, BenefitClaimStatus.SUBMITTING}
    ),
    BenefitClaimStatus.AWAITING_REVIEW: frozenset({BenefitClaimStatus.SUBMITTING}),
    BenefitClaimStatus.SUBMITTING: frozenset(
        {
            BenefitClaimStatus.CLAIMED,
            BenefitClaimStatus.UNKNOWN,
            BenefitClaimStatus.REJECTED,
            BenefitClaimStatus.FAILED_BEFORE_SEND,
        }
    ),
    BenefitClaimStatus.UNKNOWN: frozenset(
        {BenefitClaimStatus.CLAIMED, BenefitClaimStatus.REJECTED}
    ),
    BenefitClaimStatus.CLAIMED: frozenset(),
    BenefitClaimStatus.REJECTED: frozenset(),
    BenefitClaimStatus.FAILED_BEFORE_SEND: frozenset({BenefitClaimStatus.PREPARED}),
}


class WalletItemState(StrEnum):
    SAVED = "saved"
    CLAIMED = "claimed"
    DYNAMIC_APP_REQUIRED = "dynamic_app_required"
    INVALID = "invalid"
    EXPIRED = "expired"
    USED = "used"


class RedemptionState(StrEnum):
    NOT_USED = "not_used"
    PLANNED = "planned"
    USER_MARKED_USED = "user_marked_used"
    MERCHANT_CONFIRMED = "merchant_confirmed"
    EXPIRED = "expired"


# --- 机票雷达状态（分离三类，不合并为单一 status） ---
class FareSignalStatus(StrEnum):
    DISCOVERED = "discovered"
    PARSED = "parsed"
    UNUSABLE = "unusable"
    ARCHIVED = "archived"


class FareQuoteStatus(StrEnum):
    NOT_QUERIED = "not_queried"
    OBSERVED = "observed"
    CHANGED = "changed"
    UNAVAILABLE = "unavailable"
    EXPIRED = "expired"
    PROVIDER_UNKNOWN = "provider_unknown"


class FareBookingStatus(StrEnum):
    NOT_BOOKED = "not_booked"
    USER_REPORTED = "user_reported"
    CONFIRMED_FROM_AUTHORIZED_SOURCE = "confirmed_from_authorized_source"
    CANCELED_BY_USER = "canceled_by_user"
    UNKNOWN = "unknown"


class FareRiskTier(StrEnum):
    STANDARD = "standard"
    NEEDS_REVIEW = "needs_review"
    HIGH_RISK = "high_risk"


class FareRiskCode(StrEnum):
    FUEL_ANOMALY = "FUEL_ANOMALY"
    ERROR_FARE = "ERROR_FARE"
    HIDDEN_CITY = "HIDDEN_CITY"
    SPLIT_TICKET_NO_PROTECTION = "SPLIT_TICKET_NO_PROTECTION"
    MISPRICE_WITHDRAWAL = "MISPRICE_WITHDRAWAL"
    TERMS_VIOLATION_RISK = "TERMS_VIOLATION_RISK"
    COMMUNITY_UNVERIFIED = "COMMUNITY_UNVERIFIED"


class FareDealSubtype(StrEnum):
    NORMAL_PROMO = "normal_promo"
    FLASH_SALE = "flash_sale"
    ERROR_FARE = "error_fare"
    FUEL_SURCHARGE_ANOMALY = "fuel_surcharge_anomaly"
    HIDDEN_CITY = "hidden_city"
    POSITIONING_DEAL = "positioning_deal"
    LAST_MINUTE = "last_minute"
    AWARD_SPACE = "award_space"
    WAITLIST = "waitlist"
    SEAT_RESTOCK = "seat_restock"
    UNCLASSIFIED = "unclassified"


class FareDealStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"
    PRICE_UNCONFIRMED = "price_unconfirmed"
    NO_LONGER_AVAILABLE = "no_longer_available"


class FareAlertLevel(StrEnum):
    URGENT_VERIFIED = "urgent_verified"
    URGENT_UNVERIFIED = "urgent_unverified"
    DIGEST = "digest"


# --- 通用辅助 ---


def assert_transition(
    entity: str,
    current: StrEnum,
    target: StrEnum,
    table: dict,
) -> None:
    """校验状态迁移是否合法。"""
    allowed = table.get(current, frozenset())
    if target not in allowed:
        raise TransitionError(entity, str(current), str(target))


def can_transition(current: StrEnum, target: StrEnum, table: dict) -> bool:
    return target in table.get(current, frozenset())


def is_terminal(status: StrEnum, table: dict) -> bool:
    return len(table.get(status, frozenset())) == 0


def all_values(enum_cls: type[StrEnum]) -> list[str]:
    return [m.value for m in enum_cls]


def assert_in(value: str, enum_cls: type[StrEnum], field: str) -> None:
    if value not in {m.value for m in enum_cls}:
        raise FlightHunterError(
            ErrorCode.VALIDATION_FAILED,
            f"{field} 非法: {value!r}",
            details={"field": field, "allowed": all_values(enum_cls)},
        )


def ensure_no_unknown_submit_retry(current: EntryStatus) -> None:
    if current == EntryStatus.UNKNOWN:
        raise FlightHunterError(
            ErrorCode.SUBMIT_OUTCOME_UNKNOWN,
            "提交结果未知，禁止自动重试",
            details={"status": current.value},
        )
