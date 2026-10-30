"""P2 core_recommend 正向三态 + 页面分栏。"""

from __future__ import annotations

from app.services.raffle.core_recommend import evaluate_core_recommend


def test_positive_requires_all():
    r = evaluate_core_recommend(
        title="中国内地出发国际免费机票抽奖",
        evidence_text="from Mainland China departures",
        prize_is_flight=True,
        official_url="https://official.example/event",
        verify_status="verified",
    )
    assert r["core_recommend"] is True
    assert r["china_outbound"] == "confirmed_mainland_outbound"


def test_candidate_never_core():
    r = evaluate_core_recommend(
        title="中国内地出发国际免费机票抽奖",
        prize_is_flight=True,
        official_url="https://official.example/e",
        verify_status="candidate",
    )
    assert r["core_recommend"] is False


def test_domestic_never_core():
    r = evaluate_core_recommend(
        title="中国内地国内航班免费机票抽奖",
        evidence_text="中国内地出发",
        prize_is_flight=True,
        official_url="https://o.example/e",
        verify_status="verified",
    )
    assert r["core_recommend"] is False
    assert r["china_outbound"] == "excluded_or_domestic"


def test_excluded_never_core():
    r = evaluate_core_recommend(
        title="不包括中国大陆出发的国际免费机票抽奖",
        prize_is_flight=True,
        official_url="https://o.example/e",
        verify_status="verified",
    )
    assert r["core_recommend"] is False
    assert r["china_outbound"] == "excluded_or_domestic"


def test_missing_official_url():
    r = evaluate_core_recommend(
        title="中国内地出发 国际机票抽奖",
        prize_is_flight=True,
        official_url=None,
        verify_status="verified",
    )
    assert r["core_recommend"] is False
    assert r["china_outbound"] == "unknown_origin_pending"


def test_no_positive_text():
    r = evaluate_core_recommend(
        title="International flight giveaway",
        prize_is_flight=True,
        official_url="https://o.example/e",
        verify_status="verified",
    )
    assert r["core_recommend"] is False
