"""行程导出：JSON / ICS（不含私密券码）。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import BenefitOffer, Trip, WalletItem


def trip_to_export_dict(session: Session, trip_id: str) -> dict:
    import json as _json

    from sqlalchemy import select

    trip = session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")
    segments = [
        {
            "country_code": s.country_code,
            "city_code": s.city_code,
            "city_name": s.city_name,
            "start_date": s.start_date.isoformat(),
            "end_date": s.end_date.isoformat(),
            "timezone": s.timezone,
        }
        for s in trip.segments
    ]
    trip_countries = {trip.destination_country_code} | {s["country_code"] for s in segments}
    wallet_out = []
    for w in session.scalars(select(WalletItem)).all():
        offer = session.get(BenefitOffer, w.offer_id)
        if offer is None:
            continue
        countries = set(_json.loads(offer.country_codes or "[]"))
        if countries & trip_countries or not countries:
            wallet_out.append(
                {
                    "offer_title": offer.title,
                    "state": w.state,
                    "redemption_state": w.redemption_state,
                    "official_url": w.official_url,
                }
            )

    return {
        "export_type": "flighthunter_trip_v1",
        "exported_at_utc": datetime.now(UTC).isoformat(),
        "contains_private_codes": False,
        "trip": {
            "id": trip.id,
            "label": trip.label,
            "destination_country_code": trip.destination_country_code,
            "local_start_date": trip.local_start_date.isoformat(),
            "local_end_date": trip.local_end_date.isoformat(),
            "timezone": trip.timezone,
            "demo_only": trip.demo_only,
            "segments": segments,
            "interests": _json.loads(trip.interests or "[]"),
        },
        "wallet_summary": wallet_out,
        "disclaimer": "导出不包含券码；已保存≠已领取≠已使用；示例数据不代表真实优惠",
    }


def trip_to_ics(session: Session, trip_id: str) -> str:
    """生成轻量 ICS；仅事件日期，无私密码。"""
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError("行程不存在")

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//FlightHunter//Trip//CN",
        "CALSCALE:GREGORIAN",
    ]

    def add_event(uid: str, summary: str, d: date, description: str) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        dstr = d.strftime("%Y%m%d")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}@flighthunter.local",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{dstr}",
                f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}",
                f"SUMMARY:{esc(summary)}",
                f"DESCRIPTION:{esc(description)}",
                "END:VEVENT",
            ]
        )

    add_event(
        f"trip-{trip.id}-start",
        f"出发：{trip.label}",
        trip.local_start_date,
        "FlightHunter 行程开始（不含私密券码）",
    )
    add_event(
        f"trip-{trip.id}-end",
        f"返程：{trip.label}",
        trip.local_end_date,
        "FlightHunter 行程结束",
    )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
