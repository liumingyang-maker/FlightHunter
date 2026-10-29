"""R21：模拟回执不得确认非 demo 活动。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.core.ids import new_id
from app.models import Campaign, CampaignRound, Organizer, Profile
from app.services.entry.browser_pipeline import execute_browser_entry


def _round(db, demo_only: bool):
    org = Organizer(id=new_id(), name="O", official_domain="example.org")
    db.add(org)
    db.flush()
    camp = Campaign(id=new_id(), organizer_id=org.id, program_key="k", name="C")
    db.add(camp)
    db.flush()
    r = CampaignRound(
        id=new_id(),
        campaign_id=camp.id,
        edition_key="e",
        title="活动",
        organizer_name="O",
        official_url="https://example.org/x",
        verify_status="verified",
        automation_policy="PREFILL_AND_REVIEW",
        demo_only=demo_only,
    )
    p = Profile(id=new_id(), display_name="U")
    db.add(r)
    db.add(p)
    db.flush()
    return r, p


def _mock(settings: Settings) -> str:
    root = Path(settings.project_root) / "fixtures" / "mock_campaign_site"
    root.mkdir(parents=True, exist_ok=True)
    f = root / "index.html"
    f.write_text("<html></html>", encoding="utf-8")
    return f.resolve().as_uri()


def _confirmed_browser():
    br = MagicMock()
    br.ok = True
    br.status = "confirmed"
    br.submitted = True
    br.receipt_code = "DEMO-1"
    br.message = "ok"
    br.warnings = []
    br.requires_human = []
    return br


def test_mock_receipt_not_applied_to_production_round(db, settings: Settings):
    r, p = _round(db, demo_only=False)
    with patch(
        "app.services.entry.browser_pipeline.fill_form_with_playwright",
        return_value=_confirmed_browser(),
    ):
        result = execute_browser_entry(
            db,
            settings,
            r,
            p,
            file_url=_mock(settings),
            submit=True,
            explicit_submit_consent=True,
        )
    db.commit()
    assert result.status == "unknown"
    assert result.receipt_code is None
    assert "DEMO_RECEIPT_NOT_APPLIED" in result.warnings


def test_mock_receipt_applied_to_demo_round(db, settings: Settings):
    r, p = _round(db, demo_only=True)
    with patch(
        "app.services.entry.browser_pipeline.fill_form_with_playwright",
        return_value=_confirmed_browser(),
    ):
        result = execute_browser_entry(
            db,
            settings,
            r,
            p,
            file_url=_mock(settings),
            submit=True,
            explicit_submit_consent=True,
        )
    db.commit()
    assert result.status == "confirmed"
    assert result.receipt_code == "DEMO-1"
