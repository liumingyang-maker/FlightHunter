"""抽奖报名：准备、提交态、幂等；禁止 unknown 自动重试。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import (
    ErrorCode,
    FlightHunterError,
)
from app.core.ids import idempotency_key, new_id
from app.core.state import (
    ENTRY_TRANSITIONS,
    CampaignVerifyStatus,
    EntryStatus,
    assert_transition,
    ensure_no_unknown_submit_retry,
)
from app.models import CampaignRound, EntryAttempt, EntryEvent, Profile, Receipt


def participant_scope_key(profile: Profile, round_: CampaignRound) -> str:
    """按 limit_scope 生成报名人范围键。不能凭 URL 生成身份。"""
    scope = (round_.limit_scope or "person").lower()
    if scope == "household" and profile.household_id:
        return f"hh:{profile.household_id}"
    if scope == "account":
        return f"acct:{profile.id}"
    return f"person:{profile.id}"


def period_key_for_round(round_: CampaignRound) -> str:
    """默认每届一次；时区来自活动配置。"""
    tz = round_.entry_timezone or "UTC"
    edition = round_.edition_key
    return f"{edition}@{tz}"


def prepare_entry(
    session: Session,
    round_: CampaignRound,
    profile: Profile,
    *,
    automation_mode: str = "PREFILL_AND_REVIEW",
) -> EntryAttempt:
    if round_.verify_status != CampaignVerifyStatus.VERIFIED.value:
        raise FlightHunterError(
            ErrorCode.OFFICIAL_EVIDENCE_MISSING,
            "活动尚未官方核实，不能进入报名队列",
            details={"verify_status": round_.verify_status},
        )

    scope = participant_scope_key(profile, round_)
    pkey = period_key_for_round(round_)
    idem = idempotency_key(round_.id, scope, pkey, "entry")

    existing = session.scalar(select(EntryAttempt).where(EntryAttempt.idempotency_key == idem))
    if existing:
        if existing.status in (
            EntryStatus.UNKNOWN.value,
            EntryStatus.CONFIRMED.value,
            EntryStatus.SUBMITTING.value,
        ):
            ensure_no_unknown_submit_retry(EntryStatus(existing.status))
            return existing
        if existing.status in (EntryStatus.PREPARED.value, EntryStatus.AWAITING_REVIEW.value):
            return existing
        if existing.status == EntryStatus.FAILED.value:
            assert_transition(
                "entry",
                EntryStatus.FAILED,
                EntryStatus.PREPARED,
                ENTRY_TRANSITIONS,
            )
            existing.status = EntryStatus.PREPARED.value
            session.flush()
            _log_event(session, existing, EntryStatus.FAILED.value, EntryStatus.PREPARED.value)
            return existing

    attempt = EntryAttempt(
        id=new_id(),
        round_id=round_.id,
        profile_id=profile.id,
        household_scope=profile.household_id,
        participant_scope_key=scope,
        period_key=pkey,
        idempotency_key=idem,
        automation_mode=automation_mode,
        status=EntryStatus.PREPARED.value,
        manual_review_required=True,
    )
    session.add(attempt)
    session.flush()
    _log_event(session, attempt, None, EntryStatus.PREPARED.value)
    return attempt


def mark_awaiting_review(session: Session, attempt: EntryAttempt) -> EntryAttempt:
    if attempt.status == EntryStatus.AWAITING_REVIEW.value:
        return attempt
    assert_transition(
        "entry",
        EntryStatus(attempt.status),
        EntryStatus.AWAITING_REVIEW,
        ENTRY_TRANSITIONS,
    )
    prev = attempt.status
    attempt.status = EntryStatus.AWAITING_REVIEW.value
    attempt.manual_review_required = True
    session.flush()
    _log_event(session, attempt, prev, attempt.status)
    return attempt


def begin_submit(session: Session, attempt: EntryAttempt) -> EntryAttempt:
    ensure_no_unknown_submit_retry(EntryStatus(attempt.status))
    if attempt.status not in (
        EntryStatus.PREPARED.value,
        EntryStatus.AWAITING_REVIEW.value,
    ):
        raise FlightHunterError(
            ErrorCode.VALIDATION_FAILED,
            f"当前状态不可提交: {attempt.status}",
        )
    prev = attempt.status
    attempt.status = EntryStatus.SUBMITTING.value
    session.flush()
    _log_event(session, attempt, prev, attempt.status)
    return attempt


def finish_submit_success(
    session: Session, attempt: EntryAttempt, *, receipt_code: str | None = None
) -> EntryAttempt:
    assert_transition(
        "entry",
        EntryStatus(attempt.status),
        EntryStatus.CONFIRMED,
        ENTRY_TRANSITIONS,
    )
    if not receipt_code:
        raise FlightHunterError(
            ErrorCode.RECEIPT_NOT_VERIFIED,
            "缺少确认凭据，不能标记 confirmed",
        )
    receipt = Receipt(
        id=new_id(),
        attempt_id=attempt.id,
        kind="confirmation_page",
        reference_code=receipt_code,
        verified=True,
    )
    session.add(receipt)
    attempt.status = EntryStatus.CONFIRMED.value
    attempt.receipt_id = receipt.id
    attempt.last_submitted_at_utc = datetime.now(UTC)
    attempt.manual_review_required = False
    session.flush()
    _log_event(session, attempt, EntryStatus.SUBMITTING.value, EntryStatus.CONFIRMED.value)
    return attempt


def finish_submit_unknown(
    session: Session, attempt: EntryAttempt, *, message: str = ""
) -> EntryAttempt:
    """仅允许从 submitting 转 unknown；禁止改写 confirmed/cancelled 等终态。"""
    if attempt.status != EntryStatus.SUBMITTING.value:
        raise FlightHunterError(
            ErrorCode.VALIDATION_FAILED,
            f"仅 submitting 可记为 unknown，当前: {attempt.status}",
            details={"status": attempt.status},
        )
    assert_transition("entry", EntryStatus.SUBMITTING, EntryStatus.UNKNOWN, ENTRY_TRANSITIONS)
    prev = EntryStatus.SUBMITTING.value
    attempt.status = EntryStatus.UNKNOWN.value
    attempt.error_code = ErrorCode.SUBMIT_OUTCOME_UNKNOWN.value
    attempt.last_submitted_at_utc = datetime.now(UTC)
    attempt.manual_review_required = True
    attempt.notes = message or "提交结果未知，需人工核实"
    session.flush()
    _log_event(session, attempt, prev, EntryStatus.UNKNOWN.value)
    return attempt


def finish_submit_failed(session: Session, attempt: EntryAttempt, *, message: str) -> EntryAttempt:
    """可证明请求未发出 → failed，允许之后重新 prepare。"""
    if attempt.status != EntryStatus.SUBMITTING.value:
        raise FlightHunterError(
            ErrorCode.VALIDATION_FAILED,
            "仅 submitting 可转为 failed",
        )
    assert_transition("entry", EntryStatus.SUBMITTING, EntryStatus.FAILED, ENTRY_TRANSITIONS)
    attempt.status = EntryStatus.FAILED.value
    attempt.notes = message
    session.flush()
    _log_event(session, attempt, EntryStatus.SUBMITTING.value, EntryStatus.FAILED.value)
    return attempt


def cancel_entry(session: Session, attempt: EntryAttempt) -> EntryAttempt:
    ensure_no_unknown_submit_retry(EntryStatus(attempt.status))
    assert_transition(
        "entry", EntryStatus(attempt.status), EntryStatus.CANCELLED, ENTRY_TRANSITIONS
    )
    prev = attempt.status
    attempt.status = EntryStatus.CANCELLED.value
    session.flush()
    _log_event(session, attempt, prev, EntryStatus.CANCELLED.value)
    return attempt


def _log_event(
    session: Session,
    attempt: EntryAttempt,
    prev: str | None,
    new: str,
) -> None:
    session.add(
        EntryEvent(
            id=new_id(),
            attempt_id=attempt.id,
            from_status=prev,
            to_status=new,
            actor="system",
        )
    )
