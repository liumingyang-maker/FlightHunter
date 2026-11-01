"""R1-R5 主链路回归：run_discovery→Router→Adapter→Cache→Parser→DB。

反例约定：若只测辅助函数返回值、或断言恒真，不算覆盖。
每条测试必须走业务入口，并给出「坏结果」应被拒绝的证据。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.adapters.base import FetchResult, ParsedSignal, SourceAdapter
from app.config import Settings
from app.core.ids import new_id
from app.models import ArticleCache, FareDealSignal, Source
from app.services.discovery.incremental import should_fetch
from app.services.discovery.service import fetch_source, materialize_fare_signals
from sqlalchemy import select


class _EtagAdapter(SourceAdapter):
    name = "etag-fake"

    def __init__(self, results: list[FetchResult], seen_headers: list[dict | None]):
        self._results = results
        self._seen = seen_headers

    async def fetch(self, url: str, headers=None) -> FetchResult:
        self._seen.append(headers)
        if not self._results:
            raise AssertionError("adapter exhausted — unexpected extra fetch")
        return self._results.pop(0)

    def parse(self, text: str, *, url: str) -> list[ParsedSignal]:
        return []


def _fare_source(db, url: str = "https://deals.example.org/list") -> Source:
    src = Source(
        id=new_id(),
        name="etag-source",
        base_url=url,
        kind="community",
        module="fare",
        status="active",
        allowed_fetch_mode="httpx",
        access_policy="public_fetch",
        fetch_interval_hours=1,
    )
    db.add(src)
    db.flush()
    return src


def test_r1_adapter_returns_etag_on_success_path(monkeypatch):
    """R1 反例：成功 200 必须带回 ETag；异常分支不得引用 resp。"""
    from app.adapters.html_fetcher import HttpxFetchAdapter

    adapter = HttpxFetchAdapter(Settings())

    class Ok:
        status_code = 200
        headers = {"etag": '"abc123"', "last-modified": "Wed, 01 Oct 2026 00:00:00 GMT"}
        content = b"<html><a href='/d1'>deal</a></html>"
        url = "https://example.org/list"

        async def aiter_bytes(self):
            yield self.content

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url, **kwargs):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def response():
                if url.endswith("/robots.txt"):
                    r = Ok()
                    r.headers = {}
                    r.content = b"User-agent: *\nAllow: /\n"
                    yield r
                else:
                    yield Ok()

            return response()

    monkeypatch.setattr("app.adapters.html_fetcher.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(
        "app.adapters.html_fetcher.resolve_and_assert_public_host",
        lambda host: host,
    )
    result = asyncio.run(adapter.fetch("https://example.org/list"))
    assert result.ok is True
    assert result.status_code == 200
    assert result.etag == '"abc123"'
    assert result.last_modified == "Wed, 01 Oct 2026 00:00:00 GMT"


def test_r1_adapter_returns_304_without_body(monkeypatch):
    """R1：304 应返回 status_code=304 且 ok，不当 4xx 失败。"""
    from app.adapters.html_fetcher import HttpxFetchAdapter

    adapter = HttpxFetchAdapter(Settings())

    class NotModified:
        status_code = 304
        headers = {"etag": '"abc123"'}
        content = b""
        url = "https://example.org/list"

        async def aiter_bytes(self):
            yield b""

    class Ok:
        status_code = 200
        headers = {}
        content = b"User-agent: *\nAllow: /\n"

        async def aiter_bytes(self):
            yield self.content

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url, **kwargs):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def response():
                if url.endswith("/robots.txt"):
                    yield Ok()
                else:
                    yield NotModified()

            return response()

    monkeypatch.setattr("app.adapters.html_fetcher.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(
        "app.adapters.html_fetcher.resolve_and_assert_public_host",
        lambda host: host,
    )
    result = asyncio.run(adapter.fetch("https://example.org/list"))
    assert result.status_code == 304
    assert result.ok is True
    assert result.etag == '"abc123"'


def test_r1_fetch_source_saves_etag_and_sends_if_none_match(db, settings, monkeypatch):
    """主链路：200 存 ETag → 第二次 should_fetch 带 If-None-Match → 304 记 not_modified。"""
    html = (
        "<html><body>"
        "<a href='https://deals.example.org/d1'>特价机票 CKG NRT 999元 2026年10月29日</a>"
        "</body></html>"
    )
    adapter = _EtagAdapter(
        results=[
            FetchResult(
                ok=True,
                url="https://deals.example.org/list",
                status_code=200,
                text=html,
                content_hash="h1",
                final_url="https://deals.example.org/list",
                etag='"v1"',
            ),
            FetchResult(
                ok=True,
                url="https://deals.example.org/list",
                status_code=304,
                final_url="https://deals.example.org/list",
                etag='"v1"',
            ),
        ],
        seen_headers=[],
    )
    monkeypatch.setattr(
        "app.services.discovery.fetcher_router.FetcherRouter.select_adapter",
        lambda self, source: adapter,
    )
    src = _fare_source(db)

    r1 = asyncio.run(fetch_source(db, settings, src, module="fare", persist_signals=False))
    db.commit()
    assert r1["status"] in ("ok_zero", "ok_existing", "ok_valuable") or r1.get("business_status")
    assert src.etag == '"v1"'
    assert src.consecutive_failures == 0

    # 清冷却：把 last_attempt 拉回过去，保留 etag
    src.last_attempt_at = datetime.now(UTC) - timedelta(hours=5)
    db.commit()

    ok, headers = should_fetch(src, datetime.now(UTC))
    assert ok is True
    assert headers.get("If-None-Match") == '"v1"'

    r2 = asyncio.run(fetch_source(db, settings, src, module="fare", persist_signals=False))
    db.commit()
    assert r2["status"] == "not_modified"
    assert src.last_result == "not_modified"
    assert src.consecutive_failures == 0
    assert src.last_success_at is not None


def test_r1_304_is_not_treated_as_failure(db, settings, monkeypatch):
    """R4/R1：304 不得抬高 consecutive_failures，也不得 last_result=failed。"""
    adapter = _EtagAdapter(
        results=[
            FetchResult(
                ok=True,
                url="https://deals.example.org/list",
                status_code=304,
                final_url="https://deals.example.org/list",
                etag='"v9"',
            )
        ],
        seen_headers=[],
    )
    monkeypatch.setattr(
        "app.services.discovery.fetcher_router.FetcherRouter.select_adapter",
        lambda self, source: adapter,
    )
    src = _fare_source(db)
    src.consecutive_failures = 0
    db.commit()

    r = asyncio.run(fetch_source(db, settings, src, module="fare", persist_signals=False))
    db.commit()
    assert r["status"] == "not_modified"
    assert src.consecutive_failures == 0
    assert src.last_result != "failed"


def test_r2_first_insert_writes_article_cache(db):
    """R2 反例：首次新增信号必须写 ArticleCache；只建 signal 不够。"""
    from app.models import FareDealSignal

    src = _fare_source(db)
    sig = ParsedSignal(
        title="特价机票 CKG NRT 999元",
        raw_claim_text="特价机票 CKG NRT 999元",
        url="https://deals.example.org/d1",
        reported_total=999,
        currency="CNY",
        origin_airport="CKG",
        destination_airport="NRT",
        confidence="low",
        published_at=datetime(2026, 10, 29, tzinfo=UTC),
    )
    created = materialize_fare_signals(db, src, [sig], candidate_url=src.base_url)
    db.commit()
    assert len(created) == 1
    caches = db.scalars(select(ArticleCache).where(ArticleCache.source_id == src.id)).all()
    assert len(caches) == 1
    assert caches[0].content_hash
    assert len(caches[0].content_hash) == 64  # sha256 hex
    # 反例：没有缓存 → 后续同内容无法跳过
    sigs = db.scalars(select(FareDealSignal)).all()
    assert len(sigs) == 1


def test_r2_repeat_same_content_skips_duplicate_signal(db):
    """R2：同内容二次 materialize 不得新增第二条 signal。"""
    src = _fare_source(db)
    sig = ParsedSignal(
        title="特价机票 CKG NRT 999元",
        raw_claim_text="特价机票 CKG NRT 999元",
        url="https://deals.example.org/d1",
        reported_total=999,
        currency="CNY",
        origin_airport="CKG",
        destination_airport="NRT",
        confidence="low",
        published_at=datetime(2026, 10, 29, tzinfo=UTC),
    )
    materialize_fare_signals(db, src, [sig])
    db.commit()
    again = materialize_fare_signals(
        db,
        src,
        [
            ParsedSignal(
                title="特价机票 CKG NRT 999元",
                raw_claim_text="特价机票 CKG NRT 999元",
                url="https://deals.example.org/d1",
                reported_total=999,
                currency="CNY",
                origin_airport="CKG",
                destination_airport="NRT",
                confidence="low",
            )
        ],
    )
    db.commit()
    assert again == []
    sigs = db.scalars(select(FareDealSignal)).all()
    assert len(sigs) == 1


def test_r3_withdrawn_clears_reported_price(db):
    """R3：正文出现撤回关键词 → 清空 reported_total，不得保留旧价。"""
    src = _fare_source(db)
    first = ParsedSignal(
        title="特价机票 CKG NRT 999元",
        raw_claim_text="特价机票 CKG NRT 999元",
        url="https://deals.example.org/d1",
        reported_total=999,
        currency="CNY",
        origin_airport="CKG",
        destination_airport="NRT",
        confidence="low",
        published_at=datetime(2026, 10, 29, tzinfo=UTC),
    )
    materialize_fare_signals(db, src, [first])
    db.commit()
    withdrawn = ParsedSignal(
        title="特价机票 CKG NRT 999元",
        raw_claim_text="特价机票已撤回，原 999 元不再可用 withdrawn",
        url="https://deals.example.org/d1",
        reported_total=None,
        origin_airport="CKG",
        destination_airport="NRT",
        confidence="low",
        published_at=datetime(2026, 10, 29, tzinfo=UTC),
    )
    materialize_fare_signals(db, src, [withdrawn])
    db.commit()
    sig = db.scalars(select(FareDealSignal)).one()
    # 反例：若仍报 999，等于把已撤回价格继续当现货
    assert sig.reported_total is None
    assert sig.currency is None
    assert "撤回" in (sig.raw_claim_text or "")


def test_r3_updated_at_not_treated_as_published():
    """R3/PC-05：「更新于」不得当作发布日期。"""
    from app.services.fare.freshness import extract_published_from_html

    html = '<html><head><meta name="x" content="y"></head><body>更新于 2026年10月1日</body></html>'
    assert extract_published_from_html(html) is None

    html2 = '<html><head><meta property="article:published_time" content="2026-10-20"></head></html>'
    got = extract_published_from_html(html2)
    assert got is not None
    assert got.date() == datetime(2026, 10, 20).date()


def test_r4_failure_increments_once_on_main_chain(db, settings, monkeypatch):
    """R4 反例：失败只在 fetch_source 主路径 +1；ingest 不得再 +1。"""
    adapter = _EtagAdapter(
        results=[
            FetchResult(
                ok=False,
                url="https://deals.example.org/list",
                status_code=503,
                error_code="SOURCE_UNAVAILABLE",
                message="HTTP 503",
            )
        ],
        seen_headers=[],
    )
    monkeypatch.setattr(
        "app.services.discovery.fetcher_router.FetcherRouter.select_adapter",
        lambda self, source: adapter,
    )
    src = _fare_source(db)
    src.consecutive_failures = 0
    db.commit()

    r = asyncio.run(fetch_source(db, settings, src, module="fare", persist_signals=False))
    db.commit()
    assert r.get("status") == "failed" or src.last_result == "failed"
    # 只加一次：若 ingest +1 且主路径再 +1 会得到 2
    assert src.consecutive_failures == 1


def test_r4_backoff_uses_fail_count(db):
    """R4：失败后 should_fetch 应按退避窗口拒绝，而非固定间隔。"""
    src = _fare_source(db)
    src.fetch_interval_hours = 1
    src.consecutive_failures = 2
    src.last_result = "failed"
    src.last_attempt_at = datetime.now(UTC) - timedelta(hours=2)
    db.commit()
    # backoff = 1 * 2^2 = 4h → 2h 前的失败仍在退避
    ok, _ = should_fetch(src, datetime.now(UTC))
    assert ok is False

    src.last_attempt_at = datetime.now(UTC) - timedelta(hours=5)
    db.commit()
    ok2, _ = should_fetch(src, datetime.now(UTC))
    assert ok2 is True
