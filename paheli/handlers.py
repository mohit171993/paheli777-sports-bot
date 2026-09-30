"""Telegram command and callback handlers."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from paheli.config import is_admin
from paheli.copy import footer, help_text, t
from paheli.keyboards import (
    back_keyboard,
    leaderboard_keyboard,
    main_keyboard,
    pick_keyboard,
    prediction_keyboard,
    refresh_keyboard,
    score_prompt_keyboard,
    settings_keyboard,
    sport_keyboard,
    subscription_keyboard,
    website_keyboard,
)
from paheli.matches import (
    DIVIDER,
    format_match_list,
    format_news,
    match_card,
    parse_match,
    select_notable,
    sort_for_display,
    winner_label,
)
from paheli.scoring import (
    PickLocked,
    iso_utc,
    is_pick_locked,
    parse_iso,
    parse_score_text,
    prediction_streak,
    week_window,
)
from paheli.service import api_error_text, day_bounds_iso, load_highlights, local_dates, refresh_matches
from paheli.store import (
    admin_snapshot,
    fixtures_between,
    get_fixture,
    get_prediction,
    get_user,
    is_subscribed,
    predictions_for_user,
    record_event,
    record_start,
    reminders_paused,
    save_prediction,
    set_language,
    set_setting,
    set_subscribed,
    settle_finished,
    streak_flags,
    subscribed_user_ids,
    touch_user,
    track,
    upsert_fixtures,
    user_picks_between,
    user_point_total,
    user_rank,
    leaderboard,
)


logger = logging.getLogger(__name__)


def runtime(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["runtime"]


def remember(update: Update, db) -> int | None:
    user = update.effective_user
    if not user:
        return None
    touch_user(db, user.id, user.username, user.first_name)
    return user.id


def language(db, user_id: int) -> str:
    row = get_user(db, user_id)
    lang = str(row["language"]) if row and row.get("language") else "en"
    return lang if lang in {"en", "hi"} else "en"


async def respond(update: Update, text: str, markup) -> None:
    kwargs = {
        "parse_mode": "HTML",
        "reply_markup": markup,
        "disable_web_page_preview": True,
    }
    body = text[:4000]
    query = update.callback_query
    if query is not None:
        try:
            await query.edit_message_text(body, **kwargs)
        except BadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
            raise
        return
    message = update.effective_message
    if message is not None:
        await message.reply_text(body, **kwargs)


def _sports(scope: str) -> list[str]:
    if scope in {"cricket", "football"}:
        return [scope]
    return ["cricket", "football"]


def _board(fixtures: list[dict], sport: str | None) -> list[dict]:
    if sport in {"cricket", "football"}:
        pool = [item for item in fixtures if item["sport"] == sport]
        return select_notable(pool, limit=8)
    cricket = select_notable([item for item in fixtures if item["sport"] == "cricket"], limit=6)
    football = select_notable([item for item in fixtures if item["sport"] == "football"], limit=6)
    return cricket + football


def _format_board(matches: list[dict], tz, picked: int) -> str:
    lines = [
        "🎯 <b>TODAY'S PREDICTIONS</b>",
        DIVIDER,
        "",
        "Choose a match, call the winner, then optionally send the exact score.",
        "Correct winner = <b>3</b> points. Exact score = <b>+2</b>.",
        "Picks lock at kick-off.",
        "",
    ]
    if not matches:
        lines.append("No matches on the board for today. Check upcoming fixtures a little later.")
        return "\n".join(lines)
    lines.append(f"Your picks so far: <b>{picked}/{len(matches)}</b>")
    lines.append("")
    for sport, title in (("cricket", "🏏 <b>CRICKET</b>"), ("football", "⚽ <b>FOOTBALL</b>")):
        group = [item for item in matches if item["sport"] == sport]
        if not group:
            continue
        lines.append(title)
        lines.append("")
        for index, match in enumerate(group, start=1):
            lines.append(match_card(match, index, tz))
            lines.append("")
    return "\n".join(lines).strip()


def _format_pick(match: dict, prediction: dict | None, tz, locked: bool) -> str:
    lines = ["🎯 <b>MAKE YOUR PICK</b>", DIVIDER, "", match_card(match, None, tz), ""]
    if locked:
        lines.append("🔒 <b>Picks are locked.</b> Kick-off has passed or the match is already underway.")
    else:
        lines.append("Tap the winner. You can add an exact score on the next step.")
    if prediction:
        label = winner_label(str(prediction["winner"]), match)
        extra = ""
        if prediction.get("home_score") and prediction.get("away_score"):
            extra = f" ({prediction['home_score']} - {prediction['away_score']})"
        lines.append(f"Your call: <b>{escape(label)}</b>{escape(extra)}")
        if prediction.get("points") is not None:
            lines.append(f"Points: <b>{int(prediction['points'])}</b>")
    return "\n".join(lines)


def _person(row: dict) -> str:
    if row.get("username"):
        return "@" + str(row["username"])
    if row.get("first_name"):
        return str(row["first_name"])
    return str(row.get("user_id"))


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    lang = language(rt.db, user_id) if user_id else "en"
    await respond(update, t(lang, "welcome"), main_keyboard(rt.cfg.brand_url))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    context.user_data.pop("pending_score", None)
    if user_id:
        arg = context.args[0] if context.args else ""
        record_start(rt.db, user_id, arg)
    await show_home(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    remember(update, rt.db)
    await respond(update, help_text(), main_keyboard(rt.cfg.brand_url))


async def sports_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    remember(update, rt.db)
    api_state = "Connected" if rt.cfg.highlightly_api_key else "Missing API key"
    text = (
        "🏟 <b>PAHELI777 SPORTS</b>\n"
        f"{DIVIDER}\n\n"
        "🏏 Cricket — live scores, fixtures, results, news\n"
        "⚽ Football — live scores, fixtures, results, news\n"
        "🎯 Daily winner predictions and leaderboards\n\n"
        f"Data connection: <b>{api_state}</b>"
        f"{footer()}"
    )
    await respond(update, text, main_keyboard(rt.cfg.brand_url))


async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_predictions(update, context, None)


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_leaderboard(update, context, "week")


async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_stats(update, context)


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    if user_id:
        set_subscribed(rt.db, user_id, False)
        record_event(rt.db, user_id, "subscribe_off", "command")
    lang = language(rt.db, user_id) if user_id else "en"
    await respond(update, t(lang, "alerts_off"), subscription_keyboard(False))


async def team_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    remember(update, rt.db)
    query = " ".join(context.args).strip()
    if not query:
        await respond(
            update,
            "🔎 <b>Find a team</b>\n\nUsage: <code>/team India</code> or <code>/team Arsenal</code>",
            back_keyboard(),
        )
        return
    try:
        cricket, football = await asyncio.gather(
            rt.api.search_teams("cricket", query),
            rt.api.search_teams("football", query),
            return_exceptions=True,
        )
    except Exception:
        logger.exception("Team search failed")
        await respond(update, "⚠️ Team search is temporarily unavailable.", main_keyboard(rt.cfg.brand_url))
        return

    rows = []
    for sport, result, icon in (
        ("cricket", cricket, "🏏"),
        ("football", football, "⚽"),
    ):
        if isinstance(result, Exception):
            continue
        for team in result[:3]:
            if not isinstance(team, dict) or team.get("id") is None:
                continue
            name = str(team.get("name") or "Team")
            rows.append(
                [
                    InlineKeyboardButton(
                        f"{icon} {name}"[:60],
                        callback_data=f"team:{sport}:{team['id']}",
                    )
                ]
            )
    if not rows:
        await respond(
            update,
            "😕 <b>No team found.</b>\n\nTry another spelling.",
            main_keyboard(rt.cfg.brand_url),
        )
        return
    await respond(
        update,
        f"🔎 <b>SEARCH</b>\n{DIVIDER}\n\nLooking for: <b>{escape(query)}</b>\n\nChoose a team.",
        back_keyboard(rows),
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    if not is_admin(rt.cfg, user_id):
        await respond(update, "This command is restricted.", None)
        return
    snap = admin_snapshot(rt.db)
    api_state = "configured" if rt.cfg.highlightly_api_key else "missing"
    paused = "paused" if reminders_paused(rt.db) else "running"
    top = "\n".join(
        f"• {escape(str(row['action']))}: {row['c']}" for row in snap["top_actions"]
    ) or "No activity yet."
    await respond(
        update,
        "🛠 <b>PAHELI777 ADMIN</b>\n"
        f"{DIVIDER}\n\n"
        f"👥 Users: <b>{snap['users']}</b>\n"
        f"🔔 Subscribers: <b>{snap['subscribers']}</b>\n"
        f"🎯 Predictors: <b>{snap['predictors']}</b>\n"
        f"📝 Predictions: <b>{snap['predictions']}</b>\n"
        f"🌐 Website opens: <b>{snap['website_opens']}</b>\n"
        f"📊 Button actions: <b>{snap['clicks']}</b>\n"
        f"🏟 Highlightly API: <b>{api_state}</b>\n"
        f"💾 Database: <b>{escape(rt.db.dialect)}</b>\n"
        f"⏰ Reminders: <b>{paused}</b>\n\n"
        f"<b>Top actions</b>\n{top}\n\n"
        "Broadcast: <code>/broadcast your message</code>\n"
        "Leads: <code>/leads</code>\n"
        "Reminders: <code>/reminders on</code> or <code>/reminders off</code>",
        None,
    )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    if not is_admin(rt.cfg, user_id):
        await respond(update, "This command is restricted.", None)
        return
    message = " ".join(context.args).strip()
    if not message:
        await respond(update, "Usage: /broadcast your message", None)
        return
    if len(message) > 3500:
        await respond(update, "That message is too long.", None)
        return
    markup = None
    if rt.cfg.brand_url:
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🌐 Paheli777", url=rt.cfg.brand_url)]]
        )
    sent = failed = 0
    for chat_id in subscribed_user_ids(rt.db):
        try:
            await context.bot.send_message(chat_id=chat_id, text=message, reply_markup=markup)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await respond(update, f"Broadcast complete.\nSent: {sent}\nFailed: {failed}", None)


async def leads_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    if not is_admin(rt.cfg, user_id):
        await respond(update, "This command is restricted.", None)
        return
    snap = admin_snapshot(rt.db)
    campaigns = "\n".join(
        f"• {escape(str(row['campaign']))}: {row['c']}" for row in snap["campaigns"]
    ) or "No campaigns yet."
    await respond(
        update,
        "📈 <b>PAHELI777 LEADS</b>\n"
        f"{DIVIDER}\n\n"
        "Funnel counts are people, not a phone book. "
        "A deep link such as <code>?start=ad_launch</code> is stored as the campaign.\n\n"
        f"Started: <b>{snap['users']}</b>\n"
        f"Alerts on: <b>{snap['subscribers']}</b>\n"
        f"Made a pick: <b>{snap['predictors']}</b>\n"
        f"Opened website screen: <b>{snap['website_opens']}</b>\n\n"
        f"<b>Campaigns</b>\n{campaigns}",
        None,
    )


async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    if not is_admin(rt.cfg, user_id):
        await respond(update, "This command is restricted.", None)
        return
    arg = context.args[0].strip().lower() if context.args else ""
    if arg in {"off", "pause"}:
        set_setting(rt.db, "reminders_paused", "1")
    elif arg in {"on", "resume"}:
        set_setting(rt.db, "reminders_paused", "0")
    state = "paused" if reminders_paused(rt.db) else "running"
    await respond(
        update,
        "⏰ <b>PREDICTION REMINDERS</b>\n"
        f"{DIVIDER}\n\n"
        f"Status: <b>{state}</b>\n"
        f"Lead time: <b>{rt.cfg.reminder_lead_minutes} min</b> before kick-off\n"
        "Quiet hours: 11pm–8am in the app timezone.\n\n"
        "Use <code>/reminders off</code> or <code>/reminders on</code>.",
        None,
    )


async def show_predictions(update: Update, context: ContextTypes.DEFAULT_TYPE, sport: str | None) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    now = datetime.now(timezone.utc)
    sports = [sport] if sport else ["cricket", "football"]
    refresh_error = None
    try:
        await refresh_matches(
            rt.cfg,
            rt.db,
            rt.api,
            sports=sports,
            dates=local_dates(rt.cfg, now, back=0, forward=0),
        )
    except Exception as exc:
        refresh_error = exc
        logger.warning("Prediction board refresh failed: %s", exc)
    start, end = day_bounds_iso(rt.cfg, now, 0)
    fixtures = fixtures_between(rt.db, start, end)
    matches = _board(fixtures, sport)
    if refresh_error and not matches:
        await respond(update, api_error_text(refresh_error), back_keyboard())
        return
    picked = {}
    if user_id and matches:
        picked = predictions_for_user(rt.db, user_id, [item["match_key"] for item in matches])
    text = _format_board(matches, rt.cfg.timezone, len(picked)) + footer()
    await respond(update, text, prediction_keyboard(matches, set(picked)))


async def show_pick(update: Update, context: ContextTypes.DEFAULT_TYPE, match_key: str) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    fixture = get_fixture(rt.db, match_key)
    if not fixture:
        await respond(update, "That match is no longer on the board. Open today's predictions again.", back_keyboard())
        return
    now = datetime.now(timezone.utc)
    locked = is_pick_locked(parse_iso(fixture["kickoff"]), now, fixture["status"])
    prediction = get_prediction(rt.db, user_id, match_key) if user_id else None
    await respond(
        update,
        _format_pick(fixture, prediction, rt.cfg.timezone, locked),
        pick_keyboard(fixture, locked),
    )


async def choose_winner(
    update: Update, context: ContextTypes.DEFAULT_TYPE, match_key: str, winner: str
) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    if not user_id:
        return
    if winner not in {"home", "away", "draw"}:
        await show_pick(update, context, match_key)
        return
    now = datetime.now(timezone.utc)
    existing = get_prediction(rt.db, user_id, match_key)
    home_score = away_score = None
    if (
        existing
        and existing.get("winner") == winner
        and existing.get("home_score")
        and existing.get("away_score")
    ):
        home_score = existing.get("home_score")
        away_score = existing.get("away_score")
    try:
        save_prediction(
            rt.db,
            user_id=user_id,
            match_key=match_key,
            winner=winner,
            home_score=home_score,
            away_score=away_score,
            now=now,
        )
    except PickLocked:
        await show_pick(update, context, match_key)
        return
    except LookupError:
        await respond(update, "That match is no longer on the board.", back_keyboard())
        return
    record_event(rt.db, user_id, "prediction_saved", match_key)
    context.user_data["pending_score"] = {"match_key": match_key, "winner": winner}
    fixture = get_fixture(rt.db, match_key) or {"home_name": "Home", "away_name": "Away"}
    label = winner_label(winner, fixture)
    await respond(
        update,
        "🎯 <b>WINNER SAVED</b>\n"
        f"{DIVIDER}\n\n"
        f"You picked <b>{escape(label)}</b>.\n\n"
        "Optional exact score — reply with the score:\n"
        "• Football: <code>2-1</code>\n"
        "• Cricket: <code>137/8-139/4</code>\n\n"
        "Exact score is worth 2 bonus points. Skip it if you only want the winner.",
        score_prompt_keyboard(match_key),
    )


async def show_fixtures(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str, scope: str
) -> None:
    rt = runtime(context)
    remember(update, rt.db)
    now = datetime.now(timezone.utc)
    sports = _sports(scope)
    if mode == "live":
        dates = local_dates(rt.cfg, now, back=1, forward=0)
        start, _end_y = day_bounds_iso(rt.cfg, now, -1)
        _start_t, end = day_bounds_iso(rt.cfg, now, 0)
        status = "live"
        title = "🔴 <b>LIVE NOW</b>"
        empty = "Nothing is live right now. Check upcoming fixtures."
    elif mode == "up":
        dates = local_dates(rt.cfg, now, back=0, forward=1)
        start = iso_utc(now)
        _start_t, end = day_bounds_iso(rt.cfg, now, 1)
        status = "upcoming"
        title = "🗓 <b>UPCOMING</b>"
        empty = "No upcoming matches in this window."
    else:
        dates = local_dates(rt.cfg, now, back=1, forward=0)
        start, _mid = day_bounds_iso(rt.cfg, now, -1)
        _start_t, end = day_bounds_iso(rt.cfg, now, 0)
        status = "finished"
        title = "✅ <b>RESULTS</b>"
        empty = "No finished matches in the last two days."
    refresh_error = None
    try:
        await refresh_matches(rt.cfg, rt.db, rt.api, sports=sports, dates=dates)
    except Exception as exc:
        refresh_error = exc
        logger.warning("Fixture refresh failed: %s", exc)

    keyboard = refresh_keyboard(f"{mode}:{scope}", rt.cfg.brand_url)
    if scope == "both":
        grouped = {
            sport: sort_for_display(
                fixtures_between(rt.db, start, end, sport=sport, status=status)
            )
            for sport in ("cricket", "football")
        }
        total = sum(len(rows) for rows in grouped.values())
        if refresh_error and total == 0:
            await respond(update, api_error_text(refresh_error), keyboard)
            return
        sections = [title, DIVIDER, ""]
        for sport, heading in (("cricket", "🏏 <b>CRICKET</b>"), ("football", "⚽ <b>FOOTBALL</b>")):
            sections.append(
                format_match_list(
                    heading,
                    grouped[sport],
                    rt.cfg.timezone,
                    f"No {sport} matches in this list.",
                    limit=5,
                )
            )
            sections.extend(["", DIVIDER, ""])
        sections.append(f"Matches found: <b>{total}</b>")
        text = "\n".join(sections).strip() + footer()
    else:
        rows = sort_for_display(fixtures_between(rt.db, start, end, sport=scope, status=status))
        if refresh_error and not rows:
            await respond(update, api_error_text(refresh_error), keyboard)
            return
        icon = "🏏" if scope == "cricket" else "⚽"
        text = format_match_list(
            f"{icon} {title}",
            rows,
            rt.cfg.timezone,
            empty,
        ) + footer()
    await respond(update, text, keyboard)


async def show_news(update: Update, context: ContextTypes.DEFAULT_TYPE, scope: str) -> None:
    rt = runtime(context)
    remember(update, rt.db)
    now = datetime.now(timezone.utc)
    sports = _sports(scope)
    dates = local_dates(rt.cfg, now, back=1, forward=0)
    items: list[dict] = []
    errors: list[Exception] = []
    seen: set[str] = set()
    for sport in sports:
        for date_text in dates:
            try:
                batch = await load_highlights(rt.cfg, rt.api, sport, date_text)
            except Exception as exc:
                errors.append(exc)
                continue
            for item in batch:
                title = str(item.get("title") or "")
                if title in seen:
                    continue
                seen.add(title)
                copied = dict(item)
                icon = "🏏" if sport == "cricket" else "⚽"
                copied["title"] = f"{icon} {title}"
                items.append(copied)
    if not items and errors:
        await respond(
            update,
            api_error_text(errors[0]),
            refresh_keyboard(f"news:{scope}", rt.cfg.brand_url),
        )
        return
    text = format_news("📰 <b>NEWS</b>", items) + footer()
    await respond(update, text, refresh_keyboard(f"news:{scope}", rt.cfg.brand_url))


async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    now = datetime.now(timezone.utc)
    try:
        await refresh_matches(
            rt.cfg,
            rt.db,
            rt.api,
            sports=["cricket", "football"],
            dates=local_dates(rt.cfg, now, back=1, forward=0),
        )
    except Exception as exc:
        logger.warning("Leaderboard refresh failed, using saved results: %s", exc)
        settle_finished(rt.db, now)
    if period == "all":
        start_iso = end_iso = None
        title = "🏅 <b>ALL-TIME LEADERBOARD</b>"
    else:
        period = "week"
        start, end = week_window(now, rt.cfg.timezone)
        start_iso, end_iso = iso_utc(start), iso_utc(end)
        title = "📅 <b>THIS WEEK</b>"
    if user_id:
        record_event(rt.db, user_id, "leaderboard_view", period)
    rows = leaderboard(rt.db, start_iso, end_iso, limit=10)
    lines = [title, DIVIDER, ""]
    if not rows:
        lines.append("No scored picks in this window yet. Predict a match and check back after full time.")
    else:
        for index, row in enumerate(rows, start=1):
            you = " (you)" if user_id and int(row["user_id"]) == user_id else ""
            lines.append(
                f"{index}. <b>{escape(_person(row))}</b>{you} — "
                f"{int(row['points'])} pts "
                f"({int(row['correct'] or 0)}/{int(row['played'])} winners)"
            )
    await respond(update, "\n".join(lines), leaderboard_keyboard(period))


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    if not user_id:
        return
    settle_finished(rt.db)
    now = datetime.now(timezone.utc)
    start, end = week_window(now, rt.cfg.timezone)
    start_iso, end_iso = iso_utc(start), iso_utc(end)
    overall = user_point_total(rt.db, user_id)
    weekly = user_point_total(rt.db, user_id, start_iso, end_iso)
    week_rank = user_rank(rt.db, user_id, int(weekly["points"]), start_iso, end_iso)
    all_rank = user_rank(rt.db, user_id, int(overall["points"]), None, None)
    streak = prediction_streak(streak_flags(rt.db, user_id))
    week_label = f"#{week_rank}" if week_rank else "—"
    all_label = f"#{all_rank}" if all_rank else "—"
    text = (
        "📈 <b>YOUR STATS</b>\n"
        f"{DIVIDER}\n\n"
        f"All-time points: <b>{int(overall['points'])}</b>\n"
        f"Scored picks: <b>{int(overall['played'])}</b>\n"
        f"Correct winners: <b>{int(overall['correct'])}</b>\n"
        f"Exact scores: <b>{int(overall['exact'])}</b>\n"
        f"All-time rank: <b>{all_label}</b>\n\n"
        f"This week: <b>{int(weekly['points'])}</b> pts "
        f"from {int(weekly['played'])} picks\n"
        f"Weekly rank: <b>{week_label}</b>\n\n"
        f"Streak: <b>{streak}</b> correct winner{'s' if streak != 1 else ''} in a row\n\n"
        "A streak counts settled picks, newest first, and stops at the first miss."
    )
    await respond(
        update,
        text,
        back_keyboard(
            [[InlineKeyboardButton("🏆 Leaderboard", callback_data="board:week")]]
        ),
    )


async def show_my_picks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    user_id = remember(update, rt.db)
    if not user_id:
        return
    now = datetime.now(timezone.utc)
    start, end = day_bounds_iso(rt.cfg, now, 0)
    rows = user_picks_between(rt.db, user_id, start, end)
    lines = ["📋 <b>MY PICKS TODAY</b>", DIVIDER, ""]
    if not rows:
        lines.append("You have not picked a match today.")
    for row in rows:
        locked = is_pick_locked(parse_iso(row["kickoff"]), now, row["status"])
        label = winner_label(str(row["winner"]), row)
        score = ""
        if row.get("home_score") and row.get("away_score"):
            score = f" {row['home_score']}-{row['away_score']}"
        state = "locked" if locked else "open"
        points = f" • {int(row['points'])} pts" if row.get("points") is not None else ""
        lines.append(
            f"• {escape(str(row['home_name']))} vs {escape(str(row['away_name']))}\n"
            f"  {escape(label)}{escape(score)} ({state}){points}"
        )
    await respond(
        update,
        "\n".join(lines),
        back_keyboard([[InlineKeyboardButton("🎯 Predict Today", callback_data="predict")]]),
    )


async def show_team(update: Update, context: ContextTypes.DEFAULT_TYPE, sport: str, team_id: str) -> None:
    rt = runtime(context)
    try:
        team = await rt.api.team(sport, team_id)
        name = escape(str(team.get("name") or "Team"))
    except Exception as exc:
        logger.warning("Team lookup failed: %s", exc)
        name = "Team"
    icon = "🏏" if sport == "cricket" else "⚽"
    await respond(
        update,
        f"{icon} <b>{name}</b>\n{DIVIDER}\n\nWhat do you want to see?",
        back_keyboard(
            [
                [
                    InlineKeyboardButton("🗓 Upcoming", callback_data=f"tup:{sport}:{team_id}"),
                    InlineKeyboardButton("✅ Recent", callback_data=f"trc:{sport}:{team_id}"),
                ]
            ]
        ),
    )


async def show_team_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sport: str,
    team_id: str,
    recent: bool,
) -> None:
    rt = runtime(context)
    try:
        raw_matches = await rt.api.team_matches(sport, team_id, rt.cfg.timezone_name)
    except Exception as exc:
        await respond(update, api_error_text(exc), back_keyboard())
        return
    parsed = []
    seen = set()
    for raw in raw_matches:
        item = parse_match(raw, sport)
        if not item or item["match_key"] in seen:
            continue
        seen.add(item["match_key"])
        parsed.append(item)
    if parsed:
        upsert_fixtures(rt.db, parsed)
        settle_finished(rt.db)
    now = datetime.now(timezone.utc)
    if recent:
        chosen = [
            item
            for item in parsed
            if item["status"] == "finished" or parse_iso(item["kickoff"]) < now
        ]
        chosen.sort(key=lambda item: item["kickoff"], reverse=True)
        title = "✅ <b>RECENT MATCHES</b>"
        empty = "No recent matches found."
    else:
        chosen = [
            item
            for item in parsed
            if item["status"] != "finished" and parse_iso(item["kickoff"]) >= now
        ]
        chosen.sort(key=lambda item: item["kickoff"])
        title = "🗓 <b>UPCOMING MATCHES</b>"
        empty = "No upcoming matches found."
    action = f"trc:{sport}:{team_id}" if recent else f"tup:{sport}:{team_id}"
    await respond(
        update,
        format_match_list(title, chosen[:8], rt.cfg.timezone, empty) + footer(),
        refresh_keyboard(action, rt.cfg.brand_url),
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending = context.user_data.get("pending_score")
    if not pending or not update.effective_message:
        return
    rt = runtime(context)
    user_id = remember(update, rt.db)
    if not user_id:
        return
    try:
        home, away = parse_score_text(update.effective_message.text or "")
    except ValueError:
        await respond(
            update,
            "Send the exact score as <code>2-1</code> or <code>137/8-139/4</code>.\n"
            "Or tap Skip exact score.",
            score_prompt_keyboard(pending["match_key"]),
        )
        return
    try:
        save_prediction(
            rt.db,
            user_id=user_id,
            match_key=pending["match_key"],
            winner=pending["winner"],
            home_score=home,
            away_score=away,
            now=datetime.now(timezone.utc),
        )
    except PickLocked:
        context.user_data.pop("pending_score", None)
        await respond(update, "🔒 That match locked at kick-off. Your winner pick was kept.", back_keyboard())
        return
    except LookupError:
        context.user_data.pop("pending_score", None)
        await respond(update, "That match is no longer available.", back_keyboard())
        return
    context.user_data.pop("pending_score", None)
    record_event(rt.db, user_id, "exact_score_saved", pending["match_key"])
    await respond(
        update,
        f"✅ Exact score saved: <b>{escape(home)} - {escape(away)}</b>.\n\n"
        "It is worth 2 bonus points if it matches the final score.",
        back_keyboard([[InlineKeyboardButton("🎯 Today's board", callback_data="predict")]]),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    context.user_data.pop("pending_score", None)
    rt = runtime(context)
    user_id = remember(update, rt.db)
    data = query.data or ""
    if user_id:
        track(rt.db, user_id, data[:80])
    lang = language(rt.db, user_id) if user_id else "en"

    if data == "back":
        await show_home(update, context)
        return
    if data in {"sport:cricket", "sport:football"}:
        sport = data.split(":", 1)[1]
        icon = "🏏" if sport == "cricket" else "⚽"
        title = "CRICKET" if sport == "cricket" else "FOOTBALL"
        await respond(
            update,
            f"{icon} <b>{title}</b>\n{DIVIDER}\n\nLive scores, upcoming fixtures, results, news, or today's predictions.",
            sport_keyboard(sport),
        )
        return
    if data == "predict" or data.startswith("predict:"):
        sport = data.split(":", 1)[1] if ":" in data else None
        await show_predictions(update, context, sport if sport in {"cricket", "football"} else None)
        return
    if data.startswith("pick:"):
        await show_pick(update, context, data[len("pick:") :])
        return
    if data.startswith("win:"):
        match_key, winner = data[len("win:") :].rsplit(":", 1)
        await choose_winner(update, context, match_key, winner)
        return
    if data.startswith("skip:"):
        await respond(
            update,
            "✅ Winner saved. Exact score skipped.\n\nYou can change the pick until kick-off.",
            back_keyboard([[InlineKeyboardButton("🎯 Today's board", callback_data="predict")]]),
        )
        return
    if data.startswith("live:") or data.startswith("up:") or data.startswith("res:"):
        mode, scope = data.split(":", 1)
        await show_fixtures(update, context, mode, scope)
        return
    if data.startswith("news:"):
        await show_news(update, context, data.split(":", 1)[1])
        return
    if data.startswith("board:"):
        await show_leaderboard(update, context, data.split(":", 1)[1])
        return
    if data == "mystats":
        await show_stats(update, context)
        return
    if data == "mypicks":
        await show_my_picks(update, context)
        return
    if data == "settings":
        await respond(update, t(lang, "settings"), settings_keyboard())
        return
    if data in {"lang:en", "lang:hi"} and user_id:
        chosen = "en" if data.endswith("en") else "hi"
        set_language(rt.db, user_id, chosen)
        await respond(update, t(chosen, "lang_saved"), back_keyboard())
        return
    if data == "subscribe" and user_id:
        current = is_subscribed(rt.db, user_id)
        key = "alerts_on" if current else "alerts_off"
        await respond(update, t(lang, key), subscription_keyboard(current))
        return
    if data == "sub:toggle" and user_id:
        updated = not is_subscribed(rt.db, user_id)
        set_subscribed(rt.db, user_id, updated)
        record_event(rt.db, user_id, "subscribe_on" if updated else "subscribe_off", "menu")
        key = "alerts_on" if updated else "alerts_off"
        await respond(update, t(lang, key), subscription_keyboard(updated))
        return
    if data == "website":
        if user_id:
            record_event(rt.db, user_id, "website_open", rt.cfg.brand_url)
        key = "website" if rt.cfg.brand_url else "website_missing"
        await respond(update, t(lang, key), website_keyboard(rt.cfg.brand_url))
        return
    if data == "find":
        await respond(
            update,
            "🔎 <b>FIND A TEAM</b>\n"
            f"{DIVIDER}\n\n"
            "Send a command:\n\n"
            "<code>/team India</code>\n"
            "<code>/team Arsenal</code>",
            back_keyboard(),
        )
        return
    if data.startswith("team:"):
        _prefix, sport, team_id = data.split(":", 2)
        await show_team(update, context, sport, team_id)
        return
    if data.startswith("tup:") or data.startswith("trc:"):
        recent = data.startswith("trc:")
        _prefix, sport, team_id = data.split(":", 2)
        await show_team_list(update, context, sport, team_id, recent)
        return

    await respond(update, "⚡ Paheli777", back_keyboard())


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Update failed: %s", context.error)


async def _clear_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("pending_score", None)


def register(application) -> None:
    application.add_handler(MessageHandler(filters.COMMAND, _clear_pending), group=-1)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("sports", sports_command))
    application.add_handler(CommandHandler("predict", predict_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("mystats", mystats_command))
    application.add_handler(CommandHandler("team", team_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("leads", leads_command))
    application.add_handler(CommandHandler("reminders", reminders_command))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_error_handler(on_error)
