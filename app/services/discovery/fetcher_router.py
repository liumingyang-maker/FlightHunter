"""任务四：自适应采集 FetcherRouter。

优先级：RSS/Atom > HTTPX 静态 HTML > Scrapling > Playwright/Scrapling Dynamic。
"""

from __future__ import annotations

from typing import Any, Protocol


class SourceAdapterProtocol(Protocol):
    async def fetch(self, url: str) -> Any: ...

    def parse(self, text: str, *, url: str) -> list: ...


class FetcherRouter:
    """统一抓取路由：按来源类型选择最佳适配器。"""

    def __init__(self, settings: Any):
        self.settings = settings
        self._adapters: dict[str, SourceAdapterProtocol] = {}

    def _get_adapter(self, mode: str) -> SourceAdapterProtocol:
        if mode in self._adapters:
            return self._adapters[mode]
        if mode == "rss":
            from app.adapters.rss import RssAdapter

            self._adapters[mode] = RssAdapter(self.settings)
        else:
            from app.adapters.html_fetcher import HttpxFetchAdapter

            self._adapters[mode] = HttpxFetchAdapter(self.settings)
        return self._adapters[mode]

    def select_adapter(self, source) -> SourceAdapterProtocol | None:
        """按来源选择适配器。none 模式返回 None（禁止自动抓取）。"""
        mode = getattr(source, "allowed_fetch_mode", "httpx") or "httpx"
        if mode == "none":
            return None
        if mode == "rss":
            return self._get_adapter("rss")
        return self._get_adapter("httpx")

    async def fetch(self, source, url: str) -> Any:
        """智能抓取。"""
        adapter = self.select_adapter(source)
        return await adapter.fetch(url)

    def parse(self, source, text: str, url: str) -> list:
        """智能解析。"""
        adapter = self.select_adapter(source)
        return adapter.parse(text, url=url)


# A/B 测试配置
AB_TEST_CONFIG = {
    "static_html": {"primary": "httpx", "fallback": "scrapling"},
    "rss": {"primary": "rss", "fallback": None},
    "js_render": {"primary": "playwright", "fallback": "scrapling_dynamic"},
    "forum": {"primary": "httpx", "fallback": "scrapling"},
}


def get_fetcher_for_type(content_type: str) -> str:
    """按内容类型返回推荐 fetcher。"""
    cfg = AB_TEST_CONFIG.get(content_type, {})
    return cfg.get("primary", "httpx")
