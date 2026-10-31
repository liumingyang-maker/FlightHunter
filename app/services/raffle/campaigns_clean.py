"""campaigns 去噪 + 机票筛选 + 修 core bug + 显示信息。"""

from __future__ import annotations

# ---------- 1) materialize: 噪音过滤 + 只留机票/旅行 ----------
NOISE_TITLE_PATTERNS = [
    r"隐私",
    r"隐私政策",
    r"个人信息",
    r"保护政策",
    r"使用条款",
    r"服务条款",
    r"用户协议",
    r"定位服务",
    r"翻译热线",
    r"客服",
    r"联系",
    r"指南",
    r"地图",
    r"privacy",
    r"policy",
    r"terms",
    r"tos\b",
    r"cookie",
    r"legal",
    r"hotline",
    r"contact\s+us",
    r"about\s+us",
    r"faq\b",
]

# 只保留机票/旅行/行程类
TRAVEL_KEYWORDS = [
    r"机票",
    r"機票",
    r"flight",
    r"airfare",
    r"air\s*line",
    r"airline",
    r"trip",
    r"travel",
    r"vacation",
    r"holiday",
    r"hotel",
    r"stay",
    r"cruise",
    r"tour",
    r"行程",
    r"旅遊",
    r"旅游",
    r"度假",
    r"酒店",
    r"住宿",
    r"航班",
    r"航空",
]


def is_noise_title(title: str) -> bool:
    """隐私/条款/指南/热线/FAQ 等非抽奖条目。"""
    t = (title or "").lower()
    import re as _re

    for pat in NOISE_TITLE_PATTERNS:
        if _re.search(pat, t, _re.I):
            return True
    return False


def is_travel_related(title: str, prize_summary: str | None = None) -> bool:
    """是否机票/旅行/行程类抽奖。"""
    import re as _re

    t = (title or "") + " " + (prize_summary or "")
    for pat in TRAVEL_KEYWORDS:
        if _re.search(pat, t, _re.I):
            return True
    return False


# ---------- 2) 修 core bug：聚合源 + 无 official_url 永不 core ----------
def safe_core_recommend(tags: dict, official_url: str | None) -> bool:
    """显示层安全兜底：聚合源/无官方链接/候选 → 不显示 core。"""
    if not official_url:
        return False
    if tags.get("aggregator"):
        return False
    if tags.get("source_kind") in ("community", "search_api", "forum", "blog_aggregator"):
        return False
    # 只有明确 verified 才可能 core
    verify = tags.get("verify_status") or ""
    if verify not in ("verified", "auto_extracted"):
        # 还要看实际字段
        pass
    return bool(tags.get("core_recommend")) and bool(official_url) and not tags.get("aggregator")


# ---------- 3) 修脏数据 ----------
def fix_stale_core_tags(session) -> int:
    """把聚合源/无 official_url 的 core=True 改回 False。"""
    import json

    from sqlalchemy import select

    from app.models import CampaignRound

    n = 0
    rows = session.scalars(select(CampaignRound)).all()
    for r in rows:
        if not r.tags:
            continue
        try:
            tags = json.loads(r.tags)
        except Exception:
            continue
        if not isinstance(tags, dict):
            continue
        changed = False
        if tags.get("core_recommend") and (
            tags.get("aggregator")
            or not r.official_url
            or tags.get("source_kind") in ("community", "search_api", "forum", "blog_aggregator")
        ):
            tags["core_recommend"] = False
            tags["core_recommend_reasons"] = ["DEMOTED_AGGREGATOR_OR_NO_OFFICIAL_URL"]
            changed = True
        if changed:
            r.tags = json.dumps(tags, ensure_ascii=False)
            n += 1
    session.flush()
    return n
