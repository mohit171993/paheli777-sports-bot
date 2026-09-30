"""Telegram commands and button callbacks for Paheli777."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from html import escape

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from paheli.clock import local_date
from paheli.formatters import (
    api_error_text,
    clip,
    format_admin,
    format_fixture_list,
    format_leaderboard,
    format_leads,
    format_news,
    format_pick_screen,
    format_slate,
    format_stats,
    promo_footer,
    side_name,
)
from paheli.highlightly import HighlightlyError
from paheli.jobs import sync_and_settle
from paheli.keyboards import (
    back_keyboard,
    leaderboard_keyboard,
    main_keyboard,
    pick_keyboard,
    refresh_keyboard,
    settings_keyboard,
    slate_keyboard,
    sport_keyboard,
    subscription_keyboard,
    website_keyboard,
)
from paheli.matches import normalize_fixture
from paheli.scoring import is_pick_locked, winner_from_scores
from paheli.store import PickLocked
from paheli.text import DIVIDER, t

logger = logging.getLogger(__name__)

MATCH_KEY_RE = re.compile(r"^(football|cricket):[A-Za-z0-9_-]+$")
TEAM_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SYNC_CACHE_SECONDS = 45


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def services(context: ContextTypes.DEFAULT_TYPE):
    data = context.application.bot_data
    return data["settings"], data["store"], data["client"]


def touch(update: Update, store):
    user = update.effective_user
    if not user:
        return None
    store.touch_user(user.id, user.username, user.first_name, utcnow())
    return user


def is_admin(user_id: int, settings) -> bool:
    return user_id == settings.admin_user_id


async def show(query, text: str, markup) -> None:
    payload = clip(text)
    try:
        await query.edit_message_text(
            payload,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return
        logger.warning("Could not edit message: %s", exc)
        await query.message.reply_text(
            payload,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )


async def safe_text(query, loader, markup) -> None:
    try:
        text = await loader()
    except HighlightlyError as exc:
        logger.warning("Highlightly error: %s", exc)
        text = api_error_text(exc.status_code)
    except Exception:
        logger.exception("Sports screen failed")
        text = api_error_text(None)
    await show(query, text, markup)


async def maybe_sync(context: ContextTypes.DEFAULT_TYPE, force: bool = False) -> None:
    settings, store, client = services(context)
    if not settings.highlightly_api_key:
        return
    cache = context.application.bot_data
    if not force and time.time() - float(cache.get("last_sync") or 0) < SYNC_CACHE_SECONDS:
        return
    try:
        await sync_and_settle(store, client, settings)
        cache["last_sync"] = time.time()
    except Exception:
        logger.exception("Card sync failed")


def _home_markup(settings):
    return main_keyboard(settings.brand_url)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    user = touch(update, store)
    if not user:
        return
    arg = context.args[0] if context.args else ""
    store.record_start(user.id, arg, utcnow())
    lang = store.language(user.id)
    await update.effective_message.reply_text(
        t(lang, "welcome"),
        parse_mode="HTML",
        reply_markup=_home_markup(settings),
        disable_web_page_preview=True,
    )
    if arg.lower() == "predict":
        await _reply_slate(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    user = touch(update, store)
    lang = store.language(user.id) if user else "en"
    await update.effective_message.reply_text(
        t(lang, "help"),
        parse_mode="HTML",
        reply_markup=_home_markup(settings),
    )


async def sports_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    touch(update, store)
    api_state = "configured" if settings.highlightly_api_key else "missing API key"
    text = (
        "🏟 <b>PAHELI777 SPORTS</b>\n"
        f"{DIVIDER}\n\n"
        "🏏 Cricket — live scores, fixtures, results, news\n"
        "⚽ Football — live scores, fixtures, results, news\n"
        "🎯 Daily predictions and leaderboards\n\n"
        f"Data connection: <b>{api_state}</b>"
        f"{promo_footer()}"
    )
    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=_home_markup(settings),
    )


async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch(update, services(context)[1])
    await _reply_slate(update, context)


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _settings, store, _client = services(context)
    user = touch(update, store)
    text = _leaderboard_text(store, user.id if user else 0, "week")
    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=leaderboard_keyboard("week"),
        disable_web_page_preview=True,
    )


async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    user = touch(update, store)
    stats = store.user_stats(user.id) if user else _empty_stats()
    await update.effective_message.reply_text(
        format_stats(stats),
        parse_mode="HTML",
        reply_markup=_home_markup(settings),
        disable_web_page_preview=True,
    )


async def alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    user = touch(update, store)
    lang = store.language(user.id) if user else "en"
    subscribed = store.is_subscribed(user.id) if user else False
    text = t(lang, "sub_on") if subscribed else t(lang, "sub_off")
    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=subscription_keyboard(subscribed, settings.brand_url),
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    user = touch(update, store)
    if user:
        store.set_subscribed(user.id, False, utcnow())
        store.record_event(user.id, "subscribe_off", "stop", utcnow())
    lang = store.language(user.id) if user else "en"
    await update.effective_message.reply_text(
        t(lang, "sub_off"),
        parse_mode="HTML",
        reply_markup=subscription_keyboard(False, settings.brand_url),
    )


async def team_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, client = services(context)
    touch(update, store)
    query_text = " ".join(context.args).strip()
    if not query_text:
        await update.effective_message.reply_text(
            "🔎 <b>Find a team</b>\n\n"
            "Usage: <code>/team India</code>\n"
            "Example: <code>/team Arsenal</code>",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return
    try:
        cricket_results, football_results = await asyncio.gather(
            client.search_teams("cricket", query_text),
            client.search_teams("football", query_text),
            return_exceptions=True,
        )
    except Exception:
        logger.exception("Team search failed")
        await update.effective_message.reply_text(
            "⚠️ Team search is temporarily unavailable.",
            reply_markup=_home_markup(settings),
        )
        return
    rows = []
    if not isinstance(cricket_results, Exception):
        rows.extend(_team_buttons("cricket", cricket_results))
    if not isinstance(football_results, Exception):
        rows.extend(_team_buttons("football", football_results))
    if not rows:
        await update.effective_message.reply_text(
            "😕 <b>No team found.</b>\n\nTry another spelling.",
            parse_mode="HTML",
            reply_markup=_home_markup(settings),
        )
        return
    await update.effective_message.reply_text(
        f"🔎 <b>SEARCH RESULTS</b>\n{DIVIDER}\n\n"
        f"Looking for: <b>{escape(query_text)}</b>\n\nChoose a team 👇",
        parse_mode="HTML",
        reply_markup=back_keyboard(rows),
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    user = touch(update, store)
    if not user or not is_admin(user.id, settings):
        await update.effective_message.reply_text("This command is restricted.")
        return
    paused = store.get_setting("reminders_paused", "0") == "1"
    db_label = "Postgres" if store.db.dialect == "postgres" else "SQLite"
    await update.effective_message.reply_text(
        format_admin(
            store.admin_counts(),
            store.top_actions(),
            bool(settings.highlightly_api_key),
            db_label,
            paused,
        ),
        parse_mode="HTML",
    )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    user = touch(update, store)
    if not user or not is_admin(user.id, settings):
        await update.effective_message.reply_text("This command is restricted.")
        return
    message = " ".join(context.args).strip()
    if not message:
        await update.effective_message.reply_text("Usage: /broadcast your message")
        return
    markup = _home_markup(settings)
    sent = failed = 0
    for user_id in store.subscribed_user_ids():
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message[:4000],
                reply_markup=markup,
                disable_web_page_preview=True,
            )
            sent += 1
        except Exception:
            failed += 1
            logger.info("Broadcast failed for %s", user_id)
        await asyncio.sleep(0.05)
    await update.effective_message.reply_text(
        f"Broadcast complete.\nSent: {sent}\nFailed: {failed}"
    )


async def leads_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    user = touch(update, store)
    if not user or not is_admin(user.id, settings):
        await update.effective_message.reply_text("This command is restricted.")
        return
    await update.effective_message.reply_text(
        format_leads(store.lead_summary()),
        parse_mode="HTML",
    )


async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, client = services(context)
    user = touch(update, store)
    if not user or not is_admin(user.id, settings):
        await update.effective_message.reply_text("This command is restricted.")
        return
    await update.effective_message.reply_text("Refreshing today's card…")
    summary = await sync_and_settle(store, client, settings)
    context.application.bot_data["last_sync"] = time.time()
    errors = summary.get("errors") or []
    error_text = "\n".join(errors[:4]) if errors else "none"
    await update.effective_message.reply_text(
        "🔄 <b>Sync finished</b>\n"
        f"Football on card: <b>{summary.get('football', 0)}</b>\n"
        f"Cricket on card: <b>{summary.get('cricket', 0)}</b>\n"
        f"Picks settled: <b>{summary.get('settled', 0)}</b>\n"
        f"Notes: {escape(error_text)}",
        parse_mode="HTML",
    )


async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    user = touch(update, store)
    if not user or not is_admin(user.id, settings):
        await update.effective_message.reply_text("This command is restricted.")
        return
    action = (context.args[0].lower() if context.args else "").strip()
    if action in {"pause", "off"}:
        store.set_setting("reminders_paused", "1")
    elif action in {"resume", "on"}:
        store.set_setting("reminders_paused", "0")
    elif action:
        await update.effective_message.reply_text("Usage: /reminders pause  or  /reminders resume")
        return
    paused = store.get_setting("reminders_paused", "0") == "1"
    state = "paused" if paused else "running"
    await update.effective_message.reply_text(f"Pick reminders are {state}.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    user = touch(update, store)
    if not user or not update.effective_message:
        return
    pending = context.user_data.get("awaiting_exact")
    text = (update.effective_message.text or "").strip()
    from paheli.scoring import parse_exact_score

    if not pending:
        if parse_exact_score(text):
            await update.effective_message.reply_text(
                "Open today's card, choose a match, then tap Exact score.",
                reply_markup=_home_markup(settings),
            )
        return
    if not MATCH_KEY_RE.fullmatch(str(pending)):
        context.user_data.pop("awaiting_exact", None)
        return
    if not parse_exact_score(text):
        await update.effective_message.reply_text("Send a score like <code>2-1</code>, or tap Skip score.", parse_mode="HTML")
        return
    match = store.get_match(pending)
    prediction = store.prediction(user.id, pending)
    if not match or not prediction:
        context.user_data.pop("awaiting_exact", None)
        await update.effective_message.reply_text(
            "Pick a winner on that match first.",
            reply_markup=_home_markup(settings),
        )
        return
    try:
        saved = store.place_pick(user.id, pending, prediction["pick"], utcnow(), exact=text)
    except PickLocked:
        context.user_data.pop("awaiting_exact", None)
        await update.effective_message.reply_text(t(store.language(user.id), "locked"))
        return
    except ValueError:
        await update.effective_message.reply_text("Send a score like <code>2-1</code>.", parse_mode="HTML")
        return
    context.user_data.pop("awaiting_exact", None)
    store.record_event(user.id, "exact_score", pending, utcnow())
    note = _exact_note(saved["pick"], saved.get("exact_score"))
    await update.effective_message.reply_text(
        f"✅ Exact score saved.{note}\n\n" + format_pick_screen(match, saved, utcnow(), store.language(user.id)),
        parse_mode="HTML",
        reply_markup=pick_keyboard(match, utcnow(), settings.brand_url),
        disable_web_page_preview=True,
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    settings, store, client = services(context)
    user = touch(update, store)
    if not user:
        return
    data = query.data or ""
    store.track(user.id, data[:80], utcnow())
    lang = store.language(user.id)

    if data == "back":
        await show(query, t(lang, "welcome"), _home_markup(settings))
        return
    if data == "settings":
        await show(query, t(lang, "settings"), settings_keyboard())
        return
    if data in {"lang_en", "lang_hi"}:
        new_lang = "hi" if data == "lang_hi" else "en"
        store.set_language(user.id, new_lang, utcnow())
        await show(query, t(new_lang, "lang_saved"), back_keyboard())
        return
    if data == "subscribe":
        subscribed = store.is_subscribed(user.id)
        text = t(lang, "sub_on") if subscribed else t(lang, "sub_off")
        await show(query, text, subscription_keyboard(subscribed, settings.brand_url))
        return
    if data == "toggle_sub":
        new_value = not store.is_subscribed(user.id)
        store.set_subscribed(user.id, new_value, utcnow())
        store.record_event(
            user.id,
            "subscribe_on" if new_value else "subscribe_off",
            "",
            utcnow(),
        )
        text = t(lang, "sub_on") if new_value else t(lang, "sub_off")
        await show(query, text, subscription_keyboard(new_value, settings.brand_url))
        return
    if data == "website":
        store.record_event(user.id, "website_open", "", utcnow())
        key = "website" if settings.brand_url else "website_missing"
        await show(query, t(lang, key), website_keyboard(settings.brand_url))
        return
    if data == "lead:in":
        store.record_event(user.id, "interested", "", utcnow())
        await show(query, t(lang, "interested"), website_keyboard(settings.brand_url))
        return
    if data == "mystats":
        await show(query, format_stats(store.user_stats(user.id)), _home_markup(settings))
        return
    if data in {"lb:week", "lb:all"}:
        period = "all" if data.endswith("all") else "week"
        await show(query, _leaderboard_text(store, user.id, period), leaderboard_keyboard(period))
        return
    if data == "predict":
        await maybe_sync(context)
        await show(query, *_slate_payload(store, user.id, lang))
        return
    if data in {"cricket", "football"}:
        await show(query, _sport_intro(data), sport_keyboard(data, settings.brand_url))
        return
    if data == "find_team":
        await show(
            query,
            "🔎 <b>FIND A TEAM</b>\n"
            f"{DIVIDER}\n\n"
            "Type a command like:\n\n"
            "<code>/team India</code>\n"
            "<code>/team Arsenal</code>",
            back_keyboard(),
        )
        return
    if data in {"live_now", "upcoming", "results", "news"}:
        view = "live" if data == "live_now" else data
        await safe_text(
            query,
            lambda view=view: _combined_view(client, view, utcnow()),
            refresh_keyboard(data, settings.brand_url),
        )
        return
    if data.startswith("hub:"):
        parts = data.split(":", 2)
        if len(parts) == 3 and parts[1] in {"football", "cricket"}:
            _prefix, sport, view = parts
            await safe_text(
                query,
                lambda: _sport_view(client, sport, view, utcnow()),
                refresh_keyboard(data, settings.brand_url),
            )
        return
    if data.startswith("p:"):
        await _on_prediction(query, context, data, user.id, lang)
        return
    if data.startswith("team:"):
        await _on_team(query, client, data, settings.brand_url)
        return
    if data.startswith("tm:"):
        await _on_team_matches(query, client, data, settings.brand_url)
        return
    await show(query, t(lang, "welcome"), _home_markup(settings))


async def _on_prediction(query, context, data: str, user_id: int, lang: str) -> None:
    settings, store, _client = services(context)
    parts = data.split(":", 2)
    if len(parts) != 3 or not MATCH_KEY_RE.fullmatch(parts[2]):
        await show(query, t(lang, "predict_intro"), back_keyboard())
        return
    _prefix, action, match_key = parts
    if action == "o":
        await maybe_sync(context)
    match = store.get_match(match_key)
    if not match:
        await maybe_sync(context, force=True)
        match = store.get_match(match_key)
    if not match:
        await show(query, t(lang, "no_matches"), slate_keyboard([]))
        return
    now = utcnow()
    if action in {"h", "a", "d"}:
        pick = {"h": "home", "a": "away", "d": "draw"}[action]
        try:
            saved = store.place_pick(user_id, match_key, pick, now)
        except PickLocked:
            await show(query, t(lang, "locked"), pick_keyboard(match, now, settings.brand_url))
            return
        store.record_event(user_id, "prediction", match_key, now)
        context.user_data["awaiting_exact"] = match_key
        text = (
            f"✅ Winner saved: <b>{escape(side_name(match, saved['pick']))}</b>\n\n"
            "Want the exact-score bonus? Reply with a score like <code>2-1</code>, "
            "or tap Skip score.\n\n"
            + format_pick_screen(match, saved, now, lang)
        )
        await show(query, text, pick_keyboard(match, now, settings.brand_url))
        return
    if action == "x":
        context.user_data["awaiting_exact"] = match_key
        await show(
            query,
            "🎲 Reply with the exact score, for example <code>2-1</code>.\n"
            "Cricket uses leading run totals, for example <code>181-180</code>.",
            pick_keyboard(match, now, settings.brand_url),
        )
        return
    if action == "s":
        context.user_data.pop("awaiting_exact", None)
        prediction = store.prediction(user_id, match_key)
        if prediction and not is_pick_locked(match["kickoff"], now, match.get("status")):
            try:
                prediction = store.place_pick(user_id, match_key, prediction["pick"], now, exact="")
            except PickLocked:
                prediction = store.prediction(user_id, match_key)
        await show(query, format_pick_screen(match, prediction, now, lang), pick_keyboard(match, now, settings.brand_url))
        return
    prediction = store.prediction(user_id, match_key)
    await show(query, format_pick_screen(match, prediction, now, lang), pick_keyboard(match, now, settings.brand_url))


async def _on_team(query, client, data: str, brand_url: str) -> None:
    parts = data.split(":", 2)
    if len(parts) != 3 or parts[1] not in {"football", "cricket"} or not TEAM_ID_RE.fullmatch(parts[2]):
        await show(query, "Search again with /team NAME.", back_keyboard())
        return
    _prefix, sport, team_id = parts
    try:
        team = await client.team(sport, team_id)
        name = escape(str((team or {}).get("name") or "Team"))
    except Exception:
        logger.exception("Team lookup failed")
        name = "Team"
    icon = "🏏" if sport == "cricket" else "⚽"
    from telegram import InlineKeyboardButton

    extra = [
        [
            InlineKeyboardButton("🗓 Upcoming", callback_data=f"tm:u:{sport}:{team_id}"),
            InlineKeyboardButton("✅ Recent", callback_data=f"tm:r:{sport}:{team_id}"),
        ]
    ]
    if brand_url:
        extra.append([InlineKeyboardButton("🌐 Paheli777", url=brand_url)])
    await show(
        query,
        f"{icon} <b>{name}</b>\n{DIVIDER}\n\nWhat would you like to check?",
        back_keyboard(extra),
    )


async def _on_team_matches(query, client, data: str, brand_url: str) -> None:
    parts = data.split(":", 3)
    if len(parts) != 4 or parts[2] not in {"football", "cricket"} or not TEAM_ID_RE.fullmatch(parts[3]):
        await show(query, "Search again with /team NAME.", back_keyboard())
        return
    _prefix, which, sport, team_id = parts
    recent = which == "r"

    async def load():
        raws = await client.team_matches(sport, team_id)
        now = utcnow()
        items = []
        for raw in raws:
            kickoff_day = local_date(_kickoff_or_now(raw, now)).isoformat()
            item = normalize_fixture(raw, sport, kickoff_day)
            if not item:
                continue
            if recent and item["status"] in {"finished", "live"}:
                items.append(item)
            if not recent and item["status"] == "scheduled":
                items.append(item)
        items.sort(key=lambda row: row["kickoff"], reverse=recent)
        title = "✅ <b>RECENT MATCHES</b>" if recent else "🗓 <b>UPCOMING MATCHES</b>"
        return format_fixture_list(items[:8], title, "No matches found.")

    await safe_text(query, load, refresh_keyboard(data, brand_url))


async def _reply_slate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings, store, _client = services(context)
    user = update.effective_user
    lang = store.language(user.id) if user else "en"
    await maybe_sync(context)
    text, markup = _slate_payload(store, user.id if user else 0, lang)
    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )


def _slate_payload(store, user_id: int, lang: str):
    today = local_date(utcnow()).isoformat()
    matches = store.list_notable(today)
    picks = store.picks_for(user_id, [match["match_key"] for match in matches])
    return format_slate(matches, picks, utcnow(), lang), slate_keyboard(matches)


def _leaderboard_text(store, user_id: int, period: str) -> str:
    if period == "week":
        from paheli.clock import week_bounds

        start, end = week_bounds(utcnow())
        label = "WEEKLY LEADERBOARD"
    else:
        start, end = "", ""
        label = "ALL-TIME LEADERBOARD"
    rows = store.leaderboard(start, end)
    you = store.user_rank(user_id, start, end) if user_id else None
    return format_leaderboard(rows, label, you)


def _sport_intro(sport: str) -> str:
    icon = "🏏" if sport == "cricket" else "⚽"
    return (
        f"{icon} <b>{sport.upper()}</b>\n"
        f"{DIVIDER}\n\n"
        "Live scores, upcoming fixtures, results, and news.\n"
        "Winner picks for today's notable matches are on Today's Picks."
    )


async def _combined_view(client, view: str, now: datetime) -> str:
    cricket, football = await asyncio.gather(
        _sport_view(client, "cricket", view, now),
        _sport_view(client, "football", view, now),
        return_exceptions=True,
    )
    if isinstance(cricket, Exception) and isinstance(football, Exception):
        raise cricket
    parts = []
    parts.append(cricket if not isinstance(cricket, Exception) else "🏏 <b>CRICKET</b>\n\nTemporarily unavailable.")
    parts.append(football if not isinstance(football, Exception) else "⚽ <b>FOOTBALL</b>\n\nTemporarily unavailable.")
    return clip("\n\n".join(parts))


async def _sport_view(client, sport: str, view: str, now: datetime) -> str:
    today = local_date(now)
    icon = "🏏" if sport == "cricket" else "⚽"
    label = f"{icon} {sport.upper()}"
    if view in {"news", "hubnews"}:
        raws = await client.highlights(sport, today.isoformat())
        items = [item for item in (_highlight(raw) for raw in raws) if item]
        return format_news(items, label)
    if view == "live":
        dates = [today]
        title = f"{icon} <b>{sport.upper()} LIVE</b>"
        empty = f"No live {sport} matches right now."
    elif view == "upcoming":
        dates = [today, today + timedelta(days=1)]
        title = f"{icon} <b>{sport.upper()} UPCOMING</b>"
        empty = f"No upcoming {sport} fixtures in this window."
    else:
        dates = [today - timedelta(days=1), today]
        title = f"{icon} <b>{sport.upper()} RESULTS</b>"
        empty = f"No finished {sport} matches in this window."
    items = []
    for day in dates:
        raws = await client.matches(sport, day.isoformat())
        for raw in raws:
            item = normalize_fixture(raw, sport, day.isoformat())
            if not item:
                continue
            if view == "live" and item["status"] == "live":
                items.append(item)
            elif view == "upcoming" and item["status"] == "scheduled":
                items.append(item)
            elif view == "results" and item["status"] == "finished":
                items.append(item)
    items.sort(key=lambda row: row["kickoff"], reverse=view == "results")
    return format_fixture_list(items, title, empty)


def _highlight(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    url = str(raw.get("url") or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        url = ""
    description = str(raw.get("description") or "").strip()
    return {"title": title, "url": url, "description": description[:180]}


def _team_buttons(sport: str, teams: list) -> list:
    from telegram import InlineKeyboardButton

    icon = "🏏" if sport == "cricket" else "⚽"
    rows = []
    for team in list(teams or [])[:3]:
        if not isinstance(team, dict) or team.get("id") is None:
            continue
        team_id = str(team.get("id"))
        if not TEAM_ID_RE.fullmatch(team_id):
            continue
        name = str(team.get("name") or "Team")[:36]
        rows.append([InlineKeyboardButton(f"{icon} {name}", callback_data=f"team:{sport}:{team_id}")])
    return rows


def _exact_note(pick: str, exact: str | None) -> str:
    from paheli.scoring import parse_exact_score

    parsed = parse_exact_score(exact or "")
    if not parsed:
        return ""
    implied = winner_from_scores(parsed[0], parsed[1])
    if implied != pick:
        return "\nThe scoreline does not match your winner pick, so the bonus counts only if the winner is right."
    return ""


def _kickoff_or_now(raw: dict, now: datetime) -> datetime:
    from paheli.matches import kickoff_from_raw

    return kickoff_from_raw(raw) or now


def _empty_stats() -> dict:
    return {
        "picks": 0,
        "settled": 0,
        "points": 0,
        "correct": 0,
        "exacts": 0,
        "current_streak": 0,
        "best_streak": 0,
    }


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Update failed: %s", context.error)


def register_handlers(application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("sports", sports_command))
    application.add_handler(CommandHandler("predict", predict_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("mystats", mystats_command))
    application.add_handler(CommandHandler("alerts", alerts_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("team", team_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("leads", leads_command))
    application.add_handler(CommandHandler("sync", sync_command))
    application.add_handler(CommandHandler("reminders", reminders_command))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_error_handler(on_error)
