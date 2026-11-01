"""P1-2 测试：旧 0005 库升级到 0009 后 ORM 可用。"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_old_db_migration():
    """旧 0005 库升级到 0009：补时间戳字段，ORM 可用。"""
    tmp = Path(tempfile.mkdtemp(prefix="mig_old_"))
    db = tmp / "test.db"

    # 模拟旧库：alembic_version=0005
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sources (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO sources VALUES ('s1', 'test')")
    conn.execute("CREATE TABLE alembic_version (version_num TEXT)")
    conn.execute("INSERT INTO alembic_version VALUES ('0005_notification_delivery')")
    conn.commit()
    conn.close()

    # 直接用 Python API 跑 alembic upgrade
    from alembic import command
    from alembic.config import Config

    proj = Path(__file__).resolve().parents[1]
    ini = proj / "alembic.ini"
    cfg = Config(str(ini)) if ini.exists() else Config()
    cfg.set_main_option("script_location", str(proj / "app" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{db.as_posix()}")

    command.upgrade(cfg, "head")

    # 检查表
    conn = sqlite3.connect(db)
    cols = [c[1] for c in conn.execute("PRAGMA table_info(article_cache)").fetchall()]
    print(f"  article_cache cols: {cols}")
    conn.close()

    assert "created_at_utc" in cols, f"missing created_at_utc, got {cols}"
    assert "updated_at_utc" in cols, f"missing updated_at_utc, got {cols}"

    # ORM 测试
    from app.config import load_settings
    from app.db.session import create_db_engine, make_session_factory
    from app.models import ArticleCache
    from sqlalchemy import select

    cfg2 = tmp / "config.yaml"
    cfg2.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")
    s = load_settings(str(cfg2), project_root=tmp)
    engine = create_db_engine(s)
    factory = make_session_factory(engine)

    with factory() as session:
        ac = ArticleCache(id="test-old", title="Old DB Test")
        session.add(ac)
        session.commit()
        found = session.scalar(select(ArticleCache).where(ArticleCache.id == "test-old"))
        assert found is not None
        assert found.title == "Old DB Test"

    engine.dispose()
    print("PASS: old DB migration + ORM CRUD")


if __name__ == "__main__":
    test_old_db_migration()
    print("\nALL P1-2 TESTS PASSED")
