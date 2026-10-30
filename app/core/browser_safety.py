"""浏览器目标安全（C14-01）：连接期约束 + 默认拒绝。

威胁模型（本地个人工具，仅 `automation_policy=allowed` 站点）：
- 导航/子资源/弹窗/重定向：一律先 URL+DNS 公网校验，再放行
- 同源请求**同样**校验 DNS（防重绑定）
- data:/blob:/about: 放行；其它 scheme 默认拒绝
- 无法绑定「已验证 IP + TLS SNI」时，真实外站浏览器自动化保持 partial/blocked
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.core.url_safety import (
    assert_public_http_url,
    resolve_and_assert_public_host,
)


class BrowserTargetError(RuntimeError):
    """浏览器目标不安全。"""


def validate_browser_target(url: str) -> str:
    """启动前校验：返回规范化 URL；失败抛 BrowserTargetError。"""
    try:
        assert_public_http_url(url, field="browser_target")
        host = (urlparse(url).hostname or "").lower()
        resolve_and_assert_public_host(host, field="browser_target")
    except Exception as exc:
        raise BrowserTargetError(f"browser target rejected: {exc}") from exc
    return url


def _validate_request_url(url: str) -> None:
    """任意浏览器请求（含同源）：scheme/URL/DNS 公网校验。"""
    parsed = urlparse(url)
    if parsed.scheme in ("data:", "blob:", "about:"):
        return
    if parsed.scheme not in ("http", "https"):
        raise BrowserTargetError(f"scheme not allowed: {parsed.scheme}")
    assert_public_http_url(url, field="browser_request")
    host = (parsed.hostname or "").lower()
    resolve_and_assert_public_host(host, field="browser_request")


def make_route_guard_sync(page: Any, allowed_origin: str) -> Any:
    """同步 Playwright 拦截：所有请求（含同源）先验后放行；默认拒绝。"""

    def _handler(route: Any) -> None:
        try:
            req_url = route.request.url
            parsed = urlparse(req_url)
            if parsed.scheme in ("data:", "blob:", "about:"):
                route.continue_()
                return
            # C14-01：同源也要 DNS 校验，禁止直接 continue
            _validate_request_url(req_url)
            route.continue_()
        except Exception:
            route.abort()

    def _popup_handler(route: Any) -> None:
        # 弹窗/新窗口目标一律拒绝（默认拒绝策略）
        try:
            _validate_request_url(route.request.url)
            route.abort()
        except Exception:
            route.abort()

    page.route("**/*", _handler)
    try:
        page.context.route("**/*", _popup_handler)
    except Exception:
        pass
    return page
