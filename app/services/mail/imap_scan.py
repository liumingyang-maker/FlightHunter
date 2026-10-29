"""授权只读邮箱检测适配器（IMAP）。

未配置/未授权 → blocked。绝不自动回复或标记已中奖。
"""

from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config import Settings

_WIN_PATTERNS = re.compile(
    r"(congratulations|you (have )?won|中奖|恭喜)",
    re.I,
)


@dataclass
class MailCandidate:
    message_id: str
    subject: str
    sender: str
    date: datetime | None
    body_preview: str
    confidence: str  # low/medium
    needs_human: bool = True


def mail_configured(settings: Settings) -> bool:
    n = settings.notifications
    return bool(n.email_integration_enabled and n.email_host and n.email_user)


def scan_inbox_imap(
    settings: Settings,
    *,
    host: str,
    username: str,
    password: str,
    folder: str = "INBOX",
    limit: int = 20,
) -> dict[str, Any]:
    """只读扫描；失败返回 blocked/error。密码仅内存传递。"""
    if not settings.notifications.email_integration_enabled:
        return {"status": "blocked", "message": "邮件集成未在配置中启用"}
    try:
        client = imaplib.IMAP4_SSL(host)
        client.login(username, password)
        client.select(folder)
        typ, data = client.search(None, "ALL")
        if typ != "OK":
            client.logout()
            return {"status": "failed", "message": "IMAP search 失败"}
        ids = (data[0] or b"").split()[-limit:]
        candidates: list[MailCandidate] = []
        for mid in reversed(ids):
            typ, msg_data = client.fetch(mid, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw = msg_data[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(raw)
            subject = str(msg.get("Subject", ""))
            sender = str(msg.get("From", ""))
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            body = payload.decode(errors="replace")[:500]
                        break
            else:
                payload = msg.get_payload(decode=True)
                if isinstance(payload, bytes):
                    body = payload.decode(errors="replace")[:500]
            if _WIN_PATTERNS.search(subject) or _WIN_PATTERNS.search(body):
                candidates.append(
                    MailCandidate(
                        message_id=str(msg.get("Message-ID", mid.decode())),
                        subject=subject[:200],
                        sender=sender[:200],
                        date=None,
                        body_preview=body[:200],
                        confidence="low",
                        needs_human=True,
                    )
                )
        client.logout()
        return {
            "status": "ok",
            "candidates": [
                {
                    "message_id": c.message_id,
                    "subject": c.subject,
                    "sender": c.sender,
                    "confidence": c.confidence,
                    "needs_human": True,
                    "note": "仅候选；须人工核对主办方发件人与活动",
                }
                for c in candidates
            ],
            "message": f"扫描 {len(ids)} 封，候选 {len(candidates)}（均需人工确认）",
        }
    except Exception as exc:
        return {"status": "failed", "message": str(exc)[:300]}
