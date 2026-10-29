"""抽奖官方溯源：候选 → 抓取官方页（若可公开访问）→ 证据。"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.ids import content_hash_of_html, new_id
from app.core.timeutils import utc_now
from app.models import CampaignRound, Evidence


async def attempt_official_evidence(
    session: Session,
    settings: Settings,
    round_: CampaignRound,
) -> dict:
    """对候选 official_url 尝试只读抓取并保存证据。

    失败时如实返回 error；不把聚合页当官方 verified。
    """
    url = round_.official_url
    source_list = None
    if round_.tags:
        try:
            source_list = json.loads(round_.tags).get("source_list_url")
        except Exception:
            source_list = None
    target = url or source_list
    if not target:
        return {"ok": False, "reason": "no_url"}
    from app.core.url_safety import assert_public_http_url

    try:
        assert_public_http_url(target)
    except Exception as exc:
        return {"ok": False, "reason": "unsafe_url", "message": str(exc)}

    from app.adapters.html_fetcher import HttpxFetchAdapter

    adapter = HttpxFetchAdapter(settings)
    result = await adapter.fetch(target)
    if not result.ok:
        return {
            "ok": False,
            "reason": "fetch_failed",
            "error_code": result.error_code,
            "message": result.message,
        }
    ch = content_hash_of_html(result.text or "")
    now = utc_now()
    ev = Evidence(
        id=new_id(),
        entity_type="campaign_round",
        entity_id=round_.id,
        field_path="official_page_snapshot",
        source_url=result.final_url or target,
        source_kind="official_page" if url else "third_party_reporting",
        quote=(result.text or "")[:1500],
        retrieved_at_utc=now,
        content_hash=ch,
        extraction_method="httpx_snapshot",
        verification_method="pending_human",
    )
    session.add(ev)
    session.flush()
    return {
        "ok": True,
        "evidence_id": ev.id,
        "source_url": ev.source_url,
        "content_hash": ch,
        "bytes": len(result.text or ""),
        "note": "快照已保存；是否官方主办方仍须人工/规则核实，不自动 verified",
    }


async def attempt_official_evidence_batch(
    session: Session,
    settings: Settings,
    *,
    limit: int = 5,
) -> list[dict]:
    """优先处理尚无 official_page 证据的候选，避免只刷前 N 条。"""
    candidates = session.scalars(
        select(CampaignRound)
        .where(
            CampaignRound.verify_status == "candidate",
            CampaignRound.demo_only == False,  # noqa: E712
        )
        .order_by(CampaignRound.id)
    ).all()
    out = []
    tried = 0
    for r in candidates:
        if tried >= limit:
            break
        existing_ev = session.scalar(
            select(Evidence).where(
                Evidence.entity_type == "campaign_round",
                Evidence.entity_id == r.id,
                Evidence.field_path == "official_page_snapshot",
            )
        )
        if existing_ev:
            continue
        res = await attempt_official_evidence(session, settings, r)
        out.append({"round_id": r.id, "title": r.title[:60], **res})
        session.flush()
        tried += 1
    if not out:
        out.append({"note": "本轮无待溯源候选或均已尝试快照", "tried": 0})
    return out
