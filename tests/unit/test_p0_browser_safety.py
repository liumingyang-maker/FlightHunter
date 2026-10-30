"""P0 安全：浏览器目标/子资源边界 + 公网地址 backend 集成。"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.browser_safety import (
    BrowserTargetError,
    make_route_guard_sync,
    validate_browser_target,
)
from app.core.safe_http import PublicAddressBackend, public_http_transport, safe_get
from app.core.url_safety import assert_public_http_url, resolve_and_assert_public_host


def test_validate_browser_target_rejects_private():
    with pytest.raises(BrowserTargetError):
        validate_browser_target("http://127.0.0.1/x")
    with pytest.raises(BrowserTargetError):
        validate_browser_target("http://10.0.0.1/x")
    with pytest.raises(BrowserTargetError):
        validate_browser_target("http://169.254.169.254/latest/meta-data/")


def test_validate_browser_target_rejects_ip_aliases():
    with pytest.raises(BrowserTargetError):
        validate_browser_target("http://2130706433/")
    with pytest.raises(BrowserTargetError):
        validate_browser_target("http://0x7f000001/")


def test_route_guard_blocks_cross_origin_private():
    class _Req:
        url = "http://127.0.0.1/steal"

    class _Route:
        request = _Req()

        def __init__(self):
            self.action = None

        def continue_(self):
            self.action = "continue"

        def abort(self):
            self.action = "abort"

    class _Page:
        def __init__(self):
            self.handler = None

        def route(self, pattern, handler):
            self.handler = handler

    page = _Page()
    make_route_guard_sync(page, "https://public.example")
    assert page.handler is not None
    route = _Route()
    page.handler(route)
    assert route.action == "abort"


def test_route_guard_allows_same_origin():
    class _Req:
        url = "https://public.example/page"

    class _Route:
        request = _Req()

        def __init__(self):
            self.action = None

        def continue_(self):
            self.action = "continue"

        def abort(self):
            self.action = "abort"

    class _Page:
        def route(self, pattern, handler):
            self.handler = handler

    page = _Page()
    make_route_guard_sync(page, "https://public.example")
    route = _Route()
    page.handler(route)
    assert route.action == "continue"


def test_public_transport_installs_backend():
    t = public_http_transport()
    backend = t._pool._network_backend
    assert isinstance(backend, PublicAddressBackend)


def test_public_transport_unix_socket_rejected():
    backend = PublicAddressBackend()

    async def _run():
        return await backend.connect_unix_socket("/tmp/x")

    with pytest.raises(Exception):
        asyncio.run(_run())


def test_shared_address_space_blocked():
    with pytest.raises(Exception):
        assert_public_http_url("http://100.64.0.1/")
    with pytest.raises(Exception):
        resolve_and_assert_public_host("10.1.2.3")


def test_safe_get_mock_private_redirect_never_touches_private():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:9/x"})
        return httpx.Response(200, text="ok")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            r = await safe_get("https://public.example/a", check_robots=False, client=client)
            return r

    r = asyncio.run(run())
    assert r.ok is False
    assert [c for c in calls if "127.0.0.1" in c] == []
