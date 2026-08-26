from fastapi import APIRouter

from src.locator.schemas import DriveFile
from src.locator.service import search_contracts


def get_drive_client():
    from scripts.google_auth import get_credentials
    from src.locator.drive_client import DriveClient

    return DriveClient(get_credentials())


router = APIRouter()


@router.get("/drive/search")
def drive_search(q: str) -> dict[str, list[DriveFile]]:
    return {"results": search_contracts(q, drive=get_drive_client())}
