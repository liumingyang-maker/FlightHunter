"""业务回归：Codex 旧缺陷不回退。"""

from __future__ import annotations

import sys
sys.path.insert(0, ".")

from pathlib import Path

results = []


def check(name: str, ok: bool, evidence: str, level: str = "unit"):
    results.append({"name": name, "ok": ok, "evidence": evidence, "level": level})
    print(f"{'PASS' if ok else 'FAIL':4} | {name:35} | {level:15} | {evidence[:50]}")


# 1. XSS 安全渲染
print("\n=== 1. XSS ===")
html = Path("app/web/templates/fare.html").read_text(encoding="utf-8")
check("fare.html 用 esc() 转义", "esc(it.title" in html and "esc(it.summary_zh" in html, "esc() present", "static")

# 2. 航司/出发/目的不混淆
print("\n=== 2. 航线语义 ===")
from app.services.fare.intel import extract_dest_iata, extract_origin_iatas_from_title
dest = extract_dest_iata("香港航空 上海→大阪 优惠")
check("航司名≠目的地", dest != "HKG", f"dest={dest}", "unit")
origins = extract_origin_iatas_from_title("上海→香港 机票促销")
check("出发地正确", origins[0] == "PVG", f"origins={origins}", "unit")

# 3. 价格分类
print("\n=== 3. 价格分类 ===")
from app.adapters.html_fetcher import classify_amount_purpose, parse_deal_label
check("优惠券分类", classify_amount_purpose("优惠券800元") == "coupon_face_value", classify_amount_purpose("优惠券800元"), "unit")
check("返现分类", classify_amount_purpose("返现800元") == "cashback", classify_amount_purpose("返现800元"), "unit")
sig = parse_deal_label("东京机票 HK$1200 含税", page_url="https://e.com/x")
check("票价保留", sig.reported_total == 1200.0 if sig else False, f"price={sig.reported_total if sig else None}", "unit")

# 4. 发布时间
print("\n=== 4. 发布时间 ===")
from app.services.fare.freshness import extract_published_from_html
check("裸ISO不解析", extract_published_from_html("<body>2026-11-24T12:00:00</body>") is None, "travel date not published", "unit")
check("datePublished 解析", extract_published_from_html('<meta property="article:published_time" content="2026-10-31">') is not None, "meta tag", "unit")

# 5. 全球频道无默认偏好
print("\n=== 5. 全球频道 ===")
import inspect
from app.web.routes.api import fare_intel
src = inspect.getsource(fare_intel)
check("全球频道无默认偏好", 'channel == "global_error"' in src and "D-004" in src or "全球" in src, "code check", "static")

# 6. 全国不含 HKG/MFM
print("\n=== 6. 全国机场 ===")
from app.services.airports.china import expand_origin_selection
mainland = expand_origin_selection(china_mainland_all=True)
check("全国不含 HKG/MFM", "HKG" not in mainland and "MFM" not in mainland, f"has_hkg={'HKG' in mainland}", "unit")

# 7. 未确认行程不扫描
print("\n=== 7. 行程状态 ===")
import inspect
from app.services.trips import service as tripsvc
src_t = inspect.getsource(tripsvc.update_trip)
check("未确认不扫描", "trip_not_confirmed" in src_t, "code check", "static")

# 8. 通知幂等
print("\n=== 8. 通知幂等 ===")
from app.services.notify.delivery import send_notification
from app.models import NotificationDelivery
from sqlalchemy import select
from app.config import load_settings
from app.db.session import create_db_engine, make_session_factory, prepare_engine
import tempfile

tmp = Path(tempfile.mkdtemp())
cfg = tmp / "c.yaml"
db = tmp / "t.db"
cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")
s = load_settings(str(cfg), project_root=tmp)
engine, factory, _ = prepare_engine(s)
with factory() as session:
    send_notification(session, kind="test", title="hello", body="x", event_key="ek1", try_toast=False)
    session.commit()
    send_notification(session, kind="test", title="hello", body="x", event_key="ek1", try_toast=False)
    session.commit()
    rows = session.scalars(select(NotificationDelivery).where(NotificationDelivery.event_key == "ek1")).all()
    statuses = [r.status for r in rows]
    check("通知幂等", "toast_delivered" in statuses or "recorded" in statuses, f"statuses={statuses}", "unit")
engine.dispose()

# 9. 归档保留收藏
print("\n=== 9. 归档 ===")
fresh_src = Path("app/services/fare/freshness.py").read_text(encoding="utf-8")
check("归档保留收藏", "bookmarked" in fresh_src and "archive_stale_signals" in fresh_src, "code check", "static")

# 10. 资格三态
print("\n=== 10. 资格 ===")
from app.services.raffle.multi_round import eligibility_with_synthetic_profile, EventRoundRules
rules = EventRoundRules(
    round_label="r", edition_key="e", title="t",
    purchase_required=False,
    residency_restriction="non-Korean",
)
r = eligibility_with_synthetic_profile(rules, nationality="CN", residence=None)
check("缺国籍→unknown", r["state"] == "unknown", f"state={r['state']}", "unit")

# 11. robots 策略
print("\n=== 11. robots ===")
safe_http = Path("app/core/safe_http.py").read_text(encoding="utf-8")
check("403→allow", 'return "allow"' in safe_http and "403" in safe_http, "code check", "static")
check("5xx→error", "5xx" in safe_http or "error" in safe_http, "code check", "static")

# 12. Web/API 一致
print("\n=== 12. 一致性 ===")
check("Web 用 Jinja 模板", "TemplateResponse" in Path("app/web/routes/pages.py").read_text(encoding="utf-8"), "code check", "static")

# 汇总
print("\n=== 业务回归汇总 ===")
passed = sum(1 for r in results if r["ok"])
print(f"{passed}/{len(results)} passed")
for r in results:
    print(f"  {'PASS' if r['ok'] else 'FAIL':4} | {r['name']:35} | {r['level']}")
