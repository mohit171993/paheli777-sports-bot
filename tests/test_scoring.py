from datetime import datetime, timedelta, timezone

from paheli.clock import in_quiet_hours, parse_quiet_hours, week_bounds
from paheli.matches import is_notable_league, merge_match, normalize_fixture, select_notable
from paheli.scoring import (
    EXACT_POINTS,
    WINNER_POINTS,
    best_streak,
    cricket_winner,
    current_streak,
    interpret_match,
    is_pick_locked,
    parse_exact_score,
    score_prediction,
    should_remind,
)

KICKOFF = datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc)


def _football(**state):
    return {
        "id": 10,
        "homeTeam": {"name": "Arsenal"},
        "awayTeam": {"name": "Chelsea"},
        "league": {"name": "Premier League"},
        "startDate": "2026-09-30T14:00:00Z",
        "state": state,
    }


def test_lock_closes_at_kickoff_and_when_live():
    assert is_pick_locked(KICKOFF, KICKOFF - timedelta(seconds=1), "scheduled") is False
    assert is_pick_locked(KICKOFF, KICKOFF, "scheduled") is True
    assert is_pick_locked(KICKOFF, KICKOFF + timedelta(minutes=5), "scheduled") is True
    assert is_pick_locked(KICKOFF + timedelta(hours=2), KICKOFF, "live") is True


def test_football_winner_exact_score_and_penalties():
    finished = interpret_match(
        _football(description="Finished", score={"current": "2 - 1"}),
        "football",
    )
    assert finished.status == "finished"
    assert finished.winner == "home"
    assert (finished.home_score, finished.away_score) == (2, 1)

    correct = score_prediction("home", "2-1", finished)
    assert correct.points == WINNER_POINTS + EXACT_POINTS
    assert correct.winner_correct is True
    assert correct.exact_correct is True

    winner_only = score_prediction("home", "1-0", finished)
    assert winner_only.points == WINNER_POINTS
    assert winner_only.exact_correct is False

    wrong = score_prediction("away", "2-1", finished)
    assert wrong.points == 0
    assert wrong.exact_correct is False

    pens = interpret_match(
        _football(
            description="Finished after penalties",
            score={"current": "1 - 1", "penalties": "5 - 4"},
        ),
        "football",
    )
    assert pens.winner == "home"
    assert (pens.home_score, pens.away_score) == (1, 1)
    assert score_prediction("home", "1-1", pens).points == WINNER_POINTS + EXACT_POINTS
    assert score_prediction("draw", "1-1", pens).points == 0


def test_draw_void_and_pending():
    draw = interpret_match(
        _football(description="Finished", score={"current": "0-0"}),
        "football",
    )
    assert draw.winner == "draw"
    assert score_prediction("draw", "0:0", draw).points == WINNER_POINTS + EXACT_POINTS

    void = interpret_match(_football(description="Postponed"), "football")
    assert void.status == "void"
    assert score_prediction("home", "1-0", void).result_status == "void"

    live = interpret_match(
        _football(description="Second half", score={"current": "1 - 0"}),
        "football",
    )
    assert live.status == "live"
    assert score_prediction("home", None, live).result_status == "pending"


def test_cricket_winner_from_report_and_exact_runs():
    raw = {
        "id": 9,
        "startTime": "2026-09-30T14:00:00Z",
        "homeTeam": {"name": "Gujarat Titans", "abbreviation": "GT"},
        "awayTeam": {"name": "Kolkata Knight Riders", "abbreviation": "KKR"},
        "league": {"name": "IPL"},
        "state": {
            "description": "Finished",
            "report": "GT won by 5 wickets",
            "teams": {"home": {"score": "181/5"}, "away": {"score": "180"}},
        },
    }
    outcome = interpret_match(raw, "cricket")
    assert outcome.winner == "home"
    assert (outcome.home_score, outcome.away_score) == (181, 180)
    assert score_prediction("home", "181-180", outcome).points == WINNER_POINTS + EXACT_POINTS

    assert (
        cricket_winner(
            "Kolkata Knight Riders won by 6 runs",
            "Gujarat Titans",
            "Kolkata Knight Riders",
            "GT",
            "KKR",
        )
        == "away"
    )
    assert cricket_winner("Match drawn", "India", "Australia", "IND", "AUS") == "draw"
    assert (
        cricket_winner(
            "Match tied (Super Over: GT won)",
            "Gujarat Titans",
            "Kolkata Knight Riders",
            "GT",
            "KKR",
        )
        == "home"
    )


def test_streaks_skip_nothing_but_order():
    assert current_streak([True, True, False, True]) == 2
    assert current_streak([False, True]) == 0
    assert best_streak([True, True, False, True, True, True]) == 3


def test_reminder_window():
    lead = 45
    assert should_remind(KICKOFF, KICKOFF - timedelta(minutes=45), lead, False, False, "scheduled")
    assert should_remind(KICKOFF, KICKOFF - timedelta(minutes=46), lead, False, False, "scheduled") is False
    assert should_remind(KICKOFF, KICKOFF - timedelta(minutes=10), lead, True, False, "scheduled") is False
    assert should_remind(KICKOFF, KICKOFF - timedelta(minutes=10), lead, False, True, "scheduled") is False
    assert should_remind(KICKOFF, KICKOFF, lead, False, False, "scheduled") is False


def test_week_bounds_and_quiet_hours():
    start, end = week_bounds(datetime(2026, 9, 30, 12, tzinfo=timezone.utc))
    assert start.startswith("2026-09-27T18:30:00")
    assert end.startswith("2026-10-04T18:30:00")
    window = parse_quiet_hours("23-8")
    late = datetime(2026, 9, 30, 17, 45, tzinfo=timezone.utc)  # 23:15 IST
    afternoon = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)  # 13:30 IST
    assert in_quiet_hours(late, window) is True
    assert in_quiet_hours(afternoon, window) is False
    assert in_quiet_hours(late, None) is False
    assert parse_quiet_hours("") is None


def test_notable_card_prefers_known_leagues_then_falls_back():
    assert is_notable_league("football", "UEFA Champions League")
    assert is_notable_league("cricket", "Indian Premier League")
    fixtures = [
        {
            "match_key": "football:1",
            "sport": "football",
            "home_name": "A",
            "away_name": "B",
            "league": "County Cup",
            "kickoff": "2026-09-30T12:00:00+00:00",
            "status": "scheduled",
        },
        {
            "match_key": "football:2",
            "sport": "football",
            "home_name": "Arsenal",
            "away_name": "Chelsea",
            "league": "Premier League",
            "kickoff": "2026-09-30T16:00:00+00:00",
            "status": "scheduled",
        },
        {
            "match_key": "football:3",
            "sport": "football",
            "home_name": "X",
            "away_name": "Y",
            "league": "Premier League",
            "kickoff": "2026-09-30T14:00:00+00:00",
            "status": "void",
        },
    ]
    chosen = select_notable(fixtures, "football", limit=6)
    assert [item["match_key"] for item in chosen] == ["football:2"]

    crowded = select_notable(
        [
            {
                "match_key": "cricket:9",
                "sport": "cricket",
                "home_name": "Gujarat Titans",
                "away_name": "Mumbai Indians",
                "league": "IPL",
                "kickoff": "2026-09-30T14:00:00+00:00",
                "status": "scheduled",
            },
            {
                "match_key": "cricket:8",
                "sport": "cricket",
                "home_name": "Side A",
                "away_name": "Side B",
                "league": "Tamil Nadu T20",
                "kickoff": "2026-09-30T08:00:00+00:00",
                "status": "scheduled",
            },
        ],
        "cricket",
        limit=6,
    )
    assert [item["match_key"] for item in crowded] == ["cricket:9"]

    fallback = select_notable(
        [
            {
                "match_key": "cricket:1",
                "sport": "cricket",
                "home_name": "Side A",
                "away_name": "Side B",
                "league": "Local League",
                "kickoff": "2026-09-30T15:00:00+00:00",
                "status": "scheduled",
            }
        ],
        "cricket",
        limit=6,
    )
    assert [item["match_key"] for item in fallback] == ["cricket:1"]


def test_normalize_and_merge_keep_a_settled_result():
    item = normalize_fixture(_football(description="Not started"), "football", "2026-09-30")
    assert item["match_key"] == "football:10"
    assert item["status"] == "scheduled"
    finished = dict(item)
    finished.update(status="finished", winner="home", home_score=2, away_score=1, notable=1)
    merged = merge_match(finished, item, notable=False, updated_at="later")
    assert merged["status"] == "finished"
    assert merged["winner"] == "home"
    assert merged["notable"] == 1
    assert merged["home_score"] == 2
    assert normalize_fixture({"id": 1, "homeTeam": {"name": "A"}}, "football", "2026-09-30") is None
    assert parse_exact_score("score 2-1") is None
    assert parse_exact_score("2 - 1") == (2, 1)
