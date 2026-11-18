"""The test environment: a database of its own, and a secret of its own."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


@pytest.fixture(autouse=True)
def the_environment(tmp_path, monkeypatch):
    """Every test has a database, a folder and a secret of its own."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'analyzer.db'}")
    monkeypatch.setenv("JWT_SECRET", "a-secret-for-the-tests-of-this-application")
    monkeypatch.setenv("HANDOFF_SECRET", "a-shared-secret-of-at-least-thirty-two-characters")
    monkeypatch.setenv("LLM_MODEL", "auto")
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:1")

    from app.config import reset_settings

    reset_settings()

    from app.core import db as core_db
    from app.llm import client as llm_client

    core_db.reset_the_engine()
    llm_client.reset_llm()

    yield

    core_db.reset_the_engine()
    reset_settings()


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
        headers={"X-Handoff-Secret": "a-shared-secret-of-at-least-thirty-two-characters"},
    )

    ticket = answer.json()["ticket"]

    exchanged = the_app.post("/api/auth/exchange", json={"ticket": ticket})

    return {
        "headers": {"Authorization": f"Bearer {exchanged.json()['access_token']}"},
        "person": exchanged.json()["user"],
    }
