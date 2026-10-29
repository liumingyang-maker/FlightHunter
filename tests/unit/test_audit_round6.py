"""第六轮：发现 limit 顺序 + 细则语义边界。"""

from __future__ import annotations

import asyncio

from app.config import Settings
from app.core.ids import new_id
from app.db.session import ensure_default_sources
from app.models import Campaign, CampaignRound, Organizer, Source
from app.services.discovery.service import run_discovery
from app.services.verify.service import complete_verify_from_html


def test_module_filter_before_limit(db, settings: Settings):
    ensure_default_sources(db, settings)
    for i in range(5):
        db.add(
            Source(
                id=new_id(),
                name=f"trip-src-{i}",
                base_url=f"https://example{i}.org/",
                kind="community",
                module="trip",
                status="active",
            )
        )
    db.commit()
    results = asyncio.run(run_discovery(db, settings, module="fare", dry_run=True, limit=2))
    assert results, "fare 来源被 limit 挤出"


def _round(db) -> CampaignRound:
    org = Organizer(id=new_id(), name="O", official_domain="example.org")
    db.add(org)
    db.flush()
    camp = Campaign(id=new_id(), organizer_id=org.id, program_key=f"p{new_id()[:8]}", name="C")
    db.add(camp)
    db.flush()
    r = CampaignRound(
        id=new_id(),
        campaign_id=camp.id,
        edition_key="e",
        title="Win flights",
        organizer_name="O",
        official_url="https://example.org/campaign",
        verify_status="candidate",
    )
    db.add(r)
    db.flush()
    return r


def test_to_be_determined_rejected(db):
    r = _round(db)
    html = (
        "<html><head><title>Win a Trip Giveaway</title></head>"
        "<body><p>Enter to win. No purchase necessary. Closes 2027-03-01. "
        "<h2>Official Rules</h2><p>Eligibility: To be determined</p>"
        '<a href="/rules">Official Rules</a></p></body></html>'
    )
    complete_verify_from_html(db, r, html, source_url="https://example.org/campaign")
    db.commit()
    assert r.verify_status == "needs_review"


def test_eligible_participants_must_accepted(db):
    r = _round(db)
    html = (
        "<html><head><title>Win a Trip Giveaway</title></head>"
        "<body><p>Enter to win. No purchase necessary. Closes 2027-03-01. "
        "<h2>Official Rules</h2>"
        "<p>Eligible participants must be at least 18 years old and residents.</p>"
        '<a href="/rules">Official Rules</a></p></body></html>'
    )
    complete_verify_from_html(db, r, html, source_url="https://example.org/campaign")
    db.commit()
    assert r.verify_status == "verified"
