"""Seed only public Source registry (no demo trips, profiles, mock coupons)."""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from sqlalchemy import select, func
from app.config import load_settings, sqlite_path
from app.db.session import create_db_engine, make_session_factory, ensure_default_sources
from app.models import Source

settings = load_settings(project_root=Path.cwd())
db_path = sqlite_path(settings)
if not db_path.is_file():
    raise SystemExit(f"FAIL: migrate did not create configured DB: {db_path}")
with sqlite3.connect(db_path) as c:
    v = c.execute("SELECT version_num FROM alembic_version").fetchone()
    schema = c.execute("PRAGMA table_info(campaign_rounds)").fetchall()
    nullable = [row[3] for row in schema if row[1] == "official_url"]
    if not v or v[0] != "0002_official_url_nullable" or nullable != [0]:
        raise SystemExit(f"FAIL: schema mismatch, migration={v}, official_url_notnull={nullable}")
engine = create_db_engine(settings)
try:
    with make_session_factory(engine)() as db:
        created = ensure_default_sources(db, settings)
        db.commit()
        sources = db.scalars(select(Source).order_by(Source.module, Source.name)).all()
        print(f"OK: isolated DB {db_path}, migration={v[0]}, sources={len(sources)}, new={len(created)}")
        for s in sources:
            print(f"SOURCE {s.module:7} {s.name:34} {s.base_url}")
finally:
    engine.dispose()
