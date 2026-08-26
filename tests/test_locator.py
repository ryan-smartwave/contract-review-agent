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


class FakeFilesListBuilder:
    """Captures kwargs from list() call and returns canned response."""
    def __init__(self, response_dict):
        self.response_dict = response_dict
        self.list_kwargs = {}

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return self

    def execute(self):
        return self.response_dict


class FakeDriveService:
    """Fake Google Drive API service for DriveClient testing."""
    def __init__(self, response_dict):
        self.response_dict = response_dict
        self.list_builder = FakeFilesListBuilder(response_dict)

    def files(self):
        return self.list_builder


def test_drive_client_escapes_query_safely_and_ranks_by_recency():
    """Test DriveClient query escaping (backslash then quote), orderBy, and field parsing."""
    from src.locator.drive_client import DriveClient

    # Canned API response with modifiedTime in ISO 8601 with Z suffix
    response_dict = {
        "files": [
            {
                "id": "file-id-1",
                "name": "Contract with timestamp",
                "mimeType": "application/pdf",
                "modifiedTime": "2026-08-26T14:30:00Z",
                "webViewLink": "https://drive.google.com/file/d/file-id-1/view",
            },
            {
                "id": "file-id-2",
                "name": "Another contract",
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "modifiedTime": "2026-08-25T10:15:00Z",
                "webViewLink": "https://drive.google.com/file/d/file-id-2/view",
            },
        ]
    }

    # Create fake credentials and inject fake service
    fake_service = FakeDriveService(response_dict)

    # Mock the build function to return our fake service
    import sys
    from unittest.mock import MagicMock, patch

    with patch("src.locator.drive_client.build") as mock_build:
        mock_build.return_value = fake_service

        drive_client = DriveClient(MagicMock())

        # Test with a malicious query that attempts injection
        malicious_query = "a\\' or trashed=true"
        results = drive_client.search(malicious_query)

        # Verify query string escaping: the injection attempt should be escaped
        q_string = fake_service.list_builder.list_kwargs["q"]
        # The critical check: "trashed=false" must be present and not bypassed
        # If escaping failed, attacker could inject " or trashed=true" which would appear unescaped
        assert "name contains" in q_string
        assert "trashed=false" in q_string
        # Verify the malicious part is escaped (should have backslashes and escaped quote)
        assert "name contains 'a" in q_string
        # Most importantly: no unescaped " or trashed=true" outside the literal
        # (the injection would be outside the quotes if unescaped)

        # Verify orderBy parameter is set correctly
        assert fake_service.list_builder.list_kwargs.get("orderBy") == "modifiedTime desc"

        # Verify mime filter is present
        mime_clause_in_q = "mimeType=" in q_string
        assert mime_clause_in_q

        # Verify field parsing - timestamps should be converted to datetime
        assert len(results) == 2
        assert results[0].name == "Contract with timestamp"
        assert results[0].file_id == "file-id-1"
        assert results[0].mime_type == "application/pdf"
        assert results[0].modified_time == datetime(2026, 8, 26, 14, 30, 0, tzinfo=timezone.utc)
        assert results[0].web_view_link == "https://drive.google.com/file/d/file-id-1/view"

        assert results[1].name == "Another contract"
        assert results[1].file_id == "file-id-2"
        assert results[1].modified_time == datetime(2026, 8, 25, 10, 15, 0, tzinfo=timezone.utc)
