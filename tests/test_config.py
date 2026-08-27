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


def test_cors_origins_parse_to_list(monkeypatch):
    s = fresh_settings(monkeypatch, cors_origins="http://localhost:3000, https://demo.vercel.app")
    assert s.cors_origin_list == ["http://localhost:3000", "https://demo.vercel.app"]


def test_google_files_materialize_from_env(tmp_path, monkeypatch):
    from src.config import settings
    from scripts.google_auth import materialize_google_files

    cred_path = tmp_path / "credentials.json"
    token_path = tmp_path / "token.json"
    monkeypatch.setattr(settings, "google_credentials_path", cred_path)
    monkeypatch.setattr(settings, "google_token_path", token_path)
    monkeypatch.setattr(settings, "google_credentials_json", '{"installed": {}}')
    monkeypatch.setattr(settings, "google_token_json", "")

    materialize_google_files()
    assert cred_path.read_text() == '{"installed": {}}'
    assert not token_path.exists()  # empty env content writes nothing

    # existing files are never overwritten
    monkeypatch.setattr(settings, "google_credentials_json", '{"other": 1}')
    materialize_google_files()
    assert cred_path.read_text() == '{"installed": {}}'
