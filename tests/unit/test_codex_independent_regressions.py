"""Behavioral regressions found in the independent review of 58eed2b."""

from datetime import UTC, date, datetime

from app.adapters.html_fetcher import HttpxFetchAdapter, parse_deal_label
from app.config import Settings
from app.models import FareDeal, FareDealSignal
from app.services.fare.intel import IntelFilter, build_intel_view, extract_origin_iatas_from_title
from app.web.routes.api import _apply_intel_filters


def test_airline_brand_does_not_imply_hong_kong_departure():
    assert "HKG" not in extract_origin_iatas_from_title("Cathay flight SIN to JFK sale")
    assert "HKG" not in extract_origin_iatas_from_title("国泰航空纽约飞伦敦机票优惠")


def test_multiple_yuan_prices_do_not_become_one_destination_price():
    signal = parse_deal_label(
        "香港出发 台湾 ¥800 · 大阪 ¥1500 机票优惠", page_url="https://example.com/deal"
    )
    assert signal is not None
    assert signal.reported_total is None
    assert signal.currency is None


def test_multiple_yuan_suffix_prices_do_not_become_one_destination_price():
    signal = parse_deal_label(
        "香港出发 台北机票800元 大阪机票1500元 促销", page_url="https://example.com/deal"
    )
    assert signal is not None
    assert signal.reported_total is None
    assert signal.currency is None


def test_single_hk_dollar_fare_with_explicit_origin_and_destination():
    signal = parse_deal_label("香港→大阪机票 HK$1,600", page_url="https://example.com/deal")
    assert signal is not None
    assert signal.reported_total == 1600
    assert signal.currency == "HKD"


def test_html_normal_parse_preserves_explicit_publication_date():
    adapter = HttpxFetchAdapter(Settings())
    rows = adapter.parse(
        '<a href="/deal">香港出发大阪机票 HK$1600 發佈日期 · 2026年10月29日</a>',
        url="https://example.com/",
    )
    assert len(rows) == 1
    assert rows[0].published_at is not None
    assert rows[0].published_at.date() == date(2026, 10, 29)


def test_travel_date_filter_uses_actual_deal_window(db):
    now = datetime.now(UTC)
    deal = FareDeal(
        id="deal-travel", dedup_key="travel-test", origin="HKG", destination="KIX",
        travel_window_start=date(2027, 1, 1), travel_window_end=date(2027, 1, 31),
        first_seen_utc=now, last_seen_utc=now,
    )
    db.add(deal)
    db.flush()
    db.add(FareDealSignal(
        id="signal-travel", deal_id=deal.id, title="香港→大阪机票促销",
        origin_airport="HKG", destination_airport="KIX", deal_types='["flash_sale"]',
    ))
    db.flush()
    rows = build_intel_view(db, IntelFilter(preferred_origins=["HKG"]), limit=20)
    selected = _apply_intel_filters(
        rows, destination=None, category=None, date_from="2027-01-15", date_to="2027-01-20",
        feedback=None, time_field="travel",
    )
    assert [row["signal_id"] for row in selected] == ["signal-travel"]


def test_network_backend_connects_only_to_validated_address(monkeypatch):
    import asyncio

    from app.core import safe_http

    backend_class = getattr(safe_http, "PublicAddressBackend", None)
    assert backend_class is not None, "production connections need an address-validating backend"

    calls = []

    class FakeBackend:
        async def connect_tcp(self, **kwargs):
            calls.append(kwargs["host"])
            return "stream"

    monkeypatch.setattr(
        "app.core.safe_http.resolve_and_assert_public_host", lambda host: ["93.184.216.34"]
    )
    backend = backend_class(FakeBackend())
    result = asyncio.run(backend.connect_tcp("example.com", 443))
    assert result == "stream"
    assert calls == ["93.184.216.34"]


def test_network_backend_never_connects_when_dns_validation_fails(monkeypatch):
    import asyncio

    import pytest
    from app.core import safe_http

    backend_class = getattr(safe_http, "PublicAddressBackend", None)
    assert backend_class is not None, "production connections need an address-validating backend"

    calls = []

    class FakeBackend:
        async def connect_tcp(self, **kwargs):
            calls.append(kwargs["host"])

    def reject(host):
        raise ValueError("private address")

    monkeypatch.setattr("app.core.safe_http.resolve_and_assert_public_host", reject)
    with pytest.raises(Exception) as excinfo:
        asyncio.run(backend_class(FakeBackend()).connect_tcp("example.com", 443))
    # DNS 校验失败必须 fail-closed，不得连接
    assert "private address" in str(excinfo.value) or "address validation" in str(excinfo.value)
    assert not getattr(FakeBackend, "called", False)
    assert calls == []


def test_html_adapter_installs_public_address_transport(monkeypatch):
    import asyncio

    import httpx
    from app.core.safe_http import PublicAddressBackend

    captured = {}
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="ok")))

    def make_client(**kwargs):
        captured.update(kwargs)
        return client

    monkeypatch.setattr("app.adapters.html_fetcher.httpx.AsyncClient", make_client)
    monkeypatch.setattr("app.adapters.html_fetcher.resolve_and_assert_public_host", lambda host: ["8.8.8.8"])
    settings = Settings()
    settings.sources.obey_robots_and_site_terms = False
    result = asyncio.run(HttpxFetchAdapter(settings).fetch("https://example.com/"))
    assert result.ok
    assert isinstance(captured["transport"]._pool._network_backend, PublicAddressBackend)


def test_safe_get_installs_public_address_transport(monkeypatch):
    import asyncio

    import httpx
    from app.core.safe_http import PublicAddressBackend, safe_get

    captured = {}
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="ok")))

    def make_client(**kwargs):
        captured.update(kwargs)
        return client

    monkeypatch.setattr("app.core.safe_http.httpx.AsyncClient", make_client)
    monkeypatch.setattr("app.core.safe_http.resolve_and_assert_public_host", lambda host: ["8.8.8.8"])
    result = asyncio.run(safe_get("https://example.com/", check_robots=False))
    assert result.ok
    assert isinstance(captured["transport"]._pool._network_backend, PublicAddressBackend)


def test_shared_carrier_grade_nat_is_not_a_public_destination():
    import ipaddress

    from app.core.url_safety import _blocked_ip

    assert _blocked_ip(ipaddress.ip_address("100.64.0.1"))
    assert not _blocked_ip(ipaddress.ip_address("8.8.8.8"))


def test_unknown_automation_policy_requires_manual_entry():
    from app.models import CampaignRound, Profile
    from app.services.browser.prefill import build_prefill_plan

    round_ = CampaignRound(
        title="Candidate", official_url="https://example.com/event", automation_policy="unknown"
    )
    plan = build_prefill_plan(round_, Profile(display_name="Test User"))
    assert plan.mode == "MANUAL_ONLY"


def test_synthetic_eligibility_does_not_invent_an_age_requirement():
    from app.services.raffle.multi_round import EventRoundRules, eligibility_with_synthetic_profile

    rules = EventRoundRules(
        round_label="r", edition_key="e", title="flight", purchase_required=False,
        residency_restriction="non-korean citizens who do not reside in korea",
    )
    for age in (17, 30):
        result = eligibility_with_synthetic_profile(rules, nationality="CN", residence="CN", age=age)
        assert result["state"] == "unknown"
        assert next(check for check in result["checks"] if check["code"] == "AGE")["outcome"] == "unknown"


def test_auto_time_filter_uses_publication_not_travel_hint():
    rows = [{
        "signal_id": "a", "published_at": "2026-10-29T00:00:00",
        "found_at": "2026-10-30T00:00:00", "travel_date_hint": "2027-01-15",
    }]
    selected = _apply_intel_filters(
        rows, destination=None, category=None, date_from="2026-10-01", date_to="2026-10-31",
        feedback=None, time_field="auto",
    )
    assert len(selected) == 1


def test_web_start_does_not_create_tables_in_an_unversioned_existing_db(tmp_path, monkeypatch):
    import sqlite3

    from app.config import StorageConfig
    from app.web.app import create_app

    db_path = tmp_path / "existing.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE legacy_data (value TEXT)")
    settings = Settings(storage=StorageConfig(sqlite_path=str(db_path)))
    monkeypatch.setattr("app.web.app.ensure_runtime_secrets", lambda settings: None)
    create_app(settings)
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"legacy_data"}


def test_html_adapter_stops_reading_when_response_exceeds_limit(monkeypatch):
    import asyncio

    import httpx

    chunks = []

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(4):
                chunks.append(100)
                yield b"x" * 100

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Body())))
    monkeypatch.setattr("app.adapters.html_fetcher.httpx.AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr("app.adapters.html_fetcher.resolve_and_assert_public_host", lambda host: ["8.8.8.8"])
    settings = Settings()
    settings.sources.max_html_bytes = 100
    settings.sources.obey_robots_and_site_terms = False
    result = asyncio.run(HttpxFetchAdapter(settings).fetch("https://example.com/"))
    assert not result.ok
    assert sum(chunks) < 400


def test_html_adapter_fails_closed_on_oversized_robots(monkeypatch):
    import asyncio

    import httpx

    calls = []
    chunks = []

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(4):
                chunks.append(100_000)
                yield b"x" * 100_000

    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, stream=Body())

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr("app.adapters.html_fetcher.httpx.AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr("app.adapters.html_fetcher.resolve_and_assert_public_host", lambda host: ["8.8.8.8"])
    result = asyncio.run(HttpxFetchAdapter(Settings()).fetch("https://example.com/page"))
    assert not result.ok
    assert calls == ["/robots.txt"]
    assert sum(chunks) < 400_000
