"""调度 / 通知 / 提取 / 核实 测试。"""

from __future__ import annotations

from datetime import date

from app.config import Settings
from app.core.ids import new_id
from app.models import Campaign, CampaignRound, Organizer
from app.scheduler.jobs import claim_due_subscriptions, mark_offline_recovery, run_due_scans
from app.schemas.domain import TripCreate
from app.services.extract.service import extract_official_fields
from app.services.notify.service import list_unread, mark_read, notify
from app.services.trips.service import create_trip
from app.services.verify.service import complete_verify_from_html


def test_notify_dedup(db):
    n1 = notify(db, kind="deadline", title="报名将截止", body="x")
    n2 = notify(db, kind="deadline", title="报名将截止", body="x")
    db.commit()
    assert n1.id == n2.id
    unread = list_unread(db)
    assert any(n.id == n1.id for n in unread)
    mark_read(db, n1.id)
    db.commit()
    unread2 = list_unread(db)
    assert all(n.id != n1.id for n in unread2)


def test_extract_fields_conservative(db):
    html = """
    <html><head><title>Win a Trip Official</title></head>
    <body>
      <p>No purchase necessary. Enter by 2027/5/10.</p>
      <p>Must purchase a ticket to enter.</p>
    </body></html>
    """
    result = extract_official_fields(html, source_url="https://example.org/rules")
    assert result.title == "Win a Trip Official"
    paths = {f.field_path for f in result.fields}
    assert "purchase_required" in paths
    # 既有 no purchase 又有 must purchase → 至少提取到一次
    purchase_fields = [f for f in result.fields if f.field_path == "purchase_required"]
    assert purchase_fields


def test_verify_needs_review_without_enough_evidence(db):
    org = Organizer(id=new_id(), name="O")
    db.add(org)
    db.flush()
    camp = Campaign(id=new_id(), organizer_id=org.id, program_key="pk1", name="C")
    db.add(camp)
    db.flush()
    r = CampaignRound(
        id=new_id(),
        campaign_id=camp.id,
        edition_key="e",
        title="T",
        organizer_name="O",
        official_url="https://example.org/r",
        verify_status="candidate",
    )
    db.add(r)
    db.flush()
    complete_verify_from_html(db, r, "<html><body>hello</body></html>")
    db.commit()
    assert r.verify_status == "needs_review"


def test_verify_with_evidence_can_pass(db):
    org = Organizer(id=new_id(), name="O2")
    db.add(org)
    db.flush()
    camp = Campaign(id=new_id(), organizer_id=org.id, program_key="pk2", name="C2")
    db.add(camp)
    db.flush()
    r = CampaignRound(
        id=new_id(),
        campaign_id=camp.id,
        edition_key="e2",
        title="T2",
        organizer_name="O2",
        official_url="https://example.org/r2",
        verify_status="candidate",
    )
    db.add(r)
    db.flush()
    html = (
        "<html><head><title>Official Flight Giveaway</title></head>"
        "<body><p>No purchase necessary. Closes 2027-03-01.</p></body></html>"
    )
    complete_verify_from_html(db, r, html)
    db.commit()
    assert r.verify_status == "verified"


def test_scheduler_dry_run(db, settings: Settings):
    create_trip(
        db,
        settings,
        TripCreate(
            label="调度行程",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=False,
        ),
    )
    db.commit()
    due = claim_due_subscriptions(db)
    assert len(due) >= 1
    runs = run_due_scans(db, settings, dry_run=True, limit=5)
    db.commit()
    assert len(runs) >= 1
    assert all(r.dry_run for r in runs)
    assert all(r.status == "completed" for r in runs)


def test_offline_recovery_not_fake_scan(db, settings: Settings):
    trip = create_trip(
        db,
        settings,
        TripCreate(
            label="离线行程",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            demo_only=False,
        ),
    )
    trip.scan_status = "interrupted"
    db.commit()
    mark_offline_recovery(db, trip)
    db.commit()
    assert trip.scan_status == "recovery_pending"
    assert "中断" in (trip.scan_message or "")
