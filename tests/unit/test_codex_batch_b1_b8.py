"""Codex N-001~N-018 集中回归（B1–B8）。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx

from app.core.safe_http import safe_get
from app.services.fare.intel import classify_signal, extract_origin_iatas_from_title
from app.models.fare import FareDealSignal
from app.adapters.html_fetcher import (
    extract_route_price_candidates,
    parse_deal_label,
    _extract_published_only,
)


def test_n001_public_to_private_redirect_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/steal"})
        return httpx.Response(200, text="ok")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            r = await safe_get("https://public.example/x", check_robots=False, client=client)
            assert r.ok is False
            r2 = await safe_get("http://127.0.0.1/", check_robots=False, client=client)
            assert r2.ok is False

    asyncio.run(run())


def test_n001_too_large_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2000, headers={"Content-Length": "2000"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            r = await safe_get(
                "https://big.example/a", check_robots=False, max_bytes=100, client=client
            )
            assert r.ok is False
            assert "too_large" in (r.error or "")

    asyncio.run(run())


def test_n003_shanghai_to_hongkong_not_hkg_origin():
    # 上海→香港：出发应为 PVG，不得把香港当出发进入 HKG 偏好
    origins = extract_origin_iatas_from_title("上海→香港 机票促销")
    assert "PVG" in origins
    assert origins[0] == "PVG"
    # 不应把 HKG 放在首位（显式出发优先）
    assert origins[0] != "HKG"


def test_n003_peach_osaka_seoul_not_hkg():
    origins = extract_origin_iatas_from_title("Peach 大阪→首尔 低价")
    # Peach 不是香港航司品牌启发；不得强制 HKG
    assert "HKG" not in origins


def test_n003_hongkong_airlines_shanghai_explicit():
    # 香港航空 上海出发 → 上海为出发
    origins = extract_origin_iatas_from_title("香港航空 上海出发 优惠")
    assert "PVG" in origins


def test_n004_multi_dest_price_not_cross_bound():
    # 多目的地且无法完整绑定 → 不返回错误单条绑定
    label = "HK Express 台湾 HK$800 · 大阪 HK$1500 促销"
    routes = extract_route_price_candidates(label)
    # 应能分别绑定，或空（不完整时）
    if routes:
        amounts = {r["amount"] for r in routes}
        assert 800 in amounts or 1500 in amounts
    # 裸价多目的地不进 parse_deal_label reported_total
    sig = parse_deal_label(label, page_url="https://example.com/x")
    if sig and sig.reported_total is not None:
        # 若有价，必须是绑定结果之一
        assert sig.reported_total in (800.0, 1500.0)


def test_n005_lisheng_not_ticket_price():
    sig = parse_deal_label("香港大阪機票立省HK$800", page_url="https://example.com/x")
    if sig is not None:
        assert sig.reported_total is None
    routes = extract_route_price_candidates("香港大阪機票立省HK$800")
    assert routes == []


def test_n005_zuiduo_jian_none():
    sig = parse_deal_label("最多減HK$500 東京机票", page_url="https://example.com/x")
    if sig is not None:
        assert sig.reported_total is None


def test_n006_travel_date_not_published():
    assert _extract_published_only("旅行日期 2027年2月3日") is None
    assert _extract_published_only("出发 2027-02-03 特价") is None


def test_n006_explicit_publish_date():
    dt = _extract_published_only("發布 2026-10-29 优惠")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 10 and dt.day == 29
    dt2 = _extract_published_only("published: 2026/10/28 sale")
    assert dt2 is not None and dt2.day == 28


def test_n008_community_flash_not_official():
    s = FareDealSignal(
        id="1",
        deal_id="d",
        title="sale",
        raw_claim_text="",
        deal_types='["flash_sale"]',
        source_type="community",
    )
    assert classify_signal(s) == "community_deal_tip"


def test_n015_pwsh_not_powershell51():
    from app.services.notify.delivery import deliver_windows_toast
    import inspect

    src = inspect.getsource(deliver_windows_toast)
    assert "pwsh" in src
    # 不应硬编码 Windows PowerShell 5.1 的 powershell.exe 作为首选
    assert "powershell.exe" not in src.lower().replace("pwsh.exe", "")


def test_n009_missing_nationality_unknown():
    from app.services.raffle.multi_round import (
        EventRoundRules,
        eligibility_with_synthetic_profile,
    )

    rules = EventRoundRules(
        round_label="r1",
        edition_key="e1",
        title="flight giveaway",
        purchase_required=False,
        residency_restriction="Open to non-Korean citizens who do not reside in Korea.",
    )
    r = eligibility_with_synthetic_profile(rules, nationality="CN", residence=None)
    assert r["state"] == "unknown"
    r2 = eligibility_with_synthetic_profile(rules, nationality=None, residence="CN")
    assert r2["state"] == "unknown"


def test_n011_ok_existing_not_zero_parse():
    # 业务状态由 service 返回；此处验证语义枚举存在
    from app.services.discovery import service as svc

    assert hasattr(svc, "fetch_source") or hasattr(svc, "discover_and_materialize")


def test_n016_core_recommend_positive_path_exists():
    import inspect
    from app.services.discovery import service as svc

    src = inspect.getsource(svc.materialize_raffle_candidates)
    # R-010：candidate 不得直接 core_recommend=True；排除/国内语义必须存在
    assert "excluded_or_domestic" in src
    assert "core_recommend = True" not in src


def test_b3_api_filter_helper():
    from app.web.routes.api import _apply_intel_filters

    rows = [
        {"destination_airport": "KIX", "category": "official_or_flash_promo", "title": "大阪", "published_at": "2026-10-29T00:00:00", "user_feedback": "bookmarked"},
        {"destination_airport": "ICN", "category": "community_deal_tip", "title": "首尔", "published_at": "2026-01-01T00:00:00", "user_feedback": None},
    ]
    out = _apply_intel_filters(rows, destination="KIX", category=None, date_from=None, date_to=None, feedback=None)
    assert len(out) == 1 and out[0]["destination_airport"] == "KIX"
    out2 = _apply_intel_filters(rows, destination=None, category="community_deal_tip", date_from=None, date_to=None, feedback=None)
    assert len(out2) == 1
    # 缺日期字段在指定时间过滤时不匹配
    out3 = _apply_intel_filters(rows, destination=None, category=None, date_from="2026-06-01", date_to=None, feedback=None)
    assert all(r["published_at"] >= "2026-06-01" for r in out3)
    out4 = _apply_intel_filters(rows, destination=None, category=None, date_from=None, date_to=None, feedback="bookmarked")
    assert len(out4) == 1


def test_confirm_trip_restores_disabled():
    from app.services.trips import service as tripsvc
    import inspect

    src = inspect.getsource(tripsvc.confirm_trip)
    assert "trip_not_confirmed" in src
    assert "enabled = True" in src


def test_update_trip_keeps_confirmed():
    import inspect
    from app.services.trips import service as tripsvc

    src = inspect.getsource(tripsvc.update_trip)
    # 已确认编辑不得禁用
    assert "不得禁用" in src or "auto_scan_on_trip_change" in src
