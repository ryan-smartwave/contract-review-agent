from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Provider SDKs (anthropic, google-genai, openai) read their API keys from the
# process environment; exporting .env here lets one file configure both them
# and Settings.
load_dotenv()


class Settings(BaseSettings):
    model_name: str = "anthropic:claude-sonnet-4-5"
    database_url: str = "sqlite:///data/app.db"
    files_dir: Path = Path("data/files")
    google_credentials_path: Path = Path("credentials.json")
    google_token_path: Path = Path("token.json")
    gmail_poll_seconds: int = 30
    enable_gmail_poller: bool = False
    cors_origins: str = "http://localhost:3000"
    # Headless deploys can't run the browser OAuth flow; these hold the file
    # contents of credentials.json / token.json and are written to disk at
    # startup when the files are absent.
    google_credentials_json: str = ""
    google_token_json: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
