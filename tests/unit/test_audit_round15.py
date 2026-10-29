"""十五轮集成：卡包加密读写。"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.core.ids import new_id
from app.models import WalletItem
from app.services.benefits.service import (
    load_wallet_private_code,
    save_wallet_private_code,
)


def test_wallet_persist_roundtrip(db, tmp_path: Path):
    s = Settings()
    s.project_root = str(tmp_path)
    item = WalletItem(
        id=new_id(),
        offer_id=new_id(),
        state="claimed",
        official_url="https://example.org",
    )
    db.add(item)
    db.flush()
    save_wallet_private_code(db, s, wallet_item_id=item.id, plaintext_code="CODE-XYZ")
    db.commit()
    assert "CODE-XYZ" not in (item.private_code_encrypted or "")
    assert load_wallet_private_code(db, s, item.id) == "CODE-XYZ"
