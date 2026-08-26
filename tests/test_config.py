from pathlib import Path

from src.config import Settings, settings


def test_settings_defaults(test_db):
    # test_db fixture patches the global settings instance
    # Use a fresh Settings() instance to verify defaults are not affected by fixture
    fresh = Settings()
    assert fresh.files_dir == Path("data/files")
    # Verify other settings on the patched global instance
    assert settings.model_name.count(":") == 1  # "provider:model" form
    assert settings.gmail_poll_seconds == 30
    assert settings.enable_gmail_poller is False


def test_settings_ignores_unknown_env_vars(monkeypatch):
    """Test that unknown env vars don't cause ValidationError."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    # Should construct without error
    test_settings = Settings()
    assert test_settings.model_name == "anthropic:claude-sonnet-4-5"
