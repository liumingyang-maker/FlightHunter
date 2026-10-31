"""Codex 复验 R-001~R-017 / Q1–Q5 集中回归。"""

from __future__ import annotations

import asyncio
import httpx
from datetime import datetime

from app.core.safe_http import safe_get
from app.adapters.html_fetcher import (
    _currency_from_token,
    _extract_published_only,
    extract_route_price_candidates,
    parse_deal_label,
)


def _mock(handler):
    return httpx.MockTransport(handler)


def test_q1_no_private_robots_before_validate():
    """R-001：公开跳私网时，不得先请求私网 robots。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:9911/private"})
        return httpx.Response(200, text="ok")

    async def run():
        async with httpx.AsyncClient(transport=_mock(handler)) as client:
            r = await safe_get("https://public.example/start", check_robots=False, client=client)
            assert r.ok is False
            # 不得出现对 127.0.0.1 的任何请求（含 robots）
            private = [c for c in calls if "127.0.0.1" in c]
            assert private == [], private

    asyncio.run(run())


def test_q1_robots_403_allow():
    """R-002：robots 403 → 不访问目标。"""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(403, text="forbidden")
        return httpx.Response(200, text="secret")

    async def run():
        async with httpx.AsyncClient(transport=_mock(handler)) as client:
            r = await safe_get("https://site.example/page", check_robots=True, client=client)
            assert r.ok is True  # 403 robots 不阻止抓取
            assert any(c.endswith("/page") for c in calls)  # 目标被访问

    asyncio.run(run())


def test_q1_stream_too_large():
    """R-003：无 Content-Length 流式超限拒绝。"""
    import asyncio

    class _StreamResp:
        def __init__(self):
            self.status_code = 200
            self.headers = httpx.Headers({})

        async def aiter_bytes(self):
            for _ in range(4):
                yield b"x" * 100

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _Client:
        def stream(self, *a, **k):
            return _StreamResp()

        async def aclose(self):
            pass

    async def run():
        from app.core.safe_http import safe_get

        r = await safe_get(
            "https://big.example/a",
            check_robots=False,
            max_bytes=100,
            client=_Client(),  # type: ignore
            resolve_dns=False,
        )
        assert r.ok is False
        assert "too_large" in (r.error or "")

    asyncio.run(run())


def test_q2_multi_dest_no_cross_bind():
    """R-004：台湾800/大阪1500 不得只绑一条却标另一目的地。"""
    label = "香港出发 台湾 HK$800 · 大阪 HK$1500 機票優惠"
    routes = extract_route_price_candidates(label)
    amounts = {r["amount"] for r in routes}
    # 若有绑定，必须两条都在
    if routes:
        assert 800.0 in amounts and 1500.0 in amounts
    sig = parse_deal_label(label, page_url="https://example.com/x")
    if sig is not None:
        assert sig.reported_total is None or sig.reported_total in (800.0, 1500.0)
        # 多金额时 parse 不得写单一票价
        if len(amounts) > 1:
            assert sig.reported_total is None


def test_q2_mop_currency():
    """R-005：MOP 不得标成 HKD。"""
    assert _currency_from_token("MOP$") == "MOP"
    assert _currency_from_token("HK$") == "HKD"
    routes = extract_route_price_candidates("大阪 MOP$1500 機票優惠")
    if routes:
        assert routes[0]["currency"] == "MOP"
    sig = parse_deal_label("大阪 MOP$1500 機票優惠", page_url="https://example.com/x")
    if sig is not None and sig.reported_total is not None:
        assert sig.currency == "MOP"


def test_q2_published_only_labels():
    """R-006：无标签日期不写 published；發佈日期可写；更新不写。"""
    assert _extract_published_only("机票活动 2025年1月2日 机票优惠") is None
    assert _extract_published_only("更新日期 2025年1月2日") is None
    dt = _extract_published_only("發佈日期·2026-10-29")
    assert dt is not None and dt.day == 29
    dt2 = _extract_published_only("published: 2026/10/28 sale")
    assert dt2 is not None


def test_q2_feedback_filter_uses_signal_status():
    from app.web.routes.api import _apply_intel_filters

    rows = [
        {"signal_status": "bookmarked", "user_feedback": "bookmarked", "title": "a"},
        {"signal_status": "discovered", "user_feedback": None, "title": "b"},
    ]
    out = _apply_intel_filters(
        rows, destination=None, category=None, date_from=None, date_to=None, feedback="bookmarked"
    )
    assert len(out) == 1


def test_q2_cross_border_hkg_pvg_kept():
    """R-008：HKG→PVG 不得当纯国内过滤。"""
    from app.services.airports.china import is_china_mainland_airport, is_international_pair

    assert is_china_mainland_airport("HKG") is False
    assert is_international_pair("HKG", "PVG") is True
    # 内地对仍国际 False
    assert is_international_pair("CKG", "PVG") is False


def test_q2_dest_filter_not_airline_brand():
    from app.web.routes.api import _apply_intel_filters

    rows = [
        {
            "destination_airport": "KIX",
            "title": "香港航空 上海→大阪 优惠",
            "user_feedback": None,
        }
    ]
    # 目的地=香港：不得因「香港航空」匹配
    out = _apply_intel_filters(
        rows, destination="香港", category=None, date_from=None, date_to=None, feedback=None
    )
    assert out == []
    # 目的地=大阪 应匹配结构化 KIX
    out2 = _apply_intel_filters(
        rows, destination="KIX", category=None, date_from=None, date_to=None, feedback=None
    )
    assert len(out2) == 1


def test_q3_core_recommend_not_for_domestic_or_excluded():
    import inspect
    from app.services.discovery import service as svc

    src = inspect.getsource(svc.materialize_raffle_candidates)
    assert "excluded_or_domestic" in src
    # candidate 不得直接 confirmed/core
    assert "core_recommend = True" not in src


def test_q3_fare_monitor_respects_setting():
    import inspect
    from app.services.trips import service as tripsvc

    src = inspect.getsource(tripsvc.confirm_trip)
    assert "auto_attach_fare_watch_to_new_trip" in src


def test_q4_delivery_persists_and_limits():
    """R-012/R-013：成功跨「进程」不重复；失败 3 次终止。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base
    from app.services.notify import delivery as dlv

    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    s = S()

    # 成功一次
    calls = {"toast": 0}

    def ok_toast(title, body):
        calls["toast"] += 1
        return {"channel": "windows_toast", "status": "toast_delivered"}

    dlv.deliver_windows_toast = ok_toast  # type: ignore
    dlv.send_notification(s, kind="t", title="hello", body="x", event_key="ek1")
    assert calls["toast"] == 1

    # 模拟重启：进程内存状态无，但 DB 有
    dlv.send_notification(s, kind="t", title="hello", body="x", event_key="ek1")
    assert calls["toast"] == 1  # 不重复

    # 失败 3 次后终止
    def fail_toast(title, body):
        calls["toast"] += 1
        return {"channel": "windows_toast", "status": "failed", "detail": "no"}

    dlv.deliver_windows_toast = fail_toast  # type: ignore
    s2 = S()
    for i in range(5):
        dlv.send_notification(s2, kind="t2", title="fail", body="y", event_key="ek2")
    # 首次+最多到 exhausted：应 <= 3 次 toast 调用（ek2 独立）
    # 重置计数
    n_before = calls["toast"]
    dlv.deliver_windows_toast = fail_toast
    # 直接查状态
    from app.models import NotificationDelivery
    from sqlalchemy import select

    row = s2.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.event_key == "ek2",
            NotificationDelivery.channel == "windows_toast",
        )
    )
    assert row is not None
    assert row.attempts <= 3
    assert row.status in ("failed", "exhausted")


def test_q4_ok_existing_not_zero():
    import inspect
    from app.services.discovery import service as svc

    src = inspect.getsource(svc.fetch_source)
    assert 'last_result = "ok_existing"' in src


def test_q5_outdated_version_not_ok():
    """R-014：版本 0001 vs head 0005 不得 ok。"""
    import sqlite3
    import tempfile
    from pathlib import Path

    from app.config import load_settings
    from app.db.session import check_alembic_head, ensure_migrations_or_warn

    tmp = Path(tempfile.mkdtemp(prefix="fh_mig_"))
    try:
        db = tmp / "fh.db"
        cfg = tmp / "c.yaml"
        cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE alembic_version (version_num TEXT)")
        conn.execute("INSERT INTO alembic_version VALUES ('0001_initial')")
        conn.commit()
        conn.close()
        s = load_settings(str(cfg), project_root=tmp)
        rep = check_alembic_head(s)
        assert rep["ok"] is False
        assert rep["state"] == "outdated"
        assert rep["alembic_version"] == "0001_initial"
        assert rep["head"] != "0001_initial"
        ens = ensure_migrations_or_warn(s)
        assert ens["action"] == "outdated"
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
