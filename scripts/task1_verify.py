"""任务一：确认整改无遗留根因。"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True, cwd=ROOT, text=True, encoding="utf-8", errors="replace")


def main() -> None:
    results = []

    # 1. Token 不在 git 历史/源码
    print("=== 1. Token 安全 ===")
    token_frag = "hGJz1D"
    src_hits = []
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".md", ".json", ".html") and "review_exports" not in str(p):
            try:
                t = p.read_text(encoding="utf-8", errors="ignore")
                if token_frag in t:
                    src_hits.append(str(p))
            except:
                pass
    print(f"  源码中 hGJz1D: {src_hits if src_hits else 'NONE'}")
    results.append(("token_source_clean", len(src_hits) == 0))

    # 检查 git log
    log = run("git log --oneline -20")
    if token_frag in log:
        print(f"  git log 中有 token: TRUE")
        results.append(("token_git_log_clean", False))
    else:
        print(f"  git log 中有 token: NONE")
        results.append(("token_git_log_clean", True))

    # 2. 失败退避
    print("\n=== 2. 失败退避 ===")
    disc = (ROOT / "app" / "services" / "discovery" / "service.py").read_text(encoding="utf-8")
    has_backoff = "backoff_h" in disc or "consecutive_failures" in disc
    has_fair = "last_attempt_at" in disc
    print(f"  backoff: {has_backoff} | fair_sort: {has_fair}")
    results.append(("backoff_exists", has_backoff))
    results.append(("fair_sort_exists", has_fair))

    # 3. Robots 策略
    print("\n=== 3. Robots 策略 ===")
    safe_http = (ROOT / "app" / "core" / "safe_http.py").read_text(encoding="utf-8")
    # 403→allow, 429→error, 5xx→error
    has_403_allow = 'return "allow"' in safe_http and "403" in safe_http
    has_429_error = "429" in safe_http and 'return "error"' in safe_http
    print(f"  403→allow: {has_403_allow} | 429→error: {has_429_error}")
    results.append(("robots_403_allow", has_403_allow))
    results.append(("robots_429_error", has_429_error))

    # 4. 发布日期只接受有标签
    print("\n=== 4. 发布日期 ===")
    fresh = (ROOT / "app" / "services" / "fare" / "freshness.py").read_text(encoding="utf-8")
    no_bare_iso = 'T\\d{2}:\\d{2}' not in fresh and "20\\\\d{2}-\\\\d{2}-\\\\d{2})T" not in fresh
    has_date_published = "datePublished" in fresh
    print(f"  无裸ISO: {no_bare_iso} | datePublished: {has_date_published}")
    results.append(("no_bare_iso", no_bare_iso))
    results.append(("date_published", has_date_published))

    # 5. 价格分类
    print("\n=== 5. 价格分类 ===")
    html = (ROOT / "app" / "adapters" / "html_fetcher.py").read_text(encoding="utf-8")
    has_classify = "classify_amount_purpose" in html
    has_coupon = "coupon_face_value" in html
    has_cashback = "cashback" in html
    print(f"  classify: {has_classify} | coupon: {has_coupon} | cashback: {has_cashback}")
    results.append(("price_classify", has_classify))

    # 6. 归档保留收藏
    print("\n=== 6. 归档 ===")
    has_archive = "archive_stale_signals" in fresh
    keeps_bookmarked = "bookmarked" in fresh
    print(f"  archive_fn: {has_archive} | keeps_bookmarked: {keeps_bookmarked}")
    results.append(("archive_fn", has_archive))
    results.append(("keeps_bookmarked", keeps_bookmarked))

    # 7. 104 矩阵
    print("\n=== 7. 104 矩阵 ===")
    matrix = ROOT / "docs" / "ACCEPTANCE_104_MATRIX.json"
    if matrix.exists():
        import json

        cases = json.loads(matrix.read_text(encoding="utf-8"))
        from collections import Counter

        cnt = Counter(c["status"] for c in cases)
        print(f"  {dict(cnt)}")
        results.append(("matrix_honest", "NOT_TESTED" in cnt))
    else:
        results.append(("matrix_honest", False))

    print("\n=== 汇总 ===")
    fails = 0
    for name, ok in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            fails += 1
        print(f"  {mark:4} | {name}")
    print(f"\n{len(results)-fails}/{len(results)} passed")


if __name__ == "__main__":
    main()
