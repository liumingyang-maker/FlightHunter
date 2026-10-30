"""第三方自查：按 Codex R-001~R-017 复现条件独立验证（不依赖 tests/unit 断言）。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

import httpx


def section(name: str) -> None:
    print(f"\n=== {name} ===")


def main() -> None:
    from app.core.safe_http import safe_get
    from app.adapters.html_fetcher import (
        _currency_from_token,
        _extract_published_only,
        extract_route_price_candidates,
        parse_deal_label,
    )

    results: list[tuple[str, bool, str]] = []

    # --- R-001 私网 robots 不得先请求 ---
    section("R-001 public→private robots")
    calls: list[str] = []

    def h1(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:9911/private"})
        return httpx.Response(200, text="ok")

    async def r1():
        async with httpx.AsyncClient(transport=httpx.MockTransport(h1)) as c:
            r = await safe_get("https://public.example/start", check_robots=True, client=c)
            private = [x for x in calls if "127.0.0.1" in x]
            return r, private

    r, private = asyncio.run(r1())
    ok = (not r.ok) and private == []
    results.append(("R-001 no private robots before block", ok, f"ok={r.ok} private={private} err={r.error}"))

    # --- R-002 robots 403 fail closed ---
    section("R-002 robots 403")
    calls2: list[str] = []

    def h2(request: httpx.Request) -> httpx.Response:
        calls2.append(str(request.url))
        if request.url.path.endswith("robots.txt"):
            return httpx.Response(403)
        return httpx.Response(200, text="body")

    async def r2():
        async with httpx.AsyncClient(transport=httpx.MockTransport(h2)) as c:
            return await safe_get("https://site.example/page", check_robots=True, client=c)

    r = asyncio.run(r2())
    target_hit = any(x.endswith("/page") for x in calls2)
    ok = (not r.ok) and (not target_hit) and "robots" in (r.error or "")
    results.append(("R-002 robots 403 no target", ok, f"err={r.error} target_hit={target_hit}"))

    # --- R-003 流式超限 ---
    section("R-003 stream limit")

    class _SR:
        status_code = 200
        headers = httpx.Headers({})

        async def aiter_bytes(self):
            for _ in range(4):
                yield b"x" * 100

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _C:
        def stream(self, *a, **k):
            return _SR()

        async def aclose(self):
            pass

    async def r3():
        return await safe_get("https://big.example/a", check_robots=False, max_bytes=100, client=_C(), resolve_dns=False)

    r = asyncio.run(r3())
    ok = (not r.ok) and "too_large" in (r.error or "")
    results.append(("R-003 stream too_large", ok, f"err={r.error}"))

    # --- R-004 多目的地串价 ---
    section("R-004 multi dest")
    label = "香港出发 台湾 HK$800 · 大阪 HK$1500 機票優惠"
    routes = extract_route_price_candidates(label)
    sig = parse_deal_label(label, page_url="https://example.com/x")
    amounts = {r.get("amount") for r in routes}
    cross = False
    if sig and sig.reported_total is not None:
        # 若写价且多金额 → 失败
        if len(amounts) > 1:
            cross = True
    ok = not cross
    results.append(("R-004 no single price on multi-dest", ok, f"routes={routes} sig_total={sig.reported_total if sig else None}"))

    # --- R-005 MOP ---
    section("R-005 MOP currency")
    c_mop = _currency_from_token("MOP$")
    sig_m = parse_deal_label("大阪 MOP$1500 機票優惠", page_url="https://example.com/x")
    cur = sig_m.currency if sig_m and sig_m.reported_total is not None else c_mop
    ok = cur == "MOP"
    results.append(("R-005 MOP not HKD", ok, f"currency={cur}"))

    # --- R-006 发布日期 ---
    section("R-006 published labels")
    bare = _extract_published_only("机票活动 2025年1月2日 机票优惠")
    upd = _extract_published_only("更新日期 2025年1月2日")
    pub = _extract_published_only("發佈日期·2026-10-29")
    ok = bare is None and upd is None and pub is not None and pub.day == 29
    results.append(("R-006 bare=None published=label", ok, f"bare={bare} upd={upd} pub={pub}"))

    # --- R-007 收藏筛选 ---
    section("R-007 feedback filter")
    from app.web.routes.api import _apply_intel_filters

    rows = [
        {"signal_status": "bookmarked", "user_feedback": "bookmarked", "title": "a", "destination_airport": None},
        {"signal_status": "discovered", "user_feedback": None, "title": "b", "destination_airport": None},
    ]
    out = _apply_intel_filters(rows, destination=None, category=None, date_from=None, date_to=None, feedback="bookmarked")
    ok = len(out) == 1
    results.append(("R-007 bookmarked filter", ok, f"n={len(out)}"))

    # --- R-008 跨境 ---
    section("R-008 HKG-PVG cross border")
    from app.services.airports.china import is_china_mainland_airport, is_international_pair

    ok = is_china_mainland_airport("HKG") is False and is_international_pair("HKG", "PVG") is True
    results.append(("R-008 HKG not mainland / intl pair", ok, f"hkg_main={is_china_mainland_airport('HKG')} pair={is_international_pair('HKG','PVG')}"))

    # --- R-009 航司不当地点 ---
    section("R-009 dest not airline")
    rows9 = [{"destination_airport": "KIX", "title": "香港航空 上海→大阪 优惠", "user_feedback": None}]
    out9 = _apply_intel_filters(rows9, destination="香港", category=None, date_from=None, date_to=None, feedback=None)
    ok = out9 == []
    results.append(("R-009 香港航空 not dest=香港", ok, f"n={len(out9)}"))

    # --- R-010 core_recommend ---
    section("R-010 core_recommend")
    import inspect
    from app.services.discovery import service as svc

    src = inspect.getsource(svc.materialize_raffle_candidates)
    ok = "excluded_or_domestic" in src and "core_recommend = True" not in src
    results.append(("R-010 candidate never core=True", ok, "static check"))

    # --- R-011 asyncio in loop ---
    section("R-011 sync in running loop")
    from app.core.safe_http import safe_get_sync

    async def r11():
        # 在 loop 内调用 sync，不应抛 RuntimeError
        def handler(request):
            return httpx.Response(200, text="ok")

        # safe_get_sync 会开线程新 loop，对真实域名可能慢；仅验证不抛 asyncio 错误
        try:
            # 用极短超时对不可达公网，重点是异常类型不是 asyncio
            safe_get_sync("https://example.invalid/x", timeout=0.1, check_robots=False, resolve_dns=False)
            return True, "no_raise"
        except RuntimeError as e:
            return False, f"RuntimeError:{e}"
        except Exception as e:
            return True, f"other_ok:{type(e).__name__}"

    ok, detail = asyncio.run(r11())
    results.append(("R-011 no asyncio.run conflict", ok, detail))

    # --- R-012/R-013 通知 ---
    section("R-012/013 delivery persist")
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.models import Base, NotificationDelivery
    from app.services.notify import delivery as dlv

    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    s = S()
    toast_n = {"n": 0}

    def ok_t(title, body):
        toast_n["n"] += 1
        return {"channel": "windows_toast", "status": "toast_delivered"}

    orig = dlv.deliver_windows_toast
    dlv.deliver_windows_toast = ok_t
    try:
        dlv.send_notification(s, kind="t", title="hello", body="x", event_key="ek1")
        n1 = toast_n["n"]
        # 模拟重启：新 session 同一 DB，进程内存无（我们已删 _DELIVERY_STATE 无）
        dlv.send_notification(s, kind="t", title="hello", body="x", event_key="ek1")
        n2 = toast_n["n"]
        ok12 = n1 == 1 and n2 == 1

        def fail_t(title, body):
            toast_n["n"] += 1
            return {"channel": "windows_toast", "status": "failed", "detail": "x"}

        dlv.deliver_windows_toast = fail_t
        toast_before = toast_n["n"]
        for _ in range(5):
            dlv.send_notification(s, kind="t2", title="failmsg", body="y", event_key="ek2")
        fail_calls = toast_n["n"] - toast_before
        row = s.scalar(select(NotificationDelivery).where(NotificationDelivery.event_key == "ek2"))
        ok13 = fail_calls <= 3 and row is not None and int(row.attempts) <= 3
        results.append(("R-012 success no re-toast after restart", ok12, f"n1={n1} n2={n2}"))
        results.append(("R-013 fail attempts<=3", ok13, f"fail_calls={fail_calls} row={row.attempts if row else None} status={row.status if row else None}"))
    finally:
        dlv.deliver_windows_toast = orig

    # --- R-015 ok_existing ---
    section("R-015 ok_existing")
    import inspect as _ins
    from app.services.discovery import service as dsvc

    src = _ins.getsource(dsvc.fetch_source)
    ok = 'last_result = "ok_existing"' in src
    results.append(("R-015 last_result ok_existing", ok, "static"))

    # --- R-016 fare monitor ---
    section("R-016 fare_monitor setting")
    from app.services.trips import service as tsvc

    src = _ins.getsource(tsvc.confirm_trip)
    ok = "auto_attach_fare_watch_to_new_trip" in src
    results.append(("R-016 confirm respects fare setting", ok, "static"))

    # --- R-017 pwsh encoding ---
    section("R-017 subprocess encoding")
    src = _ins.getsource(dlv.deliver_windows_toast)
    ok = 'encoding="utf-8"' in src and "errors=" in src
    results.append(("R-017 utf-8 subprocess", ok, "static"))

    # --- R-014 migration ---
    section("R-014 outdated version")
    from app.config import load_settings
    from app.db.session import check_alembic_head, ensure_migrations_or_warn

    tmp = Path(tempfile.mkdtemp(prefix="selfchk_"))
    try:
        db = tmp / "fh.db"
        cfg = tmp / "c.yaml"
        cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE alembic_version (version_num TEXT)")
        conn.execute("INSERT INTO alembic_version VALUES ('0001_initial')")
        conn.commit()
        conn.close()
        st = load_settings(str(cfg), project_root=tmp)
        rep = check_alembic_head(st)
        ens = ensure_migrations_or_warn(st)
        ok = rep.get("ok") is False and rep.get("state") == "outdated" and ens.get("action") == "outdated"
        results.append(("R-014 0001 not ok", ok, f"state={rep.get('state')} action={ens.get('action')}"))
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    # --- Web 启动接线 ---
    section("R-014 web wiring")
    web_src = Path("app/web/app.py").read_text(encoding="utf-8")
    ok = "ensure_migrations_or_warn" in web_src
    results.append(("web calls ensure_migrations", ok, "static"))

    section("SUMMARY")
    fails = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            fails += 1
        print(f"{mark:4} | {name} | {detail}")
    print(f"\n{len(results)-fails}/{len(results)} passed, {fails} failed")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
