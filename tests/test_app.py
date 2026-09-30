from paheli.app import build_application
from paheli.config import Settings, resolve_database_url


def test_database_url_defaults_and_normalizes_postgres_scheme():
    assert resolve_database_url("") == "sqlite:///paheli777.db"
    assert resolve_database_url("postgres://user:pass@host:5432/db").startswith("postgresql://")
    assert resolve_database_url("postgresql://user:pass@host/db").startswith("postgresql://")


def test_application_boots_with_required_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456789:AAH12345678901234567890123456789012")
    monkeypatch.setenv("ADMIN_USER_ID", "42")
    monkeypatch.setenv("HIGHLIGHTLY_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'paheli.db'}")
    monkeypatch.setenv("BRAND_URL", "example.com/play")
    settings = Settings.from_env()
    assert settings.admin_user_id == 42
    assert settings.brand_url == "https://example.com/play"
    application = build_application(settings)
    names = {job.name for job in application.job_queue.jobs()}
    assert "paheli-maintenance" in names
    commands = {
        handler.commands
        for group in application.handlers.values()
        for handler in group
        if getattr(handler, "commands", None)
    }
    assert {"start"} in commands or any("start" in item for item in commands)
    assert application.bot_data["store"].db.dialect == "sqlite"
