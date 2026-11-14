"""Tests for the bridge to the Executive Intelligence Hub, and for the model choice.

The hub owns the sign-in and vouches for the person. The summarizer keeps its own
accounts, its own sessions and its own audit trail, and is given a single-use ticket
that the frame swaps for a session of its own.

The language model is chosen from the models that are installed on the machine, so that
the best one that is there is the one that is used.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.llm.models import (
    is_embedding_model,
    model_family,
    model_size_b,
    pick_best_model,
    score_model,
)


SECRET = "s" * 48


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def handoff_secret(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    original = settings.handoff_secret
    settings.handoff_secret = SECRET

    yield settings

    settings.handoff_secret = original


# ------------------------------------------------------------------ the handoff
def test_the_handoff_needs_the_shared_secret(client, handoff_secret):
    response = client.post("/api/auth/handoff", json={"username": "analyst"})

    assert response.status_code == 401


def test_the_handoff_gives_a_ticket(client, handoff_secret):
    response = client.post(
        "/api/auth/handoff",
        json={"username": "analyst", "full_name": "analyst"},
        headers={"X-Handoff-Secret": SECRET},
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert body["ticket"]
    assert body["role"] == "analyst"


def test_the_hub_administrator_is_an_administrator_here(client, handoff_secret):
    response = client.post(
        "/api/auth/handoff",
        json={"username": "admin"},
        headers={"X-Handoff-Secret": SECRET},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_a_ticket_is_spent_only_once(client, handoff_secret):
    response = client.post(
        "/api/auth/handoff",
        json={"username": "gm"},
        headers={"X-Handoff-Secret": SECRET},
    )

    ticket = response.json()["ticket"]

    first = client.post("/api/auth/exchange", json={"ticket": ticket})
    second = client.post("/api/auth/exchange", json={"ticket": ticket})

    assert first.status_code == 200, first.text
    assert second.status_code == 401


def test_a_ticket_gives_a_session_of_this_app(client, handoff_secret):
    response = client.post(
        "/api/auth/handoff",
        json={"username": "approver"},
        headers={"X-Handoff-Secret": SECRET},
    )

    ticket = response.json()["ticket"]

    exchanged = client.post("/api/auth/exchange", json={"ticket": ticket})

    assert exchanged.status_code == 200

    body = exchanged.json()

    assert body["access_token"]
    assert body["user"]["role"] == "analyst"

    # The session works for this app's own endpoints.
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})

    assert me.status_code == 200
    assert me.json()["role"] == "analyst"


def test_a_ticket_that_was_never_given_is_refused(client):
    response = client.post("/api/auth/exchange", json={"ticket": "not-a-real-ticket-at-all"})

    assert response.status_code == 401


def test_the_navigation_needs_no_sign_in(client):
    response = client.get("/api/ui/manifest")

    assert response.status_code == 200

    body = response.json()

    assert body["service"] == "data-summarizer"
    assert body["sections"]


def test_the_addresses_the_hub_may_use_are_published(client):
    """The browser needs to know which origin may drive it."""
    response = client.get("/api/meta")

    assert response.status_code == 200
    assert "embed_parent_origins" in response.json()


# --------------------------------------------------------------- the model choice
def test_the_family_of_a_model():
    assert model_family("qwen3:8b") == "qwen3"
    assert model_family("LLAMA3:latest") == "llama3"


def test_the_size_of_a_model():
    assert model_size_b("qwen3:8b") == 8.0
    assert model_size_b("llama3.1:70b") == 70.0
    assert model_size_b("something") == 0.0


def test_a_model_for_embeddings_is_not_used_for_writing():
    assert is_embedding_model("nomic-embed-text")
    assert is_embedding_model("bge-m3")
    assert not is_embedding_model("qwen3:8b")


def test_the_newest_family_wins():
    assert score_model("qwen3:8b") > score_model("qwen2.5:7b")
    assert score_model("qwen2.5:7b") > score_model("llama3.3:70b")


def test_the_larger_model_wins_within_a_family():
    assert score_model("qwen3:32b") > score_model("qwen3:8b")


def test_a_named_tag_is_better_than_the_rolling_latest():
    assert score_model("qwen3:8b") > score_model("qwen3:latest")


def test_the_best_installed_model_is_picked():
    names = ["nomic-embed-text", "llama3.3:70b", "qwen3:8b", "qwen3:32b"]

    assert pick_best_model(names) == "qwen3:32b"


def test_a_machine_with_only_embedding_models_has_no_model_to_write_with():
    assert pick_best_model(["nomic-embed-text", "bge-m3"]) is None


def test_a_machine_with_no_models_at_all():
    assert pick_best_model([]) is None
    assert pick_best_model(None) is None


def test_the_model_that_is_named_wins_when_it_is_installed(monkeypatch):
    from app.config import get_settings
    from app.llm.models import resolve

    settings = get_settings()
    original = settings.llm_model
    settings.llm_model = "qwen3:8b"

    try:
        model, reason = resolve(["qwen3:8b", "llama3.3:70b"])

        assert model == "qwen3:8b"
        assert "installed" in reason
    finally:
        settings.llm_model = original


def test_the_best_installed_model_is_used_when_the_named_one_is_missing(monkeypatch):
    from app.config import get_settings
    from app.llm.models import resolve

    settings = get_settings()
    original = settings.llm_model
    settings.llm_model = "a-model-that-is-not-here"

    try:
        model, reason = resolve(["qwen3:8b", "llama3.3:70b"])

        assert model == "qwen3:8b"
        assert "not installed" in reason
    finally:
        settings.llm_model = original


def test_a_model_that_is_named_but_missing_can_be_refused(monkeypatch):
    from app.config import get_settings
    from app.llm.models import resolve

    settings = get_settings()
    original_model = settings.llm_model
    original_strict = settings.llm_strict_model
    settings.llm_model = "a-model-that-is-not-here"
    settings.llm_strict_model = True

    try:
        with pytest.raises(RuntimeError):
            resolve(["qwen3:8b"])
    finally:
        settings.llm_model = original_model
        settings.llm_strict_model = original_strict


def test_auto_means_the_best_model_that_is_installed(monkeypatch):
    from app.config import get_settings
    from app.llm.models import resolve

    settings = get_settings()
    original = settings.llm_model
    settings.llm_model = "auto"

    try:
        model, reason = resolve(["llama3.3:70b", "qwen3:32b"])

        assert model == "qwen3:32b"
        assert "best model" in reason
    finally:
        settings.llm_model = original
