"""
Tests for the bridge to the Data Analyzer.

The Data Analyzer keeps its own sessions. The hub does not take that over: it asks the
analyzer for a single-use sign-in ticket on behalf of the person who signed in, and hands
that ticket to the frame.

These tests check that the hub asks for the ticket in the right way, that the secret
never reaches a browser, and that the role the analyzer is given is the role the person
holds in the News Feed.
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
    response = client.post("/api/services/analyzer/ticket")

    assert response.status_code == 401


def test_the_ticket_endpoint_says_what_is_missing(client):
    body = sign_in(client)

    settings = get_settings()

    # Without a shared secret the endpoint explains what to set,
    # instead of failing in an unclear way.
    original = settings.analyzer_handoff_secret
    settings.analyzer_handoff_secret = ""

    try:
        response = client.post(
            "/api/services/analyzer/ticket",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        assert response.status_code == 503
        assert "ANALYZER_HANDOFF_SECRET" in response.json()["detail"]
    finally:
        settings.analyzer_handoff_secret = original


def test_the_ticket_is_asked_for_with_the_secret_and_the_name(client, monkeypatch):
    """
    The hub vouches for the person who signed in, and the shared secret stays on the
    hub's server: it travels in the header of the server-to-server call, and never in
    the answer the browser gets.
    """
    body = sign_in(client)

    sent = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"ticket": "ticket-1", "expires_in": 120, "role": "user"}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(json or {})
        sent["headers"] = headers
        sent["url"] = url

        return FakeResponse()

    monkeypatch.setattr("app.api.integrations.httpx.post", fake_post)

    settings = get_settings()
    original = settings.analyzer_handoff_secret
    settings.analyzer_handoff_secret = "s" * 40

    try:
        response = client.post(
            "/api/services/analyzer/ticket",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        assert response.status_code == 200
        assert response.json()["ticket"] == "ticket-1"
        assert sent["username"] == "analyst"
        assert sent["headers"]["X-Handoff-Secret"] == "s" * 40
        assert sent["url"].endswith("/api/auth/handoff")
    finally:
        settings.analyzer_handoff_secret = original


def test_the_role_is_the_one_of_the_news_feed(client, monkeypatch):
    """
    The Data Analyzer uses the role the person holds in the News Feed, and the names are
    the same, so one person holds one role in each of the applications they may open.
    """
    body = sign_in(client)

    sent = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"ticket": "ticket-1", "expires_in": 120, "role": "user"}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(json or {})

        return FakeResponse()

    monkeypatch.setattr("app.api.integrations.httpx.post", fake_post)

    settings = get_settings()
    original = settings.analyzer_handoff_secret
    settings.analyzer_handoff_secret = "s" * 40

    try:
        client.post(
            "/api/services/analyzer/ticket",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        # The analyst holds the role "user" in the News Feed.
        assert sent["role"] == "user"
    finally:
        settings.analyzer_handoff_secret = original


def test_the_role_is_not_chosen_by_the_browser(client, monkeypatch):
    """
    The role comes from the signed-in person, not from the request. A browser cannot
    make itself an administrator of the analyzer.
    """
    body = sign_in(client)

    sent = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"ticket": "ticket-1", "expires_in": 120, "role": "user"}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(json or {})

        return FakeResponse()

    monkeypatch.setattr("app.api.integrations.httpx.post", fake_post)

    settings = get_settings()
    original = settings.analyzer_handoff_secret
    settings.analyzer_handoff_secret = "s" * 40

    try:
        client.post(
            "/api/services/analyzer/ticket",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        assert sent["role"] == "user"
        assert sent["role"] != "admin"
    finally:
        settings.analyzer_handoff_secret = original


def test_an_analyzer_that_cannot_be_reached_is_said_plainly(client, monkeypatch):
    import httpx

    body = sign_in(client)

    def fake_post(url, json=None, headers=None, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.api.integrations.httpx.post", fake_post)

    settings = get_settings()
    original = settings.analyzer_handoff_secret
    settings.analyzer_handoff_secret = "s" * 40

    try:
        response = client.post(
            "/api/services/analyzer/ticket",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        assert response.status_code == 503
        assert "ANALYZER_APP_URL" in response.json()["detail"]
    finally:
        settings.analyzer_handoff_secret = original


def test_the_manifest_endpoint_needs_no_sign_in(client, monkeypatch):
    # The navigation names the screens and nothing else, so the hub can
    # draw its own rail without holding a session of its own.

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "service": "data-analyzer",
                "title": "Data Analyzer",
                "defaultSection": "documents",
                "sections": [
                    {"id": "documents", "title": "Documents", "icon": "x", "path": "/"},
                ],
            }

    def fake_get(url, timeout=None):
        return FakeResponse()

    monkeypatch.setattr("app.api.integrations.httpx.get", fake_get)

    response = client.get("/api/services/analyzer/manifest")

    assert response.status_code == 200
    assert response.json()["title"] == "Data Analyzer"
    assert response.json()["sections"][0]["id"] == "documents"
