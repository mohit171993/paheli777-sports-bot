"""Application wiring. Polling runs as a Railway worker, not a web service."""

from __future__ import annotations

import logging
import time

from telegram import Update
from telegram.ext import Application

from paheli.config import Settings
from paheli.db import Database
from paheli.handlers import register_handlers
from paheli.highlightly import HighlightlyClient
from paheli.jobs import run_maintenance
from paheli.store import Store

logger = logging.getLogger(__name__)


def build_application(settings: Settings) -> Application:
    database = Database(settings.database_url)
    database.init()
    store = Store(database)
    client = HighlightlyClient(settings.highlightly_api_key, settings.highlightly_base_url)
    application = Application.builder().token(settings.bot_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["store"] = store
    application.bot_data["client"] = client
    register_handlers(application)
    if application.job_queue is None:
        logger.warning("Job queue is unavailable. Install python-telegram-bot[job-queue].")
    else:
        application.job_queue.run_repeating(
            maintenance_job,
            interval=settings.sync_interval_seconds,
            first=15,
            name="paheli-maintenance",
        )
    logger.info("Database ready (%s)", database.dialect)
    return application


async def maintenance_job(context) -> None:
    settings = context.application.bot_data["settings"]
    store = context.application.bot_data["store"]
    client = context.application.bot_data["client"]
    try:
        summary = await run_maintenance(context.bot, store, client, settings)
        context.application.bot_data["last_sync"] = time.time()
        logger.info(
            "Maintenance football=%s cricket=%s settled=%s reminded=%s",
            summary.get("football"),
            summary.get("cricket"),
            summary.get("settled"),
            summary.get("reminded"),
        )
    except Exception:
        logger.exception("Maintenance failed")


def run() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings.from_env()
    application = build_application(settings)
    logger.info("Starting Paheli777")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
