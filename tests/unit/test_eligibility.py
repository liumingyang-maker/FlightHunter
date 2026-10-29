"""资格引擎测试：未知不是符合。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.ids import new_id
from app.models import Campaign, CampaignRound, Organizer, Profile
from app.services.eligibility.service import evaluate_eligibility


def _round(db, **kwargs) -> CampaignRound:
    org = Organizer(id=new_id(), name="测试主办方")
    db.add(org)
    db.flush()
    camp = Campaign(
        id=new_id(),
        organizer_id=org.id,
        program_key=f"pk-{new_id()[:8]}",
        name="测试活动",
    )
    db.add(camp)
    db.flush()
    defaults = dict(
        id=new_id(),
        campaign_id=camp.id,
        edition_key="e1",
        title="t",
        organizer_name="o",
        official_url="https://example.org",
        purchase_required=None,
        verify_status="verified",
        frequency="once_per_edition",
        limit_scope="person",
    )
    defaults.update(kwargs)
    return CampaignRound(**defaults)


def test_unknown_residency_needs_review(db):
    profile = Profile(id=new_id(), display_name="A", country_of_residence=None)
    r = _round(db)
    db.add(profile)
    db.add(r)
    db.flush()
    result = evaluate_eligibility(r, profile)
    assert result.state == "needs_review"
    assert (
        "RESIDENCY_RULE_UNKNOWN" in result.reason_codes
        or "PROFILE_INFO_MISSING" in result.reason_codes
    )


def test_closed_entry_ineligible(db):
    profile = Profile(id=new_id(), display_name="A", country_of_residence="CN")
    past = datetime.now(UTC) - timedelta(days=1)
    r = _round(db, entry_closes_at_utc=past)
    db.add(profile)
    db.add(r)
    db.flush()
    result = evaluate_eligibility(r, profile)
    assert result.state == "ineligible"
    assert "ENTRY_CLOSED" in result.reason_codes


def test_rule_checks_documented(db):
    profile = Profile(id=new_id(), display_name="A")
    r = _round(db)
    db.add(profile)
    db.add(r)
    db.flush()
    result = evaluate_eligibility(r, profile)
    codes = {c.code for c in result.rule_checks}
    assert "RESIDENCY" in codes
    assert "PURCHASE_REQUIRED" in codes
    assert "ENTRY_WINDOW" in codes
