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
        """机票/通用：仅保留机票语义条目，避免财经新闻直接入库。"""
        return self._parse_entries(text, url=url, trip_only=False)

    def parse_trip(self, text: str, *, url: str) -> list[ParsedSignal]:
        return self._parse_entries(text, url=url, trip_only=True)

    def _parse_entries(self, text: str, *, url: str, trip_only: bool) -> list[ParsedSignal]:
        from app.adapters.html_fetcher import parse_deal_label, parse_trip_label

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
            combo = f"{title} {body}"[:300]
            if trip_only:
                sig = parse_trip_label(combo, page_url=link)
                if sig is None:
                    continue
                sig.title = title[:200] or sig.title
                sig.published_at = published
                sig.url = link
                sig.confidence = "low"
                out.append(sig)
            else:
                sig = parse_deal_label(combo, page_url=link)
                if sig is None:
                    continue
                sig.title = title[:200] or sig.title
                sig.published_at = published
                sig.url = link
                out.append(sig)
        return out
