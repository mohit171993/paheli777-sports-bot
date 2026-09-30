"""HTML messages for scores, the prediction card, and leaderboards."""

from __future__ import annotations

from html import escape

from paheli.clock import format_kickoff
from paheli.scoring import is_pick_locked
from paheli.text import DIVIDER, t


def clip(text: str, limit: int = 3900) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 2].rstrip() + "…"


def promo_footer() -> str:
    return f"\n\n{DIVIDER}\n🎯 <b>PAHELI777</b> • Pick the winner. Climb the board."


def display_name(row: dict) -> str:
    username = (row.get("username") or "").strip()
    if username:
        return "@" + username
    first = (row.get("first_name") or "").strip()
    if first:
        return first
    return f"Player {row.get('user_id')}"


def side_name(match: dict, pick: str | None) -> str:
    if pick == "home":
        return match.get("home_name") or "Home"
    if pick == "away":
        return match.get("away_name") or "Away"
    if pick == "draw":
        return "Draw"
    return "—"


def sport_icon(sport: str) -> str:
    return "🏏" if sport == "cricket" else "⚽"


def format_fixture(item: dict, index: int | None = None) -> str:
    icon = sport_icon(item.get("sport") or "")
    home = escape(str(item.get("home_name") or "Home"))
    away = escape(str(item.get("away_name") or "Away"))
    lines = []
    if index is not None:
        lines.append(f"{icon} <b>MATCH {index}</b>")
    score = (item.get("score_display") or "").strip()
    if score:
        lines.append(f"<b>{home}</b>\n{escape(score)}\n<b>{away}</b>")
    else:
        lines.append(f"<b>{home}</b>  vs  <b>{away}</b>")
    league = (item.get("league") or "").strip()
    if league:
        lines.append(f"🏆 {escape(league)}")
    lines.append(f"🕒 {escape(format_kickoff(item.get('kickoff')))}")
    state = (item.get("state_description") or "").strip()
    if state:
        lines.append(f"⏱ {escape(state)}")
    report = (item.get("report") or "").strip()
    if report:
        lines.append(f"📣 {escape(report)}")
    return "\n".join(lines)


def format_fixture_list(items: list[dict], title: str, empty_text: str) -> str:
    if not items:
        return clip(f"{title}\n{DIVIDER}\n\n{empty_text}{promo_footer()}")
    lines = [title, DIVIDER, ""]
    shown = items[:8]
    for index, item in enumerate(shown, start=1):
        lines.append(format_fixture(item, index))
        if index != len(shown):
            lines.extend(["", "· · ·", ""])
    if len(items) > 8:
        lines.extend(["", f"➕ {len(items) - 8} more"])
    lines.append(promo_footer())
    return clip("\n".join(lines).strip())


def format_slate(matches: list[dict], picks: dict, now, lang: str) -> str:
    lines = [t(lang, "predict_intro"), ""]
    if not matches:
        lines.append(t(lang, "no_matches"))
        return clip("\n".join(lines) + promo_footer())
    for index, match in enumerate(matches, start=1):
        locked = is_pick_locked(match["kickoff"], now, match.get("status"))
        pick = picks.get(match["match_key"])
        icon = sport_icon(match.get("sport") or "")
        state = "Locked" if locked else "Open"
        if match.get("status") == "finished":
            state = "Full time"
        elif match.get("status") == "live":
            state = "Live"
        elif match.get("status") == "void":
            state = "Void"
        lines.append(
            f"{index}. {icon} <b>{escape(match['home_name'])}</b> vs "
            f"<b>{escape(match['away_name'])}</b>"
        )
        if match.get("league"):
            lines.append(f"   🏆 {escape(match['league'])}")
        lines.append(f"   🕒 {escape(format_kickoff(match['kickoff']))} • {state}")
        if pick:
            exact = f" ({pick['exact_score']})" if pick.get("exact_score") else ""
            lines.append(f"   ✅ {escape(side_name(match, pick.get('pick')))}{escape(exact)}")
            if pick.get("result_status") == "scored":
                lines.append(f"   🏅 {int(pick.get('points') or 0)} pts")
        else:
            lines.append("   Your pick: —")
        lines.append("")
    lines.append("Tap a match to predict.")
    return clip("\n".join(lines).strip())


def format_pick_screen(match: dict, prediction: dict | None, now, lang: str) -> str:
    locked = is_pick_locked(match["kickoff"], now, match.get("status"))
    icon = sport_icon(match.get("sport") or "")
    lines = [
        f"{icon} <b>{escape(match['home_name'])} vs {escape(match['away_name'])}</b>",
        DIVIDER,
        "",
    ]
    if match.get("league"):
        lines.append(f"🏆 {escape(match['league'])}")
    lines.append(f"🕒 Kick-off {escape(format_kickoff(match.get('kickoff')))}")
    if match.get("score_display"):
        lines.append(f"📊 {escape(match['score_display'])}")
    if match.get("report"):
        lines.append(f"📣 {escape(match['report'])}")
    lines.append("🔒 Picks are locked." if locked else "🔒 Picks lock at kick-off.")
    lines.append("")
    if prediction:
        lines.append(f"Your pick: <b>{escape(side_name(match, prediction.get('pick')))}</b>")
        if prediction.get("exact_score"):
            lines.append(f"Exact score: <b>{escape(str(prediction['exact_score']))}</b>")
        if prediction.get("result_status") == "scored":
            lines.append(f"Points: <b>{int(prediction.get('points') or 0)}</b>")
        elif prediction.get("result_status") == "void":
            lines.append("This match was void. No points.")
    else:
        lines.append("Your pick: —")
    if not locked:
        lines.append("")
        lines.append("Who wins?")
    return clip("\n".join(lines))


def format_leaderboard(rows: list[dict], period_label: str, you: tuple[int, int] | None) -> str:
    lines = [f"🏆 <b>{escape(period_label)}</b>", DIVIDER, ""]
    if not rows:
        lines.append("No scored picks in this window yet.")
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"{index}. <b>{int(row['points'])} pts</b> — {escape(display_name(row))}"
        )
    lines.append("")
    if you:
        rank, points = you
        lines.append(f"You: <b>{points} pts</b> · rank {rank}")
    else:
        lines.append("You: no scored picks in this window yet.")
    lines.append(promo_footer())
    return clip("\n".join(lines).strip())


def format_stats(stats: dict) -> str:
    return clip(
        "\n".join(
            [
                "📊 <b>YOUR STATS</b>",
                DIVIDER,
                "",
                f"🏅 Points: <b>{stats['points']}</b>",
                f"🎯 Picks: <b>{stats['picks']}</b>",
                f"✅ Correct winners: <b>{stats['correct']}</b>",
                f"🎲 Exact scores: <b>{stats['exacts']}</b>",
                f"🔥 Current streak: <b>{stats['current_streak']}</b>",
                f"⭐ Best streak: <b>{stats['best_streak']}</b>",
                "",
                "A streak counts correct winners on scored matches, in kick-off order.",
                promo_footer(),
            ]
        )
    )


def format_news(items: list[dict], sport_label: str) -> str:
    title = f"📰 <b>{escape(sport_label)} NEWS</b>"
    if not items:
        return clip(f"{title}\n{DIVIDER}\n\nNo highlights or news items for this slate yet.{promo_footer()}")
    lines = [title, DIVIDER, ""]
    for item in items[:8]:
        title_text = escape(item["title"])
        if item.get("url"):
            lines.append(f'• <a href="{escape(item["url"], quote=True)}">{title_text}</a>')
        else:
            lines.append(f"• {title_text}")
        if item.get("description"):
            lines.append(f"  {escape(item['description'])}")
    lines.append(promo_footer())
    return clip("\n".join(lines).strip())


def format_reminder(match: dict) -> str:
    icon = sport_icon(match.get("sport") or "")
    lines = [
        "🔔 <b>KICKOFF SOON</b>",
        DIVIDER,
        "",
        f"{icon} <b>{escape(match['home_name'])} vs {escape(match['away_name'])}</b>",
    ]
    if match.get("league"):
        lines.append(f"🏆 {escape(match['league'])}")
    lines.append(f"🕒 {escape(format_kickoff(match.get('kickoff')))}")
    lines.extend(
        [
            "",
            "You have not picked a winner yet. Picks lock at kick-off.",
            promo_footer(),
        ]
    )
    return clip("\n".join(lines))


def format_admin(counts: dict, actions: list[dict], api_ready: bool, db_label: str, paused: bool) -> str:
    top = "\n".join(f"• {escape(row['action'])}: {row['c']}" for row in actions) or "No activity yet."
    return clip(
        "\n".join(
            [
                "🛠 <b>PAHELI777 ADMIN</b>",
                DIVIDER,
                "",
                f"👥 Users: <b>{counts['users']}</b>",
                f"🔔 Subscribers: <b>{counts['subscribers']}</b>",
                f"🎯 Predictions: <b>{counts['predictions']}</b>",
                f"📅 Open card matches: <b>{counts['open_matches']}</b>",
                f"📊 Button actions: <b>{counts['clicks']}</b>",
                f"🏟 Highlightly API: <b>{'configured' if api_ready else 'missing'}</b>",
                f"🗄 Database: <b>{escape(db_label)}</b>",
                f"🔔 Reminders: <b>{'paused' if paused else 'running'}</b>",
                "",
                "<b>Top actions</b>",
                top,
                "",
                "Broadcast: <code>/broadcast your message</code>",
                "Leads: <code>/leads</code>",
                "Refresh card: <code>/sync</code>",
                "Reminders: <code>/reminders pause</code> or <code>/reminders resume</code>",
            ]
        )
    )


def format_leads(summary: dict) -> str:
    campaigns = summary.get("campaigns") or []
    events = summary.get("events") or []
    campaign_lines = [
        f"• {escape(str(row['campaign']))}: {row['c']}" for row in campaigns
    ] or ["• none yet"]
    event_lines = [f"• {escape(str(row['event']))}: {row['c']}" for row in events] or ["• none yet"]
    return clip(
        "\n".join(
            [
                "📥 <b>PAHELI777 LEADS</b>",
                DIVIDER,
                "",
                f"🙋 Interested users: <b>{summary.get('interested', 0)}</b>",
                "",
                "<b>Campaigns</b>",
                *campaign_lines,
                "",
                "<b>Events</b>",
                *event_lines,
            ]
        )
    )


def api_error_text(status_code: int | None) -> str:
    if status_code in (401, 403):
        return "⚠️ Sports data authentication failed."
    if status_code == 429:
        return "⏳ Sports data limit reached. Please try again shortly."
    if status_code == 400:
        return "⚠️ Sports provider rejected this request. Please try again shortly."
    if status_code:
        return f"⚠️ Sports data provider returned HTTP {status_code}."
    return "⚠️ Sports data is temporarily unavailable. Please try again shortly."
