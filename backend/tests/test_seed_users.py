"""
Tests for the demo accounts.

The accounts are created before the server has ever run, so the tables
may not be there yet. This is easy to break and hard to notice, because
the failure only shows up on a machine that has never started the
backend.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]


def run_seed(database: Path) -> subprocess.CompletedProcess:
    environment = dict(os.environ)

    environment["DATABASE_URL"] = f"sqlite:///{database}"

    return subprocess.run(
        [sys.executable, "seed_users.py"],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
    )


def test_the_accounts_are_created_in_an_empty_database(tmp_path):
    database = tmp_path / "fresh.db"

    result = run_seed(database)

    assert result.returncode == 0, result.stderr

    connection = sqlite3.connect(database)

    rows = connection.execute("select username, role from users").fetchall()

    connection.close()

    accounts = dict(rows)

    assert accounts["Admin"] == "admin"
    assert accounts["analyst"] == "analyst"
    assert accounts["approver"] == "approver"
    assert accounts["gm"] == "gm"


def test_running_the_seed_again_changes_nothing(tmp_path):
    database = tmp_path / "fresh.db"

    assert run_seed(database).returncode == 0

    connection = sqlite3.connect(database)

    before = connection.execute(
        "select username, role, password_hash from users order by username"
    ).fetchall()

    connection.close()

    assert run_seed(database).returncode == 0

    connection = sqlite3.connect(database)

    after = connection.execute(
        "select username, role, password_hash from users order by username"
    ).fetchall()

    connection.close()

    assert before == after
