"""十五轮集成：卡包加密读写。"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.core.ids import new_id
from app.schemas.domain import BenefitOfferCreate
from app.services.benefits.service import (
    create_benefit_offer,
    load_wallet_private_code,
    save_wallet_private_code,
)


def test_wallet_persist_roundtrip(db, tmp_path: Path):
    s = Settings()
    s.project_root = str(tmp_path)
    offer = create_benefit_offer(
        db,
        BenefitOfferCreate(
            organizer_name="店",
            title="加密券",
            category="shopping_discount",
            official_url="https://example.org/o",
            country_codes=["JP"],
            date_certainty="unconfirmed",
        ),
    )
    db.flush()
    from app.services.benefits.service import ensure_wallet_saved

    item = ensure_wallet_saved(db, offer, None)
    db.commit()
    save_wallet_private_code(db, s, wallet_item_id=item.id, plaintext_code="CODE-XYZ")
    db.commit()
    assert "CODE-XYZ" not in (item.private_code_encrypted or "")
    assert load_wallet_private_code(db, s, item.id) == "CODE-XYZ"
