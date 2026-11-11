"""
Tests for the hand-off from the Executive Intelligence Hub.

The hub vouches for a person it has already signed in and asks this app
for a single-use ticket. These tests cover the role that travels with
the ticket, because that is what makes one sign-in mean the same thing
in every service.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """The application on a throw-away database."""
    with tempfile.TemporaryDirectory() as folder:
        os.environ["DATA_DIR"] = folder
        os.environ["DB_URL"] = f"sqlite:///{folder}/test.db"
        os.environ["SECRET_KEY"] = "test-secret-key-not-used-outside-tests"
        os.environ["HANDOFF_SECRET"] = "s" * 48
        os.environ["HANDOFF_ALLOW_STAFF"] = "true"
        os.environ["HANDOFF_SYNC_ROLE"] = "true"
        os.environ["HANDOFF_AUTO_CREATE"] = "true"

        # The settings are read when the modules are imported, so they
        # have to be in place first.
        from kpibench.main import app
        from kpibench.db import init_db

        init_db()

        with TestClient(app) as test_client:
            yield test_client

    for name in ("DATA_DIR", "DB_URL", "SECRET_KEY", "HANDOFF_SECRET",
                 "HANDOFF_ALLOW_STAFF", "HANDOFF_SYNC_ROLE", "HANDOFF_AUTO_CREATE"):
        os.environ.pop(name, None)


def handoff(client, **body):
    return client.post(
        "/api/auth/handoff",
        json={
            "username": body.pop("username", "analyst"),
            "tab": "overview",
            "embed": True,
            **body,
        },
        headers={"X-Handoff-Secret": "s" * 48},
    )


def test_a_wrong_secret_is_refused(client):
    response = client.post(
        "/api/auth/handoff",
        json={"username": "analyst"},
        headers={"X-Handoff-Secret": "wrong"},
    )

    assert response.status_code == 401


def test_a_ticket_is_issued_for_a_known_user(client):
    response = handoff(client, role="maker")

    assert response.status_code == 200

    body = response.json()

    assert body["ticket"]
    assert body["role"] == "maker"
    assert body["user_created"] is False


def test_the_ticket_carries_the_role_of_the_person(client):
    ticket = handoff(client, role="checker").json()["ticket"]

    response = client.post("/api/auth/exchange", json={"ticket": ticket})

    assert response.status_code == 200

    user = response.json()["user"]

    assert user["username"] == "analyst"
    assert user["role"] == "checker"
    assert "approve" in user["permissions"]


def test_a_ticket_can_only_be_used_once(client):
    ticket = handoff(client, role="maker").json()["ticket"]

    assert client.post("/api/auth/exchange", json={"ticket": ticket}).status_code == 200

    second = client.post("/api/auth/exchange", json={"ticket": ticket})

    assert second.status_code == 401


def test_an_unknown_user_is_created_with_the_role_the_hub_states(client):
    ticket = handoff(client, role="checker").json()["ticket"]

    assert client.post("/api/auth/exchange", json={"ticket": ticket}).status_code == 200

    from kpibench.db import User, session_scope
    from sqlalchemy import select

    with session_scope() as s:
        user = s.execute(
            select(User).where(User.username == "analyst")
        ).scalar_one()

        assert user.role == "checker"


def test_the_manifest_names_the_screens_and_needs_no_sign_in(client):
    response = client.get("/api/ui/manifest")

    assert response.status_code == 200

    body = response.json()

    assert body["defaultSection"] == "overview"

    titles = [section["title"] for section in body["sections"]]

    assert "Overview" in titles
    assert "Peer comparison" in titles
    assert "Governance" in titles


def test_a_staff_role_is_refused_when_staff_may_not_use_the_handoff(client):
    os.environ["HANDOFF_ALLOW_STAFF"] = "false"

    from kpibench import config

    # The setting is read when the settings object is built.
    config.settings.HANDOFF_ALLOW_STAFF = False

    try:
        response = handoff(client, role="maker")

        assert response.status_code == 403
    finally:
        config.settings.HANDOFF_ALLOW_STAFF = True


def test_a_reader_is_handed_over_even_when_staff_may_not_use_the_handoff(client):
    """
    The `role_bench` column of the account sheet holds `user` for the people
    who are in the platform for the news only. That role carries no work
    here, so it is handed over without any further setting.
    """
    from kpibench import config

    config.settings.HANDOFF_ALLOW_STAFF = False

    try:
        # An account that is not a member of staff here, so the hand-off is
        # not refused for the account it finds.
        response = handoff(client, username="aditya", role="user")

        assert response.status_code == 200

        assert response.json()["role"] == "user"
    finally:
        config.settings.HANDOFF_ALLOW_STAFF = True


def test_a_reader_may_read_but_may_not_work(client):
    ticket = handoff(client, username="aditya", role="user").json()["ticket"]

    response = client.post("/api/auth/exchange", json={"ticket": ticket})

    assert response.status_code == 200

    user = response.json()["user"]

    assert user["role"] == "user"
    assert user["role_label"] == "Reader"

    # Reading is allowed, working is not.
    assert "view" in user["permissions"]
    assert "run" not in user["permissions"]
    assert "approve" not in user["permissions"]
    assert "admin" not in user["permissions"]


def test_the_reader_role_is_known_to_the_application(client):
    from kpibench.security import ROLES

    assert "user" in ROLES
    assert ROLES["user"]["label"] == "Reader"
