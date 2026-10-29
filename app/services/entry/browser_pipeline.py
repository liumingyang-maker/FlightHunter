"""浏览器报名业务管道：准备 → 预填 →（先持久化提交意图）→ 浏览器 → 回执/unknown → 通知。

安全：
- file_url 仅允许仓库内 fixtures/mock_campaign_site
- 提交前 begin_submit 持久化
- 回执码通知脱敏
- 真实外站不自动提交
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import CampaignRound, Profile
from app.services.browser.playwright_exec import fill_form_with_playwright
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


def _allowed_mock_root(settings: Settings) -> Path:
    return (Path(settings.project_root) / "fixtures" / "mock_campaign_site").resolve()


def _check_file_url(settings: Settings, file_url: str) -> Path:
    from urllib.parse import unquote, urlparse

    if not file_url.startswith("file:"):
        raise ValueError("仅允许 file:// 模拟站")
    parsed = urlparse(file_url)
    # file:///C:/x 或 file:///home/x → path=/C:/x 或 /home/x
    raw_path = unquote(parsed.path or "")
    if raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
        raw_path = raw_path[1:]  # Windows /C: → C:
    path = Path(raw_path)
    resolved = path.resolve()
    root = _allowed_mock_root(settings)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("file_url 仅允许 fixtures/mock_campaign_site 沙箱") from exc
    if not resolved.is_file():
        raise ValueError(f"模拟页不存在: {resolved}")
    return resolved


def execute_browser_entry(
    session: Session,
    settings: Settings,
    round_: CampaignRound,
    profile: Profile,
    *,
    file_url: str | None = None,
    submit: bool = False,
    explicit_submit_consent: bool = False,
    user_approved_fields: dict[str, str] | None = None,
) -> BrowserPipelineResult:
    local_mock = None
    if file_url:
        local_mock = _check_file_url(settings, file_url)

    attempt = prepare_entry(session, round_, profile)
    mark_awaiting_review(session, attempt)

    from app.services.browser.prefill import build_prefill_plan

    plan = build_prefill_plan(
        round_,
        profile,
        user_approved_fields=user_approved_fields,
        allow_local_mock_submit=bool(local_mock and submit),
    )
    will_submit = bool(
        local_mock and submit and explicit_submit_consent and plan.mode == "AUTO_ALLOWED"
    )

    # GATE-02：提交前持久化 submitting
    if will_submit:
        begin_submit(session, attempt)
        session.commit()

    mock_uri = local_mock.as_uri() if local_mock else None
    try:
        result = fill_form_with_playwright(
            plan,
            file_url=mock_uri,
            submit=will_submit,
            explicit_submit_consent=explicit_submit_consent,
        )
    except Exception as exc:
        msg = f"浏览器执行异常: {exc}"
        if attempt.status == "submitting":
            finish_submit_unknown(session, attempt, message=msg[:500])
            send_notification(
                session,
                settings,
                kind="entry_unknown",
                title="报名结果未知（执行异常）",
                body=f"{round_.title}\n{msg[:200]}\n请人工核实；不会自动重试。",
                severity="warning",
                entity_type="entry_attempt",
                entity_id=attempt.id,
            )
        else:
            attempt.notes = msg[:500]
            attempt.manual_review_required = True
        session.flush()
        return BrowserPipelineResult(
            attempt_id=attempt.id,
            status=attempt.status,
            receipt_code=None,
            browser_ok=False,
            message=msg,
            warnings=[],
            requires_human=["请人工核实报名状态"],
        )

    if not result.ok:
        if attempt.status == "submitting":
            finish_submit_unknown(session, attempt, message=result.message[:500])
            send_notification(
                session,
                settings,
                kind="entry_unknown",
                title="报名结果未知",
                body=f"{round_.title}\n{result.message[:200]}\n请人工核实；系统不会自动重试。",
                severity="warning",
                entity_type="entry_attempt",
                entity_id=attempt.id,
            )
        else:
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
            requires_human=result.requires_human or ["请人工核实"],
        )

    if result.submitted and result.status == "unknown":
        if attempt.status != "submitting":
            begin_submit(session, attempt)
        finish_submit_unknown(session, attempt, message=result.message[:500])
        send_notification(
            session,
            settings,
            kind="entry_unknown",
            title="报名结果未知",
            body=f"{round_.title}\n请人工核实官网；系统不会自动重试。",
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
        # 模拟站回执不得把正式活动标成真实报名成功
        if not round_.demo_only and local_mock is not None:
            if attempt.status != "submitting":
                begin_submit(session, attempt)
            finish_submit_unknown(
                session,
                attempt,
                message="模拟站回执不得用于非 demo 活动；请人工到真实官网确认",
            )
            send_notification(
                session,
                settings,
                kind="entry_unknown",
                title="模拟回执已忽略（非 demo 活动）",
                body=f"{round_.title}\n模拟站回执不会写入正式 confirmed。",
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
                message="模拟回执已忽略；正式活动需真实官网确认",
                warnings=[*result.warnings, "DEMO_RECEIPT_NOT_APPLIED"],
                requires_human=["请在真实官网完成报名并人工标记"],
            )
        if attempt.status != "submitting":
            begin_submit(session, attempt)
        finish_submit_success(session, attempt, receipt_code=result.receipt_code)
        masked = result.receipt_code[:3] + "***" if result.receipt_code else "***"
        send_notification(
            session,
            settings,
            kind="entry_confirmed",
            title="报名已确认（演示活动）" if round_.demo_only else "报名已确认",
            body=f"{round_.title}\n回执已保存（通知中脱敏: {masked}）",
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

    attempt.notes = ((attempt.notes or "") + "\n[prefilled] " + result.message)[:1000]
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
        body="私密码已本地加密保存；导出与日志不含明文。",
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
