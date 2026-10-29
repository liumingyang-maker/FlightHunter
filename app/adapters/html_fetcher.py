"""httpx 简单抓取适配器（公开 HTML）。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from urllib import robotparser
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.adapters.base import FetchResult, ParsedSignal, SourceAdapter
from app.config import Settings
from app.core.errors import ErrorCode
from app.core.ids import content_hash_of_html
from app.core.url_safety import assert_public_http_url, safe_redirect_target


class HttpxFetchAdapter(SourceAdapter):
    name = "httpx"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._robots_cache: dict[str, robotparser.RobotFileParser] = {}

    async def _robots_allowed(self, client: httpx.AsyncClient, url: str) -> bool:
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
                else:
                    rp.parse([])
            except Exception:
                rp.parse([])
            self._robots_cache[origin] = rp
        return self._robots_cache[origin].can_fetch("*", url)

    async def fetch(self, url: str) -> FetchResult:
        try:
            assert_public_http_url(url)
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
        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
            max_redirects=self.settings.sources.max_redirects,
        ) as client:
            if not await self._robots_allowed(client, url):
                return FetchResult(
                    ok=False,
                    url=url,
                    error_code=ErrorCode.SOURCE_FETCH_DENIED.value,
                    message="robots.txt 不允许抓取",
                    robots_disallowed=True,
                    fetched_at=datetime.now(UTC),
                )
            try:
                resp = await client.get(url)
            except httpx.HTTPError as exc:
                return FetchResult(
                    ok=False,
                    url=url,
                    error_code=ErrorCode.SOURCE_UNAVAILABLE.value,
                    message=str(exc),
                    fetched_at=datetime.now(UTC),
                )

            try:
                safe_redirect_target(str(resp.url))
            except Exception as exc:
                return FetchResult(
                    ok=False,
                    url=url,
                    error_code=ErrorCode.URL_NOT_PUBLIC.value,
                    message=f"重定向目标不安全: {exc}",
                    final_url=str(resp.url),
                    fetched_at=datetime.now(UTC),
                )

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
                final_url=str(resp.url),
                fetched_at=datetime.now(UTC),
            )

    def parse(self, text: str, *, url: str) -> list[ParsedSignal]:
        """保守解析：仅提取明显的价格线索，识别不出保持 None。"""
        soup = BeautifulSoup(text, "html.parser")
        (soup.title.string or "").strip() if soup.title and soup.title.string else url
        signals: list[ParsedSignal] = []
        # 简单启发：含「元」「特价」「BUG」等的链接
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
