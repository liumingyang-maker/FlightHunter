"""P1 出发地/国际航线过滤与情报模式。"""

from __future__ import annotations

from app.services.airports.china import (
    expand_origin_selection,
    is_china_mainland_airport,
    is_hk_mo_airport,
    is_international_pair,
    match_signal_origins,
)
from app.services.fare.intel import classify_signal


def test_hkg_mfm_not_in_mainland_set():
    assert not is_china_mainland_airport("HKG")
    assert not is_china_mainland_airport("MFM")
    assert is_hk_mo_airport("HKG")
    assert is_hk_mo_airport("MFM")
    assert is_china_mainland_airport("CKG")
    assert is_china_mainland_airport("TFU")


def test_expand_mainland_all_excludes_hkg_mfm():
    codes = expand_origin_selection(china_mainland_all=True)
    assert "CKG" in codes
    assert "HKG" not in codes
    assert "MFM" not in codes
    codes2 = expand_origin_selection(china_mainland_all=True, include_hkg=True, include_mfm=True)
    assert "HKG" in codes2 and "MFM" in codes2 and "CKG" in codes2


def test_international_pair_rules():
    assert is_international_pair("CKG", "NRT") is True
    assert is_international_pair("CKG", "SHA") is False  # 纯国内
    assert is_international_pair("HKG", "ICN") is True
    assert is_international_pair("HKG", "MFM") is False
    assert is_international_pair("CKG", None) is None


def test_match_signal_domestic_excluded():
    m = match_signal_origins("SHA", ["CKG", "TFU"], signal_dest="PEK", require_international=True)
    assert m["match"] is False
    m2 = match_signal_origins("CKG", ["CKG", "TFU"], signal_dest="ICN", require_international=True)
    assert m2["match"] is True


def test_bug_fare_classification():
    from app.models.fare import FareDealSignal

    s = FareDealSignal(
        id="x",
        deal_id="y",
        title="错价",
        raw_claim_text="",
        deal_types='["error_fare"]',
        source_type="community",
    )
    assert classify_signal(s) == "suspected_bug_fare"
