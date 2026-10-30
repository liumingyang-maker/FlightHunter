"""状态模型：开放/结束/待核实/未知分离。"""

from __future__ import annotations

from datetime import datetime

from app.services.raffle.multi_round import (
    eligibility_with_synthetic_profile,
    open_status_from_dates,
    parse_multi_round_event_html,
)


def test_date_unknown_is_not_closed():
    assert open_status_from_dates(None, None, datetime(2026, 10, 30)) == "unknown"
    assert (
        open_status_from_dates(
            None, None, datetime(2026, 10, 30), requires_login=True
        )
        == "pending_verification"
    )


def test_open_closed_by_dates():
    now = datetime(2026, 10, 30)
    assert open_status_from_dates(datetime(2026, 10, 26), datetime(2026, 11, 22), now) == "open"
    assert open_status_from_dates(datetime(2026, 8, 27), datetime(2026, 10, 6), now) == "closed"
    # 尚未开始不记 closed
    assert open_status_from_dates(datetime(2026, 11, 1), datetime(2026, 12, 1), now) == "pending_verification"


def test_kspicy_like_pending_not_historical():
    html = """
    <html><head><title>Survey</title></head><body>
    <p>Read our K-SPICY FOOD article, take the quiz, and enter to win round-trip flights to Korea!</p>
    <a href="/svc/login/signin.do?reUrl=/svc/sv/event.do?id=x">Join Now</a>
    <div style="display:none">No available surveys</div>
    <div style="display:none">You have already participated in the survey.</div>
    </body></html>
    """
    parsed = parse_multi_round_event_html(
        html,
        page_url="https://english.visitkorea.or.kr/svc/sv/surveyIntro.do?srvyKeyCd=a02e295b-2b64-490a-929e-00b97bcc5ff7",
        now=datetime(2026, 10, 30),
    )
    assert parsed.rounds
    r = parsed.rounds[0]
    assert r.open_status in {"pending_verification", "unknown"}
    assert r.open_status != "closed"
    assert parsed.to_dict()["ended_or_inactive_flight_rounds"] == [] or r.open_status != "closed"


def test_local_airport_poster_facts_open():
    html = """
    <html><head><title>LOCAL AIRPORT FOOD</title></head>
    <body>
    <h1>「LOCAL AIRPORT FOOD」专栏 ⭐️韩国往返机票活动⭐️</h1>
    <p>2026/10/23</p>
    <img src="/public/images/2026/10/23/b245e07ee3104d09a69ce3cfe68a76e0.png"/>
    </body></html>
    """
    facts = {
        "opens": "2026-10-26",
        "closes": "2026-11-22",
        "winners": 3,
        "tickets": 2,
        "title": "LOCAL AIRPORT FOOD round-trip",
        "prize_summary": "3名×2张韩国地方机场往返机票",
        "evidence": "official poster: 2026.10.26~2026.11.22",
    }
    parsed = parse_multi_round_event_html(
        html,
        page_url="https://chinese.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=1594420",
        now=datetime(2026, 10, 30),
        poster_facts=facts,
    )
    flights = [r for r in parsed.rounds if r.prize_is_flight]
    assert flights
    assert any(r.open_status == "open" for r in flights)
    assert parsed.to_dict()["open_flight_rounds"]


def test_exclusive_launch_no_mix():
    html = """
    <html><body>
    <h2>Previous event</h2><p>Round-trip Ticket to Korea</p>
    <p>July 20 – August 19, 2026</p>
    <h2>Current event</h2>
    <p>Period 3: October 1 – 31, 2026</p>
    <p>Gift Voucher</p>
    <p>This event is limited to non-Korean citizens only.</p>
    </body></html>
    """
    parsed = parse_multi_round_event_html(
        html,
        page_url="https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=1591568",
        now=datetime(2026, 10, 30),
    )
    flights = [r for r in parsed.rounds if r.prize_is_flight]
    assert flights and flights[0].open_status == "closed"
    # 不得把 10/31 当作机票开放
    assert not any(r.prize_is_flight and r.open_status == "open" for r in parsed.rounds)


def test_eligibility_unknown_profile_pending():
    from app.services.raffle.multi_round import EventRoundRules

    r = EventRoundRules(
        round_label="x",
        edition_key="x",
        title="t",
        prize_is_flight=True,
        open_status="pending_verification",
        residency_restriction="non-residents of Korea",
    )
    el = eligibility_with_synthetic_profile(r, nationality=None, residence=None)
    assert el["state"] == "unknown"
    # 用户 unknown 不得导致活动被标成 closed
    assert r.open_status != "closed"
