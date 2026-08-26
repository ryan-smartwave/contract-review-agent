import subprocess

from src.llm import factory


def test_get_chat_model_uses_configured_name(monkeypatch):
    captured = {}

    def fake_init(model, **kwargs):
        captured["model"] = model
        return object()

    monkeypatch.setattr(factory, "init_chat_model", fake_init)
    factory.get_chat_model()
    assert captured["model"] == factory.settings.model_name


def test_no_vendor_sdk_imports():
    # AI abstraction constraint: no direct anthropic/openai imports in src/
    grep = subprocess.run(
        ["git", "grep", "-lE", r"^(import|from) (anthropic|openai)", "--", "src/"],
        capture_output=True, text=True,
    )
    assert grep.stdout == ""
