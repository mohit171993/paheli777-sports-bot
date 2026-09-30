"""Background scoring refresh and pre-kickoff pick reminders."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden

from paheli.matches import DIVIDER
from paheli.scoring import due_for_reminder, in_quiet_hours, iso_utc, parse_iso
from paheli.service import local_dates, refresh_matches
from paheli.store import (
    fixtures_between,
    mark_reminder_sent,
    reminders_paused,
    settle_finished,
    users_to_remind,
)


logger = logging.getLogger(__name__)
MAX_SENDS_PER_RUN = 80


def _runtime(context):
    return context.application.bot_data["runtime"]


async def settle_job(context) -> None:
    runtime = _runtime(context)
    now = datetime.now(timezone.utc)
    dates = local_dates(runtime.cfg, now, back=1, forward=0)
    try:
        await refresh_matches(
            runtime.cfg,
            runtime.db,
            runtime.api,
            sports=["cricket", "football"],
            dates=dates,
        )
    except Exception:
        logger.exception("Scheduled score refresh failed")
        settle_finished(runtime.db, now)


async def reminder_job(context) -> None:
    runtime = _runtime(context)
    now = datetime.now(timezone.utc)
    if reminders_paused(runtime.db):
        return
    if in_quiet_hours(now, runtime.cfg.timezone):
        return

    dates = local_dates(runtime.cfg, now, back=0, forward=1)
    try:
        await refresh_matches(
            runtime.cfg,
            runtime.db,
            runtime.api,
            sports=["cricket", "football"],
            dates=dates,
        )
    except Exception:
        logger.exception("Reminder match refresh failed")

    fixtures = fixtures_between(
        runtime.db,
        iso_utc(now - timedelta(hours=1)),
        iso_utc(now + timedelta(hours=30)),
    )
    sent = 0
    for fixture in fixtures:
        if sent >= MAX_SENDS_PER_RUN:
            break
        kickoff = parse_iso(fixture["kickoff"])
        if not due_for_reminder(
            kickoff=kickoff,
            now=now,
            lead_minutes=runtime.cfg.reminder_lead_minutes,
            status=fixture["status"],
            already_picked=False,
            already_sent=False,
            quiet=False,
        ):
            continue
        user_ids = users_to_remind(runtime.db, fixture["match_key"])
        if not user_ids:
            continue
        minutes = max(1, int((kickoff - now).total_seconds() // 60))
        icon = "🏏" if fixture["sport"] == "cricket" else "⚽"
        text = (
            f"⏰ <b>PAHELI777 REMINDER</b>\n{DIVIDER}\n\n"
            f"{icon} <b>{escape(str(fixture['home_name']))} vs {escape(str(fixture['away_name']))}</b>\n"
            f"Starts in about {minutes} min.\n\n"
            "You have not picked a winner yet. Picks lock at kick-off."
        )
        callback = f"pick:{fixture['match_key']}"
        markup = None
        if len(callback.encode("utf-8")) <= 64:
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🎯 Make your pick", callback_data=callback)]]
            )
        for user_id in user_ids:
            if sent >= MAX_SENDS_PER_RUN:
                break
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )
            except (Forbidden, BadRequest):
                mark_reminder_sent(runtime.db, user_id, fixture["match_key"], now)
                continue
            except Exception:
                logger.exception("Reminder failed for user %s", user_id)
                continue
            mark_reminder_sent(runtime.db, user_id, fixture["match_key"], now)
            sent += 1
            await asyncio.sleep(0.05)
    if sent:
        logger.info("Sent %s prediction reminders", sent)
