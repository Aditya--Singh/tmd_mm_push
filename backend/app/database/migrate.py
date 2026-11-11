"""Bringing an existing installation up to the current shape of the tables.

The `users` table used to carry one `role` column for the whole platform. It now carries one
role per application, `role_news` and `role_bench`. A database that was created before that
change still has the old column, and `create_all` does not alter a table that already exists,
so the change has to be made here.

The old single role is carried into both new columns:

    old role       role_news    role_bench
    admin          admin        admin
    approver       user         checker
    analyst        user         maker
    gm             user         viewer
    user           user         user

The old column is dropped once the values have been carried over. A SQLite build that is too
old to drop a column keeps it: an unused column is harmless, and the next start tries again.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


logger = logging.getLogger(__name__)


#: How a role of the old single-column table is carried into the two new columns.
LEGACY_ROLE_MAP: dict[str, tuple[str, str]] = {
    "admin": ("admin", "admin"),
    "approver": ("user", "checker"),
    "analyst": ("user", "maker"),
    "gm": ("user", "viewer"),
    "user": ("user", "user"),
}

#: The role given to a row whose old role is not known.
DEFAULT_ROLE = ("user", "user")


def _columns(engine: Engine, table: str) -> list[str]:
    inspector = inspect(engine)

    if table not in inspector.get_table_names():
        return []

    return [column["name"] for column in inspector.get_columns(table)]


def _add_column(engine: Engine, table: str, column: str, definition: str) -> bool:
    """Add a column to a table that does not have it yet."""
    with engine.begin() as connection:
        connection.execute(
            text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        )

    logger.info("Added the column %s.%s", table, column)

    return True


def migrate_user_roles(engine: Engine) -> bool:
    """
    Give the `users` table its two role columns.

    Returns whether anything was changed.
    """
    columns = _columns(engine, "users")

    if not columns:
        # The table does not exist yet; it will be created in the current shape.
        return False

    changed = False

    if "role_news" not in columns:
        _add_column(engine, "users", "role_news", "VARCHAR(20) NOT NULL DEFAULT 'user'")

        changed = True

    if "role_bench" not in columns:
        _add_column(
            engine,
            "users",
            "role_bench",
            "VARCHAR(20) NOT NULL DEFAULT 'viewer'",
        )

        changed = True

    if "role" in columns:
        with engine.begin() as connection:
            rows = connection.execute(
                text("SELECT id, role FROM users")
            ).fetchall()

            for row in rows:
                role_news, role_bench = LEGACY_ROLE_MAP.get(
                    (row.role or "").strip().lower(),
                    DEFAULT_ROLE,
                )

                connection.execute(
                    text(
                        "UPDATE users SET role_news = :role_news, role_bench = :role_bench "
                        "WHERE id = :id"
                    ),
                    {
                        "role_news": role_news,
                        "role_bench": role_bench,
                        "id": row.id,
                    },
                )

        try:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users DROP COLUMN role"))
        except Exception:  # pragma: no cover - depends on the SQLite build
            logger.warning(
                "The old users.role column could not be dropped; it is unused and will be "
                "dropped by a later start."
            )
        else:
            logger.info("Dropped the old users.role column")

        changed = True

    return changed


def migrate_feedback_roles(engine: Engine) -> bool:
    """Give the feedback table the second role column."""
    columns = _columns(engine, "application_feedback")

    if not columns:
        return False

    if "role_bench" in columns:
        return False

    _add_column(
        engine,
        "application_feedback",
        "role_bench",
        "VARCHAR(20) NOT NULL DEFAULT 'viewer'",
    )

    return True


def migrate(engine: Engine) -> bool:
    """Bring every table that changed up to the current shape."""
    changed = migrate_user_roles(engine)

    if migrate_feedback_roles(engine):
        changed = True

    if changed:
        logger.info("The database was brought up to the current shape")

    return changed
