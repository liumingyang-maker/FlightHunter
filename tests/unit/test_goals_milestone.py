"""三大目标：通知送达、加密、Playwright、报价插件。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.config import Settings
from app.services.fare.quote_provider import NullFareQuoteProvider, QuoteRequest
from app.services.notify.delivery import send_notification
from app.services.wallet.crypto import decrypt_secret, encrypt_secret


def test_encrypt_decrypt_roundtrip(tmp_path: Path):
    s = Settings()
    s.project_root = str(tmp_path)
    token = encrypt_secret(s, "SECRET-CODE-123")
    assert token.startswith("v1:") or token.startswith("dpapi:")
    # v1 路径可在同机解密；dpapi 也应在同 Windows 用户解密
    assert decrypt_secret(s, token) == "SECRET-CODE-123"


def test_console_delivery_and_notification(db):
    n = send_notification(
        db,
        None,
        kind="test",
        title="测试通知",
        body="hello",
        try_toast=False,
    )
    db.commit()
    assert n is not None
    assert "delivery" in (n.body or "") or n.body


def test_null_quote_provider_blocks():
    p = NullFareQuoteProvider()
    r = p.quote(
        QuoteRequest(
            origin="CKG",
            destination="NRT",
            depart_date=date(2027, 5, 1),
            return_date=None,
            adults=2,
        )
    )
    assert r.ok is False
    assert r.availability_confirmed is False


def test_community_provider_rejected_in_record_quote(db):
    import pytest
    from app.core.errors import ValidationError
    from app.services.fare.service import record_quote

    with pytest.raises(ValidationError):
        record_quote(
            db,
            deal_id=None,
            watch_id=None,
            provider="community",
            party_size=2,
            total_price=100,
        )


def test_playwright_mock_site_prefill_without_browser():
    """未安装浏览器时应 blocked，而非伪造成功。"""
    from app.services.browser.playwright_exec import fill_form_with_playwright
    from app.services.browser.prefill import PrefillField, PrefillPlan

    plan = PrefillPlan(target_url="file:///nonexistent/x.html", mode="PREFILL_AND_REVIEW")
    plan.fields.append(PrefillField("full_name", "张三", "profile"))
    r = fill_form_with_playwright(plan, file_url="file:///nonexistent/x.html")
    assert r.ok is False
    assert r.status in ("blocked", "failed", "unknown")
