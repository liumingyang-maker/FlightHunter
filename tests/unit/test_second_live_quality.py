"""第二轮实机验收回归：观测、分类、去重。"""

from __future__ import annotations

from app.adapters.html_fetcher import parse_deal_label, parse_raffle_label
from app.services.discovery.service import _normalize_offer_url


def test_expired_fare_rejected():
    assert parse_deal_label("航司大促：建议收藏！飞猪双11当天特价机票价格表 必看促销 过期", page_url="https://x") is None


def test_yen_price_parsed():
    sig = parse_deal_label("每日机票推荐：含元旦！泰国机票 ¥ 399", page_url="https://x")
    assert sig is not None
    assert sig.reported_total == 399


def test_cash_vehicle_not_flight():
    cash = parse_raffle_label("Ford Motor Company $60,000 Verified Cash Sweepstakes", page_url="https://x")
    assert cash is not None
    assert "prize_other" in cash.deal_types
    boat = parse_raffle_label("Win a $65,000 Fishing Boat Sweepstakes", page_url="https://x")
    assert boat is not None
    assert "prize_other" in boat.deal_types


def test_flight_still_classified():
    sig = parse_raffle_label("Win a free trip to Hawaii with flights", page_url="https://x")
    assert sig is not None
    assert "flight_giveaway" in sig.deal_types or "travel_package_unknown_air" in sig.deal_types


def test_offer_url_normalize():
    a = _normalize_offer_url("https://www.Timeout.com/tokyo/museums/best-free-museums-in-tokyo?utm=1#x")
    b = _normalize_offer_url("http://timeout.com/tokyo/museums/best-free-museums-in-tokyo")
    assert a == b
