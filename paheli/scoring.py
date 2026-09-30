"""Pure scoring and pick-lock rules for the daily prediction game.

Points:
- 3 for the correct winner (home, away, or draw)
- +2 when the exact score also matches

The exact-score bonus is paid only together with the correct winner.
Football exact score is the full-time scoreline. A penalty shootout can
decide the winner, but it is not part of the exact score.
Cricket exact score is each side's leading run total (the number before
a wicket slash, so 181/5 is 181).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from paheli.clock import parse_datetime

WINNER_POINTS = 3
EXACT_POINTS = 2

FINISHED_STATES = {
    "finished",
    "finished after extra time",
    "finished after penalties",
    "finished after over time",
}
VOID_STATES = {
    "cancelled",
    "canceled",
    "postponed",
    "abandoned",
}
FOOTBALL_LIVE_STATES = {
    "first half",
    "second half",
    "extra time",
    "break time",
    "half time",
    "penalties",
    "interrupted",
    "in progress",
}
CRICKET_LIVE_STATES = {
    "in play",
    "stumps",
    "lunch",
    "innings break",
    "drinks",
    "timeout",
    "tea",
    "match delayed",
}
UPCOMING_STATES = {
    "scheduled",
    "not started",
    "to be announced",
}
LOCKED_STATUSES = {"live", "finished", "void"}

_SCORE_RE = re.compile(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$")
_RUNS_RE = re.compile(r"(\d+)")
_WORD_WON_RE = re.compile(r"\bwon\b")
_DRAW_RE = re.compile(r"\b(drawn|draw|tied|tie)\b")


@dataclass(frozen=True)
class Outcome:
    status: str
    winner: str | None
    home_score: int | None
    away_score: int | None
    score_display: str
    report: str
    state_description: str


@dataclass(frozen=True)
class ScoredPick:
    points: int | None
    winner_correct: bool | None
    exact_correct: bool | None
    result_status: str


def is_pick_locked(kickoff, now, status: str | None = None) -> bool:
    """Picks lock at kick-off, and also once a match is live, finished, or void."""
    if status and str(status).casefold() in LOCKED_STATUSES:
        return True
    kickoff_dt = parse_datetime(kickoff)
    now_dt = parse_datetime(now)
    if kickoff_dt is None or now_dt is None:
        return True
    return now_dt >= kickoff_dt


def classify_state(description: str, sport: str) -> str:
    state = (description or "").casefold().strip()
    if state in VOID_STATES:
        return "void"
    if state in FINISHED_STATES:
        return "finished"
    live = CRICKET_LIVE_STATES if sport == "cricket" else FOOTBALL_LIVE_STATES
    if state in live:
        return "live"
    if state in UPCOMING_STATES:
        return "scheduled"
    return "unknown"


def parse_exact_score(text: str) -> tuple[int, int] | None:
    if text is None:
        return None
    match = _SCORE_RE.search(str(text).strip())
    if not match:
        return None
    home, away = int(match.group(1)), int(match.group(2))
    if home > 999 or away > 999:
        return None
    return home, away


def winner_from_scores(home: int, away: int) -> str:
    if home > away:
        return "home"
    if away > home:
        return "away"
    return "draw"


def leading_runs(score_text) -> int | None:
    if score_text is None:
        return None
    match = _RUNS_RE.search(str(score_text).strip())
    if not match:
        return None
    return int(match.group(1))


def parse_score_value(value) -> tuple[int, int] | None:
    if isinstance(value, dict):
        home = value.get("home")
        away = value.get("away")
        if home is None or away is None:
            return None
        try:
            return int(home), int(away)
        except (TypeError, ValueError):
            return None
    if value is None:
        return None
    return parse_exact_score(str(value))


def cricket_winner(
    report: str,
    home_name: str,
    away_name: str,
    home_abbr: str = "",
    away_abbr: str = "",
) -> str | None:
    text = (report or "").casefold().strip()
    if not text:
        return None
    won = _WORD_WON_RE.search(text)
    if not won and _DRAW_RE.search(text):
        return "draw"
    if not won:
        return None
    prefix = text[: won.start()]
    best: tuple[int, int, str] | None = None
    for side, name in (
        ("home", home_name),
        ("away", away_name),
        ("home", home_abbr),
        ("away", away_abbr),
    ):
        token = (name or "").casefold().strip()
        if len(token) < 2:
            continue
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])")
        found = None
        for candidate in pattern.finditer(prefix):
            found = candidate
        if not found:
            continue
        end = found.end()
        if best is None or end > best[0] or (end == best[0] and len(token) > best[1]):
            best = (end, len(token), side)
    return best[2] if best else None


def _state_dict(raw: dict) -> dict:
    state = (raw or {}).get("state") or {}
    if isinstance(state, dict):
        return state
    return {"description": str(state or "")}


def _team(raw: dict, side: str) -> dict:
    value = (raw or {}).get(f"{side}Team") or (raw or {}).get(side) or {}
    return value if isinstance(value, dict) else {"name": str(value or "")}


def team_name(raw: dict, side: str) -> str:
    team = _team(raw, side)
    return str(team.get("name") or team.get("displayName") or side.title()).strip()


def team_abbr(raw: dict, side: str) -> str:
    team = _team(raw, side)
    return str(team.get("abbreviation") or team.get("abbr") or "").strip()


def league_name(raw: dict) -> str:
    league = (raw or {}).get("league") or {}
    if isinstance(league, dict):
        return str(league.get("name") or "").strip()
    return str(league or "").strip()


def _cricket_score_text(state: dict, side: str) -> str:
    teams = state.get("teams") if isinstance(state, dict) else None
    if not isinstance(teams, dict):
        return ""
    team_state = teams.get(side) or {}
    if not isinstance(team_state, dict):
        return ""
    score = team_state.get("score")
    return "" if score is None else str(score).strip()


def interpret_match(raw: dict, sport: str) -> Outcome:
    state = _state_dict(raw or {})
    description = str(state.get("description") or "").strip()
    report = str(state.get("report") or "").strip()
    status = classify_state(description, sport)
    home_name = team_name(raw or {}, "home")
    away_name = team_name(raw or {}, "away")
    home_score = None
    away_score = None
    score_display = ""
    winner = None

    if sport == "football":
        score = state.get("score") if isinstance(state.get("score"), dict) else {}
        current = parse_score_value(score.get("current"))
        penalties = parse_score_value(score.get("penalties"))
        if current:
            home_score, away_score = current
            score_display = f"{home_score} - {away_score}"
        if status == "finished" and current:
            winner = winner_from_scores(current[0], current[1])
            if winner == "draw" and penalties:
                shootout = winner_from_scores(penalties[0], penalties[1])
                if shootout != "draw":
                    winner = shootout
                    score_display = f"{score_display} (pens {penalties[0]}-{penalties[1]})"
    else:
        home_text = _cricket_score_text(state, "home")
        away_text = _cricket_score_text(state, "away")
        home_score = leading_runs(home_text)
        away_score = leading_runs(away_text)
        if home_text or away_text:
            score_display = f"{home_text or '-'} vs {away_text or '-'}"
        if status == "finished":
            winner = cricket_winner(
                report,
                home_name,
                away_name,
                team_abbr(raw or {}, "home"),
                team_abbr(raw or {}, "away"),
            )
            if winner is None and home_score is not None and away_score is not None:
                winner = winner_from_scores(home_score, away_score)

    return Outcome(
        status=status,
        winner=winner,
        home_score=home_score,
        away_score=away_score,
        score_display=score_display,
        report=report,
        state_description=description,
    )


def score_prediction(pick: str, exact: str | None, outcome: Outcome) -> ScoredPick:
    choice = (pick or "").strip().casefold()
    if choice not in {"home", "away", "draw"}:
        raise ValueError(f"Unsupported pick: {pick}")
    if outcome.status == "void":
        return ScoredPick(0, None, None, "void")
    if outcome.status != "finished" or outcome.winner not in {"home", "away", "draw"}:
        return ScoredPick(None, None, None, "pending")

    winner_correct = choice == outcome.winner
    exact_correct = False
    if (
        winner_correct
        and exact
        and outcome.home_score is not None
        and outcome.away_score is not None
    ):
        parsed = parse_exact_score(exact)
        exact_correct = parsed == (outcome.home_score, outcome.away_score)
    points = (WINNER_POINTS if winner_correct else 0) + (EXACT_POINTS if exact_correct else 0)
    return ScoredPick(points, winner_correct, exact_correct, "scored")


def current_streak(newest_first: list[bool]) -> int:
    streak = 0
    for correct in newest_first:
        if not correct:
            break
        streak += 1
    return streak


def best_streak(oldest_first: list[bool]) -> int:
    best = running = 0
    for correct in oldest_first:
        if correct:
            running += 1
            best = max(best, running)
        else:
            running = 0
    return best


def should_remind(
    kickoff,
    now,
    lead_minutes: int,
    has_pick: bool,
    already_sent: bool,
    status: str | None = None,
) -> bool:
    """True when a subscribed user still needs a nudge before lock."""
    if has_pick or already_sent:
        return False
    if lead_minutes <= 0:
        return False
    kickoff_dt = parse_datetime(kickoff)
    now_dt = parse_datetime(now)
    if kickoff_dt is None or now_dt is None:
        return False
    if is_pick_locked(kickoff_dt, now_dt, status):
        return False
    remaining = kickoff_dt - now_dt
    return remaining <= timedelta(minutes=lead_minutes)
