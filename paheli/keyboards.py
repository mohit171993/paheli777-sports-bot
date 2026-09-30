"""Inline keyboards. Website buttons use BRAND_URL and disappear when it is empty."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from paheli.scoring import is_pick_locked


def btn(text: str, *, style: str | None = None, **kwargs) -> InlineKeyboardButton:
    if style:
        kwargs["api_kwargs"] = {"style": style}
    return InlineKeyboardButton(text, **kwargs)


def main_keyboard(brand_url: str) -> InlineKeyboardMarkup:
    rows = [
        [
            btn("🎯 Today's Picks", callback_data="predict", style="success"),
            btn("🏆 Leaderboard", callback_data="lb:week", style="primary"),
        ],
        [
            btn("🏏 Cricket", callback_data="cricket", style="primary"),
            btn("⚽ Football", callback_data="football", style="primary"),
        ],
        [
            btn("🔴 Live", callback_data="live_now", style="danger"),
            btn("🗓 Upcoming", callback_data="upcoming"),
        ],
        [
            btn("✅ Results", callback_data="results"),
            btn("📰 News", callback_data="news"),
        ],
        [
            btn("🔔 Alerts", callback_data="subscribe"),
            btn("📊 My Stats", callback_data="mystats"),
        ],
        [
            btn("🔎 Find Team", callback_data="find_team"),
            btn("⚙️ Settings", callback_data="settings"),
        ],
    ]
    if brand_url:
        rows.append([btn("🌐 Paheli777", url=brand_url, style="success")])
    else:
        rows.append([btn("🌐 Paheli777", callback_data="website")])
    return InlineKeyboardMarkup(rows)


def back_keyboard(extra=None) -> InlineKeyboardMarkup:
    rows = list(extra or [])
    rows.append([btn("⬅️ Home", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def sport_keyboard(sport: str, brand_url: str) -> InlineKeyboardMarkup:
    rows = [
        [
            btn("🔴 Live", callback_data=f"hub:{sport}:live", style="danger"),
            btn("🗓 Upcoming", callback_data=f"hub:{sport}:upcoming"),
        ],
        [
            btn("✅ Results", callback_data=f"hub:{sport}:results"),
            btn("📰 News", callback_data=f"hub:{sport}:news"),
        ],
        [btn("🎯 Today's Picks", callback_data="predict", style="success")],
    ]
    if brand_url:
        rows.append([btn("🌐 Paheli777", url=brand_url, style="success")])
    rows.append([btn("⬅️ Home", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def refresh_keyboard(action: str, brand_url: str) -> InlineKeyboardMarkup:
    rows = [[btn("🔄 Refresh", callback_data=action, style="primary")]]
    rows.append(
        [
            btn("🎯 Today's Picks", callback_data="predict", style="success"),
            btn("⬅️ Home", callback_data="back"),
        ]
    )
    if brand_url:
        rows.append([btn("🌐 Paheli777", url=brand_url)])
    return InlineKeyboardMarkup(rows)


def slate_keyboard(matches: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for index, match in enumerate(matches[:8], start=1):
        label = f"{index}. {match['home_name']} vs {match['away_name']}"
        rows.append(
            [btn(label[:40], callback_data=f"p:o:{match['match_key']}", style="primary")]
        )
    rows.append(
        [
            btn("🏆 Leaderboard", callback_data="lb:week"),
            btn("🔔 Alerts", callback_data="subscribe"),
        ]
    )
    rows.append([btn("⬅️ Home", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def pick_keyboard(match: dict, now, brand_url: str) -> InlineKeyboardMarkup:
    key = match["match_key"]
    locked = is_pick_locked(match["kickoff"], now, match.get("status"))
    rows = []
    if not locked and match.get("status") not in {"finished", "void"}:
        home = str(match.get("home_name") or "Home")[:18]
        away = str(match.get("away_name") or "Away")[:18]
        rows.append(
            [
                btn(home, callback_data=f"p:h:{key}", style="primary"),
                btn("Draw", callback_data=f"p:d:{key}"),
                btn(away, callback_data=f"p:a:{key}", style="primary"),
            ]
        )
        rows.append(
            [
                btn("🎲 Exact score", callback_data=f"p:x:{key}"),
                btn("Skip score", callback_data=f"p:s:{key}"),
            ]
        )
    rows.append(
        [
            btn("🎯 Today's card", callback_data="predict"),
            btn("🏆 Board", callback_data="lb:week"),
        ]
    )
    if brand_url:
        rows.append([btn("🌐 Paheli777", url=brand_url)])
    rows.append([btn("⬅️ Home", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def leaderboard_keyboard(period: str) -> InlineKeyboardMarkup:
    week_label = "• Weekly" if period == "week" else "Weekly"
    all_label = "• All-time" if period == "all" else "All-time"
    return InlineKeyboardMarkup(
        [
            [
                btn(week_label, callback_data="lb:week", style="primary"),
                btn(all_label, callback_data="lb:all", style="primary"),
            ],
            [
                btn("📊 My Stats", callback_data="mystats"),
                btn("🎯 Today's Picks", callback_data="predict"),
            ],
            [btn("⬅️ Home", callback_data="back")],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                btn("🇬🇧 English", callback_data="lang_en"),
                btn("🇮🇳 हिंदी", callback_data="lang_hi"),
            ],
            [btn("⬅️ Home", callback_data="back")],
        ]
    )


def subscription_keyboard(subscribed: bool, brand_url: str) -> InlineKeyboardMarkup:
    label = "🔕 Turn alerts OFF" if subscribed else "🔔 Turn alerts ON"
    rows = [[btn(label, callback_data="toggle_sub", style="primary")]]
    if brand_url:
        rows.append([btn("🌐 Paheli777", url=brand_url)])
    rows.append([btn("⬅️ Home", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def website_keyboard(brand_url: str) -> InlineKeyboardMarkup:
    rows = []
    if brand_url:
        rows.append([btn("🌐 Open Paheli777", url=brand_url, style="success")])
    rows.append([btn("🙋 Count me in", callback_data="lead:in", style="primary")])
    rows.append(
        [
            btn("🎯 Today's Picks", callback_data="predict"),
            btn("⬅️ Home", callback_data="back"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def reminder_keyboard(match_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [btn("🎯 Make your pick", callback_data=f"p:o:{match_key}", style="success")],
            [btn("🔕 Stop alerts", callback_data="toggle_sub")],
        ]
    )
