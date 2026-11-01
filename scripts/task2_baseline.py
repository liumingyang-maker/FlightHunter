"""任务二：测量当前采集效率基线。隔离数据库，不碰正式库。"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adapters.html_fetcher import HttpxFetchAdapter, parse_deal_label
from app.adapters.rss import RssAdapter
from app.config import load_settings
from app.db.session import create_db_engine, make_session_factory
from app.models import Source


def main() -> None:
    # 隔离数据库
    tmp = Path(tempfile.mkdtemp(prefix="crawl_baseline_"))
    cfg = tmp / "config.yaml"
    db = tmp / "baseline.db"
    cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")

    settings = load_settings(str(cfg), project_root=tmp)
    engine = create_db_engine(settings)
    factory = make_session_factory(engine)

    adapter = HttpxFetchAdapter(settings)
    rss = RssAdapter(settings)

    # 用真实来源
    from app.models import Base

    Base.metadata.create_all(engine)

    sources = [
        ("FlyNext.hk", "https://flynext.hk/", "httpx"),
        ("MainlyMiles RSS", "https://mainlymiles.com/feed/", "rss"),
        ("One Mile at a Time", "https://onemileatatime.com/feed/", "rss"),
        ("Premium-Flights RSS", "https://premium-flights.com/feed/", "rss"),
        ("Secret Flying", "https://www.secretflying.com/", "httpx"),
    ]

    stats = {
        "sources_total": len(sources),
        "http_requests": 0,
        "list_pages": 0,
        "detail_pages": 0,
        "status_200": 0,
        "status_304": 0,
        "status_403": 0,
        "status_429": 0,
        "status_fail": 0,
        "skipped": 0,
        "bytes_downloaded": 0,
        "rss_entries_read": 0,
        "signals_parsed": 0,
        "signals_new": 0,
        "duplicate_content": 0,
        "ocr_runs": 0,
        "errors": [],
    }

    start = time.time()

    for name, url, mode in sources:
        print(f"\n--- {name} ---")
        t0 = time.time()
        try:
            ad = rss if mode == "rss" else adapter
            result = asyncio.run(ad.fetch(url))
            stats["http_requests"] += 1
            stats["list_pages"] += 1

            if result.ok:
                stats["status_200"] += 1
                text = result.text or ""
                stats["bytes_downloaded"] += len(text.encode("utf-8"))
                elapsed = time.time() - t0

                if mode == "rss":
                    import feedparser

                    feed = feedparser.parse(text)
                    entries = feed.entries[:20]
                    stats["rss_entries_read"] += len(entries)
                    for entry in entries:
                        title = getattr(entry, "title", "")
                        body = (getattr(entry, "summary", "") or "")[:80]
                        combo = f"{title} {body}"[:220]
                        sig = parse_deal_label(combo, page_url=getattr(entry, "link", ""))
                        if sig:
                            stats["signals_parsed"] += 1
                            stats["signals_new"] += 1
                else:
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(text, "html.parser")
                    for a in soup.find_all("a", href=True)[:40]:
                        label = a.get_text(" ", strip=True)
                        sig = parse_deal_label(label, page_url=a.get("href", ""))
                        if sig:
                            stats["signals_parsed"] += 1
                            stats["signals_new"] += 1

                print(f"  OK status=200 bytes={len(text)} signals={stats['signals_new']} time={elapsed:.2f}s")
            else:
                err = result.error_code or result.message or "unknown"
                if "403" in str(err):
                    stats["status_403"] += 1
                elif "429" in str(err):
                    stats["status_429"] += 1
                else:
                    stats["status_fail"] += 1
                stats["errors"].append({"source": name, "error": str(err)[:80]})
                print(f"  FAIL {err}")

        except Exception as exc:
            stats["status_fail"] += 1
            stats["errors"].append({"source": name, "error": str(exc)[:80]})
            print(f"  EXC {exc}")

    total_time = time.time() - start

    stats["total_time_sec"] = round(total_time, 2)
    stats["generated_at"] = datetime.now(timezone.utc).isoformat()
    stats["note"] = "隔离数据库基线；不含详情页验证请求；不含 Worker 调度开销"

    out = Path(__file__).resolve().parents[1] / "docs" / "CRAWL_EFFICIENCY_BASELINE.md"
    lines = [
        "# 采集效率基线（任务二）",
        "",
        f"- **生成时间：** {stats['generated_at']}",
        f"- **总耗时：** {stats['total_time_sec']}s",
        f"- **来源数：** {stats['sources_total']}",
        "",
        "## HTTP 请求统计",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 总请求数 | {stats['http_requests']} |",
        f"| 列表页请求 | {stats['list_pages']} |",
        f"| 详情页请求 | {stats['detail_pages']} |",
        f"| 200 OK | {stats['status_200']} |",
        f"| 304 Not Modified | {stats['status_304']} |",
        f"| 403 Forbidden | {stats['status_403']} |",
        f"| 429 Rate Limited | {stats['status_429']} |",
        f"| 失败/其他 | {stats['status_fail']} |",
        f"| 下载字节 | {stats['bytes_downloaded']:,} |",
        "",
        "## 内容解析",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| RSS 条目读取 | {stats['rss_entries_read']} |",
        f"| 解析出信号 | {stats['signals_parsed']} |",
        f"| 新增信号 | {stats['signals_new']} |",
        f"| 重复内容 | {stats['duplicate_content']} |",
        f"| OCR 执行 | {stats['ocr_runs']} |",
        "",
        "## 错误记录",
        "",
    ]
    for e in stats["errors"]:
        lines.append(f"- **{e['source']}**: {e['error']}")
    if not stats["errors"]:
        lines.append("- 无")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n写入 {out}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    engine.dispose()


if __name__ == "__main__":
    main()
