"""
Tests for the authentication endpoints.

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

# The settings require a secret key, so it must exist before the
# application modules are imported.
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-not-used-outside-tests",
)

from app.auth.security import hash_password  # noqa: E402
from app.database.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture()
def client():
    # StaticPool keeps every thread on the same in-memory connection, so
    # the test client sees the tables created here.
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

    db.add(
        User(
            username="Admin",
            password_hash=hash_password("Admin@news26"),
            role="admin",
            is_active=1,
            created_at=datetime.now(timezone.utc),
        )
    )

    db.add(
        User(
            username="Viewer",
            password_hash=hash_password("Viewer@news26"),
            role="user",
            is_active=1,
            created_at=datetime.now(timezone.utc),
        )
    )

    db.add(
        User(
            username="Disabled",
            password_hash=hash_password("Disabled@news26"),
            role="user",
            is_active=0,
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


def test_login_returns_a_token_for_valid_credentials(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "Admin", "password": "Admin@news26"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["username"] == "Admin"
    assert body["role"] == "admin"
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_rejects_a_wrong_password(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "Admin", "password": "wrong"},
    )

    assert response.status_code == 401


def test_login_rejects_an_unknown_user(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "Nobody", "password": "Admin@news26"},
    )

    assert response.status_code == 401


def test_login_rejects_an_inactive_user(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "Disabled", "password": "Disabled@news26"},
    )

    assert response.status_code == 401


def test_me_returns_the_signed_in_user(client):
    token = client.post(
        "/api/auth/login",
        json={"username": "Admin", "password": "Admin@news26"},
    ).json()["access_token"]

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    body = response.json()

    assert body["username"] == "Admin"
    assert body["role"] == "admin"
    assert isinstance(body["id"], int)


def test_me_requires_a_token(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_rejects_an_invalid_token(client):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


def test_protected_routes_require_a_token(client):
    assert client.get("/api/news").status_code == 401
    assert client.get("/api/dashboard/summary").status_code == 401


def test_the_root_endpoint_reports_the_application(client):
    """
    The root endpoint is what a person opens to check that the backend is
    running, so it has to work.
    """

    response = client.get("/")

    assert response.status_code == 200

    body = response.json()

    assert body["application"]
    assert body["environment"]


def test_the_health_endpoint_reports_healthy(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_every_setting_used_by_the_application_exists(client):
    """
    Guards against a setting being read that is not declared, which
    fails at request time rather than at start-up.
    """

    from app.config.settings import Settings

    for name in ("app_name", "env", "database_url", "cors_origin_list"):
        assert hasattr(Settings(), name), f"Settings.{name} is missing"


def login(client, username="Admin", password="Admin@news26"):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )

    return response.json()["access_token"]


def test_feedback_can_be_recorded_with_only_the_ratings(client):
    """
    The landing page collects the feedback and identifies the user from
    the access token, so the body does not have to carry the user.
    """

    token = login(client)

    response = client.post(
        "/api/feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "relevance": 4,
            "accuracy": 5,
            "usefulness": 4,
            "clarity": 3,
            "timeliness": 5,
            "comments": "A good platform.",
        },
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Feedback submitted successfully"


def test_feedback_still_accepts_the_user_fields(client):
    token = login(client)

    response = client.post(
        "/api/feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "Admin",
            "role": "admin",
            "relevance": 4,
            "accuracy": 4,
            "usefulness": 4,
            "clarity": 4,
            "timeliness": 4,
        },
    )

    assert response.status_code == 201


def test_feedback_requires_a_token(client):
    response = client.post(
        "/api/feedback",
        json={
            "relevance": 4,
            "accuracy": 4,
            "usefulness": 4,
            "clarity": 4,
            "timeliness": 4,
        },
    )

    assert response.status_code == 401


def test_feedback_rejects_an_incomplete_rating(client):
    token = login(client)

    response = client.post(
        "/api/feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "relevance": 4,
            "accuracy": 4,
            "usefulness": 4,
            "clarity": 0,
            "timeliness": 4,
        },
    )

    assert response.status_code == 422
