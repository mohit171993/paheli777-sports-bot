"""Normalize Highlightly matches and choose the day's prediction card."""

from __future__ import annotations

import re

from paheli.clock import parse_datetime, utc_iso
from paheli.scoring import interpret_match, league_name, team_abbr, team_name

# Earlier tiers win. A busy card of top leagues is not replaced by every T20
# or cup fixture that happens to be on the same date.
FOOTBALL_TIERS = (
    (
        "champions league",
        "europa league",
        "premier league",
        "la liga",
        "serie a",
        "bundesliga",
        "ligue 1",
        "world cup",
        "european championship",
        "copa america",
        "indian super league",
    ),
    (
        "conference league",
        "fa cup",
        "copa del rey",
        "nations league",
        "club world cup",
        "eredivisie",
        "primeira liga",
        "afc champions",
        "uefa",
        "mls",
        "liga mx",
    ),
)

CRICKET_TIERS = (
    (
        "indian premier league",
        "ipl",
        "icc",
        "world cup",
        "asia cup",
        "the hundred",
        "big bash",
        "pakistan super league",
        "psl",
        "caribbean premier",
        "sa20",
        "women's premier",
        "wpl",
        "ashes",
        "border-gavaskar",
    ),
    (
        "t20",
        "odi",
        "test",
        "international",
    ),
)


def _keyword_in(name: str, keyword: str) -> bool:
    if len(keyword) <= 4:
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", name) is not None
    return keyword in name


def notable_rank(sport: str, league: str) -> int:
    """Lower is more important. 99 means the league is not on a priority list."""
    name = (league or "").casefold()
    if not name:
        return 99
    tiers = CRICKET_TIERS if sport == "cricket" else FOOTBALL_TIERS
    for rank, keywords in enumerate(tiers):
        if any(_keyword_in(name, keyword) for keyword in keywords):
            return rank
    return 99


def is_notable_league(sport: str, league: str) -> bool:
    return notable_rank(sport, league) < 99


def kickoff_from_raw(raw: dict):
    for field in ("startDate", "startTime", "date"):
        parsed = parse_datetime((raw or {}).get(field))
        if parsed is not None:
            return parsed
    return None


def normalize_fixture(raw: dict, sport: str, match_date: str) -> dict | None:
    if not isinstance(raw, dict) or raw.get("id") is None:
        return None
    kickoff = kickoff_from_raw(raw)
    if kickoff is None:
        return None
    home = team_name(raw, "home")
    away = team_name(raw, "away")
    if not home or not away:
        return None
    outcome = interpret_match(raw, sport)
    status = outcome.status if outcome.status != "unknown" else "scheduled"
    return {
        "match_key": f"{sport}:{raw.get('id')}",
        "sport": sport,
        "provider_id": str(raw.get("id")),
        "home_name": home,
        "away_name": away,
        "home_abbr": team_abbr(raw, "home"),
        "away_abbr": team_abbr(raw, "away"),
        "league": league_name(raw),
        "kickoff": utc_iso(kickoff),
        "status": status,
        "home_score": outcome.home_score,
        "away_score": outcome.away_score,
        "score_display": outcome.score_display,
        "winner": outcome.winner,
        "report": outcome.report,
        "state_description": outcome.state_description,
        "match_date": match_date,
    }


def select_notable(fixtures: list[dict], sport: str, limit: int = 6) -> list[dict]:
    """Prefer the best league tier. If none match, use the rest of the day."""
    playable = []
    for item in fixtures:
        if item.get("sport") != sport:
            continue
        if item.get("status") == "void":
            continue
        if not item.get("home_name") or not item.get("away_name") or not item.get("kickoff"):
            continue
        playable.append(item)
    if not playable or limit <= 0:
        return []
    best = min(notable_rank(sport, item.get("league") or "") for item in playable)
    if best == 99:
        pool = playable
    else:
        pool = [
            item
            for item in playable
            if notable_rank(sport, item.get("league") or "") == best
        ]
    pool.sort(key=lambda item: item.get("kickoff") or "")
    return pool[:limit]


def merge_match(existing: dict | None, incoming: dict, notable: bool, updated_at: str) -> dict:
    """Keep a settled result if a later payload is less complete."""
    row = dict(incoming)
    row["notable"] = 1 if notable or (existing and int(existing.get("notable") or 0) == 1) else 0
    row["updated_at"] = updated_at
    if not existing:
        return row
    incoming_status = incoming.get("status") or "unknown"
    existing_status = existing.get("status") or "scheduled"
    if existing_status in {"finished", "void"} and incoming_status in {
        "scheduled",
        "live",
        "unknown",
    }:
        row["status"] = existing_status
    elif incoming_status == "unknown":
        row["status"] = existing_status
    if not incoming.get("winner") and existing.get("winner"):
        row["winner"] = existing["winner"]
    if incoming.get("home_score") is None and existing.get("home_score") is not None:
        row["home_score"] = existing["home_score"]
        row["away_score"] = existing["away_score"]
        if existing.get("score_display"):
            row["score_display"] = existing["score_display"]
    if not incoming.get("report") and existing.get("report"):
        row["report"] = existing["report"]
    return row
