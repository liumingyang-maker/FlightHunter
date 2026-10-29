"""浏览器报名业务管道：准备 → 预填 → 人工/受限提交 → 回执/unknown → 通知。

将 playwright_exec 与 EntryAttempt/Receipt/状态机打通。
真实外站默认不自动提交；file:// 模拟站可做本地 E2E。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import CampaignRound, Profile
from app.services.browser.playwright_exec import run_prefill_for_round
from app.services.entry.service import (
    begin_submit,
    finish_submit_success,
    finish_submit_unknown,
    mark_awaiting_review,
    prepare_entry,
)
from app.services.notify.delivery import send_notification


@dataclass
class BrowserPipelineResult:
    attempt_id: str
    status: str
    receipt_code: str | None
    browser_ok: bool
    message: str
    warnings: list[str]
    requires_human: list[str]


def execute_browser_entry(
    session: Session,
    settings: Settings,
    round_: CampaignRound,
    profile: Profile,
    *,
    file_url: str | None = None,
    submit: bool = False,
    explicit_submit_consent: bool = False,
) -> BrowserPipelineResult:
    """完整链路：prepare → prefill →（可选受限 submit）→ 状态/回执 → 通知。"""
    attempt = prepare_entry(session, round_, profile)
    mark_awaiting_review(session, attempt)

    result = run_prefill_for_round(
        round_,
        profile,
        file_url=file_url,
        submit=submit,
        explicit_submit_consent=explicit_submit_consent,
    )

    if not result.ok:
        if result.status == "needs_human" or result.requires_human:
            attempt.manual_review_required = True
            attempt.notes = result.message[:500]
            session.flush()
        return BrowserPipelineResult(
            attempt_id=attempt.id,
            status=attempt.status,
            receipt_code=None,
            browser_ok=False,
            message=result.message,
            warnings=result.warnings,
            requires_human=result.requires_human,
        )

    if result.submitted and result.status == "unknown":
        begin_submit(session, attempt)
        finish_submit_unknown(session, attempt, message=result.message[:500])
        send_notification(
            session,
            settings,
            kind="entry_unknown",
            title="报名结果未知",
            body=f"{round_.title}\n{result.message}",
            severity="warning",
            entity_type="entry_attempt",
            entity_id=attempt.id,
        )
        session.flush()
        return BrowserPipelineResult(
            attempt_id=attempt.id,
            status=attempt.status,
            receipt_code=None,
            browser_ok=True,
            message=result.message,
            warnings=result.warnings,
            requires_human=result.requires_human or ["请人工核实官网是否报名成功"],
        )

    if result.submitted and result.receipt_code:
        begin_submit(session, attempt)
        finish_submit_success(session, attempt, receipt_code=result.receipt_code)
        send_notification(
            session,
            settings,
            kind="entry_confirmed",
            title="报名已确认",
            body=f"{round_.title}\n回执: {result.receipt_code}",
            severity="info",
            entity_type="entry_attempt",
            entity_id=attempt.id,
        )
        session.flush()
        return BrowserPipelineResult(
            attempt_id=attempt.id,
            status=attempt.status,
            receipt_code=result.receipt_code,
            browser_ok=True,
            message=result.message,
            warnings=result.warnings,
            requires_human=[],
        )

    # 仅预填，等待人工
    attempt.notes = (attempt.notes or "") + "\n[prefilled] " + result.message
    attempt.manual_review_required = True
    session.flush()
    return BrowserPipelineResult(
        attempt_id=attempt.id,
        status=attempt.status,
        receipt_code=None,
        browser_ok=True,
        message=result.message,
        warnings=result.warnings,
        requires_human=result.requires_human or ["请检查预填内容后人工提交"],
    )


def wallet_store_and_notify(
    session: Session,
    settings: Settings,
    *,
    wallet_item_id: str,
    plaintext_code: str,
    title: str = "券码已加密保存",
) -> dict[str, Any]:
    from app.services.benefits.service import save_wallet_private_code

    item = save_wallet_private_code(
        session, settings, wallet_item_id=wallet_item_id, plaintext_code=plaintext_code
    )
    send_notification(
        session,
        settings,
        kind="wallet_saved",
        title=title,
        body="私密码已本地加密保存；导出不含明文。",
        entity_type="wallet_item",
        entity_id=item.id,
    )
    session.flush()
    return {"wallet_item_id": item.id, "encrypted": True}


def mail_candidates_to_notifications(
    session: Session,
    settings: Settings,
    scan_result: dict[str, Any],
) -> int:
    """IMAP 候选 → 站内提醒（一律 needs_human，不写中奖）。"""
    cands = scan_result.get("candidates") or []
    n = 0
    for c in cands[:20]:
        send_notification(
            session,
            settings,
            kind="mail_candidate",
            title=f"疑似中奖/领券邮件（待人工确认）: {c.get('subject', '')[:80]}",
            body=(
                f"发件人: {c.get('sender')}\n"
                f"message_id: {c.get('message_id')}\n"
                "请人工核对主办方与活动，系统不会自动认定中奖。"
            ),
            severity="warning",
            entity_type="mail_candidate",
            entity_id=c.get("message_id"),
        )
        n += 1
    session.flush()
    return n
