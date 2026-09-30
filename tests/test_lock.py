"""Pick lock and pre-kickoff reminder window."""

import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from paheli.scoring import due_for_reminder, in_quiet_hours, is_pick_locked, parse_score_text


KICKOFF = datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc)


class LockTests(unittest.TestCase):
    def test_open_before_kickoff(self):
        self.assertFalse(
            is_pick_locked(KICKOFF, KICKOFF - timedelta(seconds=1), "upcoming")
        )

    def test_locks_at_kickoff(self):
        self.assertTrue(is_pick_locked(KICKOFF, KICKOFF, "upcoming"))

    def test_locks_after_kickoff(self):
        self.assertTrue(is_pick_locked(KICKOFF, KICKOFF + timedelta(minutes=1), "upcoming"))

    def test_live_match_is_locked_before_listed_kickoff(self):
        self.assertTrue(
            is_pick_locked(KICKOFF, KICKOFF - timedelta(hours=1), "live")
        )

    def test_finished_match_is_locked(self):
        self.assertTrue(is_pick_locked(KICKOFF, KICKOFF - timedelta(days=1), "finished"))

    def test_naive_datetimes_are_treated_as_utc(self):
        naive = KICKOFF.replace(tzinfo=None)
        self.assertFalse(
            is_pick_locked(naive, KICKOFF - timedelta(minutes=1), "upcoming")
        )
        self.assertTrue(is_pick_locked(naive, naive, "upcoming"))


class ScoreTextTests(unittest.TestCase):
    def test_football_and_cricket_formats(self):
        self.assertEqual(parse_score_text("2-1"), ("2", "1"))
        self.assertEqual(parse_score_text(" 2 : 1 "), ("2", "1"))
        self.assertEqual(parse_score_text("137/8-139/4"), ("137/8", "139/4"))

    def test_rejects_partial_score(self):
        with self.assertRaises(ValueError):
            parse_score_text("2")
        with self.assertRaises(ValueError):
            parse_score_text("soon")


class ReminderWindowTests(unittest.TestCase):
    def test_inside_lead_window(self):
        now = KICKOFF - timedelta(minutes=30)
        self.assertTrue(
            due_for_reminder(
                kickoff=KICKOFF,
                now=now,
                lead_minutes=45,
                status="upcoming",
                already_picked=False,
                already_sent=False,
                quiet=False,
            )
        )

    def test_too_early_picked_sent_live_or_quiet(self):
        early = KICKOFF - timedelta(minutes=90)
        self.assertFalse(
            due_for_reminder(
                kickoff=KICKOFF,
                now=early,
                lead_minutes=45,
                status="upcoming",
                already_picked=False,
                already_sent=False,
                quiet=False,
            )
        )
        now = KICKOFF - timedelta(minutes=20)
        for kwargs in (
            {"already_picked": True},
            {"already_sent": True},
            {"status": "live"},
            {"quiet": True},
        ):
            base = dict(
                kickoff=KICKOFF,
                now=now,
                lead_minutes=45,
                status="upcoming",
                already_picked=False,
                already_sent=False,
                quiet=False,
            )
            base.update(kwargs)
            self.assertFalse(due_for_reminder(**base))

    def test_not_due_once_kickoff_arrives(self):
        self.assertFalse(
            due_for_reminder(
                kickoff=KICKOFF,
                now=KICKOFF,
                lead_minutes=45,
                status="upcoming",
                already_picked=False,
                already_sent=False,
                quiet=False,
            )
        )

    def test_quiet_hours_cover_late_night_in_kolkata(self):
        tz = ZoneInfo("Asia/Kolkata")
        self.assertTrue(in_quiet_hours(datetime(2026, 9, 30, 17, 30, tzinfo=timezone.utc), tz))
        self.assertTrue(in_quiet_hours(datetime(2026, 9, 30, 2, 29, tzinfo=timezone.utc), tz))
        self.assertFalse(in_quiet_hours(datetime(2026, 9, 30, 2, 30, tzinfo=timezone.utc), tz))


if __name__ == "__main__":
    unittest.main()
