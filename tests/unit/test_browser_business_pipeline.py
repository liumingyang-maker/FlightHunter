"""浏览器/卡包/邮件/通知集成测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.config import Settings
from app.core.ids import new_id
from app.models import Campaign, CampaignRound, EntryAttempt, Notification, Organizer, Profile
from app.schemas.domain import BenefitOfferCreate
from app.services.benefits.service import create_benefit_offer, ensure_wallet_saved
from app.services.entry.browser_pipeline import (
    execute_browser_entry,
    mail_candidates_to_notifications,
    wallet_store_and_notify,
)


def _round_profile(db):
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
        title="模拟活动",
        organizer_name="O",
        official_url="https://example.org/x",
        verify_status="verified",
        automation_policy="PREFILL_AND_REVIEW",
    )
    p = Profile(id=new_id(), display_name="U", country_of_residence="CN")
    db.add(r)
    db.add(p)
    db.flush()
    return r, p


def _mock_file(settings: Settings) -> Path:
    root = Path(settings.project_root) / "fixtures" / "mock_campaign_site"
    root.mkdir(parents=True, exist_ok=True)
    p = root / "index.html"
    p.write_text("<html><body>mock</body></html>", encoding="utf-8")
    return p.resolve()


def _br(**kw):
    br = MagicMock()
    defaults = dict(
        ok=True,
        status="prefilled",
        submitted=False,
        receipt_code=None,
        message="ok",
        warnings=[],
        requires_human=[],
    )
    defaults.update(kw)
    for k, v in defaults.items():
        setattr(br, k, v)
    return br


def test_pipeline_prefill_only(db, settings: Settings):
    r, p = _round_profile(db)
    with patch("app.services.entry.browser_pipeline.fill_form_with_playwright", return_value=_br()):
        result = execute_browser_entry(db, settings, r, p)
    db.commit()
    attempt = db.get(EntryAttempt, result.attempt_id)
    assert attempt is not None
    assert attempt.status == "awaiting_review"


def test_repeat_prefill_idempotent(db, settings: Settings):
    r, p = _round_profile(db)
    with patch("app.services.entry.browser_pipeline.fill_form_with_playwright", return_value=_br()):
        r1 = execute_browser_entry(db, settings, r, p)
        r2 = execute_browser_entry(db, settings, r, p)
    db.commit()
    assert r1.attempt_id == r2.attempt_id


def test_pipeline_unknown_after_click(db, settings: Settings):
    r, p = _round_profile(db)
    mock = _mock_file(settings)
    with patch(
        "app.services.entry.browser_pipeline.fill_form_with_playwright",
        return_value=_br(
            status="unknown", submitted=True, message="点击后未知", requires_human=["核实"]
        ),
    ):
        result = execute_browser_entry(
            db,
            settings,
            r,
            p,
            file_url=mock.as_uri(),
            submit=True,
            explicit_submit_consent=True,
        )
    db.commit()
    assert result.status == "unknown"
    assert any(n.kind == "entry_unknown" for n in db.query(Notification).all())


def test_pipeline_confirmed_receipt(db, settings: Settings):
    r, p = _round_profile(db)
    mock = _mock_file(settings)
    with patch(
        "app.services.entry.browser_pipeline.fill_form_with_playwright",
        return_value=_br(status="confirmed", submitted=True, receipt_code="RC-1"),
    ):
        result = execute_browser_entry(
            db,
            settings,
            r,
            p,
            file_url=mock.as_uri(),
            submit=True,
            explicit_submit_consent=True,
        )
    db.commit()
    assert result.status == "confirmed"
    n = db.query(Notification).filter(Notification.kind == "entry_confirmed").first()
    assert n is not None
    assert "RC-1" not in (n.body or "")


def test_file_url_outside_sandbox_rejected(db, settings: Settings):
    r, p = _round_profile(db)
    with pytest.raises(ValueError, match="沙箱"):
        execute_browser_entry(db, settings, r, p, file_url="file:///etc/passwd")


def test_wallet_notify_encrypt(db, settings: Settings):
    offer = create_benefit_offer(
        db,
        BenefitOfferCreate(
            organizer_name="店",
            title="t",
            category="shopping_discount",
            official_url="https://example.org/o",
            country_codes=["JP"],
            date_certainty="unconfirmed",
        ),
    )
    db.flush()
    item = ensure_wallet_saved(db, offer, None)
    db.commit()
    out = wallet_store_and_notify(db, settings, wallet_item_id=item.id, plaintext_code="SECRET1")
    db.commit()
    assert out["encrypted"] is True
    assert "SECRET1" not in (item.private_code_encrypted or "")


def test_mail_candidates_notify(db, settings: Settings):
    n = mail_candidates_to_notifications(
        db,
        settings,
        {"candidates": [{"message_id": "m1", "subject": "恭喜中奖", "sender": "x@e.org"}]},
    )
    db.commit()
    assert n == 1
    assert any(x.kind == "mail_candidate" for x in db.query(Notification).all())
