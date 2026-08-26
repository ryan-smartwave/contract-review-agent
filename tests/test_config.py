from pathlib import Path

from src.config import settings


def test_settings_defaults():
    assert settings.model_name.count(":") == 1  # "provider:model" form
    assert settings.files_dir == Path("data/files")
    assert settings.gmail_poll_seconds == 30
    assert settings.enable_gmail_poller is False
