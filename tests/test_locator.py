from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.locator import router as locator_router
from src.locator import service
from src.locator.schemas import DriveFile
from src.main import app


class FakeDrive:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def search(self, q: str):
        self.queries.append(q)
        return self.rows


def _file(name):
    return DriveFile(
        file_id="f1", name=name, mime_type="application/pdf",
        modified_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
        web_view_link="https://drive.google.com/x",
    )


def test_search_contracts_passes_query_and_returns_rows():
    fake = FakeDrive([_file("Acme MSA v3.pdf")])
    results = service.search_contracts("acme", drive=fake)
    assert [r.name for r in results] == ["Acme MSA v3.pdf"]
    assert "acme" in fake.queries[0]


def test_search_endpoint_empty_result_is_200(monkeypatch):
    monkeypatch.setattr(locator_router, "get_drive_client", lambda: FakeDrive([]))
    client = TestClient(app)
    resp = client.get("/drive/search", params={"q": "nonexistent"})
    assert resp.status_code == 200
    assert resp.json() == {"results": []}
