"""Database engine, session handling and declarative base (SQLite by default, PostgreSQL via DATABASE_URL)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

_settings = get_settings()
_is_sqlite = _settings.sqlalchemy_url.startswith("sqlite")

engine = create_engine(
    _settings.sqlalchemy_url,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
    pool_pre_ping=True,
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - driver hook
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


# columns added after the first release: (table, column, SQL type) - added in place on older databases
_ADDED_COLUMNS = [
    ("circulars", "listing_group", "VARCHAR(256)"),
    ("circulars", "revision", "INTEGER DEFAULT 0"),
    ("circulars", "updated_at", "TIMESTAMP"),
    ("circulars", "superseded_by", "INTEGER"),
]


def init_db() -> None:
    from sqlalchemy import inspect, text

    from app.core import models  # noqa: F401  (register models)

    Base.metadata.create_all(engine)
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, col, sqltype in _ADDED_COLUMNS:
            if col not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {sqltype}"))


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
