"""
Tests for the bridge to the Data Summarizer.

The Data Summarizer keeps its own accounts, its own sessions and its own audit
trail. The hub does not take that over: it asks the summarizer for a single-use
sign-in ticket on behalf of the person who signed in, and hands that ticket to
the frame.

These tests check that the hub asks for the ticket in the right way, that the
secret never reaches a browser, and that the role in the summarizer is the
summarizer's own decision rather than the browser's.
"""

import pytest

from app.config.settings import get_settings


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def sign_in(client, username="analyst", password="Pnb@12345"):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )

    assert response.status_code == 200, response.text

    return response.json()


def test_the_ticket_endpoint_needs_a_signed_in_person(client):
    response = client.post("/api/services/summarizer/ticket")

    assert response.status_code == 401


def test_the_ticket_endpoint_says_what_is_missing(client):
    body = sign_in(client)

    settings = get_settings()

    # Without a shared secret the endpoint explains what to set,
    # instead of failing in an unclear way.
    original = settings.sentinel_handoff_secret
    settings.sentinel_handoff_secret = ""

    try:
        response = client.post(
            "/api/services/summarizer/ticket",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        assert response.status_code == 503
        assert "SENTINEL_HANDOFF_SECRET" in response.json()["detail"]
    finally:
        settings.sentinel_handoff_secret = original


def test_the_ticket_is_asked_for_with_the_secret_and_the_name(client, monkeypatch):
    """
    The hub vouches for the person who signed in, and the shared secret stays on
    the hub's server: it travels in the header of the server-to-server call, and
    never in the answer the browser gets.
    """
    body = sign_in(client)

    sent = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"ticket": "ticket-1", "expires_in": 120, "role": "analyst"}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(json or {})
        sent["headers"] = headers
        sent["url"] = url

        return FakeResponse()

    monkeypatch.setattr("app.api.integrations.httpx.post", fake_post)

    settings = get_settings()
    original = settings.sentinel_handoff_secret
    settings.sentinel_handoff_secret = "s" * 40

    try:
        response = client.post(
            "/api/services/summarizer/ticket",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        assert response.status_code == 200
        assert response.json()["ticket"] == "ticket-1"
        assert sent["username"] == "analyst"
        assert sent["headers"]["X-Handoff-Secret"] == "s" * 40
        assert sent["url"].endswith("/api/auth/handoff")
    finally:
        settings.sentinel_handoff_secret = original


def test_the_role_in_the_summarizer_is_not_chosen_by_the_browser(client, monkeypatch):
    """
    The hub states who the person is, not what they may do there.

    The role is the summarizer's own decision, so a request that tries to state
    a role is not given one.
    """
    body = sign_in(client)

    sent = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"ticket": "ticket-1", "expires_in": 120, "role": "admin"}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(json or {})

        return FakeResponse()

    monkeypatch.setattr("app.api.integrations.httpx.post", fake_post)

    settings = get_settings()
    original = settings.sentinel_handoff_secret
    settings.sentinel_handoff_secret = "s" * 40

    try:
        response = client.post(
            "/api/services/summarizer/ticket",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        assert response.status_code == 200
        assert "role" not in sent
        # The role the summarizer answered with is the one that is reported.
        assert response.json()["role"] == "admin"
    finally:
        settings.sentinel_handoff_secret = original


def test_a_summarizer_that_cannot_be_reached_is_said_plainly(client, monkeypatch):
    import httpx

    body = sign_in(client)

    def fake_post(url, json=None, headers=None, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.api.integrations.httpx.post", fake_post)

    settings = get_settings()
    original = settings.sentinel_handoff_secret
    settings.sentinel_handoff_secret = "s" * 40

    try:
        response = client.post(
            "/api/services/summarizer/ticket",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        assert response.status_code == 503
        assert "SENTINEL_APP_URL" in response.json()["detail"]
    finally:
        settings.sentinel_handoff_secret = original


def test_the_manifest_endpoint_needs_no_sign_in(client, monkeypatch):
    # The navigation names the screens and nothing else, so the hub can
    # draw its own rail without holding a session of its own.

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "service": "data-summarizer",
                "title": "Data Summarizer",
                "defaultSection": "overview",
                "sections": [
                    {"id": "overview", "title": "Overview", "icon": "x", "path": "/"},
                ],
            }

    def fake_get(url, timeout=None):
        return FakeResponse()

    monkeypatch.setattr("app.api.integrations.httpx.get", fake_get)

    response = client.get("/api/services/summarizer/manifest")

    assert response.status_code == 200
    assert response.json()["title"] == "Data Summarizer"
    assert response.json()["sections"][0]["id"] == "overview"
