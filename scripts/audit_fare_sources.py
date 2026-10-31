"""来源覆盖盘点：active vs manual_only vs 失败原因（诚实）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.config import load_settings
from app.db.session import create_db_engine, make_session_factory
from app.models import Source


def main() -> None:
    s = load_settings("data/daily_usage/config.yaml", project_root=".")
    e = create_db_engine(s)
    f = make_session_factory(e)
    with f() as db:
        rows = db.scalars(
            select(Source).where(Source.module == "fare").order_by(Source.status, Source.name)
        ).all()
    active = [r for r in rows if r.status == "active"]
    manual = [r for r in rows if r.status != "active"]
    print(f"=== fare 来源总数 {len(rows)} ===")
    print(f"active(可自动抓) {len(active)} | 非自动 {len(manual)}")
    print("\n-- active --")
    for r in active:
        print(f"  [{r.last_result or '-'}] {r.name}")
        print(f"    {r.base_url}")
    print("\n-- manual_only / 其它 --")
    for r in manual:
        print(f"  [{r.status}] {r.name}")
        print(f"    {r.base_url}")
    print("\n覆盖判断（主观）:")
    print("  有: 香港(FlyNext)、内地(什么值得买x2、北美票帝)、全球RSS/deal站")
    print("  缺: 航司官网(JS/登录)、中国大陆航司促销号、日本/韩国本地、已知漏报源需单独评估")
    e.dispose()


if __name__ == "__main__":
    main()
