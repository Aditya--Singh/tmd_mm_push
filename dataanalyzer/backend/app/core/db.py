"""The database: SQLite by default, PostgreSQL through DATABASE_URL."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

def _make_engine():
    """The engine of the database of this installation."""
    settings = get_settings()
    is_sqlite = settings.database_url.startswith("sqlite")

    engine = create_engine(
        settings.database_url or f"sqlite:///{settings.data_dir / 'analyzer.db'}",
        connect_args={"check_same_thread": False, "timeout": 30} if is_sqlite else {},
        pool_pre_ping=True,
    )

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - driver hook
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


engine = _make_engine()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def reset_the_engine() -> None:
    """
    Build the engine again, from the settings of right now.

    The engine is built when this module is read. A test that changes the settings
    needs a new engine, or every test would share the database of the first one.
    """
    global engine

    engine.dispose()
    engine = _make_engine()

    SessionLocal.configure(bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app.core import models  # noqa: F401  (register the models)

    Base.metadata.create_all(engine)


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
