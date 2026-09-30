"""Paheli777 Telegram bot.

Run with the environment variables in .env.example.
Use `python bot.py --check` to verify configuration and create the schema
without connecting to Telegram.
"""

from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import Application

from paheli.config import load_config
from paheli.db import Database
from paheli.handlers import register
from paheli.highlightly import HighlightlyClient
from paheli.jobs import reminder_job, settle_job


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("paheli")


class Runtime:
    def __init__(self, cfg, db: Database, api: HighlightlyClient):
        self.cfg = cfg
        self.db = db
        self.api = api


def build_application(cfg, db: Database) -> Application:
    if not cfg.bot_token:
        raise RuntimeError("BOT_TOKEN environment variable is required")
    app = (
        Application.builder()
        .token(cfg.bot_token)
        .build()
    )
    app.bot_data["runtime"] = Runtime(cfg, db, HighlightlyClient(cfg.highlightly_api_key))
    register(app)
    if app.job_queue is None:
        raise RuntimeError(
            "Job queue is unavailable. Install python-telegram-bot[job-queue]."
        )
    app.job_queue.run_repeating(settle_job, interval=600, first=15)
    app.job_queue.run_repeating(reminder_job, interval=300, first=30)
    return app


def run_check(cfg) -> None:
    if not cfg.bot_token:
        raise SystemExit("BOT_TOKEN is required")
    db = Database.connect(cfg.database_url)
    try:
        db.init()
        build_application(cfg, db)
    finally:
        db.close()
    print("Paheli777 check OK")
    print(f"database={db.dialect}")
    print(f"database_url={'set' if cfg.database_url else 'sqlite fallback paheli777.db'}")
    print(f"admin={'set' if cfg.admin_user_id is not None else 'missing'}")
    print(f"highlightly={'set' if cfg.highlightly_api_key else 'missing'}")
    print(f"brand_url={cfg.brand_url or '(not set)'}")
    print(f"timezone={cfg.timezone_name}")


def main() -> None:
    cfg = load_config()
    if "--check" in sys.argv:
        run_check(cfg)
        return
    if not cfg.bot_token:
        raise SystemExit("BOT_TOKEN environment variable is required")
    db = Database.connect(cfg.database_url)
    db.init()
    app = build_application(cfg, db)
    logger.info("Starting Paheli777 (%s)", db.dialect)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
