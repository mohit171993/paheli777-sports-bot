"""Scoring, streak, and weekly window."""

import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from paheli.scoring import (
    EXACT_SCORE_BONUS,
    WINNER_POINTS,
    prediction_streak,
    score_prediction,
    week_window,
)


class ScoringTests(unittest.TestCase):
    def test_correct_winner_without_score(self):
        result = score_prediction("home", None, None, "home", "2", "1")
        self.assertEqual(result["points"], WINNER_POINTS)
        self.assertEqual(result["winner_correct"], 1)
        self.assertEqual(result["exact_hit"], 0)

    def test_exact_score_adds_bonus(self):
        result = score_prediction("home", "2", "1", "home", "2", "1")
        self.assertEqual(result["points"], WINNER_POINTS + EXACT_SCORE_BONUS)
        self.assertEqual(result["exact_hit"], 1)

    def test_wrong_winner_scores_zero(self):
        result = score_prediction("away", "0", "1", "home", "2", "1")
        self.assertEqual(result["points"], 0)
        self.assertEqual(result["winner_correct"], 0)
        self.assertEqual(result["exact_hit"], 0)

    def test_exact_score_bonus_is_independent_of_winner_call(self):
        result = score_prediction("away", "2", "1", "home", "2", "1")
        self.assertEqual(result["points"], EXACT_SCORE_BONUS)
        self.assertEqual(result["exact_hit"], 1)
        self.assertEqual(result["winner_correct"], 0)

    def test_draw_and_exact_score(self):
        result = score_prediction("draw", "1", "1", None, "1", "1")
        self.assertEqual(result["points"], WINNER_POINTS + EXACT_SCORE_BONUS)

    def test_unknown_result_is_not_scored(self):
        self.assertIsNone(score_prediction("home", None, None, None, None, None))

    def test_cricket_scoreboard_exact_match(self):
        result = score_prediction("away", "137/8", "139/4", None, "137 / 8", "139 / 4")
        self.assertEqual(result["winner_correct"], 1)
        self.assertEqual(result["exact_hit"], 1)
        self.assertEqual(result["points"], WINNER_POINTS + EXACT_SCORE_BONUS)

    def test_integer_score_normalization(self):
        result = score_prediction("home", "2", "1", "home", "02", "1")
        self.assertEqual(result["exact_hit"], 1)

    def test_penalty_winner_can_differ_from_drawn_score(self):
        result = score_prediction("home", "1", "1", "home", "1", "1")
        self.assertEqual(result["points"], WINNER_POINTS + EXACT_SCORE_BONUS)
        drawn = score_prediction("draw", "1", "1", "home", "1", "1")
        self.assertEqual(drawn["points"], EXACT_SCORE_BONUS)
        self.assertEqual(drawn["winner_correct"], 0)

    def test_streak_stops_at_first_miss(self):
        self.assertEqual(prediction_streak([True, True, False, True]), 2)
        self.assertEqual(prediction_streak([]), 0)
        self.assertEqual(prediction_streak([False, True]), 0)
        self.assertEqual(prediction_streak([True, True, True]), 3)

    def test_week_window_uses_app_timezone(self):
        tz = ZoneInfo("Asia/Kolkata")
        # Sunday evening UTC is already Monday in Kolkata.
        now = datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc)
        start, end = week_window(now, tz)
        self.assertEqual(start, datetime(2026, 9, 28, 0, 0, tzinfo=tz))
        self.assertEqual(end - start, timedelta(days=7))


if __name__ == "__main__":
    unittest.main()
