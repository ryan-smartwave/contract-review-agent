from pathlib import Path

from src.config import Settings, settings


def fresh_settings(**kwargs) -> Settings:
    # _env_file=None keeps tests independent of any real .env in the repo root
    return Settings(_env_file=None, **kwargs)


def test_settings_defaults(test_db):
    # test_db fixture patches the global settings instance
    fresh = fresh_settings()
    assert fresh.files_dir == Path("data/files")
    assert fresh.model_name.count(":") == 1  # "provider:model" form
    assert fresh.gmail_poll_seconds == 30
    assert fresh.enable_gmail_poller is False
    # The global instance stays usable regardless of local .env contents
    assert settings.model_name.count(":") == 1


def test_settings_ignores_unknown_env_vars(monkeypatch):
    """Unknown env vars (provider API keys) must not cause ValidationError."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    # config.py exports .env into the process env at import; clear MODEL_NAME
    # so this asserts the built-in default, not the developer's local choice
    monkeypatch.delenv("MODEL_NAME", raising=False)
    test_settings = fresh_settings()
    assert test_settings.model_name == "anthropic:claude-sonnet-4-5"
