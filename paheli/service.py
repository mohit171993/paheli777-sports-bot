"""Fetch fixtures and headlines, then persist anything we can score later."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from paheli.config import Config
from paheli.db import Database
from paheli.highlightly import HighlightlyClient, HighlightlyError
from paheli.matches import parse_match
from paheli.scoring import iso_utc
from paheli.store import settle_finished, upsert_fixtures


logger = logging.getLogger(__name__)


async def refresh_matches(
    cfg: Config,
    db: Database,
    api: HighlightlyClient,
    *,
    sports: list[str],
    dates: list[str],
) -> list[dict]:
    found: dict[str, dict] = {}
    errors: list[Exception] = []
    for sport in sports:
        for date_text in dates:
            try:
                raw_matches = await api.matches_for_date(sport, date_text, cfg.timezone_name)
            except Exception as exc:
                errors.append(exc)
                logger.warning("Match fetch failed for %s %s: %s", sport, date_text, exc)
                continue
            for raw in raw_matches:
                parsed = parse_match(raw, sport)
                if parsed:
                    found[parsed["match_key"]] = parsed
    fixtures = list(found.values())
    if fixtures:
        upsert_fixtures(db, fixtures)
        settle_finished(db)
    elif errors:
        raise errors[0]
    return fixtures


async def load_highlights(
    cfg: Config,
    api: HighlightlyClient,
    sport: str,
    date_text: str,
) -> list[dict]:
    raw_items = await api.highlights(sport, date_text, cfg.timezone_name)
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        category = str(raw.get("category") or "").casefold()
        if category == "live-coverage":
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        items.append(
            {
                "title": title,
                "description": str(raw.get("description") or "").strip(),
                "url": str(raw.get("url") or "").strip(),
                "category": category,
            }
        )
    return items[:8]


def local_dates(cfg: Config, now: datetime, back: int = 0, forward: int = 0) -> list[str]:
    today = now.astimezone(cfg.timezone).date()
    dates = []
    for offset in range(-back, forward + 1):
        dates.append((today + timedelta(days=offset)).isoformat())
    return dates


def day_bounds_iso(cfg: Config, now: datetime, day_offset: int = 0) -> tuple[str, str]:
    local = now.astimezone(cfg.timezone)
    start = (local + timedelta(days=day_offset)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(days=1)
    return iso_utc(start), iso_utc(end)


def api_error_text(exc: Exception) -> str:
    if isinstance(exc, HighlightlyError):
        if exc.kind == "not_configured":
            return (
                "⚠️ <b>Sports data is not configured yet.</b>\n\n"
                "Add HIGHLIGHTLY_API_KEY and try again."
            )
        if exc.kind == "auth":
            return "⚠️ Sports data authentication failed. Check HIGHLIGHTLY_API_KEY."
        if exc.kind == "rate_limit":
            return "⏳ Sports data limit reached. Please try again in a few minutes."
        if exc.kind == "http":
            return f"⚠️ Sports data provider returned HTTP {exc.status}."
    if isinstance(exc, RuntimeError) and "HIGHLIGHTLY" in str(exc):
        return "⚠️ <b>Sports data is not configured yet.</b>"
    return "⚠️ Sports data is temporarily unavailable. Please try again shortly."
