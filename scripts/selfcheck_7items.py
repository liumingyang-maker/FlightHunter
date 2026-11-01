"""自检：七项整改验证。"""

from __future__ import annotations

import sys
sys.path.insert(0, ".")

from pathlib import Path

results = []


def check(name: str, ok: bool, evidence: str, level: str = "unit"):
    results.append({"name": name, "ok": ok, "evidence": evidence, "level": level})
    print(f"{'PASS' if ok else 'FAIL':4} | {name:35} | {level:15} | {evidence[:50]}")


# ---- 1. 来源公平调度 ----
print("\n=== 1. 来源公平调度 ===")
from app.services.discovery.incremental import should_fetch

class FakeSource:
    def __init__(self, name, interval_h=24):
        self.name = name
        self.fetch_interval_hours = interval_h
        self.last_attempt_at = None
        self.last_result = None
        self.consecutive_failures = 0

from datetime import datetime, timedelta, timezone

# 20 来源 + 虚拟时钟
srcs = [FakeSource(f"s{i}", 24) for i in range(20)]
now = datetime(2026, 1, 1, tzinfo=timezone.utc)
fetches = 0
checks = 0
t = now
end = now + timedelta(hours=27)
while t < end:
    checks += 1
    for s in srcs:
        ok, _ = should_fetch(s, t)
        if ok:
            fetches += 1
            s.last_attempt_at = t
    t += timedelta(minutes=30)

# 20 来源 * 2 次/来源 = 40 次抓取
expected = 20 * 2
check("公平调度 20 来源 27h", fetches == expected, f"fetches={fetches} expected={expected} checks={checks}", "unit")

# 冷却不刷新 last_attempt_at
src = FakeSource("test", 24)
now1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
ok1, _ = should_fetch(src, now1)
src.last_attempt_at = now1
now2 = now1 + timedelta(minutes=30)
ok2, _ = should_fetch(src, now2)
check("冷却不刷新 last_attempt", src.last_attempt_at == now1 and ok2 is False, f"updated={src.last_attempt_at != now1}", "unit")

# ---- 2. 数据库迁移 ----
print("\n=== 2. 数据库迁移 ===")
import tempfile
from app.config import load_settings
from app.db.session import prepare_engine
from app.models import ArticleCache
from sqlalchemy import select

tmp = Path(tempfile.mkdtemp())
cfg = tmp / "c.yaml"
db = tmp / "t.db"
cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")
s = load_settings(str(cfg), project_root=tmp)
engine, factory, mig = prepare_engine(s)
with factory() as session:
    ac = ArticleCache(id="test-1", title="Test")
    session.add(ac)
    session.commit()
    found = session.scalar(select(ArticleCache).where(ArticleCache.id == "test-1"))
    check("新库 ORM CRUD", found is not None, f"found={found is not None}", "unit")
engine.dispose()

# ---- 3. ETag/304 ----
print("\n=== 3. ETag/304 ===")
from app.services.discovery.incremental import handle_response

src2 = FakeSource("etag")
r1 = handle_response(src2, {"etag": "v1"}, b"content", status_code=200)
r2 = handle_response(src2, {"etag": "v1"}, b"content", status_code=200)
check("ETag 保存", src2.etag == "v1", f"etag={src2.etag}", "unit")
check("内容哈希去重", r2["content_changed"] is False, f"changed={r2['content_changed']}", "unit")
r3 = handle_response(src2, {}, b"content", status_code=304)
check("304 复用", r3["cached"] is True, f"cached={r3['cached']}", "unit")

# ---- 4. A/B 性能（真实数值）----
print("\n=== 4. A/B 性能 ===")
import asyncio
import hashlib
from app.adapters.html_fetcher import HttpxFetchAdapter
from app.adapters.rss import RssAdapter

ab_settings = load_settings(str(cfg), project_root=tmp)
adapter = HttpxFetchAdapter(ab_settings)
rss = RssAdapter(ab_settings)

sources_ab = [
    ("FlyNext", "https://flynext.hk/", "httpx"),
    ("MainlyMiles", "https://mainlymiles.com/feed/", "rss"),
    ("Premium-Flights", "https://premium-flights.com/feed/", "rss"),
]

ab_stats = {"round1": {"requests": 0, "bytes": 0, "parsed": 0}, "round2": {"requests": 0, "bytes": 0, "parsed": 0}}

for round_num in [1, 2]:
    for name, url, mode in sources_ab:
        ad = rss if mode == "rss" else adapter
        try:
            result = asyncio.run(ad.fetch(url))
            if result.ok:
                ab_stats[f"round{round_num}"]["requests"] += 1
                ab_stats[f"round{round_num}"]["bytes"] += len((result.text or "").encode())
                if mode == "rss":
                    import feedparser
                    feed = feedparser.parse(result.text or "")
                    ab_stats[f"round{round_num}"]["parsed"] += len(feed.entries)
                else:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(result.text or "", "html.parser")
                    ab_stats[f"round{round_num}"]["parsed"] += len(soup.find_all("a", href=True)[:20])
        except Exception as e:
            print(f"  {name} R{round_num}: ERROR {e}")

r1 = ab_stats["round1"]
r2 = ab_stats["round2"]
print(f"  R1: {r1['requests']} requests, {r1['bytes']:,} bytes, {r1['parsed']} parsed")
print(f"  R2: {r2['requests']} requests, {r2['bytes']:,} bytes, {r2['parsed']} parsed")
check("A/B 两轮可复现", r1["requests"] == 3 and r2["requests"] == 3, f"R1={r1['requests']} R2={r2['requests']}", "real_network")

# ---- 5. FetcherRouter ----
print("\n=== 5. FetcherRouter ===")
from app.services.discovery.fetcher_router import FetcherRouter

router = FetcherRouter(ab_settings)
class FakeSrc:
    allowed_fetch_mode = "rss"
    name = "test"

adapter_r = router.select_adapter(FakeSrc())
check("FetcherRouter RSS 路由", adapter_r is not None and "rss" in type(adapter_r).__name__.lower(), f"type={type(adapter_r).__name__}", "unit")

class FakeSrcNone:
    allowed_fetch_mode = "none"
    name = "none"

adapter_none = router.select_adapter(FakeSrcNone())
check("none 模式禁止抓取", adapter_none is None, f"adapter={adapter_none}", "unit")

# ---- 6. 缓存 ----
print("\n=== 6. 缓存 ===")
from app.services.discovery.cache import get_article_cache, save_article_cache

tmp2 = Path(tempfile.mkdtemp())
cfg2 = tmp2 / "c.yaml"
db2 = tmp2 / "t.db"
cfg2.write_text(f"storage:\n  sqlite_path: {db2.as_posix()}\n", encoding="utf-8")
s2 = load_settings(str(cfg2), project_root=tmp2)
engine2, factory2, _ = prepare_engine(s2)
with factory2() as session:
    save_article_cache(session, "https://a.com/1", guid="g1", source_id="src-a", title="Test")
    session.commit()
    found = get_article_cache(session, "https://a.com/1", guid="g1", source_id="src-a")
    check("缓存写入+查询", found is not None, f"found={found is not None}", "unit")

    save_article_cache(session, "https://b.com/1", guid="g1", source_id="src-b", title="Test2")
    session.commit()
    found2 = get_article_cache(session, "https://b.com/1", guid="g1", source_id="src-b")
    check("GUID 来源作用域", found2 is not None and found2.id != (found.id if found else ""), f"ids_differ={found2.id != (found.id if found else '')}", "unit")
engine2.dispose()

# ---- 7. 社交来源 ----
print("\n=== 7. 社交来源 ===")
from app.services.discovery.social_adapter import SocialPost, parse_social_post

post = parse_social_post({"platform": "reddit", "id": "p1", "text": "cheap flights HKG-TYO", "title": "flight deal"})
check("社交帖子解析", post.platform == "reddit", f"platform={post.platform}", "unit")
check("社交数据模型", hasattr(post, "is_bug_fare") and hasattr(post, "source_trust"), "fields=ok", "static")

# 汇总
print("\n=== 汇总 ===")
passed = sum(1 for r in results if r["ok"])
print(f"{passed}/{len(results)} passed")
for r in results:
    print(f"  {'PASS' if r['ok'] else 'FAIL':4} | {r['name']:35} | {r['level']}")
