"""The test environment: a folder of its own, and secrets of its own."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

SHARED_SECRET = "a-shared-secret-of-at-least-thirty-two-characters"


@pytest.fixture(autouse=True)
def the_environment(tmp_path, monkeypatch):
    """Every test has a folder, a key and a shared secret of its own."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JWT_SECRET", "a-secret-for-the-tests-of-this-application")
    monkeypatch.setenv("HANDOFF_SECRET", SHARED_SECRET)
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("LANGUAGETOOL_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("OLLAMA_MODEL", "a-model-for-the-tests")

    from app.core.config import get_settings

    get_settings.cache_clear()

    yield

    get_settings.cache_clear()


@pytest.fixture
def the_app():
    """The application, ready to be asked."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def a_signed_in_person(the_app):
    """A person who is signed in, the way the hub signs them in."""
    answer = the_app.post(
        "/api/auth/handoff",
        json={"username": "analyst", "role": "user"},
        headers={"X-Handoff-Secret": SHARED_SECRET},
    )

    ticket = answer.json()["ticket"]

    exchanged = the_app.post("/api/auth/exchange", json={"ticket": ticket})

    return {
        "headers": {"Authorization": f"Bearer {exchanged.json()['access_token']}"},
        "person": exchanged.json()["user"],
    }


@pytest.fixture
def an_administrator(the_app):
    """A person who is signed in as an administrator of the platform."""
    answer = the_app.post(
        "/api/auth/handoff",
        json={"username": "admin", "role": "admin"},
        headers={"X-Handoff-Secret": SHARED_SECRET},
    )

    ticket = answer.json()["ticket"]

    exchanged = the_app.post("/api/auth/exchange", json={"ticket": ticket})

    return {
        "headers": {"Authorization": f"Bearer {exchanged.json()['access_token']}"},
        "person": exchanged.json()["user"],
    }
