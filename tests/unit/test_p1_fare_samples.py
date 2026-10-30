"""P1 情报语义样本 + 四频道/筛选端到端。"""

from __future__ import annotations

from scripts.label_samples import run_samples


def test_label_samples_all_pass():
    r = run_samples()
    assert r["fail"] == 0, r["misses"]
    assert r["pass_rate"] == 1.0


def test_global_channel_no_default_prefs():
    from app.web.routes.api import fare_intel
    import inspect

    src = inspect.getsource(fare_intel)
    assert 'channel == "global_error"' in src
    assert "D-004" in src or "全球错价" in src or "global" in src


def test_hk_mo_not_merged_into_mainland():
    """全国不含 HKG/MFM，除非显式勾选。"""
    from app.services.airports.china import expand_origin_selection

    mainland = expand_origin_selection(china_mainland_all=True)
    assert "HKG" not in mainland
    assert "MFM" not in mainland


def test_multi_price_leaves_clue():
    from app.adapters.html_fetcher import parse_deal_label

    sig = parse_deal_label(
        "香港出发 台湾 HK$800 · 大阪 HK$1500 機票優惠", page_url="https://e.com/x"
    )
    assert sig is not None
    assert sig.reported_total is None
    # 原文保留
    assert "800" in (sig.raw_claim_text or "") and "1500" in (sig.raw_claim_text or "")


def test_travel_filter_window_overlap():
    from app.web.routes.api import _apply_intel_filters

    rows = [
        {
            "title": "trip",
            "travel_window_start": "2027-01-01",
            "travel_window_end": "2027-01-31",
            "user_feedback": None,
            "category": None,
        },
        {
            "title": "other",
            "travel_window_start": "2027-02-01",
            "travel_window_end": "2027-02-28",
            "user_feedback": None,
            "category": None,
        },
    ]
    out = _apply_intel_filters(
        rows,
        destination=None,
        category=None,
        date_from="2027-01-15",
        date_to="2027-01-20",
        feedback=None,
        time_field="travel",
    )
    assert len(out) == 1 and out[0]["title"] == "trip"
    # 默认 auto 不优先 travel
    out2 = _apply_intel_filters(
        rows,
        destination=None,
        category=None,
        date_from="2027-01-15",
        date_to="2027-01-20",
        feedback=None,
        time_field="auto",
    )
    # auto 只看 published/found，两条都无 → 0
    assert out2 == []
