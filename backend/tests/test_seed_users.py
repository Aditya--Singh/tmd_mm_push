"""
Tests for the demo accounts.

The accounts are read from `seed/users.csv`, which holds the content of the
`users` and `refer` worksheets of the account sheet: the name of the account,
the password in plain text, the role in the News Feed and the role in Peer
Benchmarking.

The accounts are created before the server has ever run, so the tables may not
be there yet. This is easy to break and hard to notice, because the failure
only shows up on a machine that has never started the backend.
"""

import csv
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import bcrypt


BACKEND = Path(__file__).resolve().parents[1]

SEED_FILE = BACKEND / "seed" / "users.csv"


def read_sheet():
    with SEED_FILE.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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


def accounts_in(database: Path):
    connection = sqlite3.connect(database)

    rows = connection.execute(
        "select username, password_hash, role_news, role_bench from users "
        "order by username"
    ).fetchall()

    connection.close()

    return rows


def test_the_accounts_are_created_in_an_empty_database(tmp_path):
    database = tmp_path / "fresh.db"

    result = run_seed(database)

    assert result.returncode == 0, result.stderr

    accounts = dict((row[0], row) for row in accounts_in(database))

    assert accounts["admin"][2] == "admin"
    assert accounts["admin"][3] == "admin"
    assert accounts["analyst"][2] == "user"
    assert accounts["analyst"][3] == "maker"
    assert accounts["approver"][3] == "checker"
    assert accounts["gm"][3] == "viewer"
    assert accounts["aditya"][2] == "user"
    assert accounts["aditya"][3] == "user"


def test_the_password_of_the_sheet_is_the_one_that_works(tmp_path):
    """
    The plain password of the `refer` worksheet is the password of the
    account, and the table only ever holds its hash.
    """
    database = tmp_path / "fresh.db"

    assert run_seed(database).returncode == 0

    accounts = dict((row[0], row) for row in accounts_in(database))

    for row in read_sheet():
        stored = accounts[row["username"]][1]

        assert bcrypt.checkpw(row["password"].encode(), stored.encode())

        # The plain password is never written down.
        assert row["password"] not in stored


def test_running_the_seed_again_keeps_the_same_accounts(tmp_path):
    database = tmp_path / "fresh.db"

    assert run_seed(database).returncode == 0

    before = [(row[0], row[2], row[3]) for row in accounts_in(database)]

    assert run_seed(database).returncode == 0

    after = [(row[0], row[2], row[3]) for row in accounts_in(database)]

    assert before == after


def test_an_account_under_another_spelling_is_replaced(tmp_path):
    """
    The account sheet writes the names in lower case. An older installation
    may have "Admin" for the same person, and leaving both would make the
    sign-in ambiguous.
    """
    database = tmp_path / "fresh.db"

    assert run_seed(database).returncode == 0

    connection = sqlite3.connect(database)

    connection.execute(
        "insert into users (username, password_hash, role_news, role_bench, "
        "is_active, created_at) values ('Admin', 'x', 'admin', 'admin', 1, '2026-01-01')"
    )

    connection.commit()
    connection.close()

    assert run_seed(database).returncode == 0

    names = [row[0] for row in accounts_in(database)]

    assert "admin" in names
    assert "Admin" not in names
