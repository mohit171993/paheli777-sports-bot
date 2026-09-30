"""Environment configuration for the Paheli777 bot."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from zoneinfo import ZoneInfo


BRAND_NAME = "Paheli777"
DEFAULT_TIMEZONE = "Asia/Kolkata"


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_user_id: int | None
    highlightly_api_key: str
    database_url: str
    brand_url: str
    timezone_name: str
    timezone: ZoneInfo
    reminder_lead_minutes: int


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a numeric Telegram user id") from exc


def _brand_url() -> str:
    raw = os.getenv("BRAND_URL", "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return "https://" + raw


def load_config() -> Config:
    load_dotenv()
    timezone_name = os.getenv("APP_TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        timezone = ZoneInfo(timezone_name)
    except Exception as exc:
        raise RuntimeError(f"APP_TIMEZONE is not a valid timezone: {timezone_name}") from exc

    lead_raw = os.getenv("REMINDER_LEAD_MINUTES", "45").strip() or "45"
    try:
        lead_minutes = int(lead_raw)
    except ValueError as exc:
        raise RuntimeError("REMINDER_LEAD_MINUTES must be an integer") from exc
    if lead_minutes < 5 or lead_minutes > 24 * 60:
        raise RuntimeError("REMINDER_LEAD_MINUTES must be between 5 and 1440")

    return Config(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        admin_user_id=_optional_int("ADMIN_USER_ID"),
        highlightly_api_key=os.getenv("HIGHLIGHTLY_API_KEY", "").strip(),
        database_url=os.getenv("DATABASE_URL", "").strip(),
        brand_url=_brand_url(),
        timezone_name=timezone_name,
        timezone=timezone,
        reminder_lead_minutes=lead_minutes,
    )


def is_admin(cfg: Config, user_id: int | None) -> bool:
    return (
        cfg.admin_user_id is not None
        and user_id is not None
        and int(user_id) == int(cfg.admin_user_id)
    )
