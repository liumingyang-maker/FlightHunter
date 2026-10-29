"""R20 边界：file URI 解码、执行异常收敛 unknown、失败通知。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.core.ids import new_id
from app.models import Campaign, CampaignRound, Notification, Organizer, Profile
from app.services.browser.playwright_exec import _resolve_file_target
from app.services.entry.browser_pipeline import execute_browser_entry


def test_file_uri_percent_and_windows_drive(tmp_path: Path):
    d = tmp_path / "mock site"
    d.mkdir()
    f = d / "index.html"
    f.write_text("x", encoding="utf-8")
    uri = f.as_uri()  # file:///...%20...
    ok, resolved, err = _resolve_file_target(uri)
    assert ok and err is None
    assert resolved is not None
    assert resolved.startswith("file:")

    # Windows 风格 file:///C:/ 不在此平台断言绝对路径存在，只测解析不抛错
    ok2, _, err2 = _resolve_file_target("file:///C:/nonexistent-drive/x.html")
    assert ok2 is False


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


def test_uncaught_browser_error_becomes_unknown(db, settings: Settings):
    r, p = _round_profile(db)
    root = Path(settings.project_root) / "fixtures" / "mock_campaign_site"
    root.mkdir(parents=True, exist_ok=True)
    f = root / "index.html"
    f.write_text("<html></html>", encoding="utf-8")
    with patch(
        "app.services.entry.browser_pipeline.fill_form_with_playwright",
        side_effect=RuntimeError("chromium crashed"),
    ):
        result = execute_browser_entry(
            db,
            settings,
            r,
            p,
            file_url=f.resolve().as_uri(),
            submit=True,
            explicit_submit_consent=True,
        )
    db.commit()
    assert result.status == "unknown"
    assert any(n.kind == "entry_unknown" for n in db.query(Notification).all())


def test_failed_browser_after_submit_notifies(db, settings: Settings):
    r, p = _round_profile(db)
    root = Path(settings.project_root) / "fixtures" / "mock_campaign_site"
    root.mkdir(parents=True, exist_ok=True)
    f = root / "index.html"
    f.write_text("<html></html>", encoding="utf-8")
    br = MagicMock()
    br.ok = False
    br.status = "failed"
    br.submitted = False
    br.receipt_code = None
    br.message = "fill failed"
    br.warnings = []
    br.requires_human = []
    with patch(
        "app.services.entry.browser_pipeline.fill_form_with_playwright",
        return_value=br,
    ):
        result = execute_browser_entry(
            db,
            settings,
            r,
            p,
            file_url=f.resolve().as_uri(),
            submit=True,
            explicit_submit_consent=True,
        )
    db.commit()
    assert result.status == "unknown"
    assert any(n.kind == "entry_unknown" for n in db.query(Notification).all())
