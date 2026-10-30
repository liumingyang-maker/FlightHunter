"""四频道路由与边界。"""

from __future__ import annotations

from app.services.fare.channels import filter_for_channel, is_error_fare_item, route_channels


def _item(**kw):
    base = {
        "title": "",
        "origin_airport": None,
        "destination_airport": None,
        "deal_types": "[]",
        "city_match_level": "origin_unknown",
        "signal_id": "s1",
        "source_url": "https://example.org/a",
        "reported_total": None,
    }
    base.update(kw)
    return base


def test_ckg_explicit_goes_my_origin_not_only_error():
    it = _item(title="成都→东京 国航促销", origin_airport="TFU", destination_airport="NRT", city_match_level="explicit_city")
    chans = route_channels(it, ["CKG", "TFU", "CTU"])
    assert "my_origin" in chans
    assert "global_error" not in chans


def test_us_bug_fare_only_global_error():
    it = _item(title="NYC-LAX mistake fare business class", origin_airport="JFK", destination_airport="LAX", deal_types='["error_fare"]', city_match_level="origin_unknown")
    chans = route_channels(it, ["CKG", "TFU"])
    assert "global_error" in chans
    assert "my_origin" not in chans
    assert "china_mainland" not in chans


def test_national_promo_not_explicit_and_not_hk():
    it = _item(title="全国多地-日本东京机票促销", city_match_level="national_multi_city_pending")
    routed = filter_for_channel([it], "my_origin", ["CKG", "TFU"], include_pending_in_fold=True)
    assert routed["folded_count"] == 1
    assert routed["primary_count"] == 0
    routed2 = filter_for_channel([it], "china_mainland", ["CKG"])
    assert routed2["primary_count"] == 1


def test_hkg_independent():
    it = _item(title="香港快运 东京促销", origin_airport="HKG", city_match_level="explicit_city")
    chans = route_channels(it, ["CKG", "TFU", "HKG"])
    assert "hk_mo" in chans
    routed = filter_for_channel([it], "china_mainland", expand_mainland())
    assert all("HKG" not in (x.get("origin_airport") or "") for x in routed["primary"])


def expand_mainland():
    from app.services.airports.china import expand_origin_selection

    return expand_origin_selection(china_mainland_all=True)


def test_error_detect():
    assert is_error_fare_item(_item(title="Bug fare to Europe", deal_types="[]"))
    assert is_error_fare_item(_item(title="x", deal_types='["error_fare"]'))
