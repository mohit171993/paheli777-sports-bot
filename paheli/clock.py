"""Timezone helpers. Kickoff instants are stored as UTC ISO-8601 strings."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("Asia/Kolkata")


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return ensure_aware(value)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return ensure_aware(datetime.fromisoformat(text))
    except ValueError:
        return None


def utc_iso(value: datetime) -> str:
    return ensure_aware(value).astimezone(timezone.utc).isoformat()


def format_kickoff(value, tz: ZoneInfo = APP_TIMEZONE) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return "Time TBC"
    return parsed.astimezone(tz).strftime("%d %b, %H:%M IST")


def local_date(value: datetime, tz: ZoneInfo = APP_TIMEZONE):
    return ensure_aware(value).astimezone(tz).date()


def week_bounds(now: datetime, tz: ZoneInfo = APP_TIMEZONE) -> tuple[str, str]:
    """Monday 00:00 through next Monday 00:00 in `tz`, returned as UTC ISO strings."""
    local = ensure_aware(now).astimezone(tz)
    start = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(days=7)
    return utc_iso(start), utc_iso(end)


def parse_quiet_hours(spec: str) -> tuple[int, int] | None:
    text = (spec or "").strip()
    if not text:
        return None
    parts = text.split("-", 1)
    if len(parts) != 2:
        return None
    try:
        start, end = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= start <= 23 and 0 <= end <= 23) or start == end:
        return None
    return start, end


def in_quiet_hours(now: datetime, window: tuple[int, int] | None, tz: ZoneInfo = APP_TIMEZONE) -> bool:
    if not window:
        return False
    start, end = window
    hour = ensure_aware(now).astimezone(tz).hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end
