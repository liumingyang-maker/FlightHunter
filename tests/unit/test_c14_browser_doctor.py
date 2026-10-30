"""C14-01/02 浏览器同源校验 + doctor 只读。"""

from __future__ import annotations

import pytest

from app.core.browser_safety import (
    BrowserTargetError,
    make_route_guard_sync,
    validate_browser_target,
)


class _Req:
    def __init__(self, url: str):
        self.url = url


class _Route:
    def __init__(self, url: str):
        self.request = _Req(url)
        self.action = None

    def continue_(self):
        self.action = "continue"

    def abort(self):
        self.action = "abort"


class _Context:
    def __init__(self):
        self.handler = None

    def route(self, pattern, handler):
        self.handler = handler


class _Page:
    def __init__(self):
        self.handler = None
        self.context = _Context()

    def route(self, pattern, handler):
        self.handler = handler


def test_same_origin_also_validated():
    """C14-01：同源请求不得绕过 DNS 校验。"""
    page = _Page()
    make_route_guard_sync(page, "https://public.example")
    # 同源但私网 IP（模拟 DNS 变化）→ abort
    r = _Route("https://127.0.0.1/steal")
    page.handler(r)
    assert r.action == "abort"


def test_same_origin_localhost_rejected():
    page = _Page()
    make_route_guard_sync(page, "https://localhost.evil")
    r = _Route("https://localhost/x")
    page.handler(r)
    assert r.action == "abort"


def test_cross_origin_private_rejected():
    page = _Page()
    make_route_guard_sync(page, "https://public.example")
    r = _Route("http://10.0.0.1/x")
    page.handler(r)
    assert r.action == "abort"


def test_popup_handler_rejects():
    page = _Page()
    make_route_guard_sync(page, "https://public.example")
    assert page.context.handler is not None
    r = _Route("https://public.example/popup")
    page.context.handler(r)
    assert r.action == "abort"


def test_validate_target_private_rejected():
    with pytest.raises(BrowserTargetError):
        validate_browser_target("http://192.168.1.1/")
    with pytest.raises(BrowserTargetError):
        validate_browser_target("http://169.254.169.254/")


def test_doctor_readonly_no_init_db():
    """C14-02：doctor 不得 create_all。"""
    import inspect

    from app.cli import doctor

    src = inspect.getsource(doctor)
    assert "init_db" not in src
    assert "check_alembic_head" in src
