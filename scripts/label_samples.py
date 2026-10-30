"""P1 标注样本集：出发/目的/金额/币种/发布/旅行 误命中与漏报统计。"""

from __future__ import annotations

from app.adapters.html_fetcher import (
    _currency_from_token,
    _extract_published_only,
    extract_route_price_candidates,
    parse_deal_label,
)
from app.services.fare.intel import classify_signal, extract_dest_iata, extract_origin_iatas_from_title

# (label, expect_origins, expect_dest, expect_price, expect_currency, expect_published, note)
SAMPLES: list[dict] = [
    # --- 负例：不得串价 / 不得误判出发 ---
    {
        "label": "上海→香港 机票促销",
        "origins": ["PVG"],
        "forbid_origins": ["HKG"],
        "note": "N-003 出发=上海",
    },
    {
        "label": "Peach 大阪→首尔 低价",
        "origins": [],
        "forbid_origins": ["HKG"],
        "note": "N-003 Peach 不映射 HKG",
    },
    {
        "label": "Cathay flight SIN to JFK",
        "origins": [],
        "forbid_origins": ["HKG"],
        "note": "品牌不证明出发",
    },
    {
        "label": "国泰航空纽约飞伦敦",
        "origins": [],
        "forbid_origins": ["HKG"],
        "note": "品牌不证明出发",
    },
    {
        "label": "香港航空 上海出发 优惠",
        "origins": ["PVG"],
        "note": "显式出发优先",
    },
    {
        "label": "香港出发 台湾 HK$800 · 大阪 HK$1500 機票優惠",
        "price": None,
        "forbid_price": [800.0, 1500.0],
        "note": "R-004 多金额不写单一票价",
    },
    {
        "label": "台湾 ¥800 大阪 ¥1500 机票",
        "price": None,
        "note": "多人民币价不合并",
    },
    {
        "label": "台北 800元 大阪 1500元 机票",
        "price": None,
        "note": "多元价不合并",
    },
    {
        "label": "香港大阪機票立省HK$800",
        "price": None,
        "note": "立省≠票价",
    },
    {
        "label": "最多減HK$500 東京机票",
        "price": None,
        "note": "最多減≠票价",
    },
    {
        "label": "机票活动 2025年1月2日 机票优惠",
        "published": None,
        "note": "R-006 裸日期非发布",
    },
    {
        "label": "更新日期 2025年1月2日 特价机票",
        "published": None,
        "note": "更新≠发布",
    },
    {
        "label": "旅行日期 2027年2月3日 机票",
        "published": None,
        "note": "旅行≠发布",
    },
    # --- 正例：应正确解析 ---
    {
        "label": "大阪 MOP$1500 機票優惠",
        "price": 1500.0,
        "currency": "MOP",
        "note": "R-005 MOP",
    },
    {
        "label": "香港→大阪 HK$1,600 机票",
        "price": 1600.0,
        "currency": "HKD",
        "note": "单航线 HK$",
    },
    {
        "label": "發佈日期·2026-10-29 机票优惠",
        "published": "2026-10-29",
        "note": "R-006 明确发布",
    },
    {
        "label": "published: 2026/10/28 sale",
        "published": "2026-10-28",
        "note": "英文发布",
    },
    {
        "label": "20KG 行李 机票促销 香港出发",
        "forbid_price": [20000.0],
        "note": "D-006 20KG",
    },
    {
        "label": "HKG-KIX 机票特惠 HK$800",
        "origins": ["HKG"],
        "price": 800.0,
        "currency": "HKD",
        "note": "IATA 对",
    },
    {
        "label": "香港出发 大阪機票 HK$1500 起",
        "price": 1500.0,
        "currency": "HKD",
        "note": "单目的地",
    },
]


def _iso(dt) -> str | None:
    return dt.isoformat()[:10] if dt else None


def run_samples() -> dict:
    hits = []
    misses = []
    for s in SAMPLES:
        label = s["label"]
        problems = []
        origins = extract_origin_iatas_from_title(label)
        for o in s.get("origins", []) or []:
            if o not in origins:
                problems.append(f"origin_missing:{o}")
        for o in s.get("forbid_origins", []) or []:
            if o in origins:
                problems.append(f"origin_forbidden_hit:{o}")
        dest = extract_dest_iata(label)
        if "dest" in s and dest != s["dest"]:
            problems.append(f"dest:{dest}!={s['dest']}")
        sig = parse_deal_label(label, page_url="https://example.com/x")
        price = sig.reported_total if sig else None
        cur = sig.currency if sig else None
        if "price" in s:
            if s["price"] is None:
                if price is not None:
                    problems.append(f"price_should_be_none:{price}")
            elif price != s["price"]:
                problems.append(f"price:{price}!={s['price']}")
        for fp in s.get("forbid_price", []) or []:
            if price == fp:
                problems.append(f"price_forbidden:{fp}")
        if "currency" in s and cur != s["currency"]:
            problems.append(f"currency:{cur}!={s['currency']}")
        pub = _extract_published_only(label)
        if "published" in s:
            exp = s["published"]
            if exp is None and pub is not None:
                problems.append(f"published_should_be_none:{pub}")
            elif exp is not None and _iso(pub) != exp:
                problems.append(f"published:{_iso(pub)}!={exp}")
        rec = {"label": label, "note": s.get("note", ""), "problems": problems, "origins": origins, "price": price, "currency": cur}
        if problems:
            misses.append(rec)
        else:
            hits.append(rec)
    return {
        "total": len(SAMPLES),
        "pass": len(hits),
        "fail": len(misses),
        "misses": misses,
        "pass_rate": round(len(hits) / max(len(SAMPLES), 1), 3),
    }


if __name__ == "__main__":
    r = run_samples()
    print(f"pass {r['pass']}/{r['total']} rate={r['pass_rate']}")
    for m in r["misses"]:
        print("FAIL", m["label"], m["problems"])
    if r["fail"]:
        raise SystemExit(1)
    print("ALL_PASS")
