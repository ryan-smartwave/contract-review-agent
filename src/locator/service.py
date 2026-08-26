from src.locator.schemas import DriveFile


def search_contracts(query: str, drive) -> list[DriveFile]:
    return drive.search(query)
