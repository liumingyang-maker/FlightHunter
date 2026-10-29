"""系统运行状态：健康、扫描、任务、通知汇总。"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutils import ensure_aware_utc, utc_now
from app.models import (
    FareDeal,
    FareWatch,
    Notification,
    Source,
    TaskRun,
    Trip,
    TripScanSubscription,
)


def system_status(session: Session) -> dict:
    now = utc_now()
    day_ago = now - timedelta(hours=24)

    def _count(model, *where) -> int:
        stmt = select(func.count()).select_from(model)
        for w in where:
            stmt = stmt.where(w)
        return int(session.scalar(stmt) or 0)

    tasks_24h = session.scalars(
        select(TaskRun)
        .where(TaskRun.created_at_utc >= day_ago)
        .order_by(TaskRun.created_at_utc.desc())
        .limit(50)
    ).all()
    ok = sum(1 for t in tasks_24h if t.status == "completed")
    failed = sum(1 for t in tasks_24h if t.status in ("failed", "blocked", "partial"))
    dry = sum(1 for t in tasks_24h if t.dry_run)

    last_exec = session.scalar(
        select(func.max(TaskRun.finished_at)).where(
            TaskRun.dry_run == False,  # noqa: E712
            TaskRun.status == "completed",
            TaskRun.task_type.in_(
                [
                    "source_discovery_batch",
                    "benefit_discovery",
                    "fare_monitor",
                    "source_discovery",
                ]
            ),
        )
    )
    last_exec_aware = ensure_aware_utc(last_exec) if last_exec else None

    sources = session.scalars(select(Source).where(Source.status == "active")).all()
    src_24 = sum(
        1
        for s in sources
        if s.last_fetch_at and ensure_aware_utc(s.last_fetch_at) >= day_ago
    )

    return {
        "server_time_utc": now.isoformat(),
        "db": {
            "trips": _count(Trip),
            "sources_active": len(sources),
            "sources_fetched_24h": src_24,
            "fare_deals": _count(FareDeal),
            "fare_watches": _count(FareWatch),
            "scan_subscriptions_enabled": _count(
                TripScanSubscription, TripScanSubscription.enabled == True  # noqa: E712
            ),
            "notifications": _count(Notification),
            "tasks_24h": len(tasks_24h),
            "tasks_24h_completed": ok,
            "tasks_24h_failed_or_partial": failed,
            "tasks_24h_dry_run": dry,
        },
        "last_successful_execute_scan_utc": (
            last_exec_aware.isoformat() if last_exec_aware else None
        ),
        "note": "completed 含 dry_run；真实抓取请看 last_successful_execute_scan 与 failed 计数",
    }
