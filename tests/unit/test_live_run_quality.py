"""首轮实机测试暴露的解析/汇报缺陷回归。"""

from __future__ import annotations

from app.adapters.html_fetcher import parse_deal_label, parse_raffle_label


def test_raffle_nav_category_labels_rejected():
    nav = [
        "Contest Archives",
        "Contest Tips",
        "Add a Sweepstakes",
        "Blog Giveaways",
        "Odd Entry Contests",
        "Monthly Entry Contests",
        "Weekly Entry Contests",
        "Daily Entry Contests",
        "Single Entry Contests",
        "Monthly Sweepstakes",
        "Weekly Sweepstakes",
        "Daily Sweepstakes",
        "Contestgirl",
    ]
    for label in nav:
        assert parse_raffle_label(label, page_url="https://www.contestgirl.com/x") is None, label


def test_raffle_realish_titles_still_pass():
    sig = parse_raffle_label(
        "Win a free trip to Hawaii for two",
        page_url="https://example.org/contest/1",
    )
    assert sig is not None
    assert "trip" in sig.deal_types or "travel_package_unknown_air" in sig.deal_types


def test_deal_howto_noise_rejected_without_price():
    noise = [
        "怎么买机票更便宜❓我来手把手教你🔥",
        "国外机票怎么买—",
        "去哪儿国外机票维权实录（成功版）",
        "怎么买国外机票？",
        "国外机票查询|",
        "订上海飞香港机票哪个平台靠谱？2026去哪儿机票出行保障指南",
        "国外机票预订平台→",
        "国外机票哪里订最省钱？飞国外的机票在哪买最划算？",
        "国外机票购买平台，买国际机票下载哪个app",
        "Get这6个机票潜规则，轻松搞定低价机票！",
    ]
    for label in noise:
        assert parse_deal_label(label, page_url="https://www.smzdm.com/a") is None, label


def test_deal_with_price_or_airports_still_pass():
    with_price = parse_deal_label("去曼谷机票爆降！连带普吉新低价，299元起", page_url="https://x/1")
    assert with_price is not None
    assert with_price.reported_total == 299
    with_iata = parse_deal_label("特价机票 CKG NRT 999元", page_url="https://x/2")
    assert with_iata is not None
    assert with_iata.origin_airport == "CKG"
    assert with_iata.destination_airport == "NRT"
