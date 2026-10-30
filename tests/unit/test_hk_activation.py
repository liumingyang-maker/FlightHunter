"""港澳出发与错价边界。"""

from __future__ import annotations

from app.adapters.html_fetcher import parse_deal_label
from app.services.fare.channels import origin_region, route_channels
from app.services.fare.intel import extract_origin_iatas_from_title


def test_peach_hk_title_parses_with_hkd():
    label = "Peach大阪機票優惠！來回連稅預計約HK$1,600起、連20kg行李約HK$2,150起"
    sig = parse_deal_label(label, page_url="https://flynext.hk/blog/x")
    assert sig is not None
    # 两种不同的行李方案价格未结构化区分时，不应任取一个当统一票价。
    assert sig.reported_total is None


def test_hk_origin_in_title():
    assert "HKG" in extract_origin_iatas_from_title("香港往返大阪 Peach 機票優惠")


def test_shanghai_to_hk_not_hk_origin():
    region = origin_region({"title": "上海→香港 促销", "origin_airport": "PVG"})
    assert region != "hk_mo"


def test_hk_airline_from_shanghai_not_hk_channel():
    chans = route_channels(
        {
            "title": "香港航空上海出发促销",
            "origin_airport": "PVG",
            "deal_types": "[]",
            "city_match_level": "explicit_city",
        },
        ["CKG", "TFU", "PVG"],
    )
    assert "hk_mo" not in chans


def test_hk_to_osaka_is_hk_mo():
    chans = route_channels(
        {
            "title": "香港→大阪 Peach 來回",
            "origin_airport": "HKG",
            "deal_types": "[]",
            "city_match_level": "explicit_city",
        },
        ["HKG", "CKG"],
    )
    assert "hk_mo" in chans
    assert "my_origin" in chans
