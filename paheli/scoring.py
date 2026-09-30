"""Pure scoring, lock, streak, and reminder rules.

These functions do not touch the database or the network so they can be tested
without a bot token.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


WINNER_POINTS = 3
EXACT_SCORE_BONUS = 2
QUIET_START_HOUR = 23
QUIET_END_HOUR = 8

_SCORE_RE = re.compile(r"^\s*(\d+(?:/\d+)?)\s*[-:]\s*(\d+(?:/\d+)?)\s*$")


class PickLocked(Exception):
    """Raised when a prediction is submitted at or after kick-off."""


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    """Fixed-width UTC timestamp so lexicographic comparison matches time order."""
    return as_utc(value).replace(microsecond=0).isoformat()


def parse_iso(value: str) -> datetime:
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return as_utc(parsed)


def is_pick_locked(kickoff: datetime, now: datetime, status: str = "upcoming") -> bool:
    """Picks lock at kick-off, and also whenever the match is live or finished."""
    if str(status or "").casefold() in {"live", "finished"}:
        return True
    return as_utc(now) >= as_utc(kickoff)


def normalize_score(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "")
    if not text or text in {"-", "none", "null"}:
        return None
    if re.fullmatch(r"\d+", text):
        return str(int(text))
    if re.fullmatch(r"\d+/\d+", text):
        runs, wickets = text.split("/")
        return f"{int(runs)}/{int(wickets)}"
    return text


def parse_score_text(text: str) -> tuple[str, str]:
    """Parse a user reply such as '2-1' or '137/8-139/4'."""
    match = _SCORE_RE.match(str(text or ""))
    if not match:
        raise ValueError("Send the score as 2-1 or 137/8-139/4")
    home = normalize_score(match.group(1))
    away = normalize_score(match.group(2))
    if not home or not away:
        raise ValueError("Send the score as 2-1 or 137/8-139/4")
    return home, away


def ensure_score_pair(
    home: str | None, away: str | None
) -> tuple[str | None, str | None]:
    if home is None and away is None:
        return None, None
    if home is None or away is None or str(home).strip() == "" or str(away).strip() == "":
        raise ValueError("Enter both scores, for example 2-1")
    normalized_home = normalize_score(home)
    normalized_away = normalize_score(away)
    if not normalized_home or not normalized_away:
        raise ValueError("Enter both scores, for example 2-1")
    return normalized_home, normalized_away


def parse_runs(value: object) -> int | None:
    normalized = normalize_score(value)
    if not normalized:
        return None
    match = re.match(r"(\d+)", normalized)
    if not match:
        return None
    return int(match.group(1))


def outcome_from_scores(home: object, away: object) -> str | None:
    home_runs = parse_runs(home)
    away_runs = parse_runs(away)
    if home_runs is None or away_runs is None:
        return None
    if home_runs > away_runs:
        return "home"
    if away_runs > home_runs:
        return "away"
    return "draw"


def scores_exact(
    predicted_home: object,
    predicted_away: object,
    actual_home: object,
    actual_away: object,
) -> bool:
    pairs = (
        normalize_score(predicted_home),
        normalize_score(predicted_away),
        normalize_score(actual_home),
        normalize_score(actual_away),
    )
    if any(item is None for item in pairs):
        return False
    return pairs[0] == pairs[2] and pairs[1] == pairs[3]


def score_prediction(
    predicted_winner: str,
    predicted_home: object,
    predicted_away: object,
    actual_winner: str | None,
    actual_home: object,
    actual_away: object,
) -> dict | None:
    """Score one pick.

    Returns None when the final result is not known yet.
    A correct winner is worth 3 points. An exact score is worth 2 more.
    The two calls are independent, so an exact score still scores its bonus
    when the winner call was wrong.
    """
    winner = actual_winner or outcome_from_scores(actual_home, actual_away)
    if winner not in {"home", "away", "draw"}:
        return None
    exact = scores_exact(predicted_home, predicted_away, actual_home, actual_away)
    correct = predicted_winner == winner
    points = (WINNER_POINTS if correct else 0) + (EXACT_SCORE_BONUS if exact else 0)
    return {
        "points": points,
        "winner_correct": 1 if correct else 0,
        "exact_hit": 1 if exact else 0,
    }


def prediction_streak(winner_correct_newest_first: list[bool]) -> int:
    """Consecutive correct-winner picks, counting back from the latest one."""
    streak = 0
    for flag in winner_correct_newest_first:
        if not flag:
            break
        streak += 1
    return streak


def week_window(now: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Monday 00:00 through the next Monday in the given timezone."""
    local = as_utc(now).astimezone(tz)
    start = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, start + timedelta(days=7)


def in_quiet_hours(
    now: datetime,
    tz: ZoneInfo,
    start_hour: int = QUIET_START_HOUR,
    end_hour: int = QUIET_END_HOUR,
) -> bool:
    hour = as_utc(now).astimezone(tz).hour
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def due_for_reminder(
    *,
    kickoff: datetime,
    now: datetime,
    lead_minutes: int,
    status: str,
    already_picked: bool,
    already_sent: bool,
    quiet: bool,
) -> bool:
    """True when a not-yet-picked match is inside the pre-kickoff window."""
    if quiet or already_picked or already_sent:
        return False
    if str(status or "").casefold() != "upcoming":
        return False
    delta = as_utc(kickoff) - as_utc(now)
    return timedelta(0) < delta <= timedelta(minutes=lead_minutes)
