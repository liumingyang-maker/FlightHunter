"""浏览器目标安全：Playwright 自有网络栈无法注入 PublicAddressBackend。

策略：
1. 启动前 DNS+公网校验目标主机（连接期另由 route 拦截二次校验）
2. 同一页面仅允许目标 origin；子资源/重定向到私网一律中断
3. 文件模拟站（file://）仅本地沙箱路径
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


def make_route_guard_sync(page: Any, allowed_origin: str) -> Any:
    """同步 Playwright 拦截：仅放行 allowed_origin 同源 + 公网目标。"""

    def _handler(route: Any) -> None:
        try:
            req_url = route.request.url
            parsed = urlparse(req_url)
            if parsed.scheme in ("data:", "blob:", "about:"):
                route.continue_()
                return
            if parsed.scheme not in ("http", "https"):
                route.abort()
                return
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin == allowed_origin:
                route.continue_()
                return
            assert_public_http_url(req_url, field="browser_subresource")
            host = (parsed.hostname or "").lower()
            resolve_and_assert_public_host(host, field="browser_subresource")
            route.continue_()
        except Exception:
            route.abort()

    page.route("**/*", _handler)
    return page
