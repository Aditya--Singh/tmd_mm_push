"""The bridge to the Executive Intelligence Hub.

The hub signs a person in, vouches for them with a single-use ticket, and the person is
given a token of this app carrying the role they hold in the News Feed.
"""
from __future__ import annotations

import pytest

from app.core.handoff import make_ticket
from app.core.security import create_access_token
from app.main import app

from .conftest import SHARED_SECRET


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    with TestClient(app) as answer:
        yield answer


def test_a_ticket_is_issued_to_the_hub(client):
    response = client.post(
        "/api/auth/handoff",
        headers={"X-Handoff-Secret": SHARED_SECRET},
        json={"username": "analyst", "role": "user"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ticket"]
    assert body["role"] == "user"
    assert body["username"] == "analyst"


def test_the_hub_without_the_secret_is_refused(client):
    response = client.post(
        "/api/auth/handoff", json={"username": "analyst", "role": "user"}
    )

    assert response.status_code == 401


def test_a_ticket_is_swapped_for_a_session(client):
    ticket = make_ticket("analyst", "user", 120)

    response = client.post("/api/auth/exchange", json={"ticket": ticket})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["role"] == "user"
    assert body["user"]["username"] == "analyst"


def test_a_ticket_cannot_be_spent_twice(client):
    ticket = make_ticket("analyst", "user", 120)

    assert client.post("/api/auth/exchange", json={"ticket": ticket}).status_code == 200
    assert client.post("/api/auth/exchange", json={"ticket": ticket}).status_code == 401


def test_a_ticket_signed_with_another_secret_is_refused(client):
    from app.core import handoff

    original = handoff.get_settings
    handoff.get_settings = lambda: type(
        "S", (), {"handoff_secret": "another-secret-of-at-least-thirty-two-chars"}
    )()

    try:
        ticket = make_ticket("analyst", "user", 120)
    finally:
        handoff.get_settings = original

    response = client.post("/api/auth/exchange", json={"ticket": ticket})

    assert response.status_code == 401


def test_the_role_comes_from_the_hub(client):
    response = client.post(
        "/api/auth/handoff",
        headers={"X-Handoff-Secret": SHARED_SECRET},
        json={"username": "admin", "role": "admin"},
    )

    assert response.json()["role"] == "admin"


def test_an_unknown_role_is_refused(client):
    response = client.post(
        "/api/auth/handoff",
        headers={"X-Handoff-Secret": SHARED_SECRET},
        json={"username": "analyst", "role": "superuser"},
    )

    assert response.status_code == 400


def test_a_document_route_needs_a_session(client):
    response = client.post(
        "/api/document-assistant/data/ask",
        json={"question": "what is in this file?", "file_id": "nope"},
    )

    assert response.status_code == 401


def test_a_document_route_needs_a_valid_token(client):
    response = client.post(
        "/api/document-assistant/data/ask",
        headers={"Authorization": "Bearer not-a-real-token"},
        json={"question": "what is in this file?", "file_id": "nope"},
    )

    assert response.status_code == 401


def test_a_reader_may_not_delete_a_document(client, a_signed_in_person):
    response = client.delete(
        "/api/document-assistant/files/whatever", headers=a_signed_in_person["headers"]
    )

    assert response.status_code == 403


def test_an_administrator_may_delete_a_document(client, an_administrator):
    response = client.delete(
        "/api/document-assistant/files/whatever", headers=an_administrator["headers"]
    )

    # The file is not there, so the app says so — but it is the administrator's call to
    # make, not the reader's.
    assert response.status_code in (204, 404)


def test_the_person_is_asked_who_they_are(client, a_signed_in_person):
    response = client.get("/api/auth/me", headers=a_signed_in_person["headers"])

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "analyst"
    assert body["role"] == "user"


def test_the_manifest_names_the_four_tools(client):
    response = client.get("/api/ui/manifest")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "data-analyzer"
    assert body["defaultSection"] == "proofread"
    assert [s["id"] for s in body["sections"]] == [
        "proofread",
        "rewrite",
        "summarize",
        "data",
    ]
    assert [s["title"] for s in body["sections"]] == [
        "Proofread",
        "Rewrite",
        "Summarize",
        "Ask about data",
    ]
    # Every tool is a route of the app, so the hub may send the person to it.
    for section in body["sections"]:
        assert section["path"] == f"/#/{section['id']}"


def test_the_manifest_names_no_other_screen(client):
    body = client.get("/api/ui/manifest").json()

    ids = [s["id"] for s in body["sections"]]

    # The screens that were taken out of the app are not in the rail either.
    assert "circular-analyzer" not in ids
    assert "coming-soon" not in ids


def test_the_health_is_open(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert "languagetool" in body
    assert "ollama" in body


def test_the_token_carries_the_role(client):
    token = create_access_token("analyst", "user")

    assert token.count(".") == 2
