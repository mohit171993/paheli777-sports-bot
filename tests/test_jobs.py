import asyncio
from datetime import datetime, timedelta, timezone

from paheli.config import Settings
from paheli.db import Database
from paheli.jobs import send_reminders, sync_and_settle
from paheli.store import Store

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
TODAY = "2026-09-30"


def settings(tmp_path) -> Settings:
    return Settings(
        bot_token="123456789:AAH12345678901234567890123456789012",
        admin_user_id=1,
        highlightly_api_key="test-key",
        database_url=f"sqlite:///{tmp_path / 'paheli.db'}",
        brand_url="https://example.com",
        reminder_lead_minutes=45,
    )


class FakeClient:
    def __init__(self, detail):
        self.detail = detail

    async def matches(self, sport, date_text, limit=100):
        if sport != "football" or date_text != TODAY:
            return []
        kickoff = (NOW + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return [
            {
                "id": 10,
                "homeTeam": {"name": "Arsenal"},
                "awayTeam": {"name": "Chelsea"},
                "league": {"name": "Premier League"},
                "startDate": kickoff,
                "state": {"description": "Not started"},
            },
            {
                "id": 11,
                "homeTeam": {"name": "Town"},
                "awayTeam": {"name": "City"},
                "league": {"name": "Sunday League"},
                "startDate": kickoff,
                "state": {"description": "Not started"},
            },
        ]

    async def match(self, sport, match_id):
        return self.detail.get(str(match_id), {})


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


def test_sync_keeps_notable_matches_and_reminder_goes_to_subscribers_without_a_pick(tmp_path):
    database = Database(settings(tmp_path).database_url)
    database.init()
    store = Store(database)
    store.touch_user(7, "mohit", "Mohit", NOW)
    store.set_subscribed(7, True, NOW)
    store.touch_user(8, "picked", "Picked", NOW)
    store.set_subscribed(8, True, NOW)

    summary = asyncio.run(sync_and_settle(store, FakeClient({}), settings(tmp_path), NOW))
    assert summary["football"] == 1
    card = store.list_notable(TODAY)
    assert [row["match_key"] for row in card] == ["football:10"]

    store.place_pick(8, "football:10", "home", NOW, exact="2-0")
    bot = FakeBot()
    sent = asyncio.run(send_reminders(bot, store, settings(tmp_path), NOW))
    assert sent == 1
    assert bot.sent[0]["chat_id"] == 7
    assert "Arsenal" in bot.sent[0]["text"]
    assert asyncio.run(send_reminders(bot, store, settings(tmp_path), NOW)) == 0

    finished = {
        "id": 10,
        "homeTeam": {"name": "Arsenal"},
        "awayTeam": {"name": "Chelsea"},
        "league": {"name": "Premier League"},
        "startDate": card[0]["kickoff"],
        "state": {"description": "Finished", "score": {"current": "2 - 0"}},
    }
    settled = asyncio.run(
        sync_and_settle(store, FakeClient({"10": finished}), settings(tmp_path), NOW + timedelta(hours=3))
    )
    assert settled["settled"] == 1
    assert store.prediction(8, "football:10")["points"] == 5
