"""R25：默认来源包、抽奖物化、ops 状态。"""

from __future__ import annotations

import asyncio

from app.config import Settings
from app.db.session import ensure_default_sources
from app.models import CampaignRound, Source
from app.services.discovery.service import run_discovery
from app.services.ops.status import system_status
from sqlalchemy import select


def test_default_sources_include_trip_and_raffle(db, settings: Settings):
    ensure_default_sources(db, settings)
    db.commit()
    mods = {s.module for s in db.scalars(select(Source)).all()}
    assert "fare" in mods
    assert "trip" in mods
    assert "raffle" in mods
    jp = [
        s
        for s in db.scalars(select(Source)).all()
        if s.module == "trip" and s.country_code == "JP"
    ]
    assert jp


def test_raffle_module_creates_candidate_round(db, settings: Settings, monkeypatch):
    ensure_default_sources(db, settings)
    db.commit()
    # 清掉 raffle 源状态便于执行
    src = db.scalars(select(Source).where(Source.module == "raffle")).first()
    assert src is not None

    from app.adapters.base import FetchResult, ParsedSignal

    class Fake:
        async def fetch(self, url):
            return FetchResult(
                ok=True,
                url=url,
                status_code=200,
                text="<html><a href='https://example.org/contest/1'>Win a trip giveaway 2027</a></html>",
                content_hash="h",
                final_url=url,
            )

        def parse(self, text, *, url):
            return [
                ParsedSignal(
                    title="Win a trip giveaway 2027",
                    raw_claim_text="Win a trip giveaway 2027",
                    url="https://example.org/contest/1",
                    confidence="low",
                )
            ]

    monkeypatch.setattr("app.services.discovery.service.adapter_for", lambda s, st: Fake())
    # only this source
    for s in db.scalars(select(Source)).all():
        if s.id != src.id:
            s.status = "inactive"
    db.commit()
    asyncio.run(
        run_discovery(db, settings, module="raffle", dry_run=False, limit=5, after_fetch=False)
    )
    db.commit()
    rounds = db.scalars(select(CampaignRound)).all()
    assert any(r.verify_status == "candidate" and "giveaway" in r.title.lower() for r in rounds)


def test_last_success_ignores_failed(db, settings: Settings):
    from app.core.ids import new_id
    from app.core.timeutils import utc_now
    from app.models import TaskRun

    db.add(
        TaskRun(
            id=new_id(),
            task_type="source_discovery_batch",
            status="failed",
            idempotency_key="f1",
            dry_run=False,
            finished_at=utc_now(),
        )
    )
    db.commit()
    st = system_status(db)
    assert st["last_successful_execute_scan_utc"] is None
