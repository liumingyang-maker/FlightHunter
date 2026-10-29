"""httpx 简单抓取适配器（公开 HTML）。

禁止 follow_redirects=True 自动跳转：每一跳先 assert_public_http_url 再请求。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.adapters.base import FetchResult, ParsedSignal, SourceAdapter
from app.config import Settings
from app.core.errors import ErrorCode
from app.core.ids import content_hash_of_html
from app.core.url_safety import (
    assert_public_http_url,
    resolve_and_assert_public_host,
    safe_redirect_target,
)

_MAX_REDIRECT_HOPS = 5


class HttpxFetchAdapter(SourceAdapter):
    name = "httpx"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._robots_cache: dict[str, robotparser.RobotFileParser | None] = {}

    async def _robots_allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        """robots 非 200 或异常 → fail-closed（不允许）。"""
        if not self.settings.sources.obey_robots_and_site_terms:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots_cache:
            rp = robotparser.RobotFileParser()
            try:
                resp = await client.get(f"{origin}/robots.txt", timeout=10)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                    self._robots_cache[origin] = rp
                else:
                    self._robots_cache[origin] = None
            except Exception:
                self._robots_cache[origin] = None
        entry = self._robots_cache.get(origin)
        if entry is None:
            return False
        return entry.can_fetch("*", url)

    async def fetch(self, url: str) -> FetchResult:
        try:
            assert_public_http_url(url)
            host = (urlparse(url).hostname or "").lower()
            resolve_and_assert_public_host(host)
        except Exception as exc:
            return FetchResult(
                ok=False,
                url=url,
                error_code=ErrorCode.URL_NOT_PUBLIC.value,
                message=str(exc),
                fetched_at=datetime.now(UTC),
            )

        headers = {"User-Agent": "FlightHunter/1.0 (+local personal research; respectful)"}
        timeout = self.settings.sources.max_runtime_seconds_per_page
        current = url
        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                for _hop in range(_MAX_REDIRECT_HOPS + 1):
                    try:
                        assert_public_http_url(current)
                    except Exception as exc:
                        return FetchResult(
                            ok=False,
                            url=url,
                            error_code=ErrorCode.URL_NOT_PUBLIC.value,
                            message=f"跳转目标不安全（请求前拦截）: {exc}",
                            final_url=current,
                            fetched_at=datetime.now(UTC),
                        )
                    if not await self._robots_allowed(client, current):
                        return FetchResult(
                            ok=False,
                            url=url,
                            error_code=ErrorCode.SOURCE_FETCH_DENIED.value,
                            message="robots.txt 不允许抓取",
                            robots_disallowed=True,
                            final_url=current,
                            fetched_at=datetime.now(UTC),
                        )
                    try:
                        resp = await client.get(current)
                    except httpx.HTTPError as exc:
                        return FetchResult(
                            ok=False,
                            url=url,
                            error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                            message=str(exc),
                            final_url=current,
                            fetched_at=datetime.now(UTC),
                        )

                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("location")
                        if not loc:
                            return FetchResult(
                                ok=False,
                                url=url,
                                status_code=resp.status_code,
                                error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                                message="重定向缺少 Location",
                                final_url=current,
                                fetched_at=datetime.now(UTC),
                            )
                        nxt = urljoin(current, loc)
                        try:
                            safe_redirect_target(nxt)
                        except Exception as exc:
                            return FetchResult(
                                ok=False,
                                url=url,
                                error_code=ErrorCode.URL_NOT_PUBLIC.value,
                                message=f"重定向目标不安全（未发起请求）: {exc}",
                                final_url=nxt,
                                fetched_at=datetime.now(UTC),
                            )
                        current = nxt
                        continue

                    if resp.status_code >= 400:
                        return FetchResult(
                            ok=False,
                            url=url,
                            status_code=resp.status_code,
                            error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                            message=f"HTTP {resp.status_code}",
                            final_url=str(resp.url),
                            fetched_at=datetime.now(UTC),
                        )

                    content = resp.content
                    if len(content) > self.settings.sources.max_html_bytes:
                        return FetchResult(
                            ok=False,
                            url=url,
                            status_code=resp.status_code,
                            error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                            message="响应体超过大小限制",
                            fetched_at=datetime.now(UTC),
                        )
                    text = content.decode(resp.charset or "utf-8", errors="replace")
                    return FetchResult(
                        ok=True,
                        url=url,
                        status_code=resp.status_code,
                        content_type=resp.headers.get("content-type"),
                        text=text,
                        content_hash=content_hash_of_html(text),
                        final_url=current,
                        fetched_at=datetime.now(UTC),
                    )
                return FetchResult(
                    ok=False,
                    url=url,
                    error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                    message="重定向次数过多",
                    final_url=current,
                    fetched_at=datetime.now(UTC),
                )
        except Exception as exc:
            return FetchResult(
                ok=False,
                url=url,
                error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                message=str(exc),
                fetched_at=datetime.now(UTC),
            )

    def parse(self, text: str, *, url: str) -> list[ParsedSignal]:
        soup = BeautifulSoup(text, "html.parser")
        (soup.title.string or "").strip() if soup.title and soup.title.string else url
        signals: list[ParsedSignal] = []
        for a in soup.find_all("a", href=True)[:200]:
            label = a.get_text(" ", strip=True)
            if not label or len(label) < 8:
                continue
            if any(k in label for k in ("元", "BUG", "错价", "神价", "特价", "促销", "甩尾")):
                signals.append(
                    ParsedSignal(
                        title=label[:200],
                        raw_claim_text=label,
                        url=a["href"] if a["href"].startswith("http") else url,
                        confidence="low",
                    )
                )
            if len(signals) >= 50:
                break
        return signals


async def polite_delay(seconds: float) -> None:
    await asyncio.sleep(seconds)
