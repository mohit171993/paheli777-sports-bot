"""Postgres via DATABASE_URL, with a sqlite fallback for local development."""

from __future__ import annotations

import sqlite3
import threading
from typing import Any


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

CREATE TABLE IF NOT EXISTS fixtures (
    match_key TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    home_name TEXT NOT NULL,
    away_name TEXT NOT NULL,
    league TEXT NOT NULL DEFAULT '',
    kickoff TEXT NOT NULL,
    status TEXT NOT NULL,
    state_label TEXT NOT NULL DEFAULT '',
    home_score TEXT,
    away_score TEXT,
    winner TEXT,
    detail TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    user_id INTEGER NOT NULL,
    match_key TEXT NOT NULL,
    winner TEXT NOT NULL,
    home_score TEXT,
    away_score TEXT,
    points INTEGER,
    winner_correct INTEGER,
    exact_hit INTEGER,
    scored_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, match_key)
);

CREATE TABLE IF NOT EXISTS reminder_sends (
    user_id INTEGER NOT NULL,
    match_key TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (user_id, match_key)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lead_attribution (
    user_id INTEGER PRIMARY KEY,
    campaign TEXT NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_predictions_user ON predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_fixtures_kickoff ON fixtures(kickoff);
CREATE INDEX IF NOT EXISTS idx_fixtures_status ON fixtures(status, kickoff);
CREATE INDEX IF NOT EXISTS idx_lead_events_event ON lead_events(event, created_at);
"""


POSTGRES_SCHEMA = SQLITE_SCHEMA.replace(
    "id INTEGER PRIMARY KEY AUTOINCREMENT",
    "id BIGSERIAL PRIMARY KEY",
)


class Database:
    def __init__(self, dialect: str, connection: Any):
        self.dialect = dialect
        self._conn = connection
        self._lock = threading.Lock()

    @classmethod
    def connect(cls, database_url: str | None = None) -> "Database":
        url = (database_url or "").strip()
        if url.startswith("postgres://") or url.startswith("postgresql://"):
            import psycopg
            from psycopg.rows import dict_row

            connection = psycopg.connect(
                url,
                autocommit=True,
                row_factory=dict_row,
                connect_timeout=10,
            )
            return cls("postgres", connection)

        if url.startswith("sqlite:///"):
            path = url[len("sqlite:///") :]
        elif url == "":
            path = "paheli777.db"
        else:
            raise RuntimeError(
                "DATABASE_URL must be a postgres:// or postgresql:// URL, "
                "a sqlite:/// path, or empty for the local sqlite fallback"
            )

        connection = sqlite3.connect(path, check_same_thread=False, timeout=30)
        connection.row_factory = sqlite3.Row
        return cls("sqlite", connection)

    def init(self) -> None:
        schema = POSTGRES_SCHEMA if self.dialect == "postgres" else SQLITE_SCHEMA
        statements = [part.strip() for part in schema.split(";") if part.strip()]
        with self._lock:
            for statement in statements:
                self._conn.execute(statement)
            if self.dialect == "sqlite":
                self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _sql(self, sql: str) -> str:
        if self.dialect == "postgres":
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with self._lock:
            cursor = self._conn.execute(self._sql(sql), tuple(params))
            rows: list[dict] = []
            if cursor.description:
                fetched = cursor.fetchall()
                rows = [dict(row) for row in fetched]
            if self.dialect == "sqlite":
                self._conn.commit()
            return rows

    def write(self, sql: str, params: tuple | list = ()) -> int:
        with self._lock:
            cursor = self._conn.execute(self._sql(sql), tuple(params))
            count = int(cursor.rowcount or 0)
            if self.dialect == "sqlite":
                self._conn.commit()
            return count
