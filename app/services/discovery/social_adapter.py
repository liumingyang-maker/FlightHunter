"""任务五：社交论坛数据契约 SocialSourceAdapter。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SocialPost:
    """社交帖子统一契约。"""

    platform: str  # reddit | bluesky | mastodon | flyertalk | kezhan | weibo | xiaohongshu
    author: str = ""
    post_id: str = ""
    published_at: str = ""  # ISO
    original_url: str = ""
    content_summary: str = ""
    # 机票语义
    route: str = ""  # e.g. "HKG-KIX"
    currency: str = ""
    price: float | None = None
    deal_conditions: str = ""
    # 来源可信
    source_trust: str = "unknown"  # verified | community | unknown
    is_bug_fare: bool = False
    is_fuel_dump: bool = False
    last_edited_at: str = ""
    # 增量同步
    cursor: str = ""
    sync_status: str = "pending"  # pending | synced | error


@dataclass
class SocialSourceConfig:
    """社交来源配置。"""

    platform: str
    base_url: str
    adapter_mode: str = "httpx"  # httpx | rss | api
    requires_auth: bool = False
    rate_limit_seconds: int = 60
    enabled: bool = True
    notes: str = ""


# 合法公开来源候选
SOCIAL_SOURCES = [
    SocialSourceConfig(
        platform="reddit",
        base_url="https://www.reddit.com/r/travel.json",
        adapter_mode="httpx",
        requires_auth=False,
        rate_limit_seconds=60,
        notes="公开 JSON API；遵守 robots",
    ),
    SocialSourceConfig(
        platform="flyertalk",
        base_url="https://www.flyertalk.com/forum/mileage-run-deals/",
        adapter_mode="httpx",
        requires_auth=False,
        rate_limit_seconds=120,
        notes="公开论坛；需尊重 robots",
    ),
    SocialSourceConfig(
        platform="mastodon",
        base_url="https://mastodon.social/api/v1/timelines/public",
        adapter_mode="httpx",
        requires_auth=False,
        rate_limit_seconds=60,
        notes="公开时间线；API 限速",
    ),
    SocialSourceConfig(
        platform="bluesky",
        base_url="https://bsky.social/xrpc/app.bsky.feed.getTimeline",
        adapter_mode="httpx",
        requires_auth=True,
        rate_limit_seconds=60,
        notes="需要授权；候选",
    ),
]


def parse_social_post(data: dict) -> SocialPost:
    """从原始数据解析社交帖子。"""
    return SocialPost(
        platform=data.get("platform", "unknown"),
        author=data.get("author", ""),
        post_id=data.get("id", ""),
        published_at=data.get("published_at", ""),
        original_url=data.get("url", ""),
        content_summary=(data.get("text", "") or "")[:200],
        route=data.get("route", ""),
        currency=data.get("currency", ""),
        price=data.get("price"),
        deal_conditions=data.get("conditions", ""),
        source_trust=data.get("trust", "unknown"),
        is_bug_fare=data.get("is_bug", False),
        is_fuel_dump=data.get("is_fuel", False),
        last_edited_at=data.get("edited_at", ""),
    )
