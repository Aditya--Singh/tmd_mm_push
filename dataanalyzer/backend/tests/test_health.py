from fastapi.testclient import TestClient

from app import main
from app.core.languagetool import LanguageToolClient
from app.core.ollama import OllamaClient, OllamaError

client = TestClient(main.app)


def _patch(monkeypatch, models=None, lt=True):
    async def fake_list(self, timeout=None):
        if models is None:
            raise OllamaError("down")
        return models

    async def fake_lt(self, timeout=3.0):
        return lt

    monkeypatch.setattr(OllamaClient, "list_models", fake_list)
    monkeypatch.setattr(LanguageToolClient, "is_available", fake_lt)


def test_health_all_up(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    _patch(monkeypatch, models=["gpt-oss:20b"], lt=True)
    for path in ("/health", "/api/health"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "ollama": {
                "reachable": True,
                "model": "gpt-oss:20b",
                "model_available": True,
            },
            "languagetool": {"reachable": True},
        }


def test_health_model_missing(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "gpt-oss:120b")
    _patch(monkeypatch, models=["gpt-oss:20b"], lt=True)
    body = client.get("/health").json()
    assert body["ollama"] == {
        "reachable": True,
        "model": "gpt-oss:120b",
        "model_available": False,
    }


def test_health_services_down(monkeypatch):
    _patch(monkeypatch, models=None, lt=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["ollama"]["reachable"] is False
    assert body["ollama"]["model_available"] is False
    assert body["languagetool"]["reachable"] is False
