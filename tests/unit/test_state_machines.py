"""状态机与错误码契约测试。"""

from __future__ import annotations

import pytest
from app.core.errors import ErrorCode, FlightHunterError
from app.core.state import (
    BENEFIT_CLAIM_TRANSITIONS,
    ENTRY_TRANSITIONS,
    BenefitClaimStatus,
    CampaignVerifyStatus,
    EntryStatus,
    TransitionError,
    assert_transition,
    can_transition,
    ensure_no_unknown_submit_retry,
)


def test_entry_unknown_cannot_auto_retry():
    with pytest.raises(FlightHunterError) as ei:
        ensure_no_unknown_submit_retry(EntryStatus.UNKNOWN)
    assert ei.value.code == ErrorCode.SUBMIT_OUTCOME_UNKNOWN


def test_entry_confirmed_is_terminal():
    assert can_transition(EntryStatus.CONFIRMED, EntryStatus.PREPARED, ENTRY_TRANSITIONS) is False


def test_entry_prepared_to_awaiting_review():
    assert can_transition(EntryStatus.PREPARED, EntryStatus.AWAITING_REVIEW, ENTRY_TRANSITIONS)


def test_illegal_entry_transition_raises():
    with pytest.raises(TransitionError):
        assert_transition("entry", EntryStatus.CANCELLED, EntryStatus.PREPARED, ENTRY_TRANSITIONS)


def test_campaign_candidate_to_verified_must_verify_first():
    assert can_transition(
        CampaignVerifyStatus.CANDIDATE,
        CampaignVerifyStatus.VERIFYING,
        {CampaignVerifyStatus.CANDIDATE: frozenset({CampaignVerifyStatus.VERIFYING})},
    )
    with pytest.raises(TransitionError):
        assert_transition(
            "campaign",
            CampaignVerifyStatus.CANDIDATE,
            CampaignVerifyStatus.VERIFIED,
            {CampaignVerifyStatus.CANDIDATE: frozenset({CampaignVerifyStatus.VERIFYING})},
        )


def test_benefit_claim_unknown_no_double_claim_path_to_prepared():
    # unknown 只能到 confirmed/rejected，不能直接 prepared
    assert (
        can_transition(
            BenefitClaimStatus.UNKNOWN,
            BenefitClaimStatus.PREPARED,
            BENEFIT_CLAIM_TRANSITIONS,
        )
        is False
    )


def test_error_codes_unique_values():
    values = [c.value for c in ErrorCode]
    assert len(values) == len(set(values))
