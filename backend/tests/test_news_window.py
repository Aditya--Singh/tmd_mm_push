"""
Tests for the window the news may reach.

The news pipeline is told how many days back the news may reach, and only the news
published inside that window is stored. The cut-off is a date, and the scraper stops at it.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-not-used-outside-tests",
)

from app.auth.security import hash_password  # noqa: E402
from app.database.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.scrapers.psuconnect import PSUConnectScraper  # noqa: E402
from app.services.news_pipeline import MAX_DAYS, NewsPipelineService  # noqa: E402
from app.services.scraper_service import ScraperService  # noqa: E402


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

    db.add(
        User(
            username="admin",
            password_hash=hash_password("admin@tmd26"),
            role_news="admin",
            role_bench="admin",
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


def sign_in(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin@tmd26"},
    )

    assert response.status_code == 200

    return response.json()["access_token"]


# ------------------------------------------------------------------ the endpoint
def test_the_window_is_taken_from_the_request(client, monkeypatch):
    """The number of days in the request says how far back the news may reach."""
    asked = {}

    def fake_run(self, days=30):
        asked["days"] = days

    monkeypatch.setattr(NewsPipelineService, "run", fake_run)

    token = sign_in(client)

    response = client.post(
        "/api/admin/news/ingest",
        headers={"Authorization": f"Bearer {token}"},
        json={"days": 45},
    )

    assert response.status_code == 200

    body = response.json()

    assert asked["days"] == 45
    assert body["days"] == 45
    assert body["cutoff"]


def test_the_window_has_a_default(client, monkeypatch):
    asked = {}

    def fake_run(self, days=30):
        asked["days"] = days

    monkeypatch.setattr(NewsPipelineService, "run", fake_run)

    token = sign_in(client)

    response = client.post(
        "/api/admin/news/ingest",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert response.status_code == 200
    assert asked["days"] == 30


def test_a_window_of_more_than_ninety_days_is_refused(client):
    token = sign_in(client)

    response = client.post(
        "/api/admin/news/ingest",
        headers={"Authorization": f"Bearer {token}"},
        json={"days": 91},
    )

    assert response.status_code == 422


def test_a_window_of_no_days_is_refused(client):
    token = sign_in(client)

    response = client.post(
        "/api/admin/news/ingest",
        headers={"Authorization": f"Bearer {token}"},
        json={"days": 0},
    )

    assert response.status_code == 422


def test_the_pipeline_needs_an_administrator(client, monkeypatch):
    monkeypatch.setattr(
        NewsPipelineService, "run", lambda self, days=30: None
    )

    response = client.post("/api/admin/news/ingest", json={"days": 30})

    assert response.status_code == 401


# ----------------------------------------------------------------- the cut-off
def test_the_cut_off_is_the_day_the_window_starts_at():
    """The service counts the window back from today."""
    seen = {}

    class FakeScraper:
        def __init__(self):
            pass

        def run(self, cutoff=None):
            seen["cutoff"] = cutoff

    import app.services.news_pipeline as pipeline

    original = pipeline.ScraperService

    pipeline.ScraperService = FakeScraper

    try:
        NewsPipelineService().run(days=7)
    finally:
        pipeline.ScraperService = original

    cutoff = seen["cutoff"]

    assert cutoff is not None

    expected = datetime.now(timezone.utc) - timedelta(days=7)

    # A moment of slack, because the two are not taken at the same instant.
    assert abs((expected - cutoff).total_seconds()) < 30


def test_a_window_longer_than_ninety_days_is_capped():
    """The service does not accept a window the endpoint would refuse."""
    seen = {}

    class FakeScraper:
        def __init__(self):
            pass

        def run(self, cutoff=None):
            seen["cutoff"] = cutoff

    import app.services.news_pipeline as pipeline

    original = pipeline.ScraperService

    pipeline.ScraperService = FakeScraper

    try:
        NewsPipelineService().run(days=365)
    finally:
        pipeline.ScraperService = original

    expected = datetime.now(timezone.utc) - timedelta(days=MAX_DAYS)

    assert abs((expected - seen["cutoff"]).total_seconds()) < 30


# -------------------------------------------------------------------- the scraper
def make_item(days_ago: int, identifier: int) -> dict:
    """One article of the source, published so many days ago."""
    published = datetime.now(timezone.utc) - timedelta(days=days_ago)

    return {
        "id": identifier,
        "title": f"Article {identifier}",
        "urltitle": f"article {identifier}",
        "date": published.isoformat().replace("+00:00", "Z"),
        "publisher": "PSU Connect",
        "auther": "Someone",
        "shortdesc": "A short description.",
        "image": None,
    }


def test_the_scraper_keeps_only_the_articles_inside_the_window(monkeypatch):
    """The cut-off decides what is fetched."""
    pages = [
        [make_item(1, 1), make_item(3, 2)],
        [make_item(10, 3), make_item(40, 4)],
    ]

    calls = {"offset": 0}

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, params=None, **kwargs):
        offset = params["offset"]

        calls["offset"] = offset

        if offset // 16 >= len(pages):
            return FakeResponse({"success": True, "data": []})

        return FakeResponse({"success": True, "data": pages[offset // 16]})

    monkeypatch.setattr(
        "app.scrapers.psuconnect.get", lambda *a, **k: fake_get(*a, **k)
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    articles = PSUConnectScraper().fetch_articles(cutoff=cutoff)

    identifiers = [article.external_id for article in articles]

    # The article of 40 days ago is outside the window and is left out.
    assert 4 not in identifiers
    assert 1 in identifiers
    assert 3 in identifiers


def test_the_scraper_stops_at_the_cut_off(monkeypatch):
    """A page that holds nothing inside the window ends the walk."""
    calls = {"count": 0}

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, params=None, **kwargs):
        calls["count"] += 1

        offset = params["offset"]

        # The first page is inside the window, the second is not.
        if offset == 0:
            return FakeResponse({"success": True, "data": [make_item(1, 1)]})

        return FakeResponse(
            {"success": True, "data": [make_item(60, 2), make_item(90, 3)]}
        )

    monkeypatch.setattr(
        "app.scrapers.psuconnect.get", lambda *a, **k: fake_get(*a, **k)
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    articles = PSUConnectScraper().fetch_articles(cutoff=cutoff)

    assert [article.external_id for article in articles] == [1]

    # The second page was read, the third was not.
    assert calls["count"] == 2


def test_the_scraper_has_a_window_of_its_own(monkeypatch):
    """Without a cut-off the window is 30 days."""
    calls = {"count": 0}

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, params=None, **kwargs):
        calls["count"] += 1

        offset = params["offset"]

        if offset == 0:
            return FakeResponse({"success": True, "data": [make_item(5, 1)]})

        return FakeResponse({"success": True, "data": [make_item(80, 2)]})

    monkeypatch.setattr(
        "app.scrapers.psuconnect.get", lambda *a, **k: fake_get(*a, **k)
    )

    articles = PSUConnectScraper().fetch_articles()

    assert [article.external_id for article in articles] == [1]


def test_older_articles_are_not_stored(monkeypatch):
    """The service keeps the window as well, so nothing old reaches the database."""
    stored = []

    class FakeRepository:
        def __init__(self, db):
            self.db = db

        def get_existing_urls(self):
            return set()

        def save(self, article):
            stored.append(article)

    class FakeScraper:
        def __init__(self):
            pass

        def fetch_articles(self, cutoff=None):
            return [
                make_article(2, "https://example.test/new"),
                make_article(80, "https://example.test/old"),
            ]

        def fetch_article_content(self, article):
            return article

    def make_article(days_ago, url):
        from app.schemas.news import NewsArticle

        return NewsArticle(
            source="PSU Connect",
            headline=f"Article of {days_ago} days ago",
            url=url,
            publish_date=datetime.now(timezone.utc) - timedelta(days=days_ago),
            content="Some content.",
        )

    import app.services.scraper_service as scraper_service

    original_repository = scraper_service.NewsRepository
    original_scraper = scraper_service.PSUConnectScraper

    scraper_service.NewsRepository = FakeRepository
    scraper_service.PSUConnectScraper = FakeScraper

    try:
        ScraperService().run(
            cutoff=datetime.now(timezone.utc) - timedelta(days=30)
        )
    finally:
        scraper_service.NewsRepository = original_repository
        scraper_service.PSUConnectScraper = original_scraper

    assert [article.url for article in stored] == ["https://example.test/new"]


# ----------------------------------------------------------------- the floor
def test_the_house_rule_is_the_floor(monkeypatch):
    """
    `NEWS_CUTOFF_DATE` is the oldest day the news may reach, whatever window is asked for.
    """
    from app.services.scraper_service import effective_cutoff

    monkeypatch.setattr(
        "app.services.scraper_service.settings.news_cutoff_date", "2026-06-20"
    )

    floor = effective_cutoff(None)

    assert floor is not None
    assert floor.date().isoformat() == "2026-06-20"


def test_a_window_that_reaches_further_back_than_the_floor_is_cut_short(
    monkeypatch,
):
    """A run may ask for less news, never for more."""
    from app.services.scraper_service import effective_cutoff

    monkeypatch.setattr(
        "app.services.scraper_service.settings.news_cutoff_date", "2026-06-20"
    )

    further_back = datetime(2020, 1, 1, tzinfo=timezone.utc)

    assert effective_cutoff(further_back).date().isoformat() == "2026-06-20"


def test_a_window_shorter_than_the_floor_is_left_alone(monkeypatch):
    """The window that was asked for wins when it is the shorter one."""
    from app.services.scraper_service import effective_cutoff

    monkeypatch.setattr(
        "app.services.scraper_service.settings.news_cutoff_date", "2020-01-01"
    )

    window = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert effective_cutoff(window) == window


def test_a_floor_that_cannot_be_read_is_ignored(monkeypatch):
    """A setting that is not a date is ignored rather than stopping the run."""
    from app.services.scraper_service import effective_cutoff

    monkeypatch.setattr(
        "app.services.scraper_service.settings.news_cutoff_date", "not a date"
    )

    window = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert effective_cutoff(window) == window

