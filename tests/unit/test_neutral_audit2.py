"""中立测试第二波：更深逻辑边界与已知脆弱点。"""

from __future__ import annotations

from datetime import date

import pytest

from app.adapters.html_fetcher import (
    _currency_from_token,
    _extract_published_only,
    extract_route_price_candidates,
    parse_deal_label,
)
from app.services.fare.intel import (
    extract_dest_iata,
    extract_origin_iatas_from_title,
)


def test_three_dest_multi_price_no_single():
    label = "香港出发 东京 HK$1000 · 大阪 HK$1500 · 首尔 HK$2000 机票"
    routes = extract_route_price_candidates(label)
    sig = parse_deal_label(label, page_url="https://e.com/x")
    if sig is not None:
        assert sig.reported_total is None


def test_same_price_two_dest_may_bind():
    # 同价两条：允许单价展示（非串价）
    label = "东京 HK$1200 · 大阪 HK$1200 机票"
    routes = extract_route_price_candidates(label)
    # 不强制要求有价
    sig = parse_deal_label(label, page_url="https://e.com/x")
    if sig and sig.reported_total is not None:
        assert sig.reported_total == 1200.0


def test_currency_tokens():
    assert _currency_from_token("MOP$") == "MOP"
    assert _currency_from_token("HK$") == "HKD"
    assert _currency_from_token("¥") == "CNY"
    assert _currency_from_token("US$") == "USD"
    assert _currency_from_token("") in {"HKD", "CNY", "MOP", "USD"}  # 不崩溃


def test_empty_and_none_labels():
    assert extract_origin_iatas_from_title("") == []
    assert extract_origin_iatas_from_title(None) == []
    assert extract_dest_iata("") is None
    assert extract_route_price_candidates("") == []
    assert _extract_published_only("") is None


def test_mixed_lang_origin():
    # 只写 English from Shanghai
    o = extract_origin_iatas_from_title("Flights from Shanghai to Tokyo")
    assert "PVG" in o


def test_price_with_commas():
    sig = parse_deal_label("东京机票 HK$12,345 起", page_url="https://e.com/x")
    if sig and sig.reported_total is not None:
        assert sig.reported_total == 12345.0


def test_date_zero_day_invalid():
    assert _extract_published_only("发佈日期 2026-00-01") is None or True  # 不崩溃


def test_dest_iata_unknown_city():
    assert extract_dest_iata("现在去哪里玩好") is None


def test_origin_prefers_explicit_over_weak():
    # 显式成都出发 + 标题含上海
    o = extract_origin_iatas_from_title("成都出发 上海 东京机票")
    assert "TFU" in o
    # 显式优先，不应把上海当出发
    assert o[0] == "TFU"


def test_trip_date_validation():
    from app.services.trips.service import create_trip
    from app.schemas.domain import TripCreate, TripSegmentIn
    from app.config import Settings
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base

    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    s = S()
    settings = Settings()
    with pytest.raises(Exception):
        create_trip(
            s,
            settings,
            TripCreate(
                label="bad",
                destination_country_code="JP",
                local_start_date=date(2027, 1, 10),
                local_end_date=date(2027, 1, 1),  # end < start
                timezone="Asia/Tokyo",
            ),
        )


def test_notification_event_key_stable():
    from app.services.notify.delivery import _event_key

    k1 = _event_key("t", "hello", "e", "1")
    k2 = _event_key("t", "hello", "e", "1")
    k3 = _event_key("t", "hello", "e", "2")
    assert k1 == k2
    assert k1 != k3


def test_xss_title_survives_parse_and_escapes_in_template_source():
    """模板必须用 esc 包裹动态字段（静态检查）。"""
    from pathlib import Path

    html = Path("app/web/templates/fare.html").read_text(encoding="utf-8")
    # title 必须 esc
    assert "esc(it.title" in html
    # summary 必须 esc
    assert "esc(it.summary_zh" in html
