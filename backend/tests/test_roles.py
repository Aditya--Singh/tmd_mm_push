"""
Tests for the roles of the platform and for the bridge to Peer Benchmarking.

The application is exercised with an in-memory SQLite database so that the
tests never touch the development database.
"""

import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-not-used-outside-tests",
)

from app.auth.roles import (  # noqa: E402
    BENCHMARKING_ROLE_MAP,
    ROLES,
    benchmarking_role,
    role_label,
)
from app.auth.security import hash_password  # noqa: E402
from app.config.settings import get_settings  # noqa: E402
from app.database.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402


ROLE_ACCOUNTS = [
    ("Admin", "admin"),
    ("Analyst", "analyst"),
    ("Approver", "approver"),
    ("Gm", "gm"),
    ("Reader", "user"),
]


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        autoflush=False,
        autocommit=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    for username, role in ROLE_ACCOUNTS:
        db.add(
            User(
                username=username,
                password_hash=hash_password(f"{username}@news26"),
                role=role,
                is_active=1,
                created_at=datetime.now(timezone.utc),
            )
        )

    db.commit()

    def override_get_db():
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


def sign_in(client, username):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": f"{username}@news26"},
    )

    assert response.status_code == 200

    return response.json()


# ----------------------------------------------------------------- the roles
def test_every_role_is_known():
    assert set(ROLES) == {"admin", "approver", "analyst", "gm", "user"}


def test_each_role_has_a_name():
    for role in ROLES:
        assert role_label(role)


def test_every_role_maps_to_a_benchmarking_role():
    # The role travels with the token, so that every service can ask.
    assert BENCHMARKING_ROLE_MAP["admin"] == "admin"
    assert BENCHMARKING_ROLE_MAP["analyst"] == "maker"
    assert BENCHMARKING_ROLE_MAP["approver"] == "checker"
    assert BENCHMARKING_ROLE_MAP["gm"] == "viewer"
    assert BENCHMARKING_ROLE_MAP["user"] == "viewer"


def test_an_unknown_role_falls_back_to_the_read_only_view():
    assert benchmarking_role("something-else") == "viewer"
    assert benchmarking_role("") == "viewer"


def test_the_login_response_carries_the_role_name(client):
    body = sign_in(client, "Analyst")

    assert body["role"] == "analyst"
    assert body["role_label"] == "Analyst"


def test_the_current_user_carries_the_role_name(client):
    body = sign_in(client, "Approver")

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "approver"
    assert response.json()["role_label"] == "Approver"


# --------------------------------------------------- the bridge to the app
def test_the_ticket_endpoint_needs_a_signed_in_person(client):
    response = client.post("/api/services/benchmarking/ticket")

    assert response.status_code == 401


def test_the_ticket_endpoint_says_what_is_missing(client):
    body = sign_in(client, "Analyst")

    settings = get_settings()

    # Without a shared secret the endpoint explains what to set,
    # instead of failing in an unclear way.
    original = settings.kpi_handoff_secret
    settings.kpi_handoff_secret = ""

    try:
        response = client.post(
            "/api/services/benchmarking/ticket",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        assert response.status_code == 503
        assert "KPI_HANDOFF_SECRET" in response.json()["detail"]
    finally:
        settings.kpi_handoff_secret = original


def test_the_manifest_endpoint_needs_no_sign_in(client):
    # The navigation names the screens and nothing else, so the hub can
    # draw its rail before it has a session for the app.
    original = get_settings().kpi_app_url

    # There is no benchmarking app in the tests, so the call fails. What
    # matters is that it is not refused for want of a sign-in.
    get_settings().kpi_app_url = "http://127.0.0.1:9"

    try:
        response = client.get("/api/services/benchmarking/manifest")

        assert response.status_code in (200, 502, 503)
    finally:
        get_settings().kpi_app_url = original
