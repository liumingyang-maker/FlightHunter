"""来源健康统计：区分历史成功 / 本轮成功 / 失败 / 冷却 / 零解析 / 有价值。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutils import ensure_aware_utc
from app.models import FareDealSignal, Source


def source_health_report(
    session: Session,
    *,
    module: str | None = "fare",
    window_hours: int = 24,
) -> dict[str, Any]:
    now = datetime.now(UTC).replace(tzinfo=None)
    window_start = now - timedelta(hours=window_hours)
    stmt = select(Source)
    if module:
        stmt = stmt.where(Source.module == module)
    sources = session.scalars(stmt.order_by(Source.name)).all()

    rows: list[dict[str, Any]] = []
    counters = {
        "sources_total": 0,
        "historically_fetched": 0,
        "round_success": 0,
        "round_failed": 0,
        "round_zero_parse": 0,
        "round_valuable": 0,
        "round_cooldown": 0,
        "round_not_attempted": 0,
    }

    def _aware(dt) -> datetime | None:
        if not dt:
            return None
        a = ensure_aware_utc(dt)
        return a.replace(tzinfo=None) if a else None

    for s in sources:
        counters["sources_total"] += 1
        attempt = _aware(s.last_attempt_at)
        success = _aware(s.last_success_at or s.last_fetch_at)
        in_window = attempt and attempt >= window_start
        last_result = s.last_result or (
            "ok" if success else ("failed" if (s.consecutive_failures or 0) > 0 else "unknown")
        )
        if success:
            counters["historically_fetched"] += 1
        if not in_window:
            counters["round_not_attempted"] += 1
        elif last_result in {"failed"} or ((s.consecutive_failures or 0) > 0 and not success):
            # 本轮尝试且失败
            if attempt and (not success or (s.consecutive_failures or 0) > 0):
                if last_result == "failed":
                    counters["round_failed"] += 1
                elif last_result == "skipped_cooldown":
                    counters["round_cooldown"] += 1
                elif last_result == "ok_zero":
                    counters["round_zero_parse"] += 1
                elif last_result == "ok_valuable":
                    counters["round_valuable"] += 1
                    counters["round_success"] += 1
                elif last_result == "ok":
                    counters["round_success"] += 1
                else:
                    counters["round_failed"] += 1
        else:
            if last_result == "skipped_cooldown":
                counters["round_cooldown"] += 1
            elif last_result == "ok_zero":
                counters["round_zero_parse"] += 1
                counters["round_success"] += 1
            elif last_result == "ok_existing":
                # R-015：已解析但无新增 ≠ 零解析
                counters["round_success"] += 1
            elif last_result == "ok_valuable":
                counters["round_valuable"] += 1
                counters["round_success"] += 1
            elif last_result == "ok":
                counters["round_success"] += 1
            elif last_result == "failed":
                counters["round_failed"] += 1
            else:
                counters["round_not_attempted"] += 1

        # 简化：按 last_result 直接计数（更可靠）
        rows.append(
            {
                "name": s.name,
                "module": s.module,
                "status": s.status,
                "last_result": last_result,
                "last_attempt_at": s.last_attempt_at.isoformat() if s.last_attempt_at else None,
                "last_success_at": (s.last_success_at or s.last_fetch_at).isoformat()
                if (s.last_success_at or s.last_fetch_at)
                else None,
                "last_valuable_at": s.last_valuable_at.isoformat() if s.last_valuable_at else None,
                "last_signal_count": s.last_signal_count or 0,
                "consecutive_failures": s.consecutive_failures or 0,
                "attempted_in_window": bool(in_window),
            }
        )

    # 用 last_result 重算本轮计数，避免双重逻辑出错
    counters = {
        "sources_total": len(rows),
        "historically_fetched": sum(1 for r in rows if r["last_success_at"]),
        "round_success": sum(
            1
            for r in rows
            if r["attempted_in_window"] and r["last_result"] in {"ok", "ok_zero", "ok_valuable"}
        ),
        "round_failed": sum(
            1 for r in rows if r["attempted_in_window"] and r["last_result"] == "failed"
        ),
        "round_zero_parse": sum(
            1 for r in rows if r["attempted_in_window"] and r["last_result"] == "ok_zero"
        ),
        "round_valuable": sum(
            1 for r in rows if r["attempted_in_window"] and r["last_result"] == "ok_valuable"
        ),
        "round_cooldown": sum(
            1 for r in rows if r["last_result"] == "skipped_cooldown"
        ),
        "round_not_attempted": sum(1 for r in rows if not r["attempted_in_window"]),
    }

    valuable_24h = 0
    if module in (None, "fare"):
        from sqlalchemy import func

        valuable_24h = int(
            session.scalar(
                select(func.count())
                .select_from(FareDealSignal)
                .where(FareDealSignal.created_at_utc >= window_start)
            )
            or 0
        )

    return {
        "window_hours": window_hours,
        "generated_at": now.isoformat(),
        "counters": counters,
        "fare_signals_created_in_window": valuable_24h,
        "sources": rows,
        "note": "round_* 仅统计窗口内 last_attempt_at；historically_fetched 含历史成功",
    }
