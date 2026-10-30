"""自动证据提取回归：不得硬编码具体活动。"""

from __future__ import annotations

from datetime import datetime

from app.services.raffle.evidence_extract import (
    discover_page_assets,
    open_status_from_extract,
    parse_rules_from_text,
)
from app.services.raffle.multi_round import parse_multi_round_event_html


def test_discover_assets_finds_public_image_and_pdf():
    html = """
    <html><body>
    <img src="/public/images/2026/10/23/poster.png" alt="活动海报"/>
    <img src="/static/logo.png" alt="logo"/>
    <a href="/files/rules.pdf">活动规则</a>
    <a href="javascript:goLinkPage('N','', 'https://example.org/x.pdf', '1', '1');">下载规则</a>
    </body></html>
    """
    assets = discover_page_assets(html, "https://example.org/page")
    kinds = {a["kind"] for a in assets}
    assert "poster_image" in kinds
    assert "rule_link" in kinds
    assert not any("logo" in a["url"] for a in assets)


def test_parse_dates_from_ocr_like_text():
    text = "2026.10.26(Mon) ~ 2026.11.22(Sun)\nRound-trip Ticket\n3 Winners, two tickets per 1"
    items = parse_rules_from_text(text, source_url="https://example.org/img.png", locator="img", method="image_ocr:eng")
    paths = {i.field_path: i.value for i in items}
    assert paths.get("opens") == "2026-10-26"
    assert paths.get("closes") == "2026-11-22"
    assert paths.get("prize_is_flight") == "true"
    assert paths.get("winners_count") == "3"


def test_open_status_not_closed_without_dates():
    assert open_status_from_extract(None, None, datetime(2026, 10, 30)) == "unknown"
    assert open_status_from_extract(None, None, datetime(2026, 10, 30), requires_login=True) == "pending_verification"
    assert (
        open_status_from_extract(datetime(2026, 10, 26), datetime(2026, 11, 22), datetime(2026, 10, 30))
        == "open"
    )


def test_multi_round_uses_auto_extract_not_hardcoded():
    html = "<html><head><title>Tour</title></head><body><h1>Official Giveaway</h1></body></html>"
    auto = {
        "opens": "2026-10-01",
        "closes": "2026-12-01",
        "prize_is_flight": True,
        "prize_summary": "flight",
        "winners_count": 5,
        "open_status": "open",
        "human_review_required": True,
    }
    parsed = parse_multi_round_event_html(
        html,
        page_url="https://example.org/official/giveaway",
        now=datetime(2026, 10, 30),
        auto_extract=auto,
    )
    flights = [r for r in parsed.rounds if r.prize_is_flight]
    assert flights
    assert flights[0].open_status == "open"
    assert flights[0].opens_raw == "2026-10-01"
    # 不应把 10-31 韩国活动日期硬编码进来
    assert "1594420" not in html
    assert "2026-11-22" not in html
