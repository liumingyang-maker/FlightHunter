"""第八轮：生产解析 / 风险继承 / 去重。"""

from __future__ import annotations

from app.adapters.base import ParsedSignal
from app.adapters.html_fetcher import parse_deal_label
from app.core.ids import new_id
from app.models import FareDeal, Source
from app.services.discovery.service import materialize_fare_signals, materialize_trip_offer


def test_html_parse_extracts_iata_and_price():
    sig = parse_deal_label("特价机票 CKG NRT 999元", page_url="https://example.org/deal1")
    assert sig is not None
    assert sig.origin_airport == "CKG"
    assert sig.destination_airport == "NRT"
    assert sig.reported_total == 999.0


def test_hidden_city_risk_on_deal(db):
    src = Source(
        id=new_id(),
        name="community",
        base_url="https://example.org/",
        kind="community",
        module="fare",
        status="active",
    )
    db.add(src)
    db.flush()
    sigs = materialize_fare_signals(
        db,
        src,
        [
            ParsedSignal(
                title="甩尾票 PVG LHR",
                raw_claim_text="甩尾 PVG LHR",
                url="https://example.org/s1",
                origin_airport="PVG",
                destination_airport="LHR",
                deal_types=["hidden_city"],
                confidence="low",
            )
        ],
    )
    db.commit()
    assert sigs
    deal = db.get(FareDeal, sigs[0].deal_id)
    assert deal is not None
    assert "hidden_city" in (deal.offer_subtypes or "")
    assert deal.risk_tier == "high_risk"


def test_trip_offer_dedupe_and_source_id(db):
    src = Source(
        id=new_id(),
        name="trip-src",
        base_url="https://example.org/",
        kind="community",
        module="trip",
        status="active",
    )
    db.add(src)
    db.flush()
    p = ParsedSignal(
        title="大阪折扣券",
        raw_claim_text="x",
        url="https://example.org/o1",
        reported_total=100,
        confidence="low",
    )
    o1 = materialize_trip_offer(db, src, p, country_code="JP")
    o2 = materialize_trip_offer(db, src, p, country_code="JP")
    db.commit()
    assert o1 is not None and o2 is not None
    assert o1.id == o2.id
    assert o1.source_id == src.id
    assert o1.official_url is None
