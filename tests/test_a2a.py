from datetime import datetime

from fastapi.testclient import TestClient

import src.locator.router as locator_router
import src.locator.service as locator_service
from src.locator.schemas import DriveFile
from src.main import app


def test_agent_card_served():
    resp = TestClient(app).get("/a2a/.well-known/agent-card.json")
    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "Contract Review Agent"
    assert any(s["id"] == "find_contracts" for s in card["skills"])


def _stub_drive_search(monkeypatch):
    """Point the executor's Drive calls at a fake result, no credentials needed.

    ContractReviewExecutor imports `get_drive_client`/`search_contracts` from
    their origin modules inside `execute()` (a late import), so patching those
    origin modules -- not `src.a2a_server.agent` -- is what actually takes
    effect.
    """
    fake_file = DriveFile(
        file_id="1",
        name="MSA v3.docx",
        modified_time=datetime(2026, 1, 1),
        mime_type="application/vnd.google-apps.document",
    )
    monkeypatch.setattr(locator_router, "get_drive_client", lambda: object())
    monkeypatch.setattr(locator_service, "search_contracts", lambda query, drive: [fake_file])


def test_message_endpoint_with_version_header_routes_to_drive_search(monkeypatch):
    """A caller that declares the v1.0 protocol (header + `SendMessage`) gets served."""
    _stub_drive_search(monkeypatch)

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": "m1",
                "role": "ROLE_USER",
                "parts": [{"text": "MSA"}],
            }
        },
    }
    resp = TestClient(app).post(
        "/a2a/", json=payload, headers={"A2A-Version": "1.0"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body
    text = body["result"]["message"]["parts"][0]["text"]
    assert "MSA v3.docx" in text


def test_message_endpoint_without_version_header_routes_to_drive_search(monkeypatch):
    """A header-less caller (pre-1.0 client, `message/send`) must not get -32009.

    `create_jsonrpc_routes(..., enable_v0_3_compat=True)` is what makes this
    work: header-less requests default to protocol "0.3", and the v0.3
    compat path (routed by the `message/send` method name) expects exactly
    that, so it's served instead of being rejected by the v1.0-only handler.
    """
    _stub_drive_search(monkeypatch)

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "m1",
                "role": "user",
                "parts": [{"kind": "text", "text": "MSA"}],
            }
        },
    }
    resp = TestClient(app).post("/a2a/", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body
    assert body.get("error", {}).get("code") != -32009
    text = body["result"]["parts"][0]["text"]
    assert "MSA v3.docx" in text
