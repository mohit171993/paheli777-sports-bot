"""Highlightly payload parsing, notable-match selection, and score cards."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

from paheli.scoring import iso_utc, outcome_from_scores


DIVIDER = "━━━━━━━━━━━━━━━━━━"

CRICKET_LIVE = {
    "in play",
    "stumps",
    "lunch",
    "innings break",
    "drinks",
    "timeout",
    "tea",
    "match delayed",
    "strategic timeout",
}
FOOTBALL_LIVE = {
    "first half",
    "second half",
    "extra time",
    "break time",
    "half time",
    "penalties",
    "interrupted",
    "penalty shootout",
}

_EXCLUSIONS = (
    "2. bundesliga",
    "bundesliga 2",
    "2nd bundesliga",
    "serie b",
    "serie c",
    "la liga 2",
    "laliga 2",
    "ligue 2",
    "premier league 2",
)

_BROAD = {"bundesliga", "la liga", "ligue 1", "premier league", "serie a"}

CRICKET_KEYWORDS = (
    ("indian premier league", 0),
    ("ipl", 0),
    ("women's premier league", 0),
    ("womens premier league", 0),
    ("wpl", 0),
    ("world cup", 0),
    ("champions trophy", 0),
    ("asia cup", 0),
    ("t20 international", 0),
    ("t20i", 0),
    ("one day international", 0),
    ("odi", 0),
    ("test series", 0),
    ("test match", 0),
    ("international", 1),
    ("big bash", 1),
    ("pakistan super league", 1),
    ("psl", 1),
    ("sa20", 1),
    ("the hundred", 1),
    ("caribbean premier league", 1),
    ("cpl", 1),
    ("ranji trophy", 2),
)

FOOTBALL_KEYWORDS = (
    ("world cup", 0),
    ("champions league", 0),
    ("copa america", 0),
    ("uefa euro", 0),
    ("european championship", 0),
    ("premier league", 0),
    ("la liga", 0),
    ("serie a", 0),
    ("bundesliga", 0),
    ("ligue 1", 0),
    ("indian super league", 0),
    ("isl", 0),
    ("europa league", 1),
    ("conference league", 1),
    ("fa cup", 1),
    ("copa del rey", 1),
    ("nations league", 1),
    ("copa libertadores", 1),
    ("afc champions", 1),
    ("afc cup", 1),
    ("saff championship", 1),
    ("i-league", 2),
)


def _contains(text: str, keyword: str) -> bool:
    if " " in keyword or len(keyword) >= 6:
        return keyword in text
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None


def notable_rank(sport: str, league: str) -> int | None:
    text = str(league or "").casefold()
    if not text:
        return None
    keywords = CRICKET_KEYWORDS if sport == "cricket" else FOOTBALL_KEYWORDS
    best: int | None = None
    for keyword, rank in keywords:
        if not _contains(text, keyword):
            continue
        if keyword in _BROAD and any(item in text for item in _EXCLUSIONS):
            continue
        best = rank if best is None else min(best, rank)
    return best


def sort_for_display(matches: list[dict]) -> list[dict]:
    """Show major competitions ahead of the rest, then by kick-off."""

    def sort_key(match: dict) -> tuple:
        rank = notable_rank(match.get("sport", ""), match.get("league") or "")
        return (rank is None, 9 if rank is None else rank, match.get("kickoff") or "")

    return sorted(matches, key=sort_key)


def select_notable(matches: list[dict], limit: int = 8) -> list[dict]:
    """Prefer major competitions. If none match, use the earliest matches."""
    ranked = []
    others = []
    for match in matches:
        rank = notable_rank(match.get("sport", ""), match.get("league") or "")
        if rank is None:
            others.append(match)
        else:
            ranked.append((rank, match.get("kickoff") or "", match))
    ranked.sort(key=lambda item: (item[0], item[1]))
    chosen = [item[2] for item in ranked[:limit]]
    if not chosen:
        others.sort(key=lambda match: match.get("kickoff") or "")
        chosen = others[: min(6, limit)]
    chosen.sort(key=lambda match: match.get("kickoff") or "")
    return chosen


def state_description(state: object) -> str:
    if isinstance(state, dict):
        return str(state.get("description") or "").strip()
    return str(state or "").strip()


def classify_status(description: str, sport: str) -> str:
    text = description.casefold().strip()
    if text.startswith("finished") or text in {
        "ft",
        "full time",
        "ended",
        "completed",
        "match ended",
        "abandoned",
        "cancelled",
        "canceled",
        "postponed",
    }:
        return "finished"
    live = CRICKET_LIVE if sport == "cricket" else FOOTBALL_LIVE
    if text in live or "in play" in text or "in progress" in text:
        return "live"
    return "upcoming"


def _team_name(match: dict, side: str) -> str:
    obj = match.get(f"{side}Team") or match.get(side) or {}
    if isinstance(obj, dict):
        return str(obj.get("name") or obj.get("displayName") or side.title()).strip()
    return str(obj or side.title()).strip()


def _league_name(match: dict) -> str:
    league = match.get("league") or {}
    if isinstance(league, dict):
        return str(league.get("name") or "").strip()
    return str(league or "").strip()


def _parse_kickoff(match: dict) -> datetime | None:
    for key in ("startTime", "date", "startDate"):
        raw = match.get(key)
        if not raw:
            continue
        text = str(raw).strip().strip('"')
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0)
    return None


def _split_pair(value: object) -> tuple[str | None, str | None]:
    if isinstance(value, dict):
        current = value.get("current", value)
        if isinstance(current, dict):
            home = current.get("home")
            away = current.get("away")
            return _clean_score(home), _clean_score(away)
        value = current
    if value is None:
        return None, None
    text = str(value).strip()
    if not text or text.lower() in {"-", "none", "null"}:
        return None, None
    parts = re.split(r"\s*[-:]\s*", text)
    if len(parts) != 2:
        return None, None
    return _clean_score(parts[0]), _clean_score(parts[1])


def _clean_score(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"-", "none", "null"}:
        return None
    return text


def winner_from_report(report: str, home: str, away: str) -> str | None:
    text = str(report or "").casefold()
    if not text:
        return None
    if any(token in text for token in ("tied", "match drawn", "scores level", "no result")):
        return "draw"
    won_at = text.find("won")
    if won_at < 0:
        return None
    before = text[:won_at]
    home_name = home.casefold().strip()
    away_name = away.casefold().strip()
    home_hit = bool(home_name) and home_name in before
    away_hit = bool(away_name) and away_name in before
    if home_hit and not away_hit:
        return "home"
    if away_hit and not home_hit:
        return "away"
    return None


def extract_scores(
    state: object, sport: str, home: str, away: str
) -> tuple[str | None, str | None, str | None]:
    if not isinstance(state, dict):
        return None, None, None
    if sport == "cricket":
        teams = state.get("teams") if isinstance(state.get("teams"), dict) else {}
        home_node = teams.get("home") if isinstance(teams, dict) else None
        away_node = teams.get("away") if isinstance(teams, dict) else None
        home_score = _clean_score(home_node.get("score")) if isinstance(home_node, dict) else None
        away_score = _clean_score(away_node.get("score")) if isinstance(away_node, dict) else None
        winner = outcome_from_scores(home_score, away_score)
        if winner is None:
            winner = winner_from_report(str(state.get("report") or ""), home, away)
        return home_score, away_score, winner

    score = state.get("score")
    current = score.get("current") if isinstance(score, dict) else score
    home_score, away_score = _split_pair(current)
    winner = outcome_from_scores(home_score, away_score)
    description = state_description(state).casefold()
    if "penalt" in description and isinstance(score, dict):
        penalty_home, penalty_away = _split_pair(score.get("penalties"))
        penalty_winner = outcome_from_scores(penalty_home, penalty_away)
        if penalty_winner in {"home", "away"}:
            winner = penalty_winner
    if winner is None:
        winner = winner_from_report(str(state.get("report") or ""), home, away)
    return home_score, away_score, winner


def parse_match(raw: dict, sport: str) -> dict | None:
    if not isinstance(raw, dict) or sport not in {"cricket", "football"}:
        return None
    provider_id = str(raw.get("id") if raw.get("id") is not None else "").strip()
    if not provider_id:
        return None
    kickoff = _parse_kickoff(raw)
    if kickoff is None:
        return None
    home = _team_name(raw, "home") or "Home"
    away = _team_name(raw, "away") or "Away"
    state = raw.get("state") or {}
    description = state_description(state)
    status = classify_status(description, sport)
    home_score, away_score, winner = extract_scores(state, sport, home, away)
    if status != "finished":
        winner = None
    detail = str(raw.get("format") or "").strip()
    return {
        "match_key": f"{sport}:{provider_id}",
        "sport": sport,
        "provider_id": provider_id,
        "home_name": home,
        "away_name": away,
        "league": _league_name(raw),
        "kickoff": iso_utc(kickoff),
        "status": status,
        "state_label": description or status.title(),
        "home_score": home_score,
        "away_score": away_score,
        "winner": winner,
        "detail": detail,
    }


def format_kickoff(kickoff: str, tz: ZoneInfo) -> str:
    parsed = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).astimezone(tz)
    label = parsed.strftime("%d %b, %I:%M %p")
    tz_name = parsed.tzname() or tz.key
    return f"{label} {tz_name}"


def match_card(match: dict, index: int | None, tz: ZoneInfo) -> str:
    icon = "🏏" if match.get("sport") == "cricket" else "⚽"
    home = escape(str(match.get("home_name") or "Home"))
    away = escape(str(match.get("away_name") or "Away"))
    prefix = f"{index}. " if index is not None else ""
    lines = [f"{icon} <b>{prefix}{home} vs {away}</b>"]
    if match.get("home_score") or match.get("away_score"):
        lines.append(
            "📊 "
            f"{escape(str(match.get('home_score') or '-'))}"
            " — "
            f"{escape(str(match.get('away_score') or '-'))}"
        )
    league = str(match.get("league") or "")
    detail = str(match.get("detail") or "")
    if league and detail:
        lines.append(f"🏆 {escape(league)} · {escape(detail)}")
    elif league:
        lines.append(f"🏆 {escape(league)}")
    elif detail:
        lines.append(f"🏆 {escape(detail)}")
    label = str(match.get("state_label") or match.get("status") or "")
    if label:
        lines.append(f"⏱ {escape(label)}")
    if match.get("kickoff"):
        lines.append(f"🗓 {escape(format_kickoff(str(match['kickoff']), tz))}")
    return "\n".join(lines)


def format_match_list(
    title: str,
    matches: list[dict],
    tz: ZoneInfo,
    empty_text: str,
    limit: int = 8,
) -> str:
    if not matches:
        return f"{title}\n{DIVIDER}\n\n{empty_text}"
    lines = [title, DIVIDER, ""]
    shown = matches[:limit]
    for index, match in enumerate(shown, start=1):
        lines.append(match_card(match, index, tz))
        if index != len(shown):
            lines.extend(["", "· · ·", ""])
    if len(matches) > limit:
        lines.extend(["", f"➕ {len(matches) - limit} more matches"])
    return "\n".join(lines).strip()


def winner_label(winner: str, match: dict) -> str:
    if winner == "home":
        return str(match.get("home_name") or "Home")
    if winner == "away":
        return str(match.get("away_name") or "Away")
    if winner == "draw":
        return "Draw"
    return winner


def format_news(title: str, items: list[dict]) -> str:
    if not items:
        return (
            f"{title}\n{DIVIDER}\n\n"
            "No headlines right now. Check back after the next match."
        )
    lines = [title, DIVIDER, ""]
    for index, item in enumerate(items[:8], start=1):
        lines.append(f"📰 <b>{index}. {escape(str(item.get('title') or 'Update'))}</b>")
        description = str(item.get("description") or "").strip()
        if description:
            lines.append(escape(description[:240]))
        url = str(item.get("url") or "").strip()
        if url.startswith("http"):
            lines.append(escape(url))
        if index != min(len(items), 8):
            lines.extend(["", "· · ·", ""])
    return "\n".join(lines).strip()
