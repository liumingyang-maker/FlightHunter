"""Benefit / 领券 / 卡包测试。"""

from __future__ import annotations

from datetime import date

import pytest
from app.config import Settings
from app.core.errors import BenefitClaimOutcomeUnknown, ErrorCode, FlightHunterError
from app.models import WalletItem
from app.schemas.domain import BenefitClaimStart, BenefitOfferCreate, TripCreate
from app.services.benefits.service import (
    confirm_claimed,
    create_benefit_offer,
    generate_guide,
    mark_claim_unknown,
    start_benefit_claim,
)
from app.services.trips.service import create_trip
from sqlalchemy import select


def _offer(db, **kwargs):
    payload = BenefitOfferCreate(
        organizer_name=kwargs.get("organizer_name", "演示商家"),
        title=kwargs.get("title", "免费领取券"),
        category="shopping_discount",
        claim_method=kwargs.get("claim_method", "ACCOUNT_CLAIM"),
        official_url="https://example.org/coupon",
        country_codes=["JP"],
        date_certainty=kwargs.get("date_certainty", "unconfirmed"),
        conditions=kwargs.get("conditions", {}),
        demo_only=True,
    )
    return create_benefit_offer(db, payload)


def test_public_display_goes_to_wallet_saved_not_claimed(db):
    offer = _offer(db, claim_method="PUBLIC_DISPLAY", title="展示券")
    db.flush()
    claim = start_benefit_claim(db, BenefitClaimStart(offer_id=offer.id))
    db.commit()
    assert claim.status == "available"
    item = db.scalar(select(WalletItem).where(WalletItem.offer_id == offer.id))
    assert item is not None
    assert item.state == "saved"


def test_unknown_claim_blocks_retry(db):
    offer = _offer(db)
    db.flush()
    claim = start_benefit_claim(db, BenefitClaimStart(offer_id=offer.id))
    db.commit()
    mark_claim_unknown(db, claim.id)
    db.commit()
    with pytest.raises(BenefitClaimOutcomeUnknown):
        start_benefit_claim(db, BenefitClaimStart(offer_id=offer.id))


def test_confirm_requires_receipt(db):
    offer = _offer(db)
    db.flush()
    claim = start_benefit_claim(db, BenefitClaimStart(offer_id=offer.id))
    db.commit()
    with pytest.raises(FlightHunterError) as ei:
        confirm_claimed(db, claim.id)
    assert ei.value.code == ErrorCode.RECEIPT_NOT_VERIFIED

    confirm_claimed(db, claim.id, receipt_reference="OFFICIAL-123")
    db.commit()
    refreshed = db.get(type(claim), claim.id)
    assert refreshed.status == "claimed"


def test_paid_offer_blocked(db):
    offer = _offer(db, conditions={"requires_payment": True}, title="付费券")
    db.flush()
    with pytest.raises(FlightHunterError) as ei:
        start_benefit_claim(db, BenefitClaimStart(offer_id=offer.id))
    assert ei.value.code == ErrorCode.BENEFIT_PAYMENT_REQUIRED


def test_guide_lists_unknown_fields(db):
    offer = _offer(db, title="指南券")
    db.flush()
    guide = generate_guide(db, offer.id)
    db.commit()
    assert guide.stale is False
    assert guide.language == "zh-CN"


def test_unconfirmed_dates_stay_maybe(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="待公布优惠行程",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=True,
        ),
    )
    offer = _offer(db, date_certainty="historical_reference", title="往年参考券")
    db.flush()
    from app.services.trips.service import rematch_trip_benefits

    matches = rematch_trip_benefits(db, trip)
    m = next(x for x in matches if x.offer_id == offer.id)
    assert m.state == "maybe_usable"
    assert "BENEFIT_DATES_UNCONFIRMED" in m.reason_codes
