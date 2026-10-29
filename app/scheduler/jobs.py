"""后台调度：Trip 扫描、任务锁、可恢复重扫。"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.ids import idempotency_key, new_id
from app.core.timeutils import utc_now
from app.models import TaskRun, Trip, TripScanSubscription
from app.services.trips.service import rematch_trip_benefits


def claim_due_subscriptions(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = 20,
) -> list[TripScanSubscription]:
    """取出到期且启用的订阅；带幂等任务锁。"""
    now = now or utc_now()
    due = session.scalars(
        select(TripScanSubscription)
        .where(
            TripScanSubscription.enabled == True,  # noqa: E712
            TripScanSubscription.paused_reason.is_(None),
        )
        .limit(limit)
    ).all()
    ready: list[TripScanSubscription] = []
    for sub in due:
        if sub.next_run_at and sub.next_run_at > now:
            continue
        trip = session.get(Trip, sub.trip_id)
        if trip is None or trip.archived:
            continue
        if trip.completed:
            sub.paused_reason = "trip_completed"
            continue
        ready.append(sub)
    return ready


def run_subscription_scan(
    session: Session,
    settings: Settings,
    sub: TripScanSubscription,
    *,
    dry_run: bool = True,
    fetch_fn: Callable[[TripScanSubscription], dict] | None = None,
) -> TaskRun:
    """执行一次扫描任务（可恢复）。dry-run 默认不访问外网。"""
    now = utc_now()
    idem = idempotency_key("trip_scan", sub.id, sub.task_type, now.strftime("%Y-%m-%dT%H"))
    existing = session.scalar(select(TaskRun).where(TaskRun.idempotency_key == idem))
    if existing and existing.status in ("running", "completed"):
        return existing

    run = TaskRun(
        id=new_id(),
        task_type=sub.task_type,
        status="running",
        idempotency_key=idem,
        entity_type="trip_scan_subscription",
        entity_id=sub.id,
        started_at=now,
        dry_run=dry_run,
    )
    session.add(run)
    session.flush()

    trip = session.get(Trip, sub.trip_id)
    try:
        if dry_run:
            result = {
                "action": "dry_run",
                "source_group": sub.source_group,
                "task_type": sub.task_type,
                "trip_label": trip.label if trip else None,
                "message": "未访问外部网络；仅登记扫描计划",
            }
        elif fetch_fn is not None:
            result = fetch_fn(sub)
        else:
            # 无外部适配器时如实报告降级，不假装抓取成功
            result = {
                "action": "degraded_no_adapter",
                "message": "当前环境未配置可执行抓取适配器；行程重匹配已运行",
            }
            if sub.task_type == "benefit_discovery" and trip:
                rematch_trip_benefits(session, trip)
                result["rematched"] = True

        run.status = "completed"
        run.result_summary = json.dumps(result, ensure_ascii=False)
        run.finished_at = utc_now()
        sub.last_run_at = run.finished_at
        sub.last_status = "completed"
        sub.last_message = result.get("message")
        sub.next_run_at = run.finished_at + timedelta(hours=sub.interval_hours)
        if trip:
            if sub.task_type == "benefit_discovery":
                trip.last_benefit_scan_at = run.finished_at
            elif sub.task_type == "fare_monitor":
                trip.last_fare_scan_at = run.finished_at
            trip.scan_status = "idle"
            trip.scan_message = None
    except Exception as exc:
        run.status = "failed"
        run.error_code = "SOURCE_UNAVAILABLE"
        run.message = str(exc)
        run.finished_at = utc_now()
        sub.last_status = "failed"
        sub.last_message = str(exc)
        sub.next_run_at = run.finished_at + timedelta(hours=max(1, sub.interval_hours))
        if trip:
            trip.scan_status = "interrupted"
            trip.scan_message = str(exc)
        session.flush()
        return run

    session.flush()
    return run


def mark_offline_recovery(session: Session, trip: Trip) -> None:
    """离线恢复后标记补扫；禁止假装离线期间执行过扫描。"""
    trip.scan_status = "recovery_pending"
    trip.scan_message = "设备离线期间扫描中断；恢复后将按策略补扫"
    for sub in session.scalars(
        select(TripScanSubscription).where(TripScanSubscription.trip_id == trip.id)
    ).all():
        if sub.enabled:
            sub.next_run_at = utc_now()


def run_due_scans(
    session: Session,
    settings: Settings,
    *,
    dry_run: bool = True,
    limit: int = 10,
) -> list[TaskRun]:
    runs: list[TaskRun] = []
    for sub in claim_due_subscriptions(session, limit=limit):
        runs.append(run_subscription_scan(session, settings, sub, dry_run=dry_run))
    return runs
