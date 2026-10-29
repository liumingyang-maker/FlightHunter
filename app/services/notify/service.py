"""站内通知服务：幂等、去重、不假推送。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id, sha256_text
from app.models import Notification


def notify(
    session: Session,
    *,
    kind: str,
    title: str,
    body: str = "",
    severity: str = "info",
    entity_type: str | None = None,
    entity_id: str | None = None,
    content_hash: str | None = None,
    suppress_reason: str | None = None,
) -> Notification | None:
    """写入站内提醒。相同 content_hash 不重复发送。"""
    ch = content_hash or sha256_text(f"{kind}|{title}|{entity_id}|{body[:200]}")
    existing = session.scalar(select(Notification).where(Notification.content_hash == ch))
    if existing:
        return existing
    if suppress_reason:
        n = Notification(
            id=new_id(),
            kind=kind,
            title=title,
            body=body,
            severity=severity,
            entity_type=entity_type,
            entity_id=entity_id,
            content_hash=ch,
            suppressed_reason=suppress_reason,
            read=False,
        )
        session.add(n)
        session.flush()
        return n

    n = Notification(
        id=new_id(),
        kind=kind,
        title=title,
        body=body,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
        content_hash=ch,
        read=False,
    )
    session.add(n)
    session.flush()
    return n


def list_unread(session: Session, *, limit: int = 50) -> list[Notification]:
    return list(
        session.scalars(
            select(Notification)
            .where(Notification.read == False)  # noqa: E712
            .order_by(Notification.created_at_utc.desc())
            .limit(limit)
        ).all()
    )


def mark_read(session: Session, notification_id: str) -> Notification | None:
    n = session.get(Notification, notification_id)
    if n is None:
        return None
    n.read = True
    session.flush()
    return n
