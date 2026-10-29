"""抽奖官方溯源：候选 → 只读抓取线索/官网 → 证据。

- 聚合页证据 field_path=aggregator_page_snapshot, source_kind=third_party_reporting
- 官网页证据 field_path=official_page_snapshot, source_kind=official_page
- 失败退避；不因已有聚合快照跳过后续官网核实
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.ids import content_hash_of_html, new_id
from app.core.timeutils import ensure_aware_utc, utc_now
from app.models import CampaignRound, Evidence


def _load_tags(round_: CampaignRound) -> dict:
    if not round_.tags:
        return {}
    try:
        data = json.loads(round_.tags)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_tags(round_: CampaignRound, tags: dict) -> None:
    round_.tags = json.dumps(tags, ensure_ascii=False)


async def attempt_official_evidence(
    session: Session,
    settings: Settings,
    round_: CampaignRound,
) -> dict:
    tags = _load_tags(round_)
    url = round_.official_url
    if not url:
        # 上一轮从聚合页粗提的官方候选；成功抓取后写入 official_url，仍不 verified
        url = tags.get("discovered_official_candidate") or None
    source_list = tags.get("source_list_url")
    target = url or source_list
    if not target:
        tags["last_provenance_attempt_utc"] = utc_now().isoformat()
        tags["last_provenance_ok"] = False
        _save_tags(round_, tags)
        return {"ok": False, "reason": "no_url"}

    from app.core.url_safety import assert_public_http_url

    try:
        assert_public_http_url(target)
    except Exception as exc:
        tags["last_provenance_attempt_utc"] = utc_now().isoformat()
        tags["last_provenance_ok"] = False
        _save_tags(round_, tags)
        return {"ok": False, "reason": "unsafe_url", "message": str(exc)}

    from app.adapters.html_fetcher import HttpxFetchAdapter

    adapter = HttpxFetchAdapter(settings)
    result = await adapter.fetch(target)
    now = utc_now()
    tags["last_provenance_attempt_utc"] = now.isoformat()
    tags["last_provenance_ok"] = bool(result.ok)
    if not result.ok:
        tags["last_provenance_fail_count"] = int(tags.get("last_provenance_fail_count") or 0) + 1
        _save_tags(round_, tags)
        return {
            "ok": False,
            "reason": "fetch_failed",
            "error_code": result.error_code,
            "message": result.message,
        }

    is_agg = round_.official_url is None and url is None
    # 若本轮使用 discovered 候选抓取，按官方页路径记证据，但 verify 仍保持 candidate
    use_discovered = bool(url and round_.official_url is None)
    ch = content_hash_of_html(result.text or "")
    ev = Evidence(
        id=new_id(),
        entity_type="campaign_round",
        entity_id=round_.id,
        field_path="aggregator_page_snapshot" if is_agg else "official_page_snapshot",
        source_url=result.final_url or target,
        source_kind="third_party_reporting" if is_agg else "official_page",
        quote=(result.text or "")[:1500],
        retrieved_at_utc=now,
        content_hash=ch,
        extraction_method="httpx_snapshot",
        verification_method="pending_human",
    )
    session.add(ev)
    tags["last_provenance_fail_count"] = 0
    if use_discovered and not round_.official_url:
        # 记录候选官方页；不自动 verified
        round_.official_url = (result.final_url or target)[:2000]
        tags["official_url_from"] = "aggregator_link_candidate"
    _save_tags(round_, tags)
    session.flush()
    out = {
        "ok": True,
        "evidence_id": ev.id,
        "source_url": ev.source_url,
        "content_hash": ch,
        "bytes": len(result.text or ""),
        "kind": ev.source_kind,
        "note": "快照已保存；聚合≠官方 verified",
    }
    if is_agg and result.ok:
        discovered = _discover_official_candidate(result.text or "", result.final_url or target, round_)
        if discovered:
            tags["discovered_official_candidate"] = discovered
            _save_tags(round_, tags)
            out["discovered_official_candidate"] = discovered
            out["note"] = "已保存聚合快照并记录官方候选链接；仍需人工/后续官方快照核实，不自动 verified"
    return out


def _discover_official_candidate(html: str, page_url: str, round_: CampaignRound) -> str | None:
    """从聚合页粗提主办方外链；仅作候选，不写 official_url，不 verified。"""
    from urllib.parse import urljoin, urlparse

    from bs4 import BeautifulSoup

    from app.core.url_safety import assert_public_http_url

    page_host = (urlparse(page_url).hostname or "").lower()
    # 品牌词：标题中连续大写词或常见品牌片段（保守）
    tokens = []
    for part in (round_.title or "").split():
        p = part.strip(".,!?$\"'()[]{}").lower()
        if len(p) >= 4 and p.isalpha() and p not in {"cash", "giveaway", "sweepstakes", "contest", "verified", "left", "home", "garden"}:
            tokens.append(p)
    if not tokens:
        return None
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    for a in soup.find_all("a", href=True)[:400]:
        href = urljoin(page_url, a["href"])
        if not href.startswith("http"):
            continue
        host = (urlparse(href).hostname or "").lower()
        if not host or host == page_host or host.endswith("." + page_host):
            continue
        if any(x in host for x in ("facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com", "tiktok.com", "pinterest.com")):
            continue
        label = (a.get_text(" ", strip=True) or "").lower()
        if any(t in host or t in label or t in href.lower() for t in tokens[:6]):
            try:
                assert_public_http_url(href)
            except Exception:
                continue
            candidates.append(href.split("#")[0])
    # 去重保序
    seen: set[str] = set()
    for c in candidates:
        if c not in seen:
            seen.add(c)
            return c
    return None


async def attempt_official_evidence_batch(
    session: Session,
    settings: Settings,
    *,
    limit: int = 5,
) -> list[dict]:
    """公平调度：跳过已有官方快照；失败退避后再试；优先未尝试。"""
    candidates = session.scalars(
        select(CampaignRound).where(
            CampaignRound.verify_status == "candidate",
            CampaignRound.demo_only == False,  # noqa: E712
        )
    ).all()
    now = utc_now()
    eligible = []
    for r in candidates:
        tags = _load_tags(r)
        has_official_ev = session.scalar(
            select(Evidence).where(
                Evidence.entity_type == "campaign_round",
                Evidence.entity_id == r.id,
                Evidence.field_path == "official_page_snapshot",
            )
        )
        has_agg_ev = session.scalar(
            select(Evidence).where(
                Evidence.entity_type == "campaign_round",
                Evidence.entity_id == r.id,
                Evidence.field_path == "aggregator_page_snapshot",
            )
        )
        discovered = tags.get("discovered_official_candidate")
        if has_official_ev and r.official_url:
            continue
        # 已有聚合快照但尚无官方候选：本轮可再试（在 fail 退避之后由排序决定）
        if has_agg_ev and not discovered and not r.official_url:
            # 已成功抓过聚合页且未发现官方链接 → 退避 2h 避免死循环重抓
            last_ok = tags.get("last_provenance_ok")
            if last_ok:
                continue
        fail_n = int(tags.get("last_provenance_fail_count") or 0)
        last = tags.get("last_provenance_attempt_utc")
        if fail_n and last:
            try:
                last_dt = ensure_aware_utc(datetime.fromisoformat(last))
                backoff_h = min(24, 2**min(fail_n, 5))
                if last_dt and (now - last_dt) < timedelta(hours=backoff_h):
                    continue
            except Exception:
                pass
        eligible.append(r)
    # 未尝试的优先
    eligible.sort(
        key=lambda r: (
            1 if int(_load_tags(r).get("last_provenance_fail_count") or 0) else 0,
            r.id,
        )
    )
    out = []
    for r in eligible[:limit]:
        res = await attempt_official_evidence(session, settings, r)
        out.append({"round_id": r.id, "title": r.title[:60], **res})
        session.flush()
    if not out:
        out.append({"note": "本轮无待溯源候选（含退避）", "tried": 0})
    return out
