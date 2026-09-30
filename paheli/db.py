"""SQLite for local dev, Postgres when DATABASE_URL is set (Railway)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    subscribed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    match_key TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    home_name TEXT NOT NULL,
    away_name TEXT NOT NULL,
    home_abbr TEXT NOT NULL DEFAULT '',
    away_abbr TEXT NOT NULL DEFAULT '',
    league TEXT NOT NULL DEFAULT '',
    kickoff TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    home_score INTEGER,
    away_score INTEGER,
    score_display TEXT NOT NULL DEFAULT '',
    winner TEXT,
    report TEXT NOT NULL DEFAULT '',
    state_description TEXT NOT NULL DEFAULT '',
    notable INTEGER NOT NULL DEFAULT 0,
    match_date TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    match_key TEXT NOT NULL,
    pick TEXT NOT NULL,
    exact_score TEXT,
    points INTEGER,
    winner_correct INTEGER,
    exact_correct INTEGER,
    result_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    settled_at TEXT,
    UNIQUE(user_id, match_key)
);

CREATE TABLE IF NOT EXISTS reminder_sends (
    user_id INTEGER NOT NULL,
    match_key TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (user_id, match_key)
);

CREATE TABLE IF NOT EXISTS lead_attribution (
    user_id INTEGER PRIMARY KEY,
    campaign TEXT NOT NULL DEFAULT 'direct',
    first_start_arg TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_start_arg TEXT NOT NULL DEFAULT '',
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lead_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_predictions_user ON predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_predictions_match ON predictions(match_key);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date, notable);
CREATE INDEX IF NOT EXISTS idx_lead_events_event ON lead_events(event, created_at);
CREATE INDEX IF NOT EXISTS idx_clicks_action ON clicks(action);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    subscribed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clicks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    match_key TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    home_name TEXT NOT NULL,
    away_name TEXT NOT NULL,
    home_abbr TEXT NOT NULL DEFAULT '',
    away_abbr TEXT NOT NULL DEFAULT '',
    league TEXT NOT NULL DEFAULT '',
    kickoff TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    home_score INTEGER,
    away_score INTEGER,
    score_display TEXT NOT NULL DEFAULT '',
    winner TEXT,
    report TEXT NOT NULL DEFAULT '',
    state_description TEXT NOT NULL DEFAULT '',
    notable INTEGER NOT NULL DEFAULT 0,
    match_date TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    match_key TEXT NOT NULL,
    pick TEXT NOT NULL,
    exact_score TEXT,
    points INTEGER,
    winner_correct INTEGER,
    exact_correct INTEGER,
    result_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    settled_at TEXT,
    UNIQUE(user_id, match_key)
);

CREATE TABLE IF NOT EXISTS reminder_sends (
    user_id BIGINT NOT NULL,
    match_key TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (user_id, match_key)
);

CREATE TABLE IF NOT EXISTS lead_attribution (
    user_id BIGINT PRIMARY KEY,
    campaign TEXT NOT NULL DEFAULT 'direct',
    first_start_arg TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_start_arg TEXT NOT NULL DEFAULT '',
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lead_events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    event TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_predictions_user ON predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_predictions_match ON predictions(match_key);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date, notable);
CREATE INDEX IF NOT EXISTS idx_lead_events_event ON lead_events(event, created_at);
CREATE INDEX IF NOT EXISTS idx_clicks_action ON clicks(action);
"""


def split_sql(script: str) -> list[str]:
    return [chunk.strip() for chunk in script.split(";") if chunk.strip()]


def as_dict(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    return dict(row)


class Database:
    def __init__(self, url: str):
        self.url = url
        if url.startswith("sqlite:"):
            self.dialect = "sqlite"
            if not url.startswith("sqlite:///"):
                raise ValueError("SQLite URLs must look like sqlite:///paheli777.db")
            self.sqlite_path = url[len("sqlite:///") :]
        elif url.startswith("postgresql://") or url.startswith("postgres://"):
            self.dialect = "postgres"
            self.sqlite_path = ""
        else:
            raise ValueError("DATABASE_URL must be postgres or sqlite")

    def adapt(self, sql: str) -> str:
        if self.dialect == "postgres":
            return sql.replace("?", "%s")
        return sql

    @contextmanager
    def connection(self):
        if self.dialect == "sqlite":
            conn = sqlite3.connect(self.sqlite_path, timeout=10, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return

        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(self.url, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        script = SQLITE_SCHEMA if self.dialect == "sqlite" else POSTGRES_SCHEMA
        with self.connection() as conn:
            for statement in split_sql(script):
                conn.execute(statement)

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.connection() as conn:
            cursor = conn.execute(self.adapt(sql), params)
            return [as_dict(row) for row in cursor.fetchall()]

    def fetchone(self, sql: str, params: tuple = ()):
        with self.connection() as conn:
            cursor = conn.execute(self.adapt(sql), params)
            return as_dict(cursor.fetchone())

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self.connection() as conn:
            cursor = conn.execute(self.adapt(sql), params)
            return cursor.rowcount
