from datetime import datetime, timedelta, timezone

from paheli.clock import utc_iso, week_bounds
from paheli.db import Database
from paheli.scoring import Outcome
from paheli.store import PickLocked, Store

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def make_store(tmp_path) -> Store:
    database = Database(f"sqlite:///{tmp_path / 'paheli.db'}")
    database.init()
    return Store(database)


def sample_match(kickoff: datetime, match_key: str = "football:10", status: str = "scheduled") -> dict:
    return {
        "match_key": match_key,
        "sport": match_key.split(":", 1)[0],
        "provider_id": match_key.split(":", 1)[1],
        "home_name": "Arsenal",
        "away_name": "Chelsea",
        "home_abbr": "ARS",
        "away_abbr": "CHE",
        "league": "Premier League",
        "kickoff": utc_iso(kickoff),
        "status": status,
        "home_score": None,
        "away_score": None,
        "score_display": "",
        "winner": None,
        "report": "",
        "state_description": status,
        "match_date": "2026-09-30",
    }


def test_pick_locks_at_kickoff_and_settles_with_exact_bonus(tmp_path):
    store = make_store(tmp_path)
    kickoff = NOW + timedelta(hours=2)
    store.touch_user(7, "mohit", "Mohit", NOW)
    store.upsert_match(sample_match(kickoff), notable=True, now=NOW)

    saved = store.place_pick(7, "football:10", "home", NOW, exact="2-1")
    assert saved["result_status"] == "pending"
    assert saved["exact_score"] == "2-1"

    updated = store.place_pick(7, "football:10", "away", NOW + timedelta(minutes=5))
    assert updated["pick"] == "away"
    assert updated["exact_score"] == "2-1"

    try:
        store.place_pick(7, "football:10", "home", kickoff)
        raise AssertionError("kick-off should lock the pick")
    except PickLocked:
        pass

    finished = Outcome(
        status="finished",
        winner="away",
        home_score=1,
        away_score=2,
        score_display="1 - 2",
        report="",
        state_description="Finished",
    )
    assert store.apply_outcome("football:10", finished, kickoff + timedelta(hours=2)) == 1
    row = store.prediction(7, "football:10")
    assert row["result_status"] == "scored"
    assert row["points"] == 3
    assert row["winner_correct"] == 1
    assert row["exact_correct"] == 0
    try:
        store.place_pick(7, "football:10", "home", kickoff + timedelta(hours=3))
        raise AssertionError("settled picks stay locked")
    except PickLocked:
        pass


def test_void_does_not_extend_streak_and_weekly_board_uses_kickoff(tmp_path):
    store = make_store(tmp_path)
    store.touch_user(7, "mohit", "Mohit", NOW)
    store.touch_user(8, "other", "Other", NOW)

    def add(key, kickoff, pick, outcome, user_id=7):
        store.upsert_match(sample_match(kickoff, key), notable=True, now=NOW)
        store.place_pick(user_id, key, pick, kickoff - timedelta(hours=1), exact="2-0")
        store.apply_outcome(key, outcome, kickoff + timedelta(hours=3))

    win = Outcome("finished", "home", 2, 0, "2 - 0", "", "Finished")
    loss = Outcome("finished", "away", 0, 1, "0 - 1", "", "Finished")
    void = Outcome("void", None, None, None, "", "Postponed", "Postponed")

    monday = datetime(2026, 9, 28, 4, 0, tzinfo=timezone.utc)  # Monday morning IST
    previous = datetime(2026, 9, 20, 4, 0, tzinfo=timezone.utc)
    add("football:1", monday, "home", win)
    add("football:2", monday + timedelta(hours=4), "home", win)
    add("football:3", monday + timedelta(hours=8), "home", void)
    add("football:4", monday + timedelta(hours=12), "home", loss)
    add("football:5", previous, "home", win, user_id=8)

    stats = store.user_stats(7)
    assert stats["points"] == 3 + 2 + 3 + 2
    assert stats["correct"] == 2
    assert stats["exacts"] == 2
    assert stats["current_streak"] == 0
    assert stats["best_streak"] == 2
    assert stats["picks"] == 4

    start, end = week_bounds(datetime(2026, 9, 30, 12, tzinfo=timezone.utc))
    board = store.leaderboard(start, end)
    assert [row["user_id"] for row in board] == [7]
    assert store.user_rank(7, start, end) == (1, 10)
    assert store.user_points(8, "", "") == 5
    all_time = store.leaderboard("", "")
    assert [row["user_id"] for row in all_time] == [7, 8]


def test_reminder_claim_is_once_unless_send_failed(tmp_path):
    store = make_store(tmp_path)
    assert store.claim_reminder(7, "football:10", NOW) is True
    assert store.claim_reminder(7, "football:10", NOW) is False
    store.finish_reminder(7, "football:10", "failed")
    assert store.claim_reminder(7, "football:10", NOW) is True
    store.finish_reminder(7, "football:10", "sent")
    assert store.claim_reminder(7, "football:10", NOW) is False


def test_lead_campaign_sticks_to_the_first_start(tmp_path):
    store = make_store(tmp_path)
    assert store.record_start(7, "ad_cricket", NOW) == "ad_cricket"
    assert store.record_start(7, "ad_other", NOW) == "ad_cricket"
    store.record_event(7, "interested", "", NOW)
    summary = store.lead_summary()
    assert summary["campaigns"][0]["campaign"] == "ad_cricket"
    assert summary["interested"] == 1
