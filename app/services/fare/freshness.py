"""P0：核实原文发布日期 + 过滤旧文 + 列表/详情分离。

核心原则：
- 列表页标题只是「线索」，不是「情报」
- 入库前必须抓详情页核实真实发布日期
- 发布日期 > 30 天 → 标 stale 或丢弃
- 无发布日期 → 不入正式情报（只入 raw 线索）
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# 从详情页 HTML 提取真实发布日期
_DATE_PATTERNS = [
    # JSON-LD datePublished
    r'"datePublished"\s*:\s*"(20\d{2}-\d{2}-\d{2})',
    r'"date_published"\s*:\s*"(20\d{2}-\d{2}-\d{2})',
    # <time datetime="...">
    r'<time[^>]+datetime="(20\d{2}-\d{2}-\d{2})',
    # meta 标签（name 或 property 属性）
    r'<meta[^>]+(?:name|property)="(?:date|pubdate|publish_date|article:published_time|og:published_time)"[^>]+content="(20\d{2}-\d{2}-\d{2})',
    r'<meta[^>]+content="(20\d{2}-\d{2}-\d{2})"[^>]+(?:name|property)="(?:date|pubdate|publish_date|article:published_time|og:published_time)"',
    r'<meta[^>]+(?:name|property)="[^"]*published[^"]*"[^>]+content="(20\d{2}-\d{2}-\d{2})',
    r'<meta[^>]+content="(20\d{2}-\d{2}-\d{2})"[^>]+(?:name|property)="[^"]*published[^"]*"',
    # 中文
    r'(?:發佈日期|发布日期|發佈|发布|更新于)\s*[:：·]?\s*(20\d{2}[-/年]\d{1,2}[-/月]\d{1,2})',
    # 英文
    r'(?:published|posted)\s*[:\s]*(20\d{2}-\d{2}-\d{2})',
    # 宽松日期（放在最后）
    r'(20\d{2}-\d{2}-\d{2})T\d{2}:\d{2}',
]

# 列表页 URL 特征（只当线索，不当情报）
_LIST_URL_PATTERNS = [
    r"/category/",
    r"/fenlei/",
    r"/theme/",
    r"/tag/",
    r"/tags/",
    r"/archive/",
    r"/page/\d+",
    r"/search",
    r"/rss$",
    r"/feed$",
    r"/blog/?$",
    r"/news/?$",
    r"/deals/?$",
    r"/promotions?/?$",
    r"\?.*page=",
]


def extract_published_from_html(html: str) -> datetime | None:
    """从详情页 HTML 提取真实发布日期。"""
    if not html:
        return None
    head = html[:80000]  # 大多数 date meta 在前 80k
    for pat in _DATE_PATTERNS:
        m = re.search(pat, head, re.I)
        if m:
            raw = m.group(1).replace("年", "-").replace("月", "-").replace("日", "")
            try:
                dt = datetime.fromisoformat(raw[:10])
                # 未来日期不合理 → 忽略
                if dt.year > datetime.now(timezone.utc).year + 1:
                    continue
                return dt
            except ValueError:
                continue
    return None


def is_list_page(url: str) -> bool:
    """判断是否列表/聚合页（只当线索，不当情报）。"""
    u = (url or "").lower()
    return any(re.search(p, u) for p in _LIST_URL_PATTERNS)


def is_stale(published: datetime | None, max_age_days: int = 30) -> bool:
    """发布日期超过 N 天 → 旧文。无日期 → 不算 stale（交给上游处理）。"""
    if published is None:
        return False
    now = datetime.now(timezone.utc)
    pub = published.replace(tzinfo=timezone.utc) if published.tzinfo is None else published
    return (now - pub).days > max_age_days


def is_future(published: datetime | None) -> bool:
    """发布日期在未来 → 无效。"""
    if published is None:
        return False
    now = datetime.now(timezone.utc)
    pub = published.replace(tzinfo=timezone.utc) if published.tzinfo is None else published
    return pub > now


def classify_signal_freshness(published: datetime | None) -> str:
    """新鲜度分类：new / recent / aging / stale / unknown。"""
    if published is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    pub = published.replace(tzinfo=timezone.utc) if published.tzinfo is None else published
    hours = (now - pub).total_seconds() / 3600
    if hours < 0:
        return "invalid"
    if hours < 24:
        return "new"
    if hours < 72:
        return "recent"
    if hours <= 24 * 30:
        return "aging"
    return "stale"


async def verify_published_date(
    fetcher: Any,
    url: str,
    *,
    timeout: float = 15.0,
) -> datetime | None:
    """抓详情页核实发布日期。失败返回 None。"""
    try:
        result = await fetcher.fetch(url)
        if not result.ok or not result.text:
            return None
        return extract_published_from_html(result.text)
    except Exception:
        return None
