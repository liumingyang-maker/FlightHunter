"""外送通知：站内记录 + 可选 Windows toast。

送达语义：
- console → recorded（仅记录）
- toast success → toast_delivered
- R-012：成功状态持久化（NotificationDelivery），进程重启不重复
- R-013：失败限次重试（默认 3），attempts 正确解析
- R-017：subprocess 明确 UTF-8 编码，避免 GBK 解码异常
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.ids import new_id
from app.models import Notification, NotificationDelivery
from app.services.notify.service import notify

MAX_DELIVERY_ATTEMPTS = 3


def deliver_windows_toast(title: str, body: str) -> dict[str, Any]:
    """使用 pwsh；标题/正文经 Base64 传参；输出按 UTF-8 解码（R-017）。"""
    import base64
    import os
    import shutil

    t_b64 = base64.b64encode(title.encode("utf-16-le")).decode("ascii")
    b_b64 = base64.b64encode(body.encode("utf-16-le")).decode("ascii")
    script = (
        "$t=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($env:FH_TOAST_TITLE));"
        "$b=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($env:FH_TOAST_BODY));"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null;"
        "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent('ToastText02');"
        "$n=$x.GetElementsByTagName('text');"
        "$n.Item(0).AppendChild($x.CreateTextNode($t)) | Out-Null;"
        "$n.Item(1).AppendChild($x.CreateTextNode($b)) | Out-Null;"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('FlightHunter').Show("
        "[Windows.UI.Notifications.ToastNotification]::new($x));"
    )
    pwsh = shutil.which("pwsh") or shutil.which("pwsh.exe") or r"C:\Program Files\PowerShell\7\pwsh.exe"
    try:
        r = subprocess.run(
            [pwsh, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            env={**os.environ, "FH_TOAST_TITLE": t_b64, "FH_TOAST_BODY": b_b64},
        )
        if r.returncode == 0:
            return {"channel": "windows_toast", "status": "toast_delivered"}
        return {
            "channel": "windows_toast",
            "status": "failed",
            "detail": ((r.stderr or r.stdout or "")[:500]),
        }
    except Exception as exc:
        return {"channel": "windows_toast", "status": "failed", "detail": str(exc)}


def deliver_console(title: str, body: str) -> dict[str, Any]:
    print(f"[NOTIFY] {title}\n  {body}")
    return {"channel": "console", "status": "recorded"}


def _event_key(kind: str, title: str, entity_type: str | None, entity_id: str | None) -> str:
    return hashlib.sha256(
        f"{kind}|{title}|{entity_type or ''}|{entity_id or ''}".encode("utf-8")
    ).hexdigest()[:24]


def _get_delivery_state(session: Session, event_key: str, channel: str) -> NotificationDelivery | None:
    return session.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.event_key == event_key,
            NotificationDelivery.channel == channel,
        )
    )


def _upsert_delivery(
    session: Session,
    event_key: str,
    channel: str,
    *,
    status: str,
    attempts: int,
    notification_id: str | None = None,
    error: str | None = None,
) -> NotificationDelivery:
    row = _get_delivery_state(session, event_key, channel)
    if row is None:
        row = NotificationDelivery(
            id=new_id(),
            event_key=event_key,
            channel=channel,
            status=status,
            attempts=attempts,
            notification_id=notification_id,
            last_error=error,
        )
        session.add(row)
    else:
        row.status = status
        row.attempts = attempts
        row.notification_id = notification_id or row.notification_id
        row.last_error = error
    session.flush()
    return row


def send_notification(
    session: Session,
    settings: Settings | None = None,
    *,
    kind: str,
    title: str,
    body: str = "",
    severity: str = "info",
    entity_type: str | None = None,
    entity_id: str | None = None,
    try_toast: bool = True,
    event_key: str | None = None,
) -> Notification | None:
    """外送：持久事件键 + 渠道状态；成功幂等；失败限次重试。"""
    key = event_key or _event_key(kind, title, entity_type, entity_id)
    n = notify(
        session,
        kind=kind,
        title=title,
        body=body,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    if n is None:
        return n
    if n.suppressed_reason:
        return n

    channels = ["console"]
    if try_toast:
        channels.append("windows_toast")

    # R-012：任一外部渠道已成功 → 不再外送
    toast_row = _get_delivery_state(session, key, "windows_toast")
    if toast_row is not None and toast_row.status == "toast_delivered":
        if "[D]" not in (n.body or "")[:24]:
            n.body = "[D][skip_dup]" + (n.body or "")[:3980]
            session.flush()
        return n
    # 仅 console 且已 recorded（无 toast 需求）→ 跳过
    if not try_toast:
        console_row = _get_delivery_state(session, key, "console")
        if console_row is not None and console_row.status == "recorded":
            if "[D]" not in (n.body or "")[:24]:
                n.body = "[D][skip_dup]" + (n.body or "")[:3980]
                session.flush()
            return n

    attempts = 0
    if toast_row is not None:
        attempts = int(toast_row.attempts or 0)
        if toast_row.status in ("exhausted",) or (
            toast_row.status == "failed" and attempts >= MAX_DELIVERY_ATTEMPTS
        ):
            _upsert_delivery(
                session, key, "windows_toast", status="exhausted", attempts=attempts, notification_id=n.id
            )
            n.body = "[D][retry_exhausted]" + (n.body or "")[:3980]
            session.flush()
            return n

    deliveries = [deliver_console(title, body)]
    if try_toast:
        deliveries.append(deliver_windows_toast(title, body))
    ok = external_delivery_ok(deliveries)
    attempts = attempts + 1

    _upsert_delivery(
        session,
        key,
        "console",
        status="recorded",
        attempts=1,
        notification_id=n.id,
    )
    if try_toast:
        if ok:
            _upsert_delivery(
                session,
                key,
                "windows_toast",
                status="toast_delivered",
                attempts=attempts,
                notification_id=n.id,
            )
        elif attempts >= MAX_DELIVERY_ATTEMPTS:
            _upsert_delivery(
                session,
                key,
                "windows_toast",
                status="exhausted",
                attempts=attempts,
                notification_id=n.id,
                error=next((d.get("detail") for d in deliveries if d.get("status") == "failed"), None),
            )
        else:
            _upsert_delivery(
                session,
                key,
                "windows_toast",
                status="failed",
                attempts=attempts,
                notification_id=n.id,
                error=next((d.get("detail") for d in deliveries if d.get("status") == "failed"), None),
            )

    if ok or not try_toast:
        note = "[D]" + json.dumps(deliveries, ensure_ascii=False)[:200]
        n.body = (note + "\n" + (n.body or ""))[:4000]
    else:
        n.body = (f"[D:fail:a{attempts}:k{key}]" + (n.body or ""))[:4000]
    session.flush()
    return n


def external_delivery_ok(deliveries: list[dict[str, Any]]) -> bool:
    return any(d.get("status") == "toast_delivered" for d in deliveries)
