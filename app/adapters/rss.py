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
        feed = feedparser.parse(text)
        out: list[ParsedSignal] = []
        for entry in feed.entries[:100]:
            published = None
            if getattr(entry, "published_parsed", None):
                from datetime import datetime

                published = datetime(*entry.published_parsed[:6], tzinfo=UTC)
            body = getattr(entry, "summary", "") or getattr(entry, "title", "")
            out.append(
                ParsedSignal(
                    title=getattr(entry, "title", "") or url,
                    raw_claim_text=body,
                    url=getattr(entry, "link", url),
                    published_at=published,
                    confidence="medium",
                )
            )
        return out
