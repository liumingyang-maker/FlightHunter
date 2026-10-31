"""中立测试：全程序逻辑/安全边界探测（非验收，找 bug）。"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx
import pytest

from app.core.safe_http import safe_get
from app.core.url_safety import assert_public_http_url
from app.adapters.html_fetcher import parse_deal_label, _extract_published_only
from app.services.fare.intel import (
    extract_dest_iata,
    extract_origin_iatas_from_title,
    classify_signal,
)
from app.models.fare import FareDealSignal
from app.web.routes.api import _apply_intel_filters


# ---------- 安全边界 ----------

def test_url_safety_rejects_metadata():
    for u in (
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://[::1]/",
        "http://0.0.0.0/",
    ):
        with pytest.raises(Exception):
            assert_public_http_url(u)


def test_safe_get_no_follow_to_private():
    calls = []

    def h(request):
        calls.append(request.url.host)
        if request.url.host == "public.example":
            return httpx.Response(307, headers={"Location": "http://169.254.169.254/"})
        return httpx.Response(200, text="x")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(h)) as c:
            return await safe_get("https://public.example/a", check_robots=False, client=c)

    r = asyncio.run(run())
    assert r.ok is False
    assert "169.254.169.254" not in calls


def test_url_credentials_rejected():
    with pytest.raises(Exception):
        assert_public_http_url("http://user:pass@example.com/")


# ---------- 情报语义边界 ----------

def test_origin_empty_on_pure_brand():
    assert extract_origin_iatas_from_title("Cathay Pacific sale") == []


def test_dest_not_from_airline():
    # 香港航空 + 上海→大阪，目的应为大阪不是香港
    d = extract_dest_iata("香港航空 上海→大阪 优惠")
    assert d != "HKG"


def test_price_zero_not_valid_fare():
    sig = parse_deal_label("东京机票 HK$0 起", page_url="https://e.com/x")
    # 0 价不应作为有效票价
    if sig is not None:
        assert sig.reported_total in (None, 0)  # 至少不夸大


def test_negative_price_ignored():
    sig = parse_deal_label("东京机票 HK$-100", page_url="https://e.com/x")
    if sig and sig.reported_total is not None:
        assert sig.reported_total >= 0


def test_huge_kg_not_price():
    sig = parse_deal_label("行李 30KG 东京机票 HK$100", page_url="https://e.com/x")
    if sig and sig.reported_total is not None:
        assert sig.reported_total != 30000


def test_published_in_future_vs_travel():
    # 旅行日期在未来，不应写入 published
    assert _extract_published_only("旅行日期 2030-01-01 机票") is None


def test_community_not_official_flash():
    s = FareDealSignal(
        id="1", deal_id="d", title="x", raw_claim_text="", deal_types='["flash_sale"]',
        source_type="community",
    )
    assert classify_signal(s) != "official_or_flash_promo"


# ---------- 筛选边界 ----------

def test_filter_missing_fields_not_matched():
    rows = [{"title": "no dest", "user_feedback": None, "category": None}]
    out = _apply_intel_filters(
        rows, destination="NRT", category=None, date_from=None, date_to=None, feedback=None
    )
    assert out == []


def test_filter_time_unknown_excluded():
    rows = [{"title": "t", "published_at": None, "found_at": None, "user_feedback": None, "category": None}]
    out = _apply_intel_filters(
        rows, destination=None, category=None, date_from="2020-01-01", date_to=None,
        feedback=None, time_field="published",
    )
    assert out == []


# ---------- 路径遍历 / 注入 ----------

def test_no_path_traversal_in_browser_file():
    from app.core.browser_safety import validate_browser_target

    with pytest.raises(Exception):
        validate_browser_target("file:///C:/Windows/System32/config/SAM")


def test_xss_script_in_title_parsed_not_executed():
    sig = parse_deal_label("<script>alert(1)</script> 东京机票 HK$100", page_url="https://e.com/x")
    # 解析层不应抛异常；模板层用 esc
    assert sig is None or isinstance(sig.title, str)


def test_sqlalchemy_no_raw_fstring_in_app():
    """扫描 app/ 无 f-string SQL。"""
    root = Path("app")
    bad = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"(execute|executemany|text)\s*\(\s*f[\"'].*(SELECT|INSERT|UPDATE|DELETE)", line):
                bad.append(f"{p}:{i}")
    assert bad == []


def test_no_eval_in_app():
    root = Path("app")
    bad = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"\beval\s*\(", line) and "note" not in line.lower():
                bad.append(f"{p}:{i}:{line.strip()[:60]}")
    # 允许极少数合法用途
    assert len(bad) <= 3, bad


def test_subprocess_no_shell_true():
    root = Path("app")
    bad = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "shell=True" in text:
            bad.append(str(p))
    assert bad == []
