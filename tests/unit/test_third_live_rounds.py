"""第三阶段：多期拆分 / result.text 边界 / 过期机票。"""

from __future__ import annotations

from datetime import datetime

from app.adapters.base import FetchResult
from app.config import Settings
from app.db.session import ensure_default_sources
from app.services.discovery.service import fetch_source
from app.services.raffle.multi_round import (
    eligibility_with_synthetic_profile,
    parse_multi_round_event_html,
)


def _sample_b_html() -> str:
    return """
    <html><head><title>VISITKOREA Exclusive Launch Event</title></head><body>
    <h1>VISITKOREA Exclusive Launch Event</h1>
    <h2>Previous event</h2>
    <p>Round-trip Ticket to Korea</p>
    <p>July 20 – August 19, 2026 (KST / 31 days)</p>
    <p>The winner receives a round-trip ticket to Korea. Winners announced August 26, 2026.</p>
    <h2>Current event</h2>
    <p>Period 1: July 20 – August 31, 2026</p>
    <p>Period 2: September 1 – 30, 2026</p>
    <p>Period 3: October 1 – 31, 2026</p>
    <p>Gift Card / Gift Voucher / eGift Card winners</p>
    <h2>Event Disclaimer</h2>
    <p>This event is limited to non-Korean citizens only.</p>
    </body></html>
    """


def _sample_c_html() -> str:
    return """
    <html><head><title>Watch, Comment, Fly to Korea!: K-Local Food Hunters 33</title></head><body>
    <h1>K-Local Food Hunters 33</h1>
    <p>enter for a chance to win a round-trip flight to Korea!</p>
    <p>Event Period August 27 (Thu) - October 6 (Tue)</p>
    <p>Round-trip Ticket to Korea (3 Winners, two tickets per 1)</p>
    <p>This event is open to foreign nationals who do not reside in Korea.</p>
    </body></html>
    """


def test_multi_round_does_not_mix_flight_with_gift_dates():
    # 固定 now 在 Event2 第三期窗口内（2026-10-15），Event1 机票已结束
    now = datetime(2026, 10, 15, 12, 0, 0)
    parsed = parse_multi_round_event_html(
        _sample_b_html(), page_url="https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=1591568", now=now
    )
    flights = [r for r in parsed.rounds if r.prize_is_flight]
    gifts = [r for r in parsed.rounds if r.prize_is_gift_or_other]
    assert flights, "应拆出机票轮次"
    assert gifts, "应拆出礼券轮次"
    # 机票轮不得把 active 标成 true（其窗口 7/20-8/19 已过）
    for fr in flights:
        assert fr.active_now is not True, fr
        assert (fr.closes_raw and "August 19" in (fr.opens_raw or "") + (fr.closes_raw or "")) or fr.opens_raw
    # 礼券轮可以是 active（第三期 10/1-10/31）
    gift_active = [g for g in gifts if g.active_now is True]
    assert gift_active, "当前礼券期应可识别为进行中"
    # 防护：不存在「open 且 flight 且用 10/31 作为 closes」的错误轮
    for fr in flights:
        if fr.active_now is True:
            raise AssertionError("机票轮不应在 10/15 仍开放")


def test_ended_flight_not_open():
    now = datetime(2026, 10, 30, 12, 0, 0)
    parsed = parse_multi_round_event_html(
        _sample_c_html(),
        page_url="https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=1593009",
        now=now,
    )
    flights = [r for r in parsed.rounds if r.prize_is_flight]
    assert flights
    for fr in flights:
        assert fr.active_now is not True
        assert fr.closes_iso and fr.closes_iso.startswith("2026-10-06")


def test_eligibility_synthetic_cn_unknown_vs_pass():
    now = datetime(2026, 10, 15)
    parsed = parse_multi_round_event_html(
        _sample_b_html(),
        page_url="https://english.visitkorea.or.kr/x",
        now=now,
    )
    flight = next(r for r in parsed.rounds if r.prize_is_flight)
    u = eligibility_with_synthetic_profile(flight, nationality=None, residence=None)
    assert u["state"] == "unknown"
    p = eligibility_with_synthetic_profile(flight, nationality="CN", residence="CN")
    # 非韩国公民限制下 CN 合成档案应 pass 该条，但年龄等仍可能 unknown
    codes = {c["code"]: c["outcome"] for c in p["checks"]}
    assert codes["RESIDENCY_OR_NATIONALITY"] == "pass"
    assert p["state"] in {"unknown", "eligible"}
    kr = eligibility_with_synthetic_profile(flight, nationality="KR", residence="KR")
    assert kr["state"] == "ineligible"


async def test_fetch_source_with_none_text_does_not_crash(db, settings: Settings):
    ensure_default_sources(db, settings)
    db.commit()
    from app.models import Source
    from sqlalchemy import select

    src = db.scalars(select(Source).where(Source.module == "raffle")).first()
    assert src is not None

    class _EmptyAdapter:
        name = "empty"

        async def fetch(self, url: str):
            return FetchResult(
                ok=True,
                url=url,
                status_code=200,
                text=None,  # type: ignore[arg-type]
                content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                final_url=url,
            )

        def parse_raffle(self, text: str, *, url: str):
            return []

    import app.services.discovery.service as svc

    real = svc.adapter_for
    try:
        svc.adapter_for = lambda s, st: _EmptyAdapter()  # type: ignore[assignment]
        out = await fetch_source(db, settings, src, module="raffle", dry_run=False, persist_signals=True)
        assert out["status"] in {"ok", "failed", "ok_zero"}
    finally:
        svc.adapter_for = real  # type: ignore[assignment]
