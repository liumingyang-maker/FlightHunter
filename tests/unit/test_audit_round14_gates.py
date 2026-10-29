"""第十四轮 P0/P1 回归。"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.config import Settings
from app.services.browser.playwright_exec import fill_form_with_playwright
from app.services.browser.prefill import PrefillField, PrefillPlan
from app.services.notify.delivery import send_notification
from app.services.wallet.crypto import decrypt_secret, encrypt_secret


def test_prefill_review_never_auto_submits():
    plan = PrefillPlan(target_url="https://example.org/x", mode="PREFILL_AND_REVIEW")
    plan.fields.append(PrefillField("full_name", "张三", "profile"))
    r = fill_form_with_playwright(plan, submit=True, explicit_submit_consent=True)
    assert r.ok is False
    assert r.submitted is False
    assert r.status in ("needs_human", "blocked", "needs_manual")


def test_console_is_not_external_delivered(db):
    n = send_notification(db, None, kind="t", title="hi", body="b", try_toast=False)
    db.commit()
    assert n is not None
    assert "toast_delivered" not in (n.body or "")


def test_wallet_rejects_weak_or_roundtrips(tmp_path: Path):
    s = Settings()
    s.project_root = str(tmp_path)
    token = encrypt_secret(s, "A" * 128)
    assert token.startswith("dpapi:") or token.startswith("aesgcm:")
    assert not token.startswith("v1:")
    assert decrypt_secret(s, token) == "A" * 128


def test_wallet_rejects_legacy_v1(tmp_path: Path):
    s = Settings()
    s.project_root = str(tmp_path)
    with pytest.raises(ValueError, match="未知密文格式"):
        decrypt_secret(s, "v1:AAAA")
