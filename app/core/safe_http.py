"""统一安全 HTTP：每跳校验公网 + DNS、可选 robots、限制跳转/体积。

供入口探测、OCR、AJAX 列表等旁路使用，避免仅主机名校验后 follow_redirects。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib import robotparser
from urllib.parse import urlparse

import httpx

from app.core.url_safety import (
    assert_public_http_url,
    resolve_and_assert_public_host,
)

MAX_REDIRECTS = 5
MAX_BYTES = 8_000_000
DEFAULT_UA = "FlightHunter-Bot/1.0 (safe-fetch; local research)"


@dataclass
class SafeFetchResult:
    ok: bool
    status_code: int | None
    text: str | None
    content: bytes | None
    final_url: str
    error: str | None = None
    redirects: list[str] | None = None
    robots_blocked: bool = False


async def safe_get(
    url: str,
    *,
    timeout: float = 20.0,
    headers: dict[str, str] | None = None,
    check_robots: bool = True,
    max_bytes: int = MAX_BYTES,
    client: httpx.AsyncClient | None = None,
    resolve_dns: bool = True,
) -> SafeFetchResult:
    """逐跳 URL + DNS 公网校验后 GET；禁止跳到非公网；限制体积与跳转。"""

    redirects: list[str] = []
    current = url
    own_client = client is None
    # 注入 client（测试 MockTransport）时跳过真实 DNS；生产路径 own_client 强制解析
    do_dns = resolve_dns and own_client
    try:
        assert_public_http_url(current)
        if do_dns:
            resolve_and_assert_public_host((urlparse(current).hostname or "").lower())
    except Exception as exc:
        return SafeFetchResult(False, None, None, None, current, f"unsafe_url:{exc}", redirects)

    hdrs = {"User-Agent": DEFAULT_UA, **(headers or {})}
    if own_client:
        client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            headers=hdrs,
        )
    try:
        for _hop in range(MAX_REDIRECTS + 1):
            if check_robots:
                blocked = await _robots_disallowed(client, current)
                if blocked:
                    return SafeFetchResult(
                        False, None, None, None, current, "robots_disallowed", redirects, True
                    )
            try:
                assert_public_http_url(current)
                if do_dns:
                    resolve_and_assert_public_host((urlparse(current).hostname or "").lower())
            except Exception as exc:
                return SafeFetchResult(
                    False, None, None, None, current, f"unsafe_redirect:{exc}", redirects
                )
            redirects.append(current)
            resp = await client.get(current)
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location") or ""
                if not loc:
                    return SafeFetchResult(
                        False, resp.status_code, None, None, current, "redirect_without_location", redirects
                    )
                current = str(httpx.URL(current).join(loc))
                continue
            # 响应体积上限（Content-Length 预检 + 实际截断）
            cl = resp.headers.get("content-length")
            if cl:
                try:
                    if int(cl) > max_bytes:
                        return SafeFetchResult(
                            False,
                            resp.status_code,
                            None,
                            None,
                            current,
                            f"response_too_large:{cl}",
                            redirects,
                        )
                except ValueError:
                    pass
            body = resp.content[:max_bytes]
            if len(resp.content) > max_bytes:
                return SafeFetchResult(
                    False, resp.status_code, None, None, current, "response_too_large", redirects
                )
            text = None
            try:
                text = body.decode(resp.encoding or "utf-8", errors="replace")
            except Exception:
                text = body.decode("utf-8", errors="replace")
            return SafeFetchResult(
                resp.status_code < 400,
                resp.status_code,
                text,
                body,
                current,
                None if resp.status_code < 400 else f"http_{resp.status_code}",
                redirects,
            )
        return SafeFetchResult(False, None, None, None, current, "too_many_redirects", redirects)
    except Exception as exc:
        return SafeFetchResult(False, None, None, None, current, type(exc).__name__, redirects)
    finally:
        if own_client:
            await client.aclose()


def safe_get_sync(
    url: str,
    *,
    timeout: float = 20.0,
    headers: dict[str, str] | None = None,
    check_robots: bool = True,
    max_bytes: int = MAX_BYTES,
    resolve_dns: bool = True,
) -> SafeFetchResult:
    """同步包装：内部 asyncio.run；勿在已有事件循环中调用。"""
    return asyncio.run(
        safe_get(
            url,
            timeout=timeout,
            headers=headers,
            check_robots=check_robots,
            max_bytes=max_bytes,
            resolve_dns=resolve_dns,
        )
    )


def safe_fetch_bytes_sync(
    url: str,
    *,
    timeout: float = 40.0,
    headers: dict[str, str] | None = None,
    check_robots: bool = True,
    max_bytes: int = MAX_BYTES,
) -> bytes:
    """安全取二进制（图片等）；失败抛 RuntimeError。"""
    result = safe_get_sync(
        url,
        timeout=timeout,
        headers=headers,
        check_robots=check_robots,
        max_bytes=max_bytes,
    )
    if not result.ok or result.content is None:
        raise RuntimeError(result.error or "safe_fetch_failed")
    return result.content


async def _robots_disallowed(client: httpx.AsyncClient, url: str) -> bool:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    try:
        r = await client.get(f"{origin}/robots.txt", timeout=8)
        if r.status_code != 200:
            return False  # 无 robots 通常允许；站点策略由调用方额外处理
        rp = robotparser.RobotFileParser()
        rp.parse(r.text.splitlines())
        path = parsed.path or "/"
        return not rp.can_fetch(DEFAULT_UA, path)
    except Exception:
        return False
