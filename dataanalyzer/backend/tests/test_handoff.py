"""The sign-in from the hub."""
from __future__ import annotations

import pytest

SECRET = "a-shared-secret-of-at-least-thirty-two-characters"


def test_the_hub_gets_a_ticket(the_app):
    answer = the_app.post(
        "/api/auth/handoff",
        json={"username": "analyst", "role": "user"},
        headers={"X-Handoff-Secret": SECRET},
    )

    assert answer.status_code == 200

    body = answer.json()

    assert body["ticket"]
    assert body["role"] == "user"
    assert body["username"] == "analyst"


def test_a_wrong_secret_is_refused(the_app):
    answer = the_app.post(
        "/api/auth/handoff",
        json={"username": "analyst", "role": "admin"},
        headers={"X-Handoff-Secret": "not the secret of the hub"},
    )

    assert answer.status_code == 401
    assert "ticket" not in answer.json()


def test_a_browser_cannot_ask_for_a_ticket(the_app):
    """The secret is what keeps the browser out."""
    answer = the_app.post("/api/auth/handoff", json={"username": "analyst", "role": "admin"})

    assert answer.status_code == 401


def test_the_role_is_the_one_of_the_news_feed(the_app):
    """The role of the hub is handed over unchanged."""
    for role in ("admin", "user"):
        answer = the_app.post(
            "/api/auth/handoff",
            json={"username": "analyst", "role": role},
            headers={"X-Handoff-Secret": SECRET},
        )

        assert answer.json()["role"] == role


def test_a_role_that_is_not_known_becomes_a_reader(the_app):
    answer = the_app.post(
        "/api/auth/handoff",
        json={"username": "analyst", "role": "administrator of everything"},
        headers={"X-Handoff-Secret": SECRET},
    )

    assert answer.json()["role"] == "user"


def test_the_ticket_is_spent_once(the_app):
    answer = the_app.post(
        "/api/auth/handoff",
        json={"username": "analyst", "role": "user"},
        headers={"X-Handoff-Secret": SECRET},
    )

    ticket = answer.json()["ticket"]

    assert the_app.post("/api/auth/exchange", json={"ticket": ticket}).status_code == 200

    # The second attempt is refused: a ticket that was copied out of a message
    # cannot be used again.
    assert the_app.post("/api/auth/exchange", json={"ticket": ticket}).status_code == 401


def test_a_ticket_that_was_never_given_is_refused(the_app):
    answer = the_app.post("/api/auth/exchange", json={"ticket": "x" * 40})

    assert answer.status_code == 401


def test_the_session_carries_the_person_and_the_role(the_app, a_signed_in_person):
    assert a_signed_in_person["person"]["username"] == "analyst"
    assert a_signed_in_person["person"]["role"] == "user"


def test_the_manifest_names_the_screens(the_app):
    answer = the_app.get("/api/ui/manifest")

    assert answer.status_code == 200

    body = answer.json()

    assert body["service"] == "data-analyzer"
    assert body["sections"]
    assert body["sections"][0]["id"] == "documents"
