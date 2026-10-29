"""报名尝试详情：供 UI/API 展示回执与状态。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CampaignRound, EntryAttempt, EntryEvent, Receipt


def attempt_detail(session: Session, attempt_id: str) -> dict:
    a = session.get(EntryAttempt, attempt_id)
    if a is None:
        return {"error": "not_found", "attempt_id": attempt_id}
    rnd = session.get(CampaignRound, a.round_id)
    receipt = None
    if a.receipt_id:
        r = session.get(Receipt, a.receipt_id)
        if r:
            receipt = {
                "id": r.id,
                "kind": r.kind,
                "reference_code_masked": (r.reference_code[:3] + "***")
                if r.reference_code
                else None,
                "verified": r.verified,
            }
    events = session.scalars(
        select(EntryEvent)
        .where(EntryEvent.attempt_id == a.id)
        .order_by(EntryEvent.created_at_utc)
    ).all()
    return {
        "attempt_id": a.id,
        "round_id": a.round_id,
        "title": rnd.title if rnd else None,
        "status": a.status,
        "manual_review_required": bool(a.manual_review_required),
        "error_code": a.error_code,
        "notes": (a.notes or "")[:300],
        "receipt": receipt,
        "events": [
            {
                "from": e.from_status,
                "to": e.to_status,
                "at": e.created_at_utc.isoformat() if e.created_at_utc else None,
            }
            for e in events
        ],
    }


def list_attempts_for_ui(session: Session, limit: int = 50) -> list[dict]:
    rows = session.scalars(
        select(EntryAttempt).order_by(EntryAttempt.updated_at_utc.desc()).limit(limit)
    ).all()
    return [attempt_detail(session, a.id) for a in rows]


def reconcile_all_stuck(session: Session) -> int:
    from app.services.entry.service import reconcile_stuck_submitting

    stuck = session.scalars(
        select(EntryAttempt).where(EntryAttempt.status == "submitting")
    ).all()
    n = 0
    for a in stuck:
        reconcile_stuck_submitting(session, a)
        n += 1
    session.flush()
    return n
