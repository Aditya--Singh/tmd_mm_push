"""
Tests for bringing an existing installation up to the current shape.

The `users` table used to carry one `role` column for the whole platform. It now
carries one role per application, `role_news` and `role_bench`, and an existing
database has to be brought over to them.
"""

import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-secret-key-not-used-outside-tests",
)

from app.database.migrate import LEGACY_ROLE_MAP, migrate  # noqa: E402


LEGACY_TABLE = """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        username VARCHAR(100) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(20) NOT NULL,
        is_active INTEGER NOT NULL,
        created_at DATETIME NOT NULL
    )
"""


@pytest.fixture()
def legacy_database(tmp_path):
    """A database that was made before the roles were split."""
    path = tmp_path / "legacy.db"

    connection = sqlite3.connect(path)

    connection.execute(LEGACY_TABLE)

    for index, (username, role) in enumerate(
        [
            ("admin", "admin"),
            ("analyst", "analyst"),
            ("approver", "approver"),
            ("gm", "gm"),
            ("aditya", "user"),
        ],
        start=1,
    ):
        connection.execute(
            "insert into users (id, username, password_hash, role, is_active, "
            "created_at) values (?, ?, ?, ?, 1, '2026-01-01')",
            (index, username, "hash", role),
        )

    connection.commit()
    connection.close()

    return path


def columns_of(path, table="users"):
    connection = sqlite3.connect(path)

    names = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]

    connection.close()

    return names


def test_an_old_database_gains_the_two_role_columns(legacy_database):
    engine = create_engine(f"sqlite:///{legacy_database}")

    try:
        assert migrate(engine) is True
    finally:
        engine.dispose()

    assert "role_news" in columns_of(legacy_database)
    assert "role_bench" in columns_of(legacy_database)


def test_the_old_role_is_carried_into_both_columns(legacy_database):
    engine = create_engine(f"sqlite:///{legacy_database}")

    try:
        migrate(engine)
    finally:
        engine.dispose()

    connection = sqlite3.connect(legacy_database)

    rows = dict(
        (row[0], (row[1], row[2]))
        for row in connection.execute(
            "select username, role_news, role_bench from users"
        )
    )

    connection.close()

    assert rows["admin"] == ("admin", "admin")
    assert rows["analyst"] == ("user", "maker")
    assert rows["approver"] == ("user", "checker")
    assert rows["gm"] == ("user", "viewer")
    assert rows["aditya"] == ("user", "user")


def test_the_old_column_is_dropped(legacy_database):
    engine = create_engine(f"sqlite:///{legacy_database}")

    try:
        migrate(engine)
    finally:
        engine.dispose()

    assert "role" not in columns_of(legacy_database)


def test_a_database_that_is_already_current_is_left_alone(tmp_path):
    path = tmp_path / "current.db"

    connection = sqlite3.connect(path)

    connection.execute(
        "create table users (id integer primary key, username varchar(100) "
        "not null, password_hash varchar(255) not null, role_news varchar(20) "
        "not null, role_bench varchar(20) not null, is_active integer not null, "
        "created_at datetime not null)"
    )

    connection.commit()
    connection.close()

    engine = create_engine(f"sqlite:///{path}")

    try:
        assert migrate(engine) is False
    finally:
        engine.dispose()


def test_every_old_role_has_a_place_to_go():
    for role in ("admin", "approver", "analyst", "gm", "user"):
        assert role in LEGACY_ROLE_MAP

        role_news, role_bench = LEGACY_ROLE_MAP[role]

        assert role_news in ("admin", "user")
        assert role_bench in ("admin", "maker", "checker", "viewer", "user")


def test_a_role_that_is_not_known_gets_the_read_only_view(tmp_path):
    path = tmp_path / "odd.db"

    connection = sqlite3.connect(path)

    connection.execute(LEGACY_TABLE)
    connection.execute(
        "insert into users (id, username, password_hash, role, is_active, "
        "created_at) values (1, 'nobody', 'hash', 'something-else', 1, '2026-01-01')"
    )

    connection.commit()
    connection.close()

    engine = create_engine(f"sqlite:///{path}")

    try:
        migrate(engine)
    finally:
        engine.dispose()

    connection = sqlite3.connect(path)

    row = connection.execute(
        "select role_news, role_bench from users where username = 'nobody'"
    ).fetchone()

    connection.close()

    assert row == ("user", "user")


def test_the_rows_survive_the_change(legacy_database):
    engine = create_engine(f"sqlite:///{legacy_database}")

    try:
        migrate(engine)

        count = engine.connect().execute(
            text("select count(*) from users")
        ).scalar()
    finally:
        engine.dispose()

    assert count == 5
