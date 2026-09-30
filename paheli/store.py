"""Persistence for users, fixtures, predictions, reminders, and leads."""

from __future__ import annotations

from datetime import datetime, timezone

from paheli.db import Database
from paheli.leads import campaign_from_start_arg, clean_start_arg
from paheli.scoring import (
    PickLocked,
    ensure_score_pair,
    is_pick_locked,
    iso_utc,
    parse_iso,
    score_prediction,
)


def now_iso() -> str:
    return iso_utc(datetime.now(timezone.utc))


def touch_user(
    db: Database,
    user_id: int,
    username: str | None,
    first_name: str | None,
) -> None:
    stamp = now_iso()
    db.execute(
        """
        INSERT INTO users(user_id, username, first_name, language, subscribed, created_at, last_seen)
        VALUES (?, ?, ?, 'en', 0, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name,
            last_seen=excluded.last_seen
        """,
        (user_id, username, first_name, stamp, stamp),
    )


def get_user(db: Database, user_id: int) -> dict | None:
    return _one(db, "SELECT * FROM users WHERE user_id = ?", (user_id,))


def set_language(db: Database, user_id: int, language: str) -> None:
    db.write(
        "UPDATE users SET language = ?, last_seen = ? WHERE user_id = ?",
        (language, now_iso(), user_id),
    )


def is_subscribed(db: Database, user_id: int) -> bool:
    row = _one(db, "SELECT subscribed FROM users WHERE user_id = ?", (user_id,))
    return bool(row and int(row["subscribed"]))


def set_subscribed(db: Database, user_id: int, value: bool) -> None:
    db.write(
        "UPDATE users SET subscribed = ?, last_seen = ? WHERE user_id = ?",
        (1 if value else 0, now_iso(), user_id),
    )


def track(db: Database, user_id: int, action: str) -> None:
    db.execute(
        "INSERT INTO clicks(user_id, action, created_at) VALUES (?, ?, ?)",
        (user_id, action[:80], now_iso()),
    )


def get_setting(db: Database, key: str, default: str = "") -> str:
    row = _one(db, "SELECT value FROM app_settings WHERE key = ?", (key,))
    if not row:
        return default
    return str(row["value"])


def set_setting(db: Database, key: str, value: str) -> None:
    db.execute(
        """
        INSERT INTO app_settings(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def reminders_paused(db: Database) -> bool:
    return get_setting(db, "reminders_paused", "0") == "1"


def upsert_fixtures(db: Database, fixtures: list[dict]) -> None:
    stamp = now_iso()
    for item in fixtures:
        db.execute(
            """
            INSERT INTO fixtures(
                match_key, sport, provider_id, home_name, away_name, league,
                kickoff, status, state_label, home_score, away_score, winner,
                detail, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_key) DO UPDATE SET
                home_name=excluded.home_name,
                away_name=excluded.away_name,
                league=excluded.league,
                kickoff=excluded.kickoff,
                status=excluded.status,
                state_label=excluded.state_label,
                home_score=excluded.home_score,
                away_score=excluded.away_score,
                winner=excluded.winner,
                detail=excluded.detail,
                updated_at=excluded.updated_at
            """,
            (
                item["match_key"],
                item["sport"],
                item["provider_id"],
                item["home_name"],
                item["away_name"],
                item.get("league") or "",
                item["kickoff"],
                item["status"],
                item.get("state_label") or "",
                item.get("home_score"),
                item.get("away_score"),
                item.get("winner"),
                item.get("detail") or "",
                stamp,
            ),
        )


def get_fixture(db: Database, match_key: str) -> dict | None:
    return _one(db, "SELECT * FROM fixtures WHERE match_key = ?", (match_key,))


def fixtures_between(
    db: Database,
    start_iso: str,
    end_iso: str,
    sport: str | None = None,
    status: str | None = None,
) -> list[dict]:
    sql = "SELECT * FROM fixtures WHERE kickoff >= ? AND kickoff < ?"
    params: list = [start_iso, end_iso]
    if sport:
        sql += " AND sport = ?"
        params.append(sport)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY kickoff ASC"
    return db.execute(sql, params)


def save_prediction(
    db: Database,
    *,
    user_id: int,
    match_key: str,
    winner: str,
    home_score: str | None,
    away_score: str | None,
    now: datetime,
) -> dict:
    if winner not in {"home", "away", "draw"}:
        raise ValueError("Pick home, away, or draw")
    home_score, away_score = ensure_score_pair(home_score, away_score)
    fixture = get_fixture(db, match_key)
    if not fixture:
        raise LookupError("Match not found")
    if is_pick_locked(parse_iso(fixture["kickoff"]), now, fixture["status"]):
        raise PickLocked("Picks lock at kick-off")

    stamp = iso_utc(now)
    existing = get_prediction(db, user_id, match_key)
    if existing:
        db.write(
            """
            UPDATE predictions
            SET winner = ?, home_score = ?, away_score = ?, updated_at = ?,
                points = NULL, winner_correct = NULL, exact_hit = NULL, scored_at = NULL
            WHERE user_id = ? AND match_key = ?
            """,
            (winner, home_score, away_score, stamp, user_id, match_key),
        )
    else:
        db.execute(
            """
            INSERT INTO predictions(
                user_id, match_key, winner, home_score, away_score,
                points, winner_correct, exact_hit, scored_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?)
            """,
            (user_id, match_key, winner, home_score, away_score, stamp, stamp),
        )
    saved = get_prediction(db, user_id, match_key)
    if saved is None:
        raise RuntimeError("Prediction was not saved")
    return saved


def get_prediction(db: Database, user_id: int, match_key: str) -> dict | None:
    return _one(
        db,
        "SELECT * FROM predictions WHERE user_id = ? AND match_key = ?",
        (user_id, match_key),
    )


def predictions_for_user(db: Database, user_id: int, match_keys: list[str]) -> dict[str, dict]:
    if not match_keys:
        return {}
    placeholders = ", ".join("?" for _ in match_keys)
    rows = db.execute(
        f"""
        SELECT * FROM predictions
        WHERE user_id = ? AND match_key IN ({placeholders})
        """,
        [user_id, *match_keys],
    )
    return {str(row["match_key"]): row for row in rows}


def user_picks_between(
    db: Database, user_id: int, start_iso: str, end_iso: str
) -> list[dict]:
    return db.execute(
        """
        SELECT p.*, f.home_name, f.away_name, f.sport, f.kickoff, f.status,
               f.league, f.home_score AS actual_home, f.away_score AS actual_away,
               f.winner AS actual_winner, f.state_label
        FROM predictions p
        JOIN fixtures f ON f.match_key = p.match_key
        WHERE p.user_id = ? AND f.kickoff >= ? AND f.kickoff < ?
        ORDER BY f.kickoff ASC
        """,
        (user_id, start_iso, end_iso),
    )


def settle_finished(db: Database, now: datetime | None = None) -> int:
    """Score every finished match. Safe to run repeatedly."""
    stamp = iso_utc(now or datetime.now(timezone.utc))
    rows = db.execute(
        """
        SELECT p.user_id, p.match_key, p.winner, p.home_score, p.away_score,
               p.points, p.winner_correct, p.exact_hit,
               f.winner AS actual_winner, f.home_score AS actual_home,
               f.away_score AS actual_away, f.status
        FROM predictions p
        JOIN fixtures f ON f.match_key = p.match_key
        WHERE f.status = 'finished'
        """
    )
    changed = 0
    for row in rows:
        result = score_prediction(
            row["winner"],
            row["home_score"],
            row["away_score"],
            row["actual_winner"],
            row["actual_home"],
            row["actual_away"],
        )
        if result is None:
            continue
        if (
            row["points"] is not None
            and int(row["points"]) == result["points"]
            and int(row["winner_correct"] or 0) == result["winner_correct"]
            and int(row["exact_hit"] or 0) == result["exact_hit"]
        ):
            continue
        db.write(
            """
            UPDATE predictions
            SET points = ?, winner_correct = ?, exact_hit = ?, scored_at = ?
            WHERE user_id = ? AND match_key = ?
            """,
            (
                result["points"],
                result["winner_correct"],
                result["exact_hit"],
                stamp,
                row["user_id"],
                row["match_key"],
            ),
        )
        changed += 1
    return changed


def leaderboard(
    db: Database,
    start_iso: str | None = None,
    end_iso: str | None = None,
    limit: int = 10,
) -> list[dict]:
    return db.execute(
        """
        SELECT u.user_id, u.username, u.first_name,
               SUM(p.points) AS points,
               COUNT(*) AS played,
               SUM(p.winner_correct) AS correct
        FROM predictions p
        JOIN users u ON u.user_id = p.user_id
        JOIN fixtures f ON f.match_key = p.match_key
        WHERE p.points IS NOT NULL
          AND (? IS NULL OR f.kickoff >= ?)
          AND (? IS NULL OR f.kickoff < ?)
        GROUP BY u.user_id, u.username, u.first_name
        ORDER BY points DESC, correct DESC, played ASC, u.user_id ASC
        LIMIT ?
        """,
        (start_iso, start_iso, end_iso, end_iso, limit),
    )


def user_point_total(
    db: Database, user_id: int, start_iso: str | None = None, end_iso: str | None = None
) -> dict:
    row = _one(
        db,
        """
        SELECT COALESCE(SUM(p.points), 0) AS points,
               COUNT(p.match_key) AS played,
               COALESCE(SUM(p.winner_correct), 0) AS correct,
               COALESCE(SUM(p.exact_hit), 0) AS exact
        FROM predictions p
        JOIN fixtures f ON f.match_key = p.match_key
        WHERE p.user_id = ? AND p.points IS NOT NULL
          AND (? IS NULL OR f.kickoff >= ?)
          AND (? IS NULL OR f.kickoff < ?)
        """,
        (user_id, start_iso, start_iso, end_iso, end_iso),
    )
    return row or {"points": 0, "played": 0, "correct": 0, "exact": 0}


def user_rank(
    db: Database, user_id: int, points: int, start_iso: str | None, end_iso: str | None
) -> int | None:
    if int(points) <= 0 and user_point_total(db, user_id, start_iso, end_iso)["played"] == 0:
        return None
    row = _one(
        db,
        """
        SELECT 1 + COUNT(*) AS rank
        FROM (
            SELECT p.user_id AS user_id, SUM(p.points) AS pts
            FROM predictions p
            JOIN fixtures f ON f.match_key = p.match_key
            WHERE p.points IS NOT NULL
              AND (? IS NULL OR f.kickoff >= ?)
              AND (? IS NULL OR f.kickoff < ?)
            GROUP BY p.user_id
        ) totals
        WHERE totals.pts > ?
        """,
        (start_iso, start_iso, end_iso, end_iso, points),
    )
    if not row:
        return None
    return int(row["rank"])


def streak_flags(db: Database, user_id: int, limit: int = 200) -> list[bool]:
    rows = db.execute(
        """
        SELECT p.winner_correct
        FROM predictions p
        JOIN fixtures f ON f.match_key = p.match_key
        WHERE p.user_id = ? AND p.points IS NOT NULL
        ORDER BY f.kickoff DESC, p.match_key DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    return [bool(int(row["winner_correct"] or 0)) for row in rows]


def users_to_remind(db: Database, match_key: str) -> list[int]:
    """Subscribed users, plus anyone who has predicted before, who have not picked."""
    rows = db.execute(
        """
        SELECT u.user_id
        FROM users u
        WHERE (
            u.subscribed = 1
            OR EXISTS (
                SELECT 1 FROM predictions earlier WHERE earlier.user_id = u.user_id
            )
        )
        AND NOT EXISTS (
            SELECT 1 FROM predictions p
            WHERE p.user_id = u.user_id AND p.match_key = ?
        )
        AND NOT EXISTS (
            SELECT 1 FROM reminder_sends r
            WHERE r.user_id = u.user_id AND r.match_key = ?
        )
        ORDER BY u.user_id ASC
        """,
        (match_key, match_key),
    )
    return [int(row["user_id"]) for row in rows]


def mark_reminder_sent(db: Database, user_id: int, match_key: str, when: datetime) -> None:
    db.execute(
        """
        INSERT INTO reminder_sends(user_id, match_key, sent_at) VALUES (?, ?, ?)
        ON CONFLICT(user_id, match_key) DO NOTHING
        """,
        (user_id, match_key, iso_utc(when)),
    )


def subscribed_user_ids(db: Database) -> list[int]:
    rows = db.execute(
        "SELECT user_id FROM users WHERE subscribed = 1 ORDER BY user_id ASC"
    )
    return [int(row["user_id"]) for row in rows]


def record_start(db: Database, user_id: int, arg: str = "") -> str:
    stamp = now_iso()
    start_arg = clean_start_arg(arg)
    candidate = campaign_from_start_arg(start_arg)
    existing = _one(
        db, "SELECT campaign FROM lead_attribution WHERE user_id = ?", (user_id,)
    )
    if existing:
        current = str(existing["campaign"] or "direct")
        chosen = current
        if current in {"direct", "internal"} and candidate not in {"direct", "internal"}:
            chosen = candidate
        db.write(
            """
            UPDATE lead_attribution
            SET campaign = ?, last_start_arg = ?, last_seen_at = ?
            WHERE user_id = ?
            """,
            (chosen, start_arg, stamp, user_id),
        )
        campaign = chosen
    else:
        campaign = candidate
        db.execute(
            """
            INSERT INTO lead_attribution(
                user_id, campaign, first_start_arg, first_seen_at, last_start_arg, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, campaign, start_arg, stamp, start_arg, stamp),
        )
    record_event(db, user_id, "bot_start", campaign)
    return campaign


def record_event(db: Database, user_id: int, event: str, value: str = "") -> None:
    db.execute(
        "INSERT INTO lead_events(user_id, event, value, created_at) VALUES (?, ?, ?, ?)",
        (user_id, str(event)[:64], str(value)[:160], now_iso()),
    )


def admin_snapshot(db: Database) -> dict:
    users = _count(db, "SELECT COUNT(*) AS c FROM users")
    subs = _count(db, "SELECT COUNT(*) AS c FROM users WHERE subscribed = 1")
    clicks = _count(db, "SELECT COUNT(*) AS c FROM clicks")
    predictions = _count(db, "SELECT COUNT(*) AS c FROM predictions")
    predictors = _count(db, "SELECT COUNT(DISTINCT user_id) AS c FROM predictions")
    website = _count(
        db, "SELECT COUNT(DISTINCT user_id) AS c FROM lead_events WHERE event = 'website_open'"
    )
    top = db.execute(
        """
        SELECT action, COUNT(*) AS c FROM clicks
        GROUP BY action ORDER BY c DESC LIMIT 8
        """
    )
    campaigns = db.execute(
        """
        SELECT campaign, COUNT(*) AS c FROM lead_attribution
        GROUP BY campaign ORDER BY c DESC LIMIT 8
        """
    )
    return {
        "users": users,
        "subscribers": subs,
        "clicks": clicks,
        "predictions": predictions,
        "predictors": predictors,
        "website_opens": website,
        "top_actions": top,
        "campaigns": campaigns,
    }


def _one(db: Database, sql: str, params: tuple | list = ()) -> dict | None:
    rows = db.execute(sql, params)
    return rows[0] if rows else None


def _count(db: Database, sql: str) -> int:
    row = _one(db, sql)
    if not row:
        return 0
    return int(row["c"])
