"""后台调度：可恢复到期扫描，接入真实发现。

- dry-run 与 execute 幂等键分离；dry-run 不推进正式 next_run_at
- 先过滤到期再 limit，避免未到期挤占有期任务
- benefit 订阅按 source_group 传给发现（目的国）
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.ids import idempotency_key, new_id
from app.core.timeutils import dt_gt, ensure_aware_utc, utc_now
from app.models import TaskRun, Trip, TripScanSubscription
from app.services.discovery.service import run_discovery


def claim_due_subscriptions(
    session: Session,
    *,
    now=None,
    limit: int = 50,
) -> list[TripScanSubscription]:
    """筛出真正到期的订阅，再截断 limit（避免未到期挤掉到期任务）。"""
    now = ensure_aware_utc(now) or utc_now()
    candidates = session.scalars(
        select(TripScanSubscription).where(
            TripScanSubscription.enabled == True,  # noqa: E712
            TripScanSubscription.paused_reason.is_(None),
        )
    ).all()
    ready: list[TripScanSubscription] = []
    for sub in candidates:
        if sub.next_run_at and dt_gt(ensure_aware_utc(sub.next_run_at), now):
            continue
        trip = session.get(Trip, sub.trip_id)
        if trip is None or trip.archived:
            continue
        if trip.completed:
            sub.paused_reason = "trip_completed"
            continue
        ready.append(sub)
    # 稳定排序：先按 next_run_at 升序（None 最前）
    ready.sort(key=lambda s: ensure_aware_utc(s.next_run_at).timestamp() if s.next_run_at else 0.0)
    return ready[:limit]


async def _discovery_for_task(
    session: Session,
    settings: Settings,
    sub: TripScanSubscription,
    *,
    dry_run: bool,
) -> dict:
    module = "trip" if sub.task_type == "benefit_discovery" else "fare"
    # source_group 若形如 JP / JP_national，取前 2 位作国家码
    country = None
    sg = (sub.source_group or "").strip()
    if len(sg) >= 2 and sg[:2].isalpha():
        country = sg[:2].upper()
    results = await run_discovery(
        session,
        settings,
        module=module,
        dry_run=dry_run,
        limit=5,
        persist_signals=not dry_run,
        after_fetch=not dry_run,
        country_code=country,
    )
    ok = sum(1 for r in results if r.get("status") == "ok")
    failed = sum(1 for r in results if r.get("status") in ("failed", "denied", "manual_only"))
    if dry_run or (ok and not failed):
        status = "completed"
    elif ok and failed:
        status = "partial"
    elif failed:
        status = "failed"
    else:
        status = "blocked"
    return {
        "action": "discovery_scan",
        "module": module,
        "country_code": country,
        "status": status,
        "ok": ok,
        "failed": failed,
        "steps": [
            {k: r.get(k) for k in ("source_id", "status", "signals_persisted", "offers_persisted")}
            for r in results
        ],
        "message": f"discovery ok={ok} failed={failed}",
    }


def run_subscription_scan(
    session: Session,
    settings: Settings,
    sub: TripScanSubscription,
    *,
    dry_run: bool = True,
    fetch_fn: Callable[[TripScanSubscription], dict] | None = None,
) -> TaskRun:
    now = utc_now()
    mode = "dry" if dry_run else "exec"
    idem = idempotency_key("trip_scan", sub.id, sub.task_type, mode, now.strftime("%Y-%m-%dT%H"))
    existing = session.scalar(select(TaskRun).where(TaskRun.idempotency_key == idem))
    if existing and existing.status in ("running", "completed", "blocked", "partial"):
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
        if fetch_fn is not None:
            result = fetch_fn(sub)
            run.status = result.get("status", "completed")
            success = (not dry_run) and run.status in ("completed", "partial")
        else:
            result = asyncio.run(_discovery_for_task(session, settings, sub, dry_run=dry_run))
            run.status = result["status"]
            success = (not dry_run) and run.status in ("completed", "partial")

        run.result_summary = json.dumps(result, ensure_ascii=False, default=str)[:4000]
        run.finished_at = utc_now()
        sub.last_run_at = run.finished_at
        sub.last_status = run.status
        sub.last_message = result.get("message")
        # dry-run 不推进正式调度时间，避免污染 execute
        if not dry_run:
            sub.next_run_at = run.finished_at + timedelta(hours=max(1, sub.interval_hours))
        if trip:
            if success:
                if sub.task_type == "benefit_discovery":
                    trip.last_benefit_scan_at = run.finished_at
                elif sub.task_type == "fare_monitor":
                    trip.last_fare_scan_at = run.finished_at
                trip.scan_status = "idle"
                trip.scan_message = None
            elif run.status in ("blocked", "failed"):
                trip.scan_status = "degraded" if run.status == "failed" else "blocked"
                trip.scan_message = result.get("message")
            else:
                trip.scan_status = "idle"
                trip.scan_message = "dry-run 完成，未访问外部网络"
    except Exception as exc:
        run.status = "failed"
        run.error_code = "SOURCE_UNAVAILABLE"
        run.message = str(exc)
        run.finished_at = utc_now()
        sub.last_status = "failed"
        sub.last_message = str(exc)
        if not dry_run:
            sub.next_run_at = run.finished_at + timedelta(hours=max(1, sub.interval_hours))
        if trip:
            trip.scan_status = "interrupted"
            trip.scan_message = str(exc)
        session.flush()
        return run

    session.flush()
    return run


def mark_offline_recovery(session: Session, trip: Trip) -> None:
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
