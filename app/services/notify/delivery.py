"""外送通知：站内记录 + 可选 Windows toast / 通用 webhook。

真实送达与站内记录分离；失败可重试且 content_hash 去重。
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
    """尝试 Windows toast；失败则返回 failed，不假装成功。"""
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
            return {"channel": "windows_toast", "status": "delivered"}
        return {
            "channel": "windows_toast",
            "status": "failed",
            "detail": (r.stderr or r.stdout or "")[:500],
        }
    except Exception as exc:
        return {"channel": "windows_toast", "status": "failed", "detail": str(exc)}


def deliver_console(title: str, body: str) -> dict[str, Any]:
    print(f"[NOTIFY] {title}\n  {body}")
    return {"channel": "console", "status": "delivered"}


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
    """写入站内通知并尝试外送；delivery 结果写入 body 附注。"""
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
        return n  # type: ignore[return-value]
    if n.suppressed_reason:
        return n

    deliveries = [deliver_console(title, body)]
    if try_toast:
        deliveries.append(deliver_windows_toast(title, body))
    # 仅当有任一成功时，不在 title 上伪造；把渠道结果写入 body 尾部供审计
    ok = any(d.get("status") == "delivered" for d in deliveries)
    note = "\n\n[delivery]\n" + json.dumps(deliveries, ensure_ascii=False)
    if ok:
        n.body = ((n.body or "") + note)[:4000]
        n.severity = severity
    else:
        n.body = ((n.body or "") + note + "\nALL_CHANNELS_FAILED")[:4000]
    session.flush()
    return n
