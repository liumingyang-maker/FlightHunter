"""发现管道：来源 → RawCandidate → 模块分发。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import FetchResult, SourceAdapter
from app.adapters.html_fetcher import HttpxFetchAdapter
from app.adapters.rss import RssAdapter
from app.config import Settings
from app.core.errors import ErrorCode
from app.core.ids import content_hash_of_html, new_id
from app.core.timeutils import utc_now
from app.models import RawCandidate, Source


def adapter_for(source: Source, settings: Settings) -> SourceAdapter | None:
    if source.allowed_fetch_mode == "rss":
        return RssAdapter(settings)
    if source.allowed_fetch_mode == "httpx":
        return HttpxFetchAdapter(settings)
    return None


def ingest_fetch_result(
    session: Session,
    source: Source,
    result: FetchResult,
    *,
    module: str = "fare",
    title: str | None = None,
) -> RawCandidate | None:
    """将抓取结果写入 RawCandidate；失败只记状态不伪造内容。"""
    now = utc_now()
    if not result.ok:
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        if result.error_code == ErrorCode.SOURCE_FETCH_DENIED.value:
            source.status = "manual_only"
        session.flush()
        return None

    existing = session.scalar(
        select(RawCandidate).where(
            RawCandidate.source_id == source.id,
            RawCandidate.url == (result.final_url or result.url),
        )
    )
    ch = result.content_hash or content_hash_of_html(result.text or "")
    if existing:
        existing.raw_content_hash = ch
        existing.discovered_at_utc = now
        session.flush()
        return existing

    cand = RawCandidate(
        id=new_id(),
        source_id=source.id,
        url=result.final_url or result.url,
        title=title or (result.text or "")[:200] if result.text else title,
        discovered_at_utc=now,
        content_type=result.content_type or "text/html",
        raw_content_hash=ch,
        status="candidate",
        module=module,
        payload_excerpt=(result.text or "")[:4000] if result.text else None,
    )
    session.add(cand)
    source.last_seen_at = now
    source.consecutive_failures = 0
    session.flush()
    return cand


async def fetch_source(
    session: Session,
    settings: Settings,
    source: Source,
    *,
    module: str = "fare",
    dry_run: bool = False,
) -> dict[str, Any]:
    """抓取单一来源；dry_run 不访问网络。manual_only 禁止自动抓取。"""
    if source.status == "manual_only" or source.access_policy == "manual_only":
        return {
            "source_id": source.id,
            "status": "manual_only",
            "error_code": "SOURCE_FETCH_DENIED",
            "message": "来源仅限人工导入，不自动抓取",
        }
    if source.access_policy in ("forbidden",) or source.allowed_fetch_mode == "none":
        return {
            "source_id": source.id,
            "status": "denied",
            "error_code": ErrorCode.SOURCE_FETCH_DENIED.value,
            "message": "来源策略禁止自动抓取",
        }
    if dry_run:
        return {
            "source_id": source.id,
            "status": "dry_run",
            "message": "未访问外部网络",
        }

    adapter = adapter_for(source, settings)
    if adapter is None:
        return {
            "source_id": source.id,
            "status": "manual_only",
            "message": "无可用自动抓取适配器；请使用人工粘贴入口",
        }

    result = await adapter.fetch(source.base_url)
    cand = ingest_fetch_result(session, source, result, module=module)
    signals = []
    if result.ok and result.text:
        for s in adapter.parse(result.text, url=source.base_url)[:20]:
            signals.append(
                {
                    "title": s.title,
                    "reported_total": s.reported_total,
                    "origin": s.origin_airport,
                    "destination": s.destination_airport,
                    "confidence": s.confidence,
                }
            )
    return {
        "source_id": source.id,
        "status": "ok" if result.ok else "failed",
        "candidate_id": cand.id if cand else None,
        "error_code": result.error_code,
        "message": result.message,
        "signal_preview_count": len(signals),
        "signals": signals,
    }


async def run_discovery(
    session: Session,
    settings: Settings,
    *,
    module: str = "fare",
    dry_run: bool = True,
    limit: int = 10,
) -> list[dict[str, Any]]:
    # 仅 active：manual_only 不进入自动发现队列
    stmt = select(Source).where(Source.status == "active").limit(limit)
    sources = list(session.scalars(stmt).all())
    if module != "all":
        sources = [s for s in sources if s.module in (module, "shared")]
    out = []
    for s in sources:
        out.append(await fetch_source(session, settings, s, module=module, dry_run=dry_run))
    session.flush()
    return out
