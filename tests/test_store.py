"""Sqlite persistence for locks, scoring, and the weekly board."""

import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from paheli.db import Database
from paheli.leads import campaign_from_start_arg
from paheli.scoring import PickLocked, iso_utc, week_window
from paheli.store import (
    get_prediction,
    leaderboard,
    mark_reminder_sent,
    record_start,
    save_prediction,
    settle_finished,
    streak_flags,
    touch_user,
    upsert_fixtures,
    user_point_total,
    user_rank,
    users_to_remind,
)
from paheli.scoring import prediction_streak


def fixture(match_key, kickoff, status="upcoming", home="2", away="1", winner="home"):
    return {
        "match_key": match_key,
        "sport": "football",
        "provider_id": match_key.split(":", 1)[1],
        "home_name": "Home Town",
        "away_name": "Away Town",
        "league": "Premier League",
        "kickoff": iso_utc(kickoff),
        "status": status,
        "state_label": status,
        "home_score": home if status == "finished" else None,
        "away_score": away if status == "finished" else None,
        "winner": winner if status == "finished" else None,
        "detail": "",
    }


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.db = Database.connect("sqlite:///:memory:")
        self.db.init()

    def tearDown(self):
        self.db.close()

    def test_pick_locks_at_kickoff_and_keeps_the_earlier_call(self):
        kickoff = datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)
        upsert_fixtures(self.db, [fixture("football:1", kickoff)])
        touch_user(self.db, 7, "sam", "Sam")
        save_prediction(
            self.db,
            user_id=7,
            match_key="football:1",
            winner="home",
            home_score=None,
            away_score=None,
            now=kickoff - timedelta(minutes=5),
        )
        with self.assertRaises(PickLocked):
            save_prediction(
                self.db,
                user_id=7,
                match_key="football:1",
                winner="away",
                home_score="0",
                away_score="1",
                now=kickoff,
            )
        self.assertEqual(get_prediction(self.db, 7, "football:1")["winner"], "home")

    def test_live_status_rejects_a_new_pick(self):
        kickoff = datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)
        upsert_fixtures(self.db, [fixture("football:2", kickoff, status="live")])
        with self.assertRaises(PickLocked):
            save_prediction(
                self.db,
                user_id=3,
                match_key="football:2",
                winner="home",
                home_score=None,
                away_score=None,
                now=kickoff - timedelta(hours=1),
            )

    def test_settle_scores_exact_pick_and_builds_leaderboards(self):
        tz = ZoneInfo("Asia/Kolkata")
        now = datetime(2026, 9, 30, 12, 0, tzinfo=tz)
        inside = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)
        older = datetime(2026, 1, 10, 15, 0, tzinfo=timezone.utc)
        upsert_fixtures(
            self.db,
            [
                fixture("football:week", inside),
                fixture("football:old", older),
            ],
        )
        touch_user(self.db, 4, "ada", "Ada")
        for key, kickoff in (("football:week", inside), ("football:old", older)):
            save_prediction(
                self.db,
                user_id=4,
                match_key=key,
                winner="home",
                home_score="2",
                away_score="1",
                now=kickoff - timedelta(hours=2),
            )
            upsert_fixtures(
                self.db,
                [fixture(key, kickoff, status="finished")],
            )
        changed = settle_finished(self.db, now)
        self.assertEqual(changed, 2)
        self.assertEqual(get_prediction(self.db, 4, "football:week")["points"], 5)
        self.assertEqual(prediction_streak(streak_flags(self.db, 4)), 2)

        start, end = week_window(now, tz)
        weekly = leaderboard(self.db, iso_utc(start), iso_utc(end))
        overall = leaderboard(self.db)
        self.assertEqual(len(weekly), 1)
        self.assertEqual(int(weekly[0]["points"]), 5)
        self.assertEqual(int(overall[0]["points"]), 10)
        self.assertEqual(user_rank(self.db, 4, 5, iso_utc(start), iso_utc(end)), 1)
        self.assertEqual(user_rank(self.db, 4, 10, None, None), 1)
        self.assertEqual(int(user_point_total(self.db, 4)["exact"]), 2)
        self.assertEqual(settle_finished(self.db, now), 0)

    def test_reminder_audience_skips_people_who_already_picked(self):
        kickoff = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)
        upsert_fixtures(self.db, [fixture("football:9", kickoff)])
        touch_user(self.db, 1, "sub", "Sub")
        touch_user(self.db, 2, "played", "Played")
        touch_user(self.db, 3, "cold", "Cold")
        self.db.write("UPDATE users SET subscribed = 1 WHERE user_id = 1")
        save_prediction(
            self.db,
            user_id=2,
            match_key="football:9",
            winner="draw",
            home_score=None,
            away_score=None,
            now=kickoff - timedelta(hours=3),
        )
        # A previous pick on another match makes user 2 eligible for other games,
        # but not for the match they already called.
        earlier = kickoff - timedelta(days=3)
        upsert_fixtures(self.db, [fixture("football:8", earlier)])
        save_prediction(
            self.db,
            user_id=2,
            match_key="football:8",
            winner="home",
            home_score=None,
            away_score=None,
            now=earlier - timedelta(hours=1),
        )
        audience = users_to_remind(self.db, "football:9")
        self.assertIn(1, audience)
        self.assertNotIn(2, audience)
        self.assertNotIn(3, audience)
        upsert_fixtures(self.db, [fixture("football:10", kickoff + timedelta(hours=4))])
        later = users_to_remind(self.db, "football:10")
        self.assertIn(1, later)
        self.assertIn(2, later)
        self.assertNotIn(3, later)
        mark_reminder_sent(self.db, 1, "football:9", kickoff - timedelta(minutes=30))
        self.assertNotIn(1, users_to_remind(self.db, "football:9"))

    def test_start_link_keeps_the_first_ad_campaign(self):
        self.assertEqual(campaign_from_start_arg("ad_launch"), "ad_launch")
        self.assertEqual(campaign_from_start_arg(""), "direct")
        touch_user(self.db, 9, "lee", "Lee")
        self.assertEqual(record_start(self.db, 9, "ad_launch"), "ad_launch")
        self.assertEqual(record_start(self.db, 9, "start"), "ad_launch")


if __name__ == "__main__":
    unittest.main()
