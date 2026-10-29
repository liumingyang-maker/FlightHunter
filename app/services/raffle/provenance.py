"""抽奖官方溯源：候选 → 抓取官方页（若可公开访问）→ 证据。"""

from __future__ import annotations

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
    if not url:
        return {"ok": False, "reason": "no_url"}
    from app.core.url_safety import assert_public_http_url

    try:
        assert_public_http_url(url)
    except Exception as exc:
        return {"ok": False, "reason": "unsafe_url", "message": str(exc)}

    from app.adapters.html_fetcher import HttpxFetchAdapter

    adapter = HttpxFetchAdapter(settings)
    result = await adapter.fetch(url)
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
        source_url=result.final_url or url,
        source_kind="official_page"
        if round_.verify_status == "verified"
        else "third_party_reporting",
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
    rounds = session.scalars(
        select(CampaignRound)
        .where(CampaignRound.verify_status == "candidate", CampaignRound.demo_only == False)  # noqa: E712
        .limit(limit)
    ).all()
    out = []
    for r in rounds:
        res = await attempt_official_evidence(session, settings, r)
        out.append({"round_id": r.id, "title": r.title[:60], **res})
        session.flush()
    return out
