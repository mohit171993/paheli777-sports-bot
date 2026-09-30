"""Inline keyboards for Paheli777."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _clip(text: str, limit: int = 60) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def main_keyboard(brand_url: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🎯 Predict Today", callback_data="predict"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="board:week"),
        ],
        [
            InlineKeyboardButton("🏏 Cricket", callback_data="sport:cricket"),
            InlineKeyboardButton("⚽ Football", callback_data="sport:football"),
        ],
        [
            InlineKeyboardButton("🔴 Live Now", callback_data="live:both"),
            InlineKeyboardButton("🗓 Upcoming", callback_data="up:both"),
        ],
        [
            InlineKeyboardButton("✅ Results", callback_data="res:both"),
            InlineKeyboardButton("📰 News", callback_data="news:both"),
        ],
        [
            InlineKeyboardButton("📋 My Picks", callback_data="mypicks"),
            InlineKeyboardButton("📈 My Stats", callback_data="mystats"),
        ],
        [
            InlineKeyboardButton("🔔 Match Alerts", callback_data="subscribe"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
    ]
    if brand_url:
        rows.append([InlineKeyboardButton("🌐 Paheli777 Website", callback_data="website")])
    else:
        rows.append([InlineKeyboardButton("🌐 Website", callback_data="website")])
    return InlineKeyboardMarkup(rows)


def back_keyboard(extra: list | None = None) -> InlineKeyboardMarkup:
    rows = list(extra or [])
    rows.append([InlineKeyboardButton("⬅️ Back to Home", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def sport_keyboard(sport: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔴 Live", callback_data=f"live:{sport}"),
                InlineKeyboardButton("🗓 Upcoming", callback_data=f"up:{sport}"),
            ],
            [
                InlineKeyboardButton("✅ Results", callback_data=f"res:{sport}"),
                InlineKeyboardButton("📰 News", callback_data=f"news:{sport}"),
            ],
            [InlineKeyboardButton("🎯 Predict today", callback_data=f"predict:{sport}")],
            [InlineKeyboardButton("🔎 Find Team", callback_data="find")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def refresh_keyboard(action: str, brand_url: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=action),
            InlineKeyboardButton("🎯 Predict", callback_data="predict"),
        ],
        [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
    ]
    if brand_url:
        rows.insert(1, [InlineKeyboardButton("🌐 Paheli777 Website", callback_data="website")])
    return InlineKeyboardMarkup(rows)


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
                InlineKeyboardButton("🇮🇳 हिंदी", callback_data="lang:hi"),
            ],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def subscription_keyboard(subscribed: bool) -> InlineKeyboardMarkup:
    label = "🔕 Turn Alerts OFF" if subscribed else "🔔 Turn Alerts ON"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data="sub:toggle")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def website_keyboard(brand_url: str) -> InlineKeyboardMarkup:
    rows = []
    if brand_url:
        rows.append([InlineKeyboardButton("🌐 Open Paheli777", url=brand_url)])
    rows.append([InlineKeyboardButton("⬅️ Back to Home", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def prediction_keyboard(matches: list[dict], picked: set[str]) -> InlineKeyboardMarkup:
    rows = []
    for match in matches:
        mark = "✅ " if match["match_key"] in picked else ""
        home = _clip(match.get("home_name") or "Home", 16)
        away = _clip(match.get("away_name") or "Away", 16)
        icon = "🏏" if match.get("sport") == "cricket" else "⚽"
        rows.append(
            [
                InlineKeyboardButton(
                    _clip(f"{mark}{icon} {home} vs {away}", 60),
                    callback_data=f"pick:{match['match_key']}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("📅 This week", callback_data="board:week"),
            InlineKeyboardButton("🏅 All time", callback_data="board:all"),
        ]
    )
    rows.append([InlineKeyboardButton("⬅️ Back to Home", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def pick_keyboard(match: dict, locked: bool) -> InlineKeyboardMarkup:
    key = match["match_key"]
    if locked:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🎯 Today's board", callback_data="predict")],
                [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
            ]
        )
    home = _clip(match.get("home_name") or "Home", 28)
    away = _clip(match.get("away_name") or "Away", 28)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"🏠 {home}", callback_data=f"win:{key}:home")],
            [InlineKeyboardButton("🤝 Draw / Tie", callback_data=f"win:{key}:draw")],
            [InlineKeyboardButton(f"🚩 {away}", callback_data=f"win:{key}:away")],
            [InlineKeyboardButton("⬅️ Today's board", callback_data="predict")],
        ]
    )


def score_prompt_keyboard(match_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Skip exact score", callback_data=f"skip:{match_key}")],
            [InlineKeyboardButton("Change pick", callback_data=f"pick:{match_key}")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def leaderboard_keyboard(period: str) -> InlineKeyboardMarkup:
    week = "• This week" if period == "week" else "This week"
    overall = "• All time" if period == "all" else "All time"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(week, callback_data="board:week"),
                InlineKeyboardButton(overall, callback_data="board:all"),
            ],
            [InlineKeyboardButton("📈 My Stats", callback_data="mystats")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )
