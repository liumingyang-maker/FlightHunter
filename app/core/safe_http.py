"""统一安全 HTTP：每跳先验 URL/DNS 再 robots/正文；流式限量；403/429 fail-closed。

供入口探测、OCR、AJAX 列表等旁路使用，避免仅主机名校验后 follow_redirects。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib import robotparser
from urllib.parse import urlparse

import httpcore
import httpx

from app.core.url_safety import (
    assert_public_http_url,
    resolve_and_assert_public_host,
)

MAX_REDIRECTS = 5
MAX_BYTES = 8_000_000
ROBOTS_MAX_BYTES = 256_000
DEFAULT_UA = "FlightHunter-Bot/1.0 (safe-fetch; local research)"


class PublicAddressBackend(httpcore.AsyncNetworkBackend):
    """Resolve and validate the address used by the actual TCP connection.

    HTTPX/httpcore still see the original origin, so Host and TLS SNI/certificate
    validation continue to use the hostname rather than the chosen IP address.
    """

    def __init__(self, backend: httpcore.AsyncNetworkBackend | None = None) -> None:
        self._backend = backend or httpcore.AnyIOBackend()

    async def connect_tcp(
        self, host: str, port: int, timeout: float | None = None,
        local_address: str | None = None, socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            addresses = await asyncio.to_thread(resolve_and_assert_public_host, host)
        except Exception as exc:
            raise httpcore.ConnectError(f"address validation failed: {exc}") from exc
        if not addresses:
            raise httpcore.ConnectError("No validated public address available")
        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self._backend.connect_tcp(
                    host=address, port=port, timeout=timeout,
                    local_address=local_address, socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
            except TypeError as exc:
                # 旧 httpcore 签名兼容：去掉可选参数重试一次
                try:
                    return await self._backend.connect_tcp(host=address, port=port)
                except Exception as exc2:
                    last_error = exc2
        if last_error:
            raise last_error
        raise httpcore.ConnectError("No validated public address available")

    async def connect_unix_socket(self, *args: Any, **kwargs: Any) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("Unix sockets are not allowed for public fetches")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


def public_http_transport() -> httpx.AsyncHTTPTransport:
    """Install the validating network backend on HTTPX's direct connection pool."""
    transport = httpx.AsyncHTTPTransport(trust_env=False)
    # HTTPX exposes no public hook for httpcore's network_backend. Fail closed
    # if a future HTTPX version no longer provides the expected direct pool.
    pool = transport._pool
    if not isinstance(pool, httpcore.AsyncConnectionPool) or not hasattr(pool, "_network_backend"):
        raise RuntimeError("HTTPX public-address transport is incompatible")
    pool._network_backend = PublicAddressBackend()
    return transport


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


async def _read_body_limited(resp: httpx.Response, max_bytes: int) -> bytes | None:
    """流式读取，超过 max_bytes 立即停止并返回 None。"""
    chunks: list[bytes] = []
    total = 0
    try:
        async for chunk in resp.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                return None
            chunks.append(chunk)
    except httpx.HTTPError:
        return None
    return b"".join(chunks)


async def _validate_hop(url: str, *, do_dns: bool) -> str | None:
    """返回错误信息；None 表示通过。先于任何网络请求。"""
    try:
        assert_public_http_url(url)
        if do_dns:
            resolve_and_assert_public_host((urlparse(url).hostname or "").lower())
    except Exception as exc:
        return f"unsafe_url:{exc}"
    return None


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
    """每跳：先 URL/DN 校验 → 再 robots → 再正文；禁止先请求后校验。"""

    redirects: list[str] = []
    current = url
    own_client = client is None
    # 注入 client（测试 MockTransport）时跳过真实 DNS；生产路径 own_client 强制解析
    do_dns = resolve_dns and own_client
    err = await _validate_hop(current, do_dns=do_dns)
    if err:
        return SafeFetchResult(False, None, None, None, current, err, redirects)

    hdrs = {"User-Agent": DEFAULT_UA, **(headers or {})}
    if own_client:
        client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            transport=public_http_transport(),
            headers=hdrs,
        )
    try:
        for _hop in range(MAX_REDIRECTS + 1):
            # R-001：先验本跳，再 robots，再请求 —— 私网绝不在校验前被访问
            err = await _validate_hop(current, do_dns=do_dns)
            if err:
                return SafeFetchResult(
                    False, None, None, None, current, f"unsafe_redirect:{err}", redirects
                )
            redirects.append(current)

            if check_robots:
                rb = await _robots_policy(client, current)
                if rb == "blocked":
                    return SafeFetchResult(
                        False, None, None, None, current, "robots_disallowed", redirects, True
                    )
                if rb == "error":
                    return SafeFetchResult(
                        False, None, None, None, current, "robots_unavailable_fail_closed", redirects, True
                    )

            async with client.stream("GET", current) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location") or ""
                    if not loc:
                        return SafeFetchResult(
                            False, resp.status_code, None, None, current, "redirect_without_location", redirects
                        )
                    current = str(httpx.URL(current).join(loc))
                    continue

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

                body = await _read_body_limited(resp, max_bytes)
                if body is None:
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
    """同步包装。若已在事件循环中，启动临时线程运行，避免 asyncio.run 冲突。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
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
    # 已在 loop 中：不能 asyncio.run —— 用独立线程新 loop
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            asyncio.run,
            safe_get(
                url,
                timeout=timeout,
                headers=headers,
                check_robots=check_robots,
                max_bytes=max_bytes,
                resolve_dns=resolve_dns,
            ),
        ).result()


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


async def _robots_policy(client: httpx.AsyncClient, url: str) -> str:
    """返回 allow | blocked | error。

    - 200 + disallow → blocked
    - 200 + allow → allow
    - 404 → allow（明确无 robots 文件的常见约定）
    - 403/429/其它/异常 → error（fail-closed，不访问目标）
    """
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = f"{origin}/robots.txt"
    try:
        # robots 自身也先验公网
        err = await _validate_hop(robots_url, do_dns=False)
        if err:
            return "error"
        async with client.stream("GET", robots_url, timeout=8) as resp:
            status = resp.status_code
            if status == 404:
                return "allow"
            if status in (403, 429, 401, 405, 500, 502, 503):
                return "error"
            if status != 200:
                return "error"
            raw = await _read_body_limited(resp, ROBOTS_MAX_BYTES)
            if raw is None:
                return "error"
            text = raw.decode("utf-8", errors="replace")
        rp = robotparser.RobotFileParser()
        rp.parse(text.splitlines())
        path = parsed.path or "/"
        return "allow" if rp.can_fetch(DEFAULT_UA, path) else "blocked"
    except Exception:
        return "error"
