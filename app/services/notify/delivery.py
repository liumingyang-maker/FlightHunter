"""外送通知：站内记录 + 可选 Windows toast。

送达语义：
- console → recorded（仅记录）
- toast success → toast_delivered
- 仅当 toast/远程成功时才可标 delivered 外送
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Notification
from app.services.notify.service import notify


def deliver_windows_toast(title: str, body: str) -> dict[str, Any]:
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent('ToastText02');"
        "$n = $t.GetElementsByTagName('text');"
        f"$n.Item(0).AppendChild($t.CreateTextNode('{title.replace(chr(39), '')}')) | Out-Null;"
        f"$n.Item(1).AppendChild($t.CreateTextNode('{body.replace(chr(39), '')}')) | Out-Null;"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('FlightHunter').Show("
        "[Windows.UI.Notifications.ToastNotification]::new($t));"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0:
            return {"channel": "windows_toast", "status": "toast_delivered"}
        return {
            "channel": "windows_toast",
            "status": "failed",
            "detail": (r.stderr or r.stdout or "")[:500],
        }
    except Exception as exc:
        return {"channel": "windows_toast", "status": "failed", "detail": str(exc)}


def deliver_console(title: str, body: str) -> dict[str, Any]:
    print(f"[NOTIFY] {title}\n  {body}")
    return {"channel": "console", "status": "recorded"}


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
) -> Notification | None:
    n = notify(
        session,
        kind=kind,
        title=title,
        body=body,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    if n is None or n.suppressed_reason:
        return n
    # D-009：同 content_hash 已外送过则不再 console/toast
    if "[delivery]" in (n.body or ""):
        n.body = ((n.body or "") + "\n[delivery_skipped:already_sent]")[:4000]
        session.flush()
        return n

    deliveries = [deliver_console(title, body)]
    if try_toast:
        deliveries.append(deliver_windows_toast(title, body))
    note = "\n\n[delivery]\n" + json.dumps(deliveries, ensure_ascii=False)
    n.body = ((n.body or "") + note)[:4000]
    session.flush()
    return n


def external_delivery_ok(deliveries: list[dict[str, Any]]) -> bool:
    return any(d.get("status") == "toast_delivered" for d in deliveries)
