from pathlib import Path

from src.config import Settings, settings


def fresh_settings(monkeypatch, **kwargs) -> Settings:
    # config.py exports .env into the process env at import; strip every
    # Settings-modeled env var (and skip .env) so defaults are asserted
    # regardless of the developer's local configuration
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    return Settings(_env_file=None, **kwargs)


def test_settings_defaults(test_db, monkeypatch):
    # test_db fixture patches the global settings instance
    fresh = fresh_settings(monkeypatch)
    assert fresh.files_dir == Path("data/files")
    assert fresh.model_name.count(":") == 1  # "provider:model" form
    assert fresh.gmail_poll_seconds == 30
    assert fresh.enable_gmail_poller is False
    # The global instance stays usable regardless of local .env contents
    assert settings.model_name.count(":") == 1


def test_settings_ignores_unknown_env_vars(monkeypatch):
    """Unknown env vars (provider API keys) must not cause ValidationError."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    test_settings = fresh_settings(monkeypatch)
    assert test_settings.model_name == "anthropic:claude-sonnet-4-5"
