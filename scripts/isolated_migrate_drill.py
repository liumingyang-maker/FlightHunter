"""B7 隔离迁移演练（临时脚本）。"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import load_settings
from app.db.session import (
    check_alembic_head,
    create_db_engine,
    ensure_migrations_or_warn,
    init_db,
)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="fh_migrate_"))
    try:
        cfg = tmp / "cfg.yaml"
        db = tmp / "fh.db"
        cfg.write_text(
            "storage:\n"
            f"  sqlite_path: {db.as_posix()}\n",
            encoding="utf-8",
        )
        s = load_settings(str(cfg), project_root=tmp)
        r = ensure_migrations_or_warn(s)
        print("new_db", r.get("action"), "head", r.get("head"))

        eng = create_db_engine(s)
        init_db(eng)
        eng.dispose()
        r2 = check_alembic_head(s)
        print("after_create_all", r2)

        conn = sqlite3.connect(db)
        conn.execute("DROP TABLE IF EXISTS alembic_version")
        conn.commit()
        conn.close()
        r3 = ensure_migrations_or_warn(s)
        print("old_no_version", r3.get("action"))

        shutil.copy2(db, tmp / "fh.backup.db")
        proj = Path(".").resolve()
        ini = proj / "alembic.ini"
        acfg = Config(str(ini)) if ini.exists() else Config()
        acfg.set_main_option("script_location", str((proj / "app" / "alembic").as_posix()))
        acfg.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{db.as_posix()}")
        command.upgrade(acfg, "head")
        r4 = check_alembic_head(s)
        print(
            "after_upgrade",
            r4.get("alembic_version"),
            r4.get("head"),
            "match",
            r4.get("alembic_version") == r4.get("head"),
        )
        print("backup_exists", (tmp / "fh.backup.db").exists())
        print("done_ok")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
