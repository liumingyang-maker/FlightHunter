"""Playwright e2e：登录 + 四频道 + 收藏筛选。"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

base = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
cands = sorted(base.glob("chromium-*/chrome-win64/chrome.exe"))
if not cands:
    print("NO CHROMIUM")
    raise SystemExit(2)
exe = str(cands[-1])
out = Path("data/ui_screens")
out.mkdir(parents=True, exist_ok=True)
token = "hGJz1D_cN656GL4tn3cHQTy5S5t1WysET9oioZD2JtE"
results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=exe)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.goto("http://127.0.0.1:8765/login", wait_until="domcontentloaded")
    page.fill("input[name=token]", token)
    page.click("button[type=submit], input[type=submit]")
    page.wait_for_timeout(1500)
    results.append(("login", page.url.endswith("/"), page.url))

    for tab in ["my_origin", "china_mainland", "hk_mo", "global_error"]:
        page.goto("http://127.0.0.1:8765/fare", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        try:
            page.locator(f'button[data-ch="{tab}"]').first.click()
            page.wait_for_timeout(1500)
            status = page.locator("#origin-status").inner_text()
            items = page.locator("#intel-list article").count()
            page.screenshot(path=str(out / f"channel_{tab}.png"), full_page=False)
            results.append((f"channel_{tab}", "已更新" in status, f"items={items} {status[:40]}"))
        except Exception as e:
            results.append((f"channel_{tab}", False, str(e)[:80]))

    try:
        page.goto("http://127.0.0.1:8765/fare", wait_until="domcontentloaded")
        page.wait_for_timeout(1800)
        # 切回 my_origin 以保证有可收藏项
        try:
            page.locator('button[data-ch="my_origin"]').first.click()
            page.wait_for_timeout(1200)
        except Exception:
            pass
        fb = page.locator("button.fb").first
        if fb.count():
            fb.click(timeout=5000)
            page.wait_for_timeout(1200)
        page.evaluate("() => { const s=document.getElementById('f-fb'); if(s) s.value='bookmarked'; }")
        page.evaluate("() => { const b=document.getElementById('btn-apply'); if(b) b.click(); }")
        page.wait_for_timeout(1800)
        items = page.locator("#intel-list article").count()
        status = page.locator("#origin-status").inner_text()
        page.screenshot(path=str(out / "filter_bookmarked.png"), full_page=False)
        results.append(("filter_bookmarked", items >= 1, f"items={items} {status[:40]}"))
    except Exception as e:
        results.append(("filter_bookmarked", False, str(e)[:80]))

    browser.close()

print("=== e2e results ===")
fails = 0
for name, ok, detail in results:
    mark = "PASS" if ok else "FAIL"
    if not ok:
        fails += 1
    print(f"{mark:4} | {name} | {detail}")
print(f"{len(results)-fails}/{len(results)} passed")
raise SystemExit(1 if fails else 0)
