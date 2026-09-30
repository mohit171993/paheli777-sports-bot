"""Sync the day's card, settle finished matches, and nudge users who have not picked."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram.error import Forbidden, RetryAfter

from paheli.clock import APP_TIMEZONE, in_quiet_hours, local_date
from paheli.config import Settings
from paheli.formatters import format_reminder
from paheli.highlightly import HighlightlyClient, HighlightlyError
from paheli.keyboards import reminder_keyboard
from paheli.matches import normalize_fixture, select_notable
from paheli.scoring import Outcome, interpret_match, should_remind
from paheli.store import Store

logger = logging.getLogger(__name__)

MAX_REMINDERS_PER_RUN = 30


async def sync_slate(store: Store, client: HighlightlyClient, settings: Settings, now: datetime) -> dict:
    today = local_date(now, APP_TIMEZONE)
    dates = [today - timedelta(days=1), today, today + timedelta(days=1)]
    counts = {"football": 0, "cricket": 0}
    scored_from_list = 0
    errors: list[str] = []
    for sport in ("football", "cricket"):
        collected: dict[str, list[dict]] = {}
        for day in dates:
            try:
                raws = await client.matches(sport, day.isoformat())
            except HighlightlyError as exc:
                errors.append(f"{sport} {day.isoformat()}: {exc}")
                logger.warning("Match list failed: %s", exc)
                continue
            normalized = []
            for raw in raws:
                item = normalize_fixture(raw, sport, day.isoformat())
                if item:
                    normalized.append(item)
            collected[day.isoformat()] = normalized
        chosen = {
            item["match_key"]
            for item in select_notable(
                collected.get(today.isoformat(), []),
                sport,
                settings.notable_per_sport,
            )
        }
        counts[sport] = len(chosen)
        for day_items in collected.values():
            for item in day_items:
                already = store.get_match(item["match_key"])
                if item["match_key"] not in chosen and not already:
                    continue
                store.upsert_match(item, notable=item["match_key"] in chosen, now=now)
                if item["status"] == "void" or (item["status"] == "finished" and item.get("winner")):
                    scored_from_list += store.apply_outcome(
                        item["match_key"], _outcome_from_item(item), now
                    )
    return {
        "football": counts["football"],
        "cricket": counts["cricket"],
        "errors": errors,
        "settled": scored_from_list,
    }


def _outcome_from_item(item: dict) -> Outcome:
    return Outcome(
        status=item.get("status") or "unknown",
        winner=item.get("winner"),
        home_score=item.get("home_score"),
        away_score=item.get("away_score"),
        score_display=item.get("score_display") or "",
        report=item.get("report") or "",
        state_description=item.get("state_description") or "",
    )


async def settle_open(store: Store, client: HighlightlyClient, now: datetime) -> int:
    scored = 0
    for match in store.matches_to_refresh():
        try:
            raw = await client.match(match["sport"], match["provider_id"])
        except HighlightlyError as exc:
            logger.warning("Match refresh failed for %s: %s", match["match_key"], exc)
            continue
        if not isinstance(raw, dict) or not raw:
            continue
        outcome = interpret_match(raw, match["sport"])
        scored += store.apply_outcome(match["match_key"], outcome, now)
    return scored


async def sync_and_settle(store: Store, client: HighlightlyClient, settings: Settings, now: datetime | None = None) -> dict:
    moment = now or datetime.now(timezone.utc)
    if not settings.highlightly_api_key:
        return {"football": 0, "cricket": 0, "errors": ["HIGHLIGHTLY_API_KEY is not configured"], "settled": 0}
    summary = await sync_slate(store, client, settings, moment)
    summary["settled"] = int(summary.get("settled") or 0) + await settle_open(store, client, moment)
    return summary


async def send_reminders(bot, store: Store, settings: Settings, now: datetime | None = None) -> int:
    moment = now or datetime.now(timezone.utc)
    if store.get_setting("reminders_paused", "0") == "1":
        return 0
    if in_quiet_hours(moment, settings.quiet_window, APP_TIMEZONE):
        return 0
    today = local_date(moment, APP_TIMEZONE).isoformat()
    matches = store.list_notable(today)
    users = store.subscribed_user_ids()
    sent = 0
    for match in matches:
        for user_id in users:
            if sent >= MAX_REMINDERS_PER_RUN:
                return sent
            if not should_remind(
                match["kickoff"],
                moment,
                settings.reminder_lead_minutes,
                store.has_pick(user_id, match["match_key"]),
                False,
                match.get("status"),
            ):
                continue
            if not store.claim_reminder(user_id, match["match_key"], moment):
                continue
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=format_reminder(match),
                    parse_mode="HTML",
                    reply_markup=reminder_keyboard(match["match_key"]),
                    disable_web_page_preview=True,
                )
            except Forbidden:
                store.finish_reminder(user_id, match["match_key"], "failed")
                store.set_subscribed(user_id, False, moment)
                logger.info("User %s blocked the bot; alerts turned off", user_id)
                continue
            except RetryAfter as exc:
                store.finish_reminder(user_id, match["match_key"], "failed")
                await asyncio.sleep(float(exc.retry_after))
                continue
            except Exception:
                store.finish_reminder(user_id, match["match_key"], "failed")
                logger.exception("Reminder failed for user %s", user_id)
                continue
            store.finish_reminder(user_id, match["match_key"], "sent")
            sent += 1
    return sent


async def run_maintenance(bot, store: Store, client: HighlightlyClient, settings: Settings) -> dict:
    summary = await sync_and_settle(store, client, settings)
    summary["reminded"] = await send_reminders(bot, store, settings)
    return summary
