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
    """使用 pwsh（非 Windows PowerShell 5.1）；标题/正文经 Base64 传参避免拼接注入。"""
    import base64
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
            timeout=15,
            env={
                **__import__("os").environ,
                "FH_TOAST_TITLE": t_b64,
                "FH_TOAST_BODY": b_b64,
            },
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
    # D-009/N-010：标记放在 body 开头，避免长正文截断丢失
    if "[D]" in (n.body or "")[:20]:
        n.body = "[D][skip_dup]" + (n.body or "")[:3980]
        session.flush()
        return n

    deliveries = [deliver_console(title, body)]
    if try_toast:
        deliveries.append(deliver_windows_toast(title, body))
    note = "[D]" + json.dumps(deliveries, ensure_ascii=False)[:200]
    n.body = (note + "\n" + (n.body or ""))[:4000]
    session.flush()
    return n


def external_delivery_ok(deliveries: list[dict[str, Any]]) -> bool:
    return any(d.get("status") == "toast_delivered" for d in deliveries)
