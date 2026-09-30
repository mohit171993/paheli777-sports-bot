"""Highlightly payload parsing and notable-match selection."""

import unittest

from paheli.matches import notable_rank, parse_match, select_notable


def _match(key, league, kickoff="2026-09-30T15:00:00+00:00", sport="football"):
    return {
        "match_key": key,
        "sport": sport,
        "league": league,
        "kickoff": kickoff,
    }


class NotableTests(unittest.TestCase):
    def test_major_leagues_outrank_the_rest(self):
        self.assertEqual(notable_rank("football", "Premier League"), 0)
        self.assertIsNone(notable_rank("football", "2. Bundesliga"))
        self.assertEqual(notable_rank("football", "Indian Super League"), 0)
        self.assertEqual(notable_rank("cricket", "Indian Premier League"), 0)
        self.assertIsNone(notable_rank("football", "League Two"))

    def test_known_competition_hides_lower_leagues(self):
        matches = [
            _match("prem", "Premier League", "2026-09-30T18:00:00+00:00"),
            _match("low", "League Two", "2026-09-30T12:00:00+00:00"),
        ]
        self.assertEqual([item["match_key"] for item in select_notable(matches)], ["prem"])

    def test_fallback_when_nothing_is_notable(self):
        matches = [
            _match("later", "League Two", "2026-09-30T18:00:00+00:00"),
            _match("earlier", "League Two", "2026-09-30T12:00:00+00:00"),
        ]
        self.assertEqual(
            [item["match_key"] for item in select_notable(matches)],
            ["earlier", "later"],
        )


class ParseMatchTests(unittest.TestCase):
    def test_football_penalty_winner_keeps_the_drawn_score(self):
        parsed = parse_match(
            {
                "id": 11,
                "date": "2023-05-20T15:30:00.000Z",
                "homeTeam": {"name": "Lyon"},
                "awayTeam": {"name": "Reims"},
                "league": {"name": "Ligue 1"},
                "state": {
                    "description": "Finished after penalties",
                    "score": {"current": "1 - 1", "penalties": "5 - 4"},
                },
            },
            "football",
        )
        self.assertEqual(parsed["status"], "finished")
        self.assertEqual(parsed["winner"], "home")
        self.assertEqual(parsed["home_score"], "1")
        self.assertEqual(parsed["away_score"], "1")
        self.assertEqual(parsed["match_key"], "football:11")

    def test_cricket_finished_score_decides_the_winner(self):
        parsed = parse_match(
            {
                "id": "48514657",
                "startTime": "2024-01-13T14:30:00.000Z",
                "homeTeam": {"name": "Melbourne Stars"},
                "awayTeam": {"name": "Melbourne Renegades"},
                "league": {"name": "Big Bash League"},
                "format": "T20",
                "state": {
                    "description": "Finished",
                    "report": "Renegades won by 6 wickets",
                    "teams": {
                        "home": {"score": "137/8"},
                        "away": {"score": "139/4"},
                    },
                },
            },
            "cricket",
        )
        self.assertEqual(parsed["winner"], "away")
        self.assertEqual(parsed["home_score"], "137/8")
        self.assertEqual(parsed["away_score"], "139/4")
        self.assertEqual(parsed["detail"], "T20")
        self.assertEqual(parsed["kickoff"], "2024-01-13T14:30:00+00:00")

    def test_live_score_does_not_set_a_winner(self):
        parsed = parse_match(
            {
                "id": 9,
                "date": "2026-09-30T15:00:00Z",
                "homeTeam": {"name": "Arsenal"},
                "awayTeam": {"name": "Chelsea"},
                "league": {"name": "Premier League"},
                "state": {
                    "description": "Second half",
                    "score": {"current": "1 - 0"},
                },
            },
            "football",
        )
        self.assertEqual(parsed["status"], "live")
        self.assertIsNone(parsed["winner"])
        self.assertEqual(parsed["home_score"], "1")

    def test_report_names_the_winner_when_scores_are_missing(self):
        parsed = parse_match(
            {
                "id": "99",
                "startTime": "2026-09-30T09:00:00Z",
                "homeTeam": {"name": "India"},
                "awayTeam": {"name": "Australia"},
                "league": {"name": "Asia Cup"},
                "state": {
                    "description": "Finished",
                    "report": "India won by 5 wickets",
                    "teams": {"home": {}, "away": {}},
                },
            },
            "cricket",
        )
        self.assertEqual(parsed["winner"], "home")


if __name__ == "__main__":
    unittest.main()
