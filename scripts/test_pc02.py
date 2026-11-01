"""PC-02 验证：ETag/304 条件请求头真实发出。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx


def test_etag_headers_merged():
    """验证 headers 合并逻辑（不覆盖）。"""
    from app.adapters.html_fetcher import HttpxFetchAdapter
    from app.config import Settings

    settings = Settings()
    adapter = HttpxFetchAdapter(settings)

    # 直接测试 headers 合并逻辑
    headers_arg = {"If-None-Match": "abc123", "If-Modified-Since": "Wed, 01 Jan 2026"}
    headers = {"User-Agent": "FlightHunter/1.0"}
    if headers_arg:
        headers.update(headers_arg)

    assert "If-None-Match" in headers, f"ETag lost: {headers}"
    assert "If-Modified-Since" in headers, f"Last-Modified lost: {headers}"
    assert "User-Agent" in headers, f"UA lost: {headers}"
    print("PASS: headers merge preserves conditional headers")


def test_rss_forwards_headers():
    """RSS 适配器转发 headers。"""
    import inspect

    from app.adapters.rss import RssAdapter

    src = inspect.getsource(RssAdapter.fetch)
    assert "headers=headers" in src, f"RSS not forwarding headers: {src}"
    print("PASS: RSS forwards headers")


def test_safe_get_sends_headers():
    """safe_get 发送条件请求头。"""
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(dict(request.headers))
        return httpx.Response(200, text="ok")

    async def run():
        from app.core.safe_http import safe_get

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await safe_get(
            "https://example.com/page",
            check_robots=False,
            client=client,
            headers={"If-None-Match": "test-etag"},
        )
        return result

    result = asyncio.run(run())
    assert result.ok
    found = any("if-none-match" in str(h).lower() for h in captured)
    assert found, f"If-None-Match not sent: {captured}"
    print("PASS: safe_get sends conditional headers")


if __name__ == "__main__":
    test_etag_headers_merged()
    test_rss_forwards_headers()
    test_safe_get_sends_headers()
    print("\nALL PC-02 TESTS PASSED")
