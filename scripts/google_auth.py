"""One-time OAuth flow; later runs reuse token.json silently."""
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.readonly",
]


def get_credentials() -> Credentials:
    creds = None
    if settings.google_token_path.exists():
        creds = Credentials.from_authorized_user_file(
            str(settings.google_token_path), SCOPES
        )
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(settings.google_credentials_path), SCOPES
        )
        creds = flow.run_local_server(port=0)
    settings.google_token_path.write_text(creds.to_json())
    return creds


if __name__ == "__main__":
    from googleapiclient.discovery import build

    creds = get_credentials()
    profile = build("gmail", "v1", credentials=creds).users().getProfile(userId="me").execute()
    print(f"Authorized as: {profile['emailAddress']}")
