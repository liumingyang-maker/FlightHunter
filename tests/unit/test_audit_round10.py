"""第十轮：final_url 链接、卡包分类、满减语义、RSS 福利筛选。"""

from __future__ import annotations

from datetime import date

from app.adapters.html_fetcher import parse_trip_label
from app.config import Settings
from app.schemas.domain import BenefitOfferCreate, TripCreate
from app.services.benefits.service import create_benefit_offer
from app.services.trips.service import create_trip, rematch_trip_benefits


def test_spent_minus_discount_uses_discount_amount():
    sig = parse_trip_label("满100元减20元优惠券", page_url="https://example.org/c")
    assert sig is not None
    assert sig.reported_total == 20.0
    assert "min_spend=100" in sig.raw_claim_text


def test_unconfirmed_not_wallet(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="jp2",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=True,
        ),
    )
    offer = create_benefit_offer(
        db,
        BenefitOfferCreate(
            organizer_name="店",
            title="未确认券",
            category="shopping_discount",
            claim_method="PUBLIC_DISPLAY",
            country_codes=["JP"],
            date_certainty="unconfirmed",
        ),
    )
    db.flush()
    matches = rematch_trip_benefits(db, trip)
    db.commit()
    m = next(x for x in matches if x.offer_id == offer.id)
    assert m.match_category != "wallet"


def test_parse_base_uses_final_url():
    """parse 时传入的 url 应为 final_url；链接相对解析基于该 URL。"""
    from app.adapters.html_fetcher import HttpxFetchAdapter
    from app.config import Settings

    adapter = HttpxFetchAdapter(Settings())
    html = "<a href='/benefit/22'>大阪折扣券</a>"
    # 模拟重定向后的最终页
    sigs = adapter.parse_trip(html, url="https://cdn.example.org/final/page")
    assert sigs
    assert sigs[0].url == "https://cdn.example.org/benefit/22"


def test_rss_trip_filters_news(monkeypatch):

    class FakeEntry(dict):
        def __getattr__(self, k):
            return self.get(k)

    class FakeFeed:
        entries = [
            {"title": "美股收盘快讯", "summary": "市场波动", "link": "https://x/1"},
            {"title": "大阪美食节免费入场", "summary": "祭典", "link": "https://x/2"},
        ]

        def __init__(self):
            for e in self.entries:
                o = type("E", (), e)()
                yield o

    # 用简单结构模拟
    class E:
        def __init__(self, title, summary, link):
            self.title = title
            self.summary = summary
            self.link = link

    class Feed:
        entries = [
            E("美股收盘快讯", "市场波动", "https://x/1"),
            E("大阪美食节免费入场", "祭典优惠", "https://x/2"),
        ]

    monkeypatch.setattr("app.adapters.rss.feedparser.parse", lambda t: Feed())
    from app.adapters.rss import RssAdapter
    from app.config import Settings

    ad = RssAdapter(Settings())
    trips = ad.parse_trip("<rss/>", url="https://example.org/feed")
    assert all("美股" not in s.title for s in trips)
    assert any("祭典" in s.title or "祭典" in s.raw_claim_text for s in trips)
