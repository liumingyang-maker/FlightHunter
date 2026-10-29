"""R29：去重、证据类型。"""

from __future__ import annotations

import asyncio
import json

from app.adapters.html_fetcher import HttpxFetchAdapter
from app.config import Settings
from app.core.ids import new_id
from app.models import CampaignRound, Evidence, Source
from app.services.discovery.service import materialize_raffle_candidates
from sqlalchemy import select


def test_rescan_same_aggregator_no_unique_error(db):
    src = Source(
        id=new_id(),
        name="agg",
        base_url="https://agg.example.org/",
        kind="community",
        module="raffle",
        status="active",
    )
    db.add(src)
    db.flush()
    from app.adapters.base import ParsedSignal

    sigs = [
        ParsedSignal(
            title="Win a free trip to Tokyo",
            raw_claim_text="Win a free trip",
            url="https://agg.example.org/x",
            deal_types=["flight_giveaway"],
            confidence="low",
        )
    ]
    for _ in range(5):
        materialize_raffle_candidates(db, src, sigs)
        db.commit()
    rounds = db.scalars(
        select(CampaignRound).where(CampaignRound.title == "Win a free trip to Tokyo")
    ).all()
    assert len(rounds) == 1
    assert rounds[0].official_url is None


def test_aggregator_evidence_kind(db, monkeypatch):
    from app.services.raffle.provenance import attempt_official_evidence

    src = Source(
        id=new_id(),
        name="agg2",
        base_url="https://agg2.example.org/",
        kind="community",
        module="raffle",
        status="active",
    )
    db.add(src)
    db.flush()
    from app.adapters.base import FetchResult, ParsedSignal

    materialize_raffle_candidates(
        db,
        src,
        [
            ParsedSignal(
                title="Win a free trip test",
                raw_claim_text="Win a free trip",
                url="https://agg2.example.org/y",
                deal_types=["flight_giveaway"],
                confidence="low",
            )
        ],
    )
    db.commit()
    r = db.scalars(
        select(CampaignRound).where(CampaignRound.title == "Win a free trip test")
    ).first()
    assert r is not None

    async def fake_fetch(self, url):
        return FetchResult(
            ok=True,
            url=url,
            status_code=200,
            text="<html>ok</html>",
            content_hash="x",
            final_url=url,
        )

    monkeypatch.setattr(HttpxFetchAdapter, "fetch", fake_fetch)
    res = asyncio.run(attempt_official_evidence(db, Settings(), r))
    assert res["ok"] is True
    assert res["kind"] == "third_party_reporting"
    ev = db.get(Evidence, res["evidence_id"])
    assert ev is not None
    assert ev.field_path == "aggregator_page_snapshot"
    tags = json.loads(r.tags or "{}")
    assert tags.get("last_provenance_ok") is True
