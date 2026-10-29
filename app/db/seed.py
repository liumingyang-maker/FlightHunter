"""安全种子：仅 fixture 演示数据，不冒充真实活动。"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.ids import new_id, sha256_text
from app.db.session import ensure_default_sources
from app.models import (
    BenefitOffer,
    BenefitOrganizer,
    Campaign,
    CampaignRound,
    FareDeal,
    FareDealSignal,
    FareWatch,
    Organizer,
    Profile,
    Source,
    Trip,
    TripScanSubscription,
)


def _load_example_json(project_root: Path, name: str) -> dict | None:
    for candidate in (
        project_root / "fixtures" / name,
        project_root / "examples" / name,
    ):
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return None


def seed_safe_fixtures(session: Session, settings: Settings, *, project_root: Path) -> dict:
    """写入安全演示数据。幂等：重复执行不重复插入关键 fixture。"""
    ensure_default_sources(session, settings)
    summary = {
        "profiles": 0,
        "campaigns": 0,
        "trips_demo": 0,
        "benefit_offers": 0,
        "fare_deals": 0,
        "fare_watches": 0,
        "notes": [],
    }

    # --- Profile 演示（明确未填真实国籍） ---
    existing_profile = session.scalar(select(Profile).where(Profile.display_name == "演示用户A"))
    if existing_profile is None:
        session.add(
            Profile(
                id=new_id(),
                display_name="演示用户A",
                country_of_residence=None,
                nationality=None,
                preferred_departure_airports=json.dumps(["CKG", "TFU"]),
                preferred_party_size=2,
            )
        )
        summary["profiles"] += 1

    # --- 抽奖 fixture campaign/round（demo_only） ---
    organizer = session.scalar(select(Organizer).where(Organizer.name == "演示航司（fixture）"))
    if organizer is None:
        organizer = Organizer(
            id=new_id(),
            name="演示航司（fixture）",
            official_domain="example.org",
            website_url="https://example.org",
            trust_notes="仅用于 schema/流程演示，非真实主办方",
        )
        session.add(organizer)
        session.flush()

    campaign = session.scalar(
        select(Campaign).where(Campaign.program_key == "demo-flight-giveaway-2027")
    )
    if campaign is None:
        campaign = Campaign(
            id=new_id(),
            organizer_id=organizer.id,
            program_key="demo-flight-giveaway-2027",
            name="演示：双人往返机票抽奖（fixture）",
            category="flight_giveaway",
            legacy_seed=False,
        )
        session.add(campaign)
        session.flush()
        summary["campaigns"] += 1

        round_ = CampaignRound(
            id=new_id(),
            campaign_id=campaign.id,
            edition_key="2027-demo",
            title="演示活动期 · 双人日本往返机票（fixture）",
            organizer_name="演示航司（fixture）",
            official_url="https://example.org/campaigns/demo-2027",
            prize_summary="双人经济舱往返机票（模拟，不可兑现）",
            entry_timezone="Asia/Tokyo",
            verify_status="candidate",
            automation_policy="unknown",
            frequency="once_per_edition",
            limit_scope="person",
            demo_only=True,
        )
        session.add(round_)
    else:
        summary["notes"].append("campaign fixture 已存在，跳过")

    # --- Trip demo fixture（不会自动成为用户真实行程） ---
    demo_trip = session.scalar(select(Trip).where(Trip.label == "2027 日本旅行（演示）"))
    if demo_trip is None:
        trip = Trip(
            id=new_id(),
            label="2027 日本旅行（演示）",
            destination_country_code="JP",
            local_start_date=date(2027, 5, 10),
            local_end_date=date(2027, 5, 30),
            timezone="Asia/Tokyo",
            interests=json.dumps(["shopping", "food", "attractions", "events"]),
            created_from="seed_fixture",
            demo_only=True,
            scan_registered=False,
        )
        session.add(trip)
        session.flush()
        summary["trips_demo"] += 1
        session.add(
            TripScanSubscription(
                id=new_id(),
                trip_id=trip.id,
                source_group="JP_national",
                task_type="benefit_discovery",
                policy_hash=sha256_text("JP_national|benefit_discovery|v1"),
                enabled=True,
                interval_hours=settings.trip_benefits.daily_discovery_interval_hours,
            )
        )
        session.add(
            TripScanSubscription(
                id=new_id(),
                trip_id=trip.id,
                source_group="JP_national",
                task_type="fare_monitor",
                policy_hash=sha256_text("JP_national|fare_monitor|v1"),
                enabled=True,
                interval_hours=settings.airfare_radar.publicly_shared_deals_scan_minutes // 60 or 1,
            )
        )
        summary["notes"].append("已创建 demo 行程 fixture（demo_only=true）")
    else:
        summary["notes"].append("demo 行程已存在，跳过")

    # --- Benefit offer fixture ---
    existing_offer = session.scalar(
        select(BenefitOffer).where(BenefitOffer.title.like("演示：成田机场%"))
    )
    if existing_offer is None:
        bo_org = session.scalar(
            select(BenefitOrganizer).where(BenefitOrganizer.name == "演示商店（fixture）")
        )
        if bo_org is None:
            bo_org = BenefitOrganizer(
                id=new_id(),
                name="演示商店（fixture）",
                official_domain="example.org",
                website_url="https://example.org/shop",
                country_code="JP",
            )
            session.add(bo_org)
            session.flush()
        session.add(
            BenefitOffer(
                id=new_id(),
                organizer_id=bo_org.id,
                organizer_name="演示商店（fixture）",
                title="演示：成田机场免税 95 折券（fixture）",
                category="shopping_discount",
                claim_method="PUBLIC_DISPLAY",
                official_url="https://example.org/offers/nrt-95",
                country_codes=json.dumps(["JP"]),
                city_codes=json.dumps(["NRT"]),
                date_certainty="unconfirmed",
                conditions=json.dumps({"payment_network": "Visa", "currency": "JPY"}),
                offer_status="candidate",
                demo_only=True,
            )
        )
        summary["benefit_offers"] += 1

    # --- Fare deal + signal fixture ---
    fare_demo = session.scalar(select(FareDeal).where(FareDeal.dedup_key == "demo:CKG-NRT:2027-05"))
    if fare_demo is None:
        fare_demo = FareDeal(
            id=new_id(),
            dedup_key="demo:CKG-NRT:2027-05",
            origin="CKG",
            destination="NRT",
            travel_date_hint="2027-05 灵活",
            travel_window_start=date(2027, 5, 1),
            travel_window_end=date(2027, 5, 31),
            airline=None,
            cabin="economy",
            offer_subtypes=json.dumps(["flash_sale", "unclassified"]),
            status="price_unconfirmed",
            risk_tier="needs_review",
            first_seen_utc=datetime.now(UTC),
            last_seen_utc=datetime.now(UTC),
            link="https://example.org/deals/demo-ckg-nrt",
        )
        session.add(fare_demo)
        session.flush()
        community = session.scalar(
            select(Source).where(Source.base_url.like("%smzdm.com/fenlei/guowaijipiao%"))
        )
        session.add(
            FareDealSignal(
                id=new_id(),
                deal_id=fare_demo.id,
                source_id=community.id if community else None,
                original_url="https://example.org/deals/demo-ckg-nrt",
                title="【fixture】网友爆料 CKG-NRT 双人含税示例价",
                raw_claim_text="示例文案：两人往返含税 999/人（虚构 fixture，非现价）",
                published_at_utc=datetime.now(UTC),
                reported_total=1998,
                currency="CNY",
                party_size=2,
                taxes_included=True,
                origin_airport="CKG",
                destination_airport="NRT",
                deal_types=json.dumps(["flash_sale"]),
                source_type="community",
                signal_status="parsed",
                confidence="low",
                user_supplied=False,
            )
        )
        summary["fare_deals"] += 1

    # --- Fare watch ---
    existing_watch = session.scalar(
        select(FareWatch).where(FareWatch.name == "演示：重庆出发全球（fixture）")
    )
    if existing_watch is None:
        session.add(
            FareWatch(
                id=new_id(),
                name="演示：重庆出发全球（fixture）",
                origin_airports=json.dumps(["CKG", "TFU"]),
                destination_scope="any",
                depart_window_start=date(2027, 5, 1),
                depart_window_end=date(2027, 5, 31),
                trip_type="round_trip",
                adults=2,
                max_total_cost_cny=None,
                accept_error_fares=False,
                enabled=False,  # 默认不自动开扫，onboarding 后用户确认
            )
        )
        summary["fare_watches"] += 1

    session.flush()
    summary["notes"].append("seed 完成：全部为 demo fixture，不代表真实可买机票/活动")
    return summary


def import_design_fixtures(
    session: Session,
    settings: Settings,
    *,
    travel_plan_path: Path | None,
    fare_signal_path: Path | None,
) -> dict:
    """导入设计包提供的 example JSON。"""
    result = {"travel_plan": None, "fare_signal": None}
    if travel_plan_path and travel_plan_path.is_file():
        data = json.loads(travel_plan_path.read_text(encoding="utf-8"))
        label = data.get("name") or data.get("label") or "导入的模拟行程"
        existing = session.scalar(select(Trip).where(Trip.label == label))
        if existing is None:
            trip = Trip(
                id=new_id(),
                label=label,
                destination_country_code=(data.get("destination") or {}).get("country_code", "XX"),
                local_start_date=date.fromisoformat(data["start_date_local"]),
                local_end_date=date.fromisoformat(data["end_date_local"]),
                timezone=data.get("timezone", "UTC"),
                interests=json.dumps(data.get("interests") or []),
                created_from="seed_fixture",
                demo_only=bool(data.get("demo_only", True)),
                scan_registered=False,
            )
            session.add(trip)
            result["travel_plan"] = trip.id
    if fare_signal_path and fare_signal_path.is_file():
        data = json.loads(fare_signal_path.read_text(encoding="utf-8"))
        # 简单映射为 signal；无 deal 时创建 fixture deal
        origin = data.get("origin_airport") or data.get("origin")
        dest = data.get("destination_airport") or data.get("destination")
        dedup = f"import:{origin}-{dest}:{data.get('travel_window') or 'flex'}"
        deal = session.scalar(select(FareDeal).where(FareDeal.dedup_key == dedup))
        if deal is None:
            deal = FareDeal(
                id=new_id(),
                dedup_key=dedup,
                origin=origin,
                destination=dest,
                travel_date_hint=str(data.get("travel_window")),
                offer_subtypes=json.dumps(data.get("deal_types") or ["unclassified"]),
                status="price_unconfirmed",
                risk_tier="needs_review",
                first_seen_utc=datetime.now(UTC),
                last_seen_utc=datetime.now(UTC),
                link=data.get("original_url"),
            )
            session.add(deal)
            session.flush()
        session.add(
            FareDealSignal(
                id=new_id(),
                deal_id=deal.id,
                original_url=data.get("original_url"),
                title=data.get("title") or "导入的机票爆料（fixture）",
                raw_claim_text=data.get("raw_claim_text") or "",
                reported_total=data.get("reported_total"),
                currency=data.get("currency"),
                party_size=data.get("party_size"),
                taxes_included=data.get("taxes_included"),
                origin_airport=origin,
                destination_airport=dest,
                deal_types=json.dumps(data.get("deal_types") or []),
                source_type="user_supplied" if data.get("user_supplied", True) else "community",
                signal_status="parsed",
                confidence="low",
                user_supplied=True,
            )
        )
        result["fare_signal"] = deal.id
    session.flush()
    return result
