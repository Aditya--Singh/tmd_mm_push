"""
Tests for the roles of the platform and for the bridge to Peer Benchmarking.

A person holds one role in each application: `role_news` for the News Feed and
`role_bench` for Peer Benchmarking. Both are read from the `users` table and
from nowhere else.

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
    BENCH_ROLES,
    BENCH_ROLE_LABELS,
    NEWS_ROLES,
    NEWS_ROLE_LABELS,
    bench_role_label,
    is_bench_role,
    is_news_role,
    news_role_label,
)
from app.auth.security import hash_password  # noqa: E402
from app.config.settings import get_settings  # noqa: E402
from app.database.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402


#: The password every account of the account sheet holds.
PASSWORD = "Pnb@12345"


#: The accounts of the platform, as they are in the account sheet:
#: the name, the role in the News Feed and the role in Peer Benchmarking.
ROLE_ACCOUNTS = [
    ("admin", "admin", "admin"),
    ("aditya", "user", "user"),
    ("analyst", "user", "maker"),
    ("approver", "user", "checker"),
    ("gm", "user", "viewer"),
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

    for username, role_news, role_bench in ROLE_ACCOUNTS:
        db.add(
            User(
                username=username,
                password_hash=hash_password(PASSWORD),
                role_news=role_news,
                role_bench=role_bench,
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
        json={"username": username, "password": PASSWORD},
    )

    assert response.status_code == 200

    return response.json()


# ----------------------------------------------------------------- the roles
def test_the_news_feed_knows_its_own_roles():
    assert set(NEWS_ROLES) == {"admin", "user"}


def test_peer_benchmarking_knows_its_own_roles():
    assert set(BENCH_ROLES) == {"admin", "maker", "checker", "viewer", "user"}


def test_each_role_has_a_name():
    for role in NEWS_ROLES:
        assert news_role_label(role)

    for role in BENCH_ROLES:
        assert bench_role_label(role)


def test_the_names_of_the_benchmarking_roles_are_its_own():
    # Peer Benchmarking shows these names itself, so the two never disagree.
    assert BENCH_ROLE_LABELS["maker"] == "Analyst (Maker)"
    assert BENCH_ROLE_LABELS["checker"] == "Approver (Checker)"
    assert BENCH_ROLE_LABELS["viewer"] == "Top Management (Viewer)"
    assert BENCH_ROLE_LABELS["user"] == "Reader"


def test_the_news_roles_are_known_by_name():
    assert is_news_role("admin")
    assert is_news_role("user")
    assert not is_news_role("maker")
    assert not is_news_role(None)


def test_the_benchmarking_roles_are_known_by_name():
    assert is_bench_role("maker")
    assert is_bench_role("user")
    assert not is_bench_role("analyst")
    assert not is_bench_role("")


# ------------------------------------------------------------------- sign-in
def test_the_login_response_carries_both_roles(client):
    body = sign_in(client, "analyst")

    assert body["role_news"] == "user"
    assert body["role_bench"] == "maker"
    assert body["role_news_label"] == "Reader"
    assert body["role_bench_label"] == "Analyst (Maker)"


def test_the_current_user_carries_both_roles(client):
    body = sign_in(client, "approver")

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["role_news"] == "user"
    assert response.json()["role_bench"] == "checker"


def test_the_administrator_holds_both_roles(client):
    body = sign_in(client, "admin")

    assert body["role_news"] == "admin"
    assert body["role_bench"] == "admin"


def test_the_account_name_is_matched_without_regard_to_case(client):
    # People type "Admin" and "admin" for the same account.
    body = sign_in(client, "ADMIN")

    assert body["username"] == "admin"


def test_a_wrong_password_is_refused(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )

    assert response.status_code == 401


# --------------------------------------------------- the bridge to the app
def test_the_ticket_endpoint_needs_a_signed_in_person(client):
    response = client.post("/api/services/benchmarking/ticket")

    assert response.status_code == 401


def test_the_ticket_endpoint_says_what_is_missing(client):
    body = sign_in(client, "analyst")

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


def test_the_ticket_is_asked_for_with_the_benchmarking_role(client, monkeypatch):
    """
    The role handed to Peer Benchmarking is the `role_bench` column.

    The role a person holds in the News Feed has no say in it: an analyst of
    the news is a maker of the figures.
    """
    body = sign_in(client, "analyst")

    sent = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"ticket": "ticket-1", "expires_in": 120, "path": "/#overview"}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(json or {})
        sent["headers"] = headers

        return FakeResponse()

    monkeypatch.setattr("app.api.integrations.httpx.post", fake_post)

    settings = get_settings()
    original = settings.kpi_handoff_secret
    settings.kpi_handoff_secret = "x" * 40

    try:
        response = client.post(
            "/api/services/benchmarking/ticket",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        assert response.status_code == 200
        assert sent["role"] == "maker"
        assert sent["username"] == "analyst"
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


# ---------------------------------------------- the administrator of the news
def test_the_screens_of_the_administrator_are_kept_from_a_reader(client):
    """
    The summary and the insights belong to the administrator of the News
    Feed, which is the `role_news` column and not the one held in Peer
    Benchmarking.
    """
    reader = sign_in(client, "aditya")

    for path in (
        "/api/dashboard/summary",
        "/api/dashboard/top-banks",
        "/api/dashboard/top-topics",
        "/api/dashboard/stats",
    ):
        response = client.get(
            path,
            headers={"Authorization": f"Bearer {reader['access_token']}"},
        )

        assert response.status_code == 403, path


def test_the_administrator_of_the_news_may_open_those_screens(client):
    admin = sign_in(client, "admin")

    response = client.get(
        "/api/dashboard/summary",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )

    assert response.status_code == 200


def test_a_maker_of_figures_is_still_a_reader_of_the_news(client):
    """
    The analyst collects the figures in Peer Benchmarking, and reads the
    news in the News Feed. The role of one application says nothing about
    the other.
    """
    maker = sign_in(client, "analyst")

    assert maker["role_bench"] == "maker"

    response = client.get(
        "/api/dashboard/summary",
        headers={"Authorization": f"Bearer {maker['access_token']}"},
    )

    assert response.status_code == 403


def test_the_news_feed_is_open_to_every_role(client):
    for username in ("admin", "aditya", "analyst", "approver", "gm"):
        body = sign_in(client, username)

        response = client.get(
            "/api/news",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )

        assert response.status_code == 200, username
