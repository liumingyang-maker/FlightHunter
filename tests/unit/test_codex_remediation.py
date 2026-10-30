"""Codex 缺陷整改回归：D-001~D-012 关键路径。"""

from __future__ import annotations

from datetime import date

from app.adapters.html_fetcher import parse_deal_label
from app.config import Settings
from app.schemas.domain import TripCreate, TripUpdate
from app.services.fare.channels import filter_for_channel
from app.services.fare.intel import extract_origin_iatas_from_title
from app.services.trips.service import create_trip, update_trip


def test_d003_hk_airline_shanghai_not_hkg():
    origins = extract_origin_iatas_from_title("香港航空上海出发机票促销")
    assert "PVG" in origins
    assert "HKG" not in origins


def test_d003_hk_express_hk_not_pek():
    origins = extract_origin_iatas_from_title("HK Express 13週年優惠！台灣來回連稅HK$800、日本東京大阪HK$1,500起 北京")
    # 品牌本身不能证明出发地；无明确出发信息时保持未知。
    assert "HKG" not in origins
    assert "PEK" not in origins


def test_d005_discount_not_price():
    sig = parse_deal_label(
        "國泰×渣打11.11機票優惠！來回最高減11%、額外賺3,000里數 HK$800",
        page_url="https://flynext.hk/x",
    )
    if sig is not None:
        assert sig.reported_total != 800.0


def test_d006_uppercase_kg_not_price():
    sig = parse_deal_label("香港→大阪機票 連20KG行李", page_url="https://x")
    assert sig is None or sig.reported_total != 20000.0


def test_d004_global_error_no_default_pref():
    # 空偏好下全球错价可见
    routed = filter_for_channel(
        [
            {
                "title": "JFK LHR mistake fare business",
                "origin_airport": "JFK",
                "destination_airport": "LHR",
                "deal_types": '["error_fare"]',
                "city_match_level": "origin_unknown",
                "signal_id": "s1",
                "source_url": "https://x/e",
            }
        ],
        "global_error",
        [],
    )
    assert routed["primary_count"] == 1


def test_d010_unknown_origin_not_core():
    # 标签逻辑：unknown 不得当核心 — 单测 channels 不设 core；此处验证推荐过滤依赖 open+eligible
    from app.services.fare.channels import route_channels

    chans = route_channels(
        {
            "title": "free flight giveaway unknown origin",
            "origin_airport": None,
            "deal_types": '["flight_giveaway"]',
            "city_match_level": "origin_unknown",
        },
        ["CKG"],
    )
    assert "my_origin" not in chans  # 无明确匹配机场


def test_d001_edit_unconfirmed_does_not_enable_scans(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="未确认",
            destination_country_code="JP",
            local_start_date=date(2027, 6, 1),
            local_end_date=date(2027, 6, 10),
            timezone="Asia/Tokyo",
            demo_only=False,
            confirmed=False,
        ),
    )
    db.commit()
    assert trip.scan_registered is False
    update_trip(db, settings, trip.id, TripUpdate(label="改名后"))
    db.commit()
    from app.core.timeutils import utc_now
    from app.models import TripScanSubscription
    from app.scheduler.jobs import claim_due_subscriptions
    from sqlalchemy import select

    subs = db.scalars(
        select(TripScanSubscription).where(TripScanSubscription.trip_id == trip.id)
    ).all()
    # 允许存在订阅对象但必须 disabled 或被调度器跳过
    ready = claim_due_subscriptions(db, now=utc_now())
    assert all(s.trip_id != trip.id for s in ready)
    for s in subs:
        if s.enabled:
            # 若曾被错误 enable，调度器也不得取出
            assert trip.id not in {x.trip_id for x in ready}
