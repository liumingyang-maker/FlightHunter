"""时间与时区工具。统一使用 UTC 存储 + IANA 时区原文。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def to_utc(dt: datetime) -> datetime:
    """将 naive（按 UTC 解释）或 aware 时间转为 aware UTC。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def local_date_in_tz(dt_utc: datetime, tz_name: str) -> date:
    return to_utc(dt_utc).astimezone(ZoneInfo(tz_name)).date()


def parse_iana(tz_name: str) -> ZoneInfo:
    return ZoneInfo(tz_name)


def ensure_valid_date_range(start: date, end: date) -> None:
    if end < start:
        raise ValueError("结束日期不能早于开始日期")


def date_range_days(start: date, end: date) -> int:
    return (end - start).days + 1


def overlaps(start_a: date, end_a: date, start_b: date, end_b: date) -> bool:
    """两个闭区间日期是否重叠。"""
    return start_a <= end_b and start_b <= end_a


def period_key(d: date, tz_name: str) -> str:
    """报名/领取周期键：本地日期 + 时区。"""
    return f"{d.isoformat()}@{tz_name}"
