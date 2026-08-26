from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_name: str = "anthropic:claude-sonnet-4-5"
    database_url: str = "sqlite:///data/app.db"
    files_dir: Path = Path("data/files")
    google_credentials_path: Path = Path("credentials.json")
    google_token_path: Path = Path("token.json")
    gmail_poll_seconds: int = 30
    enable_gmail_poller: bool = False

    model_config = {"env_file": ".env"}


settings = Settings()
