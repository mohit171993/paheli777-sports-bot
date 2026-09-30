"""Environment configuration. Nothing here is shared with another brand."""

from __future__ import annotations

import os
from dataclasses import dataclass

from paheli.clock import parse_quiet_hours


def resolve_database_url(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return "sqlite:///paheli777.db"
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    return value


def _brand_url(raw: str | None) -> str:
    value = (raw or "").strip().rstrip("/")
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return "https://" + value


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_user_id: int
    highlightly_api_key: str = ""
    database_url: str = "sqlite:///paheli777.db"
    brand_url: str = ""
    brand_name: str = "Paheli777"
    timezone_name: str = "Asia/Kolkata"
    reminder_lead_minutes: int = 45
    notable_per_sport: int = 6
    reminder_quiet_hours: str = ""
    sync_interval_seconds: int = 300
    highlightly_base_url: str = "https://sports.highlightly.net"

    @property
    def quiet_window(self) -> tuple[int, int] | None:
        return parse_quiet_hours(self.reminder_quiet_hours)

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Settings":
        source = env if env is not None else os.environ
        token = str(source.get("BOT_TOKEN", "")).strip()
        admin_raw = str(source.get("ADMIN_USER_ID", "")).strip()
        if not token:
            raise RuntimeError("BOT_TOKEN environment variable is required")
        if not admin_raw:
            raise RuntimeError("ADMIN_USER_ID environment variable is required")
        try:
            admin_id = int(admin_raw)
        except ValueError as exc:
            raise RuntimeError("ADMIN_USER_ID must be an integer") from exc
        lead = _positive_int(source.get("REMINDER_LEAD_MINUTES"), 45)
        notable = _positive_int(source.get("NOTABLE_PER_SPORT"), 6)
        interval = _positive_int(source.get("SYNC_INTERVAL_SECONDS"), 300)
        return cls(
            bot_token=token,
            admin_user_id=admin_id,
            highlightly_api_key=str(source.get("HIGHLIGHTLY_API_KEY", "")).strip(),
            database_url=resolve_database_url(source.get("DATABASE_URL")),
            brand_url=_brand_url(source.get("BRAND_URL")),
            reminder_lead_minutes=lead,
            notable_per_sport=min(notable, 8),
            reminder_quiet_hours=str(source.get("REMINDER_QUIET_HOURS", "")).strip(),
            sync_interval_seconds=max(interval, 60),
            highlightly_base_url=str(
                source.get("HIGHLIGHTLY_BASE_URL", "https://sports.highlightly.net")
            ).strip()
            or "https://sports.highlightly.net",
        )


def _positive_int(value, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
