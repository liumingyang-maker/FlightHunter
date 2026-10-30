"""统一安全 HTTP：每跳校验公网、可选 robots、限制跳转/体积。

供入口探测、OCR、AJAX 列表等旁路使用，避免仅主机名校验后 follow_redirects。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib import robotparser
from urllib.parse import urlparse

import httpx

from app.core.url_safety import assert_public_http_url

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
) -> SafeFetchResult:
    """逐跳校验后 GET；禁止跳到非公网。"""

    redirects: list[str] = []
    current = url
    try:
        assert_public_http_url(current)
    except Exception as exc:
        return SafeFetchResult(False, None, None, None, current, f"unsafe_url:{exc}", redirects)

    hdrs = {"User-Agent": DEFAULT_UA, **(headers or {})}
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=hdrs)
    try:
        for _hop in range(MAX_REDIRECTS + 1):
            if check_robots:
                blocked = await _robots_disallowed(client, current)
                if blocked:
                    return SafeFetchResult(
                        False, None, None, None, current, "robots_disallowed", redirects, True
                    )
            assert_public_http_url(current)
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
            body = resp.content[:max_bytes]
            text = None
            if b"html" in (resp.headers.get("content-type") or "").encode() or b"xml" in (
                resp.headers.get("content-type") or ""
            ).encode() or True:
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
