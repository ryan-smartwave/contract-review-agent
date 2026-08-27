from fastapi.testclient import TestClient

from src.main import app


def test_agent_card_served():
    resp = TestClient(app).get("/a2a/.well-known/agent-card.json")
    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "Contract Review Agent"
    assert any(s["id"] == "find_contracts" for s in card["skills"])
