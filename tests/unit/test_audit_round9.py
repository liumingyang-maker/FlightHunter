"""第九轮：相对链接、分类、国家归属。"""

from __future__ import annotations

import json
from datetime import date

from app.adapters.base import ParsedSignal
from app.adapters.html_fetcher import parse_deal_label, parse_trip_label
from app.config import Settings
from app.core.ids import new_id
from app.models import Source
from app.schemas.domain import TripCreate
from app.services.discovery.service import materialize_trip_offer
from app.services.trips.service import create_trip, rematch_trip_benefits


def test_relative_href_joined():
    from app.adapters.html_fetcher import HttpxFetchAdapter
    from app.config import Settings

    adapter = HttpxFetchAdapter(Settings())
    html = "<html><body><a href='/deals/42'>特价机票 CKG NRT 999元</a></body></html>"
    sigs = adapter.parse(html, url="https://example.org/list/")
    assert sigs
    assert sigs[0].url == "https://example.org/deals/42"


def test_meal_coupon_not_airfare():
    sig = parse_deal_label("餐饮满100元减20元", page_url="https://example.org/x")
    assert sig is None


def test_festival_parses_as_trip_not_null():
    sig = parse_trip_label("免费秋日祭典", page_url="https://example.org/f")
    assert sig is not None
    assert sig.reported_total is None


def test_geo_unknown_not_wallet(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="us",
            destination_country_code="US",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="America/New_York",
            demo_only=True,
        ),
    )
    src = Source(
        id=new_id(),
        name="s",
        base_url="https://example.org/",
        kind="community",
        module="trip",
        status="active",
    )
    db.add(src)
    db.flush()
    offer = materialize_trip_offer(
        db,
        src,
        ParsedSignal(title="大阪餐饮券", raw_claim_text="x", confidence="low"),
        country_code=None,
    )
    db.flush()
    matches = rematch_trip_benefits(db, trip)
    db.commit()
    m = next(x for x in matches if x.offer_id == offer.id)
    reasons = json.loads(m.reason_codes or "[]")
    assert "GEO_COUNTRY_UNKNOWN" in reasons
    assert m.match_category != "wallet"
    assert m.state != "usable"
