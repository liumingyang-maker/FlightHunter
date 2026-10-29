"""发现管道测试。"""

from __future__ import annotations

import asyncio

from app.adapters.base import FetchResult
from app.config import Settings
from app.db.session import ensure_default_sources
from app.models import Source
from app.services.discovery.service import ingest_fetch_result, run_discovery
from sqlalchemy import select


def test_dry_run_discovery(db, settings: Settings):
    ensure_default_sources(db, settings)
    db.commit()
    results = asyncio.run(run_discovery(db, settings, module="fare", dry_run=True, limit=5))
    assert results
    assert all(r["status"] == "dry_run" for r in results)


def test_ingest_denied_marks_source(db, settings: Settings):
    ensure_default_sources(db, settings)
    db.commit()
    src = db.scalars(select(Source)).first()
    assert src is not None
    fr = FetchResult(
        ok=False,
        url=src.base_url,
        error_code="SOURCE_FETCH_DENIED",
        message="robots",
    )
    cand = ingest_fetch_result(db, src, fr)
    db.commit()
    assert cand is None
    assert src.status == "manual_only"


def test_ingest_success_stores_candidate(db, settings: Settings):
    ensure_default_sources(db, settings)
    db.commit()
    src = db.scalars(select(Source)).first()
    assert src is not None
    fr = FetchResult(
        ok=True,
        url=src.base_url,
        status_code=200,
        text="<html><title>Deal list</title><a href='https://x'>特价机票 999元</a></html>",
        content_hash="abc",
        final_url=src.base_url,
    )
    cand = ingest_fetch_result(db, src, fr)
    db.commit()
    assert cand is not None
    assert cand.status == "parsed"
    assert cand.raw_content_hash == "abc"
