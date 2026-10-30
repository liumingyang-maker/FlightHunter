"""跨来源情报合并。"""

from __future__ import annotations

from app.services.fare.intel import merge_intel_signals


def test_merge_same_route_same_title_keeps_both_urls():
    a = {
        "title": "国航 东京 往返 含税 1999元",
        "origin_airport": "CKG",
        "destination_airport": "NRT",
        "source_url": "https://a.example/1",
        "source_name": "A",
        "found_at": "2026-10-30T00:00:00+00:00",
        "priority": -10,
        "category": "official_or_flash_promo",
    }
    b = {
        "title": "国航 东京往返含税1999元",
        "origin_airport": "CKG",
        "destination_airport": "NRT",
        "source_url": "https://b.example/2",
        "source_name": "B",
        "found_at": "2026-10-30T01:00:00+00:00",
        "priority": 0,
        "category": "community_deal_tip",
    }
    merged = merge_intel_signals([a, b])
    assert len(merged) == 1
    assert merged[0]["is_merged"] is True
    assert set(merged[0]["source_urls"]) == {"https://a.example/1", "https://b.example/2"}


def test_different_routes_not_merged():
    a = {
        "title": "东京特价",
        "origin_airport": "CKG",
        "destination_airport": "NRT",
        "source_url": "https://a/1",
        "source_name": "A",
        "found_at": "2026-10-30",
        "priority": 0,
        "category": "community_deal_tip",
    }
    b = {
        "title": "东京特价",
        "origin_airport": "PVG",
        "destination_airport": "NRT",
        "source_url": "https://b/2",
        "source_name": "B",
        "found_at": "2026-10-30",
        "priority": 0,
        "category": "community_deal_tip",
    }
    assert len(merge_intel_signals([a, b])) == 2
