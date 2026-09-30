"""Persistence for users, the prediction card, scores, reminders, and leads."""

from __future__ import annotations

from datetime import datetime

from paheli.clock import utc_iso
from paheli.db import Database, as_dict
from paheli.leads import campaign_from_start_arg, clean_start_arg
from paheli.matches import merge_match
from paheli.scoring import (
    Outcome,
    best_streak,
    current_streak,
    is_pick_locked,
    parse_exact_score,
    score_prediction,
)

KEEP = object()


class PickLocked(Exception):
    """Raised when a winner or exact score is submitted at or after kick-off."""


class Store:
    def __init__(self, db: Database):
        self.db = db

    def touch_user(self, user_id: int, username: str | None, first_name: str | None, now: datetime) -> None:
        stamp = utc_iso(now)
        self.db.execute(
            """
            INSERT INTO users(user_id, username, first_name, language, subscribed, created_at, last_seen)
            VALUES (?, ?, ?, 'en', 0, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen = excluded.last_seen
            """,
            (user_id, username, first_name, stamp, stamp),
        )

    def language(self, user_id: int) -> str:
        row = self.db.fetchone("SELECT language FROM users WHERE user_id = ?", (user_id,))
        if row and row.get("language") in {"en", "hi"}:
            return row["language"]
        return "en"

    def set_language(self, user_id: int, language: str, now: datetime) -> None:
        self.db.execute(
            "UPDATE users SET language = ?, last_seen = ? WHERE user_id = ?",
            (language, utc_iso(now), user_id),
        )

    def is_subscribed(self, user_id: int) -> bool:
        row = self.db.fetchone("SELECT subscribed FROM users WHERE user_id = ?", (user_id,))
        return bool(row and int(row["subscribed"]) == 1)

    def set_subscribed(self, user_id: int, value: bool, now: datetime) -> None:
        self.db.execute(
            "UPDATE users SET subscribed = ?, last_seen = ? WHERE user_id = ?",
            (1 if value else 0, utc_iso(now), user_id),
        )

    def subscribed_user_ids(self) -> list[int]:
        rows = self.db.fetchall(
            "SELECT user_id FROM users WHERE subscribed = 1 ORDER BY user_id"
        )
        return [int(row["user_id"]) for row in rows]

    def track(self, user_id: int, action: str, now: datetime) -> None:
        self.db.execute(
            "INSERT INTO clicks(user_id, action, created_at) VALUES (?, ?, ?)",
            (user_id, action[:80], utc_iso(now)),
        )

    def admin_counts(self) -> dict:
        users = self.db.fetchone("SELECT COUNT(*) AS c FROM users")
        subs = self.db.fetchone("SELECT COUNT(*) AS c FROM users WHERE subscribed = 1")
        clicks = self.db.fetchone("SELECT COUNT(*) AS c FROM clicks")
        preds = self.db.fetchone("SELECT COUNT(*) AS c FROM predictions")
        open_matches = self.db.fetchone(
            """
            SELECT COUNT(*) AS c FROM matches
            WHERE notable = 1 AND status IN ('scheduled', 'live')
            """
        )
        return {
            "users": int(users["c"]) if users else 0,
            "subscribers": int(subs["c"]) if subs else 0,
            "clicks": int(clicks["c"]) if clicks else 0,
            "predictions": int(preds["c"]) if preds else 0,
            "open_matches": int(open_matches["c"]) if open_matches else 0,
        }

    def top_actions(self, limit: int = 8) -> list[dict]:
        return self.db.fetchall(
            """
            SELECT action, COUNT(*) AS c FROM clicks
            GROUP BY action ORDER BY c DESC LIMIT ?
            """,
            (limit,),
        )

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.db.fetchone("SELECT value FROM app_settings WHERE key = ?", (key,))
        if not row:
            return default
        return str(row["value"])

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute(
            """
            INSERT INTO app_settings(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def get_match(self, match_key: str) -> dict | None:
        return self.db.fetchone("SELECT * FROM matches WHERE match_key = ?", (match_key,))

    def upsert_match(self, incoming: dict, notable: bool, now: datetime) -> None:
        existing = self.get_match(incoming["match_key"])
        row = merge_match(existing, incoming, notable, utc_iso(now))
        self.db.execute(
            """
            INSERT INTO matches(
                match_key, sport, provider_id, home_name, away_name, home_abbr, away_abbr,
                league, kickoff, status, home_score, away_score, score_display, winner,
                report, state_description, notable, match_date, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_key) DO UPDATE SET
                sport = excluded.sport,
                provider_id = excluded.provider_id,
                home_name = excluded.home_name,
                away_name = excluded.away_name,
                home_abbr = excluded.home_abbr,
                away_abbr = excluded.away_abbr,
                league = excluded.league,
                kickoff = excluded.kickoff,
                status = excluded.status,
                home_score = excluded.home_score,
                away_score = excluded.away_score,
                score_display = excluded.score_display,
                winner = excluded.winner,
                report = excluded.report,
                state_description = excluded.state_description,
                notable = excluded.notable,
                match_date = excluded.match_date,
                updated_at = excluded.updated_at
            """,
            (
                row["match_key"],
                row["sport"],
                row["provider_id"],
                row["home_name"],
                row["away_name"],
                row.get("home_abbr") or "",
                row.get("away_abbr") or "",
                row.get("league") or "",
                row["kickoff"],
                row.get("status") or "scheduled",
                row.get("home_score"),
                row.get("away_score"),
                row.get("score_display") or "",
                row.get("winner"),
                row.get("report") or "",
                row.get("state_description") or "",
                int(row.get("notable") or 0),
                row["match_date"],
                row["updated_at"],
            ),
        )

    def list_notable(self, match_date: str, sport: str | None = None) -> list[dict]:
        if sport:
            return self.db.fetchall(
                """
                SELECT * FROM matches
                WHERE match_date = ? AND notable = 1 AND sport = ?
                ORDER BY kickoff ASC, match_key ASC
                """,
                (match_date, sport),
            )
        return self.db.fetchall(
            """
            SELECT * FROM matches
            WHERE match_date = ? AND notable = 1
            ORDER BY kickoff ASC, match_key ASC
            """,
            (match_date,),
        )

    def matches_to_refresh(self) -> list[dict]:
        return self.db.fetchall(
            """
            SELECT * FROM matches
            WHERE status NOT IN ('finished', 'void')
               OR match_key IN (
                    SELECT match_key FROM predictions WHERE result_status = 'pending'
               )
            ORDER BY kickoff ASC
            """
        )

    def prediction(self, user_id: int, match_key: str) -> dict | None:
        return self.db.fetchone(
            "SELECT * FROM predictions WHERE user_id = ? AND match_key = ?",
            (user_id, match_key),
        )

    def has_pick(self, user_id: int, match_key: str) -> bool:
        return self.prediction(user_id, match_key) is not None

    def picks_for(self, user_id: int, match_keys: list[str]) -> dict[str, dict]:
        if not match_keys:
            return {}
        placeholders = ", ".join("?" for _ in match_keys)
        rows = self.db.fetchall(
            f"""
            SELECT * FROM predictions
            WHERE user_id = ? AND match_key IN ({placeholders})
            """,
            (user_id, *match_keys),
        )
        return {row["match_key"]: row for row in rows}

    def place_pick(
        self,
        user_id: int,
        match_key: str,
        pick: str,
        now: datetime,
        exact=KEEP,
    ) -> dict:
        choice = (pick or "").strip().casefold()
        if choice not in {"home", "away", "draw"}:
            raise ValueError("Pick must be home, away, or draw")
        existing = self.prediction(user_id, match_key)
        if exact is KEEP:
            exact_value = existing.get("exact_score") if existing else None
        elif exact in (None, ""):
            exact_value = None
        else:
            parsed = parse_exact_score(str(exact))
            if not parsed:
                raise ValueError("Exact score must look like 2-1")
            exact_value = f"{parsed[0]}-{parsed[1]}"

        stamp = utc_iso(now)
        with self.db.connection() as conn:
            cursor = conn.execute(
                self.db.adapt("SELECT * FROM matches WHERE match_key = ?"),
                (match_key,),
            )
            match = as_dict(cursor.fetchone())
            if not match:
                raise LookupError("Match is not on the card")
            if is_pick_locked(match["kickoff"], now, match.get("status")):
                raise PickLocked()
            current = conn.execute(
                self.db.adapt(
                    "SELECT result_status FROM predictions WHERE user_id = ? AND match_key = ?"
                ),
                (user_id, match_key),
            )
            current_row = as_dict(current.fetchone())
            if current_row and current_row.get("result_status") != "pending":
                raise PickLocked()
            saved = conn.execute(
                self.db.adapt(
                    """
                    INSERT INTO predictions(
                        user_id, match_key, pick, exact_score, points, winner_correct,
                        exact_correct, result_status, created_at, updated_at, settled_at
                    ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, 'pending', ?, ?, NULL)
                    ON CONFLICT(user_id, match_key) DO UPDATE SET
                        pick = excluded.pick,
                        exact_score = excluded.exact_score,
                        updated_at = excluded.updated_at
                    WHERE predictions.result_status = 'pending'
                    """
                ),
                (user_id, match_key, choice, exact_value, stamp, stamp),
            )
            if saved.rowcount == 0:
                raise PickLocked()
        row = self.prediction(user_id, match_key)
        if row is None:
            raise PickLocked()
        return row

    def apply_outcome(self, match_key: str, outcome: Outcome, now: datetime) -> int:
        """Update a stored match and score any pending picks that can settle."""
        existing = self.get_match(match_key)
        if not existing:
            return 0
        status = existing["status"]
        if outcome.status == "unknown":
            status = existing["status"]
        elif existing["status"] in {"finished", "void"} and outcome.status in {"scheduled", "live"}:
            status = existing["status"]
        elif outcome.status in {"finished", "void", "live", "scheduled"}:
            status = outcome.status
        winner = outcome.winner or existing.get("winner")
        home_score = outcome.home_score if outcome.home_score is not None else existing.get("home_score")
        away_score = outcome.away_score if outcome.away_score is not None else existing.get("away_score")
        score_display = outcome.score_display or existing.get("score_display") or ""
        report = outcome.report or existing.get("report") or ""
        description = outcome.state_description or existing.get("state_description") or ""
        settled = Outcome(
            status=status,
            winner=winner,
            home_score=home_score,
            away_score=away_score,
            score_display=score_display,
            report=report,
            state_description=description,
        )
        stamp = utc_iso(now)
        scored = 0
        with self.db.connection() as conn:
            conn.execute(
                self.db.adapt(
                    """
                    UPDATE matches SET
                        status = ?, home_score = ?, away_score = ?, score_display = ?,
                        winner = ?, report = ?, state_description = ?, updated_at = ?
                    WHERE match_key = ?
                    """
                ),
                (
                    settled.status,
                    settled.home_score,
                    settled.away_score,
                    settled.score_display,
                    settled.winner,
                    settled.report,
                    settled.state_description,
                    stamp,
                    match_key,
                ),
            )
            ready = settled.status == "void" or (
                settled.status == "finished" and settled.winner in {"home", "away", "draw"}
            )
            if not ready:
                return 0
            cursor = conn.execute(
                self.db.adapt(
                    """
                    SELECT * FROM predictions
                    WHERE match_key = ? AND result_status = 'pending'
                    """
                ),
                (match_key,),
            )
            pending = [as_dict(row) for row in cursor.fetchall()]
            for row in pending:
                result = score_prediction(row["pick"], row.get("exact_score"), settled)
                if result.result_status == "pending":
                    continue
                conn.execute(
                    self.db.adapt(
                        """
                        UPDATE predictions SET
                            points = ?, winner_correct = ?, exact_correct = ?,
                            result_status = ?, settled_at = ?, updated_at = ?
                        WHERE id = ?
                        """
                    ),
                    (
                        result.points,
                        _flag(result.winner_correct),
                        _flag(result.exact_correct),
                        result.result_status,
                        stamp,
                        stamp,
                        row["id"],
                    ),
                )
                scored += 1
        return scored

    def leaderboard(self, start_iso: str, end_iso: str, limit: int = 10) -> list[dict]:
        return self.db.fetchall(
            """
            SELECT u.user_id, u.username, u.first_name,
                   SUM(p.points) AS points,
                   SUM(CASE WHEN p.winner_correct = 1 THEN 1 ELSE 0 END) AS correct,
                   COUNT(*) AS played
            FROM predictions p
            JOIN matches m ON m.match_key = p.match_key
            JOIN users u ON u.user_id = p.user_id
            WHERE p.result_status = 'scored'
              AND (? = '' OR m.kickoff >= ?)
              AND (? = '' OR m.kickoff < ?)
            GROUP BY u.user_id, u.username, u.first_name
            ORDER BY points DESC, correct DESC, u.user_id ASC
            LIMIT ?
            """,
            (start_iso, start_iso, end_iso, end_iso, limit),
        )

    def user_points(self, user_id: int, start_iso: str, end_iso: str) -> int | None:
        row = self.db.fetchone(
            """
            SELECT SUM(p.points) AS points
            FROM predictions p
            JOIN matches m ON m.match_key = p.match_key
            WHERE p.user_id = ? AND p.result_status = 'scored'
              AND (? = '' OR m.kickoff >= ?)
              AND (? = '' OR m.kickoff < ?)
            """,
            (user_id, start_iso, start_iso, end_iso, end_iso),
        )
        if not row or row["points"] is None:
            return None
        return int(row["points"])

    def user_rank(self, user_id: int, start_iso: str, end_iso: str) -> tuple[int, int] | None:
        points = self.user_points(user_id, start_iso, end_iso)
        if points is None:
            return None
        row = self.db.fetchone(
            """
            SELECT COUNT(*) AS c FROM (
                SELECT p.user_id, SUM(p.points) AS points
                FROM predictions p
                JOIN matches m ON m.match_key = p.match_key
                WHERE p.result_status = 'scored'
                  AND (? = '' OR m.kickoff >= ?)
                  AND (? = '' OR m.kickoff < ?)
                GROUP BY p.user_id
            ) AS totals
            WHERE totals.points > ?
            """,
            (start_iso, start_iso, end_iso, end_iso, points),
        )
        ahead = int(row["c"]) if row else 0
        return ahead + 1, points

    def user_stats(self, user_id: int) -> dict:
        totals = self.db.fetchone(
            """
            SELECT
                COUNT(*) AS picks,
                SUM(CASE WHEN result_status = 'scored' THEN 1 ELSE 0 END) AS settled,
                SUM(CASE WHEN result_status = 'scored' THEN points ELSE 0 END) AS points,
                SUM(CASE WHEN winner_correct = 1 THEN 1 ELSE 0 END) AS correct,
                SUM(CASE WHEN exact_correct = 1 THEN 1 ELSE 0 END) AS exacts
            FROM predictions
            WHERE user_id = ?
            """,
            (user_id,),
        )
        rows = self.db.fetchall(
            """
            SELECT p.winner_correct AS ok
            FROM predictions p
            JOIN matches m ON m.match_key = p.match_key
            WHERE p.user_id = ? AND p.result_status = 'scored'
            ORDER BY m.kickoff ASC, p.id ASC
            """,
            (user_id,),
        )
        flags = [bool(row["ok"]) for row in rows]
        return {
            "picks": int(totals["picks"] or 0) if totals else 0,
            "settled": int(totals["settled"] or 0) if totals else 0,
            "points": int(totals["points"] or 0) if totals else 0,
            "correct": int(totals["correct"] or 0) if totals else 0,
            "exacts": int(totals["exacts"] or 0) if totals else 0,
            "current_streak": current_streak(list(reversed(flags))),
            "best_streak": best_streak(flags),
        }

    def claim_reminder(self, user_id: int, match_key: str, now: datetime) -> bool:
        stamp = utc_iso(now)
        with self.db.connection() as conn:
            cursor = conn.execute(
                self.db.adapt(
                    """
                    INSERT INTO reminder_sends(user_id, match_key, sent_at, status)
                    VALUES (?, ?, ?, 'pending')
                    ON CONFLICT(user_id, match_key) DO UPDATE SET
                        status = 'pending',
                        sent_at = excluded.sent_at
                    WHERE reminder_sends.status = 'failed'
                    """
                ),
                (user_id, match_key, stamp),
            )
            return cursor.rowcount == 1

    def finish_reminder(self, user_id: int, match_key: str, status: str) -> None:
        self.db.execute(
            "UPDATE reminder_sends SET status = ? WHERE user_id = ? AND match_key = ?",
            (status, user_id, match_key),
        )

    def record_start(self, user_id: int, arg: str, now: datetime) -> str:
        stamp = utc_iso(now)
        start_arg = clean_start_arg(arg)
        campaign = campaign_from_start_arg(start_arg)
        with self.db.connection() as conn:
            existing = as_dict(
                conn.execute(
                    self.db.adapt("SELECT campaign FROM lead_attribution WHERE user_id = ?"),
                    (user_id,),
                ).fetchone()
            )
            if existing:
                conn.execute(
                    self.db.adapt(
                        """
                        UPDATE lead_attribution
                        SET last_start_arg = ?, last_seen_at = ?
                        WHERE user_id = ?
                        """
                    ),
                    (start_arg, stamp, user_id),
                )
                stored = existing["campaign"]
            else:
                conn.execute(
                    self.db.adapt(
                        """
                        INSERT INTO lead_attribution(
                            user_id, campaign, first_start_arg, first_seen_at,
                            last_start_arg, last_seen_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """
                    ),
                    (user_id, campaign, start_arg, stamp, start_arg, stamp),
                )
                stored = campaign
            conn.execute(
                self.db.adapt(
                    """
                    INSERT INTO lead_events(user_id, event, value, created_at)
                    VALUES (?, 'start', ?, ?)
                    """
                ),
                (user_id, start_arg, stamp),
            )
        return stored

    def record_event(self, user_id: int, event: str, value: str, now: datetime) -> None:
        self.db.execute(
            "INSERT INTO lead_events(user_id, event, value, created_at) VALUES (?, ?, ?, ?)",
            (user_id, event[:64], (value or "")[:160], utc_iso(now)),
        )

    def lead_summary(self) -> dict:
        campaigns = self.db.fetchall(
            """
            SELECT campaign, COUNT(*) AS c
            FROM lead_attribution
            GROUP BY campaign
            ORDER BY c DESC, campaign ASC
            LIMIT 12
            """
        )
        events = self.db.fetchall(
            """
            SELECT event, COUNT(*) AS c
            FROM lead_events
            GROUP BY event
            ORDER BY c DESC, event ASC
            """
        )
        interested = self.db.fetchone(
            "SELECT COUNT(DISTINCT user_id) AS c FROM lead_events WHERE event = 'interested'"
        )
        return {
            "campaigns": campaigns,
            "events": events,
            "interested": int(interested["c"]) if interested else 0,
        }


def _flag(value: bool | None):
    if value is None:
        return None
    return 1 if value else 0
