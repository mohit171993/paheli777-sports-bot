"""The bot process can be constructed from the required environment."""

import unittest
from zoneinfo import ZoneInfo

from bot import build_application
from paheli.config import Config
from paheli.db import Database


class AppTests(unittest.TestCase):
    def test_application_wires_jobs_and_handlers(self):
        cfg = Config(
            bot_token="123456:TESTTOKEN",
            admin_user_id=42,
            highlightly_api_key="test-key",
            database_url="",
            brand_url="https://example.com",
            timezone_name="Asia/Kolkata",
            timezone=ZoneInfo("Asia/Kolkata"),
            reminder_lead_minutes=45,
        )
        db = Database.connect("sqlite:///:memory:")
        self.addCleanup(db.close)
        db.init()
        app = build_application(cfg, db)
        self.assertIsNotNone(app.job_queue)
        self.assertIs(app.bot_data["runtime"].db, db)
        self.assertGreaterEqual(len(app.handlers[0]), 8)


if __name__ == "__main__":
    unittest.main()
