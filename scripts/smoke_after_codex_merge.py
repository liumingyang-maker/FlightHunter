"""隔离冒烟：合并后验证旧库不被 create_all 改写、迁移检查、连接 backend。"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path


def main() -> None:
    from app.config import load_settings
    from app.core.safe_http import PublicAddressBackend, public_http_transport, safe_get
    from app.db.session import check_alembic_head, create_db_engine, ensure_migrations_or_warn, init_db

    tmp = Path(tempfile.mkdtemp(prefix="fh_smoke_"))
    try:
        # 1) 新库
        db = tmp / "new.db"
        cfg = tmp / "c.yaml"
        cfg.write_text(f"storage:\n  sqlite_path: {db.as_posix()}\n", encoding="utf-8")
        s = load_settings(str(cfg), project_root=tmp)
        mig = ensure_migrations_or_warn(s)
        print("new_db_action", mig.get("action"))
        if mig.get("action") == "create_all_new_db":
            eng = create_db_engine(s)
            init_db(eng)
            eng.dispose()
        print("new_db_ok", check_alembic_head(s).get("state"))

        # 2) 旧库：只有 legacy 表，无 alembic_version
        db2 = tmp / "old.db"
        cfg2 = tmp / "c2.yaml"
        cfg2.write_text(f"storage:\n  sqlite_path: {db2.as_posix()}\n", encoding="utf-8")
        conn = sqlite3.connect(db2)
        conn.execute("CREATE TABLE legacy_data (id INTEGER PRIMARY KEY, note TEXT)")
        conn.execute("INSERT INTO legacy_data (id, note) VALUES (1, 'keep')")
        conn.commit()
        conn.close()
        s2 = load_settings(str(cfg2), project_root=tmp)
        mig2 = ensure_migrations_or_warn(s2)
        print("old_db_action", mig2.get("action"), "state", mig2.get("state"))
        # 模拟 create_app：非 create_all_new_db 时不 init_db
        eng2 = create_db_engine(s2)
        if mig2.get("action") == "create_all_new_db":
            init_db(eng2)
        eng2.dispose()
        conn = sqlite3.connect(db2)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        conn.close()
        print("old_db_tables", sorted(tables))
        print("old_db_unchanged", "legacy_data" in tables and "trips" not in tables)

        # 3) 过期版本
        db3 = tmp / "old2.db"
        cfg3 = tmp / "c3.yaml"
        cfg3.write_text(f"storage:\n  sqlite_path: {db3.as_posix()}\n", encoding="utf-8")
        conn = sqlite3.connect(db3)
        conn.execute("CREATE TABLE alembic_version (version_num TEXT)")
        conn.execute("INSERT INTO alembic_version VALUES ('0001_initial')")
        conn.commit()
        conn.close()
        s3 = load_settings(str(cfg3), project_root=tmp)
        rep3 = check_alembic_head(s3)
        print("outdated", rep3.get("state"), rep3.get("ok"), rep3.get("head"))

        # 4) PublicAddressBackend
        t = public_http_transport()
        backend = t._pool._network_backend
        print("backend_type", type(backend).__name__, isinstance(backend, PublicAddressBackend))
        # 拒绝 unix socket
        import asyncio

        async def _unix():
            return await backend.connect_unix_socket("/tmp/x")

        try:
            asyncio.run(_unix())
            print("unix_rejected", False)
        except Exception as e:
            print("unix_rejected", True, type(e).__name__)

        # 5) is_global 拒绝共享地址
        from app.core.url_safety import assert_public_http_url

        for u in ("http://100.64.0.1/", "http://10.0.0.1/", "http://8.8.8.8/"):
            try:
                assert_public_http_url(u)
                print("url", u, "allowed")
            except Exception as e:
                print("url", u, "blocked")

        print("smoke_done_ok")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
