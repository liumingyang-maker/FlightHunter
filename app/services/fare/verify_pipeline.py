"""P0：入库前核实发布日期 + 过滤旧文。"""

from __future__ import annotations

import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone

from app.services.fare.freshness import (
    classify_signal_freshness,
    extract_published_from_html,
    is_list_page,
    is_stale,
    verify_published_date,
)


async def enrich_and_filter_signals(
    fetcher,
    parsed: list,
    *,
    max_age_days: int = 30,
    verify_detail: bool = True,
    max_verify: int = 15,
) -> list:
    """入库前处理：
    1. 列表页信号 → 标 lead（不入正式情报）
    2. 有 URL 的信号 → 抓详情页核实发布日期
    3. 旧文（>30天）→ 标 stale 或丢弃
    4. 无发布日期 → 标 unverified
    """
    out = []
    verified = 0
    for sig in parsed:
        url = getattr(sig, "url", None) or ""
        # 1) 列表页 → 只当线索
        if is_list_page(url):
            sig.confidence = "lead_only"
            out.append(sig)
            continue

        # 2) 核实发布日期
        pub = getattr(sig, "published_at", None)
        if verify_detail and url and verified < max_verify and pub is None:
            pub = await verify_published_date(fetcher, url)
            verified += 1
            if pub:
                sig.published_at = pub

        # 3) 过滤旧文
        if pub and is_stale(pub, max_age_days):
            sig.confidence = "stale"
            out.append(sig)  # 保留但标 stale，让 UI 显示灰色
            continue

        # 4) 无发布日期 → 标 unverified
        if pub is None:
            sig.confidence = "unverified_date"

        out.append(sig)
    return out
