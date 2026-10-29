"""RSS/Atom 适配器。"""

from __future__ import annotations

from datetime import UTC

import feedparser

from app.adapters.base import FetchResult, ParsedSignal, SourceAdapter
from app.adapters.html_fetcher import HttpxFetchAdapter
from app.config import Settings


class RssAdapter(SourceAdapter):
    name = "rss"

    def __init__(self, settings: Settings) -> None:
        self._http = HttpxFetchAdapter(settings)

    async def fetch(self, url: str) -> FetchResult:
        return await self._http.fetch(url)

    def parse(self, text: str, *, url: str) -> list[ParsedSignal]:
        """机票/通用：全部条目（保守低置信）。"""
        return self._parse_entries(text, url=url, trip_only=False)

    def parse_trip(self, text: str, *, url: str) -> list[ParsedSignal]:
        """行程福利：仅保留旅游/券/活动语义，过滤普通财经新闻。"""
        return self._parse_entries(text, url=url, trip_only=True)

    def _parse_entries(self, text: str, *, url: str, trip_only: bool) -> list[ParsedSignal]:
        from app.adapters.html_fetcher import parse_trip_label

        feed = feedparser.parse(text)
        out: list[ParsedSignal] = []
        for entry in feed.entries[:100]:
            title = getattr(entry, "title", "") or ""
            body = getattr(entry, "summary", "") or title
            published = None
            if getattr(entry, "published_parsed", None):
                from datetime import datetime

                published = datetime(*entry.published_parsed[:6], tzinfo=UTC)
            link = getattr(entry, "link", url)
            if trip_only:
                sig = parse_trip_label(f"{title} {body}"[:200], page_url=link)
                if sig is None:
                    continue
                sig.title = title[:200] or sig.title
                sig.published_at = published
                sig.url = link
                sig.confidence = "low"
                out.append(sig)
            else:
                out.append(
                    ParsedSignal(
                        title=title or url,
                        raw_claim_text=body,
                        url=link,
                        published_at=published,
                        confidence="medium",
                    )
                )
        return out
