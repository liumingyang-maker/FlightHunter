"""无人值守：对已有 official_url 的抽奖轮次自动核验证据与开放状态。

由 discover/调度在 after_fetch 调用，无需人工逐步 CLI。
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.ids import new_id
from app.models import CampaignRound, Evidence

# 报名入口探测：低频，避免打爆官方站
ENTRY_PROBE_MIN_INTERVAL_HOURS = 6
MAX_ROUNDS_PER_RUN = 8


def _load_tags(r: CampaignRound) -> dict:
    if not r.tags:
        return {}
    try:
        d = json.loads(r.tags)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_tags(r: CampaignRound, tags: dict) -> None:
    r.tags = json.dumps(tags, ensure_ascii=False)


def _verify_priority(r: CampaignRound) -> int:
    """优先核验像真实活动的轮次，避免先烧在页脚/条款链接上。"""
    title = (r.title or "").lower()
    tags = _load_tags(r)
    score = 0
    if tags.get("prize_is_flight") or "flight" in title or "机票" in (r.title or "") or "giveaway" in title:
        score -= 100
    if any(k in title for k in ("event", "活动", "contest", "sweep", "quiz", "k-food", "机场")):
        score -= 50
    if any(k in title for k in ("privacy", "terms", "条款", "政策", "手册", "热线", "app", "地图", "guide")):
        score += 80
    if r.prize_summary:
        score -= 20
    if r.entry_closes_at_utc:
        score -= 10
    return score


def _needs_verify(r: CampaignRound, now: datetime) -> bool:
    tags = _load_tags(r)
    if not r.official_url:
        return False
    if tags.get("auto_verify_done") and tags.get("auto_verify_at"):
        try:
            last = datetime.fromisoformat(str(tags["auto_verify_at"]))
            if last.tzinfo:
                last = last.replace(tzinfo=None)
            if now - last < timedelta(hours=ENTRY_PROBE_MIN_INTERVAL_HOURS):
                # 已核验且未到再探报名间隔
                if tags.get("entry_operable") is True:
                    return False
                # 未完成入口核验且到间隔再跑
                if now - last < timedelta(hours=ENTRY_PROBE_MIN_INTERVAL_HOURS):
                    return False
        except Exception:
            return True
        return False
    return True


def _build_zh_guide(ext, tags: dict, entry_url: str | None) -> str:
    lines = ["【中文参加说明（自动整理）】"]
    lines.append("1. 打开官方详情页，确认海报/正文中活动时间。")
    if ext.opens_raw or ext.closes_raw:
        lines.append(f"2. 活动期：{ext.opens_raw or '?'} ~ {ext.closes_raw or '?'}")
    else:
        lines.append("2. 活动期：页面未结构化解析到，请以官方海报为准。")
    if ext.prize_is_flight:
        lines.append("3. 奖品含往返机票；是否适用于中国内地出发/往返 **未确认**（unknown_origin_pending）。")
    lines.append("4. 报名入口：" + (entry_url or "页面内/海报「参加活动」") + "；需登录/同意隐私时请自行完成，系统不代提交。")
    if ext.residency_text:
        lines.append(f"5. 资格提示：{ext.residency_text}；无真实国籍/居住档案时保持 unknown。")
    else:
        lines.append("5. 资格：未完整解析；无档案不得假设 eligible。")
    lines.append("6. 中奖后可能需提供护照等信息；请仅在官方页填写。")
    lines.append("注意：开放日期 ≠ 用户有资格；本说明不构成已报名。")
    return "\n".join(lines)


async def probe_entry_url(url: str, *, timeout: float = 20.0) -> dict[str, Any]:
    """只读探测报名/活动入口；不登录、不提交。使用统一安全 GET。"""
    from app.core.safe_http import safe_get

    out: dict[str, Any] = {
        "url": url,
        "ok": False,
        "status_code": None,
        "error": None,
        "requires_human": False,
        "note": "",
        "redirects": None,
    }
    result = await safe_get(
        url,
        timeout=timeout,
        headers={"User-Agent": "FlightHunter-Bot/1.0 (entry probe, low frequency)"},
        check_robots=True,
    )
    out["status_code"] = result.status_code
    out["redirects"] = result.redirects
    out["final_url"] = result.final_url
    if result.robots_blocked:
        out["error"] = "robots_disallowed"
        out["note"] = "blocked_by_robots"
        return out
    if not result.ok:
        out["error"] = result.error
        if result.status_code in (401, 403, 429):
            out["requires_human"] = True
        return out
    text = (result.text or "").lower()
    if any(x in text for x in ("no available surveys", "already participated")):
        out["note"] = "page_indicates_unavailable_or_done"
        out["requires_human"] = True
        out["ok"] = True
    elif any(x in text for x in ("login", "signin", "password")) and "join now" in text:
        out["note"] = "login_or_join_gate"
        out["requires_human"] = True
        out["ok"] = True
    else:
        out["ok"] = True
        out["note"] = "http_200_readonly"
    return out


async def verify_round_auto(
    session: Session,
    settings: Settings,
    round_: CampaignRound,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """自动：详情页 → 资产/OCR 证据 → 开放状态 → （低频）报名入口探测。"""
    from app.adapters.html_fetcher import HttpxFetchAdapter
    from app.services.raffle.evidence_extract import extract_official_evidence
    from app.services.raffle.multi_round import parse_multi_round_event_html

    now_n = now or datetime.now(UTC).replace(tzinfo=None)
    tags = _load_tags(round_)
    url = round_.official_url
    if not url:
        return {"ok": False, "reason": "no_official_url", "round_id": round_.id}

    adapter = HttpxFetchAdapter(settings)
    result = await adapter.fetch(url)
    if not result.ok:
        tags["auto_verify_done"] = True
        tags["auto_verify_at"] = now_n.isoformat()
        tags["auto_verify_error"] = result.error_code
        _save_tags(round_, tags)
        return {
            "ok": False,
            "reason": "fetch_failed",
            "round_id": round_.id,
            "error_code": result.error_code,
        }

    async def _fetch_bytes(u: str) -> bytes:
        from app.core.safe_http import safe_get

        r = await safe_get(
            u,
            headers={"User-Agent": "FlightHunter-Bot/1.0 (evidence extract)"},
            timeout=40,
            check_robots=True,
            max_bytes=12_000_000,
        )
        if not r.ok or r.content is None:
            raise RuntimeError(r.error or "fetch_bytes_failed")
        return r.content

    ext = await extract_official_evidence(
        result.text or "",
        page_url=result.final_url or url,
        fetch_bytes=_fetch_bytes,
        now=now_n,
    )

    # 冲突：HTML 与 OCR 日期不一致 → 不自动择优，标人工复核
    html_opens = {e.value for e in ext.evidence if e.field_path == "opens" and e.method == "html_text"}
    ocr_opens = {
        e.value
        for e in ext.evidence
        if e.field_path == "opens" and str(e.method).startswith("image_ocr")
    }
    if html_opens and ocr_opens and not (html_opens & ocr_opens):
        ext.conflict_notes.append(f"html_vs_ocr_opens:{sorted(html_opens)}!={sorted(ocr_opens)}")
        ext.human_review_required = True
        for e in ext.evidence:
            if e.field_path in {"opens", "closes", "entry_period"} and e.confidence == "high":
                e.confidence = "pending"
                e.notes.append("conflict_with_other_source")

    auto_extract = {
        "title": (ext.prize_summary or round_.title or "auto")[:200],
        "opens": ext.opens_raw,
        "closes": ext.closes_raw,
        "opens_iso": ext.opens_iso,
        "closes_iso": ext.closes_iso,
        "prize_summary": ext.prize_summary,
        "prize_is_flight": ext.prize_is_flight
        if ext.prize_is_flight is not None
        else tags.get("prize_is_flight"),
        "winners_count": ext.winners_count,
        "tickets_per_winner": ext.tickets_per_winner,
        "free_entry": ext.free_entry,
        "residency_text": ext.residency_text,
        "entry_channel": ext.entry_channel,
        "open_status": ext.open_status,
        "human_review_required": ext.human_review_required,
        "confidence": "medium",
        "evidence_quote": (ext.ocr_text_sample or "")[:400],
    }
    parsed = parse_multi_round_event_html(
        result.text or "",
        page_url=result.final_url or url,
        now=now_n,
        auto_extract=auto_extract,
    )
    # 取与本 round 最接近的 open_status（优先 auto_extracted 或同 official_url 轮）
    status = ext.open_status
    opens_dt = datetime.fromisoformat(ext.opens_iso) if ext.opens_iso else None
    closes_dt = datetime.fromisoformat(ext.closes_iso) if ext.closes_iso else None
    # 用 multi_round 结果覆盖若更具体
    for r in parsed.rounds:
        if r.open_status in {"open", "closed", "pending_verification"}:
            if r.prize_is_flight or r.edition_key == "auto_extract":
                status = r.open_status
                if r.opens_iso:
                    opens_dt = datetime.fromisoformat(r.opens_iso)
                if r.closes_iso:
                    closes_dt = datetime.fromisoformat(r.closes_iso)
                break

    # 证据入库（去重 by content_hash+field+url）
    saved_ev = 0
    for e in ext.evidence:
        if e.field_path not in {
            "opens",
            "closes",
            "entry_period",
            "prize_is_flight",
            "winners_count",
            "residency_text",
            "entry_channel",
            "contact_text",
            "rule_link",
        }:
            continue
        exists = session.scalar(
            select(Evidence).where(
                Evidence.entity_type == "campaign_round",
                Evidence.entity_id == round_.id,
                Evidence.field_path == f"auto.{e.field_path}",
                Evidence.content_hash == e.content_hash,
            )
        )
        if exists:
            continue
        session.add(
            Evidence(
                id=new_id(),
                entity_type="campaign_round",
                entity_id=round_.id,
                field_path=f"auto.{e.field_path}",
                source_url=e.source_url,
                source_kind="official_page" if "visitkorea" in e.source_url or e.method == "html_text" else "third_party_reporting",
                quote=(e.raw_excerpt or e.value or "")[:1500],
                html_locator=e.locator,
                retrieved_at_utc=datetime.fromisoformat(e.retrieved_at_utc)
                if "T" in e.retrieved_at_utc
                else now_n,
                content_hash=e.content_hash,
                extraction_method=e.method,
                verification_method="pending_human"
                if e.confidence in {"low", "pending"} or ext.human_review_required
                else "machine_extracted",
            )
        )
        saved_ev += 1

    # 更新轮次字段
    if opens_dt and (round_.entry_opens_at_utc is None):
        round_.entry_opens_at_utc = opens_dt
    if closes_dt:
        round_.entry_opens_at_utc = round_.entry_opens_at_utc or opens_dt
        round_.entry_closes_at_utc = closes_dt
    if ext.prize_summary and not round_.prize_summary:
        round_.prize_summary = ext.prize_summary[:500]
    # 不自动 verified
    if round_.verify_status == "candidate" and ext.human_review_required:
        pass

    # 报名入口：从 HTML 提取 event.do 等，低频探测
    entry_url = tags.get("entry_url")
    if not entry_url:
        m = re.search(
            r"https?://[^\"'\s]+/(?:svc/sv/)?event\.do\?id=[a-f0-9-]+",
            result.text or "",
            re.I,
        )
        if m:
            entry_url = m.group(0)
        else:
            m2 = re.search(r"event\.do\?id=([a-f0-9-]+)", result.text or "", re.I)
            if m2:
                base = f"{urlparse(result.final_url or url).scheme}://{urlparse(result.final_url or url).netloc}"
                entry_url = f"{base}/svc/sv/event.do?id={m2.group(1)}"

    entry_probe = None
    last_probe = tags.get("entry_probe_at")
    can_probe = True
    if last_probe:
        try:
            lp = datetime.fromisoformat(str(last_probe))
            if lp.tzinfo:
                lp = lp.replace(tzinfo=None)
            if now_n - lp < timedelta(hours=ENTRY_PROBE_MIN_INTERVAL_HOURS):
                can_probe = False
        except Exception:
            can_probe = True
    if entry_url and can_probe:
        entry_probe = await probe_entry_url(entry_url)
        tags["entry_url"] = entry_url
        tags["entry_probe_at"] = now_n.isoformat()
        tags["entry_probe"] = entry_probe
        tags["entry_operable"] = bool(entry_probe.get("ok") and entry_probe.get("status_code") == 200)
        tags["entry_status"] = entry_probe.get("error") or entry_probe.get("note") or "unknown"
    elif entry_url:
        tags["entry_operable"] = tags.get("entry_operable", False)
        tags["entry_status"] = tags.get("entry_status", "probe_cooldown")

    # 六态：http_ok / extract_ok / rules_complete / date_open / entry_operable / user_eligible
    six = {
        "http_ok": True,
        "extract_ok": bool(ext.opens_iso or ext.prize_is_flight is not None),
        "rules_complete": not ext.human_review_required
        and bool(ext.opens_iso and ext.closes_iso and ext.prize_is_flight is not None),
        "date_open": status == "open",
        "entry_operable": bool(tags.get("entry_operable")),
        "user_eligible": False,  # 无真实档案永不自动 true
    }

    tags.update(
        {
            "auto_verify_done": True,
            "auto_verify_at": now_n.isoformat(),
            "open_status": status,
            "active_now": status == "open",
            "automated_evidence": True,
            "human_review_required": ext.human_review_required,
            "six_state": six,
            "conflict_notes": ext.conflict_notes,
            "prize_is_flight": auto_extract.get("prize_is_flight"),
            "entry_channel": ext.entry_channel,
            "guide_zh": True,
            "china_outbound_relevance": (
                "unknown_origin_pending"
                if auto_extract.get("prize_is_flight")
                else tags.get("china_outbound_relevance")
            ),
            "guide_zh_content": _build_zh_guide(ext, tags, entry_url),
        }
    )
    # C14-03/04：核验后用真实证据重算 core_recommend（接业务流）
    from app.services.raffle.core_recommend import evaluate_core_recommend

    core = evaluate_core_recommend(
        title=round_.title or "",
        evidence_text=(ext.prize_summary or "") + "\n" + (ext.residency_text or ""),
        prize_is_flight=auto_extract.get("prize_is_flight"),
        official_url=round_.official_url,
        verify_status="auto_extracted" if not ext.human_review_required else "candidate",
        source_kind=(tags.get("source_kind") or "official_page"),
    )
    tags["china_outbound_relevance"] = core["china_outbound"]
    tags["core_recommend"] = core["core_recommend"]
    tags["core_recommend_reasons"] = core["reasons"]
    # 证据撤销/降级：需人工复核或冲突时强制非 core
    if ext.human_review_required or ext.conflict_notes:
        tags["core_recommend"] = False
        tags["core_recommend_reasons"] = [
            *core["reasons"],
            "DEMOTED_HUMAN_REVIEW_OR_CONFLICT",
        ]
    if status in ("closed", "unknown"):
        tags["core_recommend"] = False
        tags["core_recommend_reasons"] = [
            *tags.get("core_recommend_reasons", []),
            "DEMOTED_NOT_OPEN",
        ]
    # open_status 写入便于 API
    if status == "open":
        tags["active_now"] = True
    elif status == "closed":
        tags["active_now"] = False
    else:
        tags["active_now"] = None
    _save_tags(round_, tags)
    session.flush()

    return {
        "ok": True,
        "round_id": round_.id,
        "title": (round_.title or "")[:60],
        "open_status": status,
        "opens": ext.opens_raw,
        "closes": ext.closes_raw,
        "evidence_saved": saved_ev,
        "human_review": ext.human_review_required,
        "conflicts": ext.conflict_notes,
        "entry": entry_probe,
        "six_state": six,
        "note": "auto verify; not verified; not eligible; no submit",
    }


async def auto_verify_pending_rounds(
    session: Session,
    settings: Settings,
    *,
    limit: int = MAX_ROUNDS_PER_RUN,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    now_n = now or datetime.now(UTC).replace(tzinfo=None)
    rows = session.scalars(
        select(CampaignRound)
        .where(CampaignRound.demo_only == False)  # noqa: E712
        .where(CampaignRound.official_url.is_not(None))
        .order_by(CampaignRound.updated_at_utc.desc())
        .limit(limit * 6)
    ).all()
    candidates = [r for r in rows if _needs_verify(r, now_n)]
    candidates.sort(key=lambda r: (_verify_priority(r), r.updated_at_utc or now_n))
    out: list[dict[str, Any]] = []
    for r in candidates:
        if len(out) >= limit:
            break
        try:
            res = await verify_round_auto(session, settings, r, now=now_n)
            out.append(res)
        except Exception as exc:
            out.append({"ok": False, "round_id": r.id, "error": type(exc).__name__, "message": str(exc)[:200]})
    session.flush()
    return out
