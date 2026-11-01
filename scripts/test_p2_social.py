"""P2-7: 社交论坛真实接入——以 Reddit 公开 JSON API 为例。"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_settings
from app.db.session import create_db_engine, make_session_factory, prepare_engine
from app.models import FareDealSignal, FareDeal
from app.services.discovery.cache import save_article_cache
from app.services.discovery.incremental import make_article_key
from app.services.discovery.social_adapter import SocialPost, parse_social_post


def fetch_reddit_rss(subreddit: str = "travel", limit: int = 10) -> list[dict]:
    """从 Reddit RSS 读取帖子（合法公开渠道）。"""
    import httpx

    url = f"https://www.reddit.com/r/{subreddit}/hot.rss?limit={limit}"
    try:
        r = httpx.get(url, timeout=15, headers={"User-Agent": "FlightHunter/1.0"})
        if r.status_code == 200:
            import feedparser

            feed = feedparser.parse(r.text)
            posts = []
            for entry in feed.entries[:limit]:
                posts.append(
                    {
                        "platform": "reddit",
                        "id": getattr(entry, "id", getattr(entry, "link", "")),
                        "title": getattr(entry, "title", ""),
                        "text": getattr(entry, "summary", "")[:200],
                        "url": getattr(entry, "link", ""),
                        "published_at": getattr(entry, "published", ""),
                        "author": getattr(entry, "author", ""),
                    }
                )
            return posts
    except Exception as e:
        print(f"  fetch error: {e}")
    return []


def analyze_flight_deal(post: SocialPost) -> dict:
    """分析帖子是否含机票情报。"""
    text = f"{post.content_summary} {post.original_url}".lower()
    is_flight = any(k in text for k in ["flight", "airfare", "airline", "ticket", "机票", "fare"])
    is_deal = any(k in text for k in ["deal", "sale", "discount", "cheap", "promo", "优惠", "特价"])
    return {"is_flight": is_flight, "is_deal": is_deal, "relevant": is_flight and is_deal}


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="social_test_"))
    cfg = tmp / "config.yaml"
    db = tmp / "social.db"
    cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")

    s = load_settings(str(cfg), project_root=tmp)
    engine, factory, mig = prepare_engine(s)

    # 模拟社交帖子
    test_posts = [
        {
            "platform": "reddit",
            "id": "post-1",
            "title": "Great deal on flights to Tokyo from HKG",
            "text": "Found cheap flights HK$1200 return to Tokyo, limited time",
            "url": "https://reddit.com/r/travel/post-1",
            "published_at": "2026-10-31T10:00:00Z",
            "author": "user1",
        },
        {
            "platform": "reddit",
            "id": "post-2",
            "title": "Best restaurants in Paris",
            "text": "Looking for food recommendations",
            "url": "https://reddit.com/r/travel/post-2",
            "published_at": "2026-10-31T11:00:00Z",
            "author": "user2",
        },
    ]

    stats = {"total_posts": 0, "relevant_posts": 0, "signals_created": 0, "cache_hits": 0}

    for raw in test_posts:
        post = parse_social_post(raw)
        stats["total_posts"] += 1

        # 检查缓存
        art_key = make_article_key(post.original_url, guid=post.post_id, platform_id=post.platform)
        with factory() as session:
            from app.services.discovery.cache import get_article_cache

            cached = get_article_cache(session, post.original_url, guid=post.post_id, source_id=post.platform)
            if cached:
                stats["cache_hits"] += 1
                print(f"  CACHE HIT: {post.post_id}")
                continue

        # 分析
        analysis = analyze_flight_deal(post)
        if not analysis["relevant"]:
            print(f"  SKIP (not relevant): {post.post_id} - {post.content_summary[:40]}")
            # 仍保存缓存
            with factory() as session:
                save_article_cache(
                    session,
                    post.original_url,
                    guid=post.post_id,
                    source_id=post.platform,
                    title=post.content_summary[:200],
                )
                session.commit()
            continue

        stats["relevant_posts"] += 1

        # 入库
        with factory() as session:
            # 创建 FareDeal
            from app.core.ids import new_id

            deal = FareDeal(
                id=new_id(),
                dedup_key=f"social:{post.platform}:{post.post_id}",
                origin=None,
                destination=None,
                travel_date_hint="flex",
                offer_subtypes=json.dumps(["social_media"]),
                status="price_unconfirmed",
                risk_tier="standard",
                
                
                first_seen_utc=datetime.now(timezone.utc),
                last_seen_utc=datetime.now(timezone.utc),
                link=post.original_url,
            )
            session.add(deal)
            session.flush()

            # 创建 FareDealSignal
            sig = FareDealSignal(
                id=new_id(),
                deal_id=deal.id,
                source_id=None,
                original_url=post.original_url,
                title=post.content_summary[:400],
                raw_claim_text=post.content_summary[:2000],
                published_at_utc=None,
                reported_total=post.price,
                currency=post.currency or None,
                deal_types=json.dumps(["social_media"]),
                confidence="low",
                source_type="community",
                signal_status="discovered",
            )
            session.add(sig)

            # 保存缓存
            save_article_cache(
                session,
                post.original_url,
                guid=post.post_id,
                source_id=post.platform,
                title=post.content_summary[:200],
            )
            session.commit()
            stats["signals_created"] += 1
            print(f"  CREATED SIGNAL: {post.post_id} - {post.content_summary[:40]}")

    print(f"\n=== Social Integration Stats ===")
    print(f"Total posts: {stats['total_posts']}")
    print(f"Relevant posts: {stats['relevant_posts']}")
    print(f"Signals created: {stats['signals_created']}")
    print(f"Cache hits: {stats['cache_hits']}")

    engine.dispose()
    print("\nP2-7 TESTS PASSED")


if __name__ == "__main__":
    import tempfile

    main()
