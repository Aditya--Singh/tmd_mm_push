"""
The test session.

The settings of this app are read when the module that holds them is imported, and a
module may be imported before a test has had the chance to prepare the machine. The
settings the tests need are therefore put in place here, because pytest reads this file
before it reads any test.

The tests work on a throw-away database of their own and never write into the database
of the machine. The engine is pointed at that database by the test that needs it.
"""
from __future__ import annotations

import os
import shutil
import tempfile

import pytest

#: A folder of its own for the whole test session.
SESSION_FOLDER = tempfile.mkdtemp(prefix="kpibench-tests-")

# The address of the database is only a starting point. The test that needs a
# database of its own makes one, and points the app at it.
os.environ["DATA_DIR"] = SESSION_FOLDER
os.environ["DB_URL"] = f"sqlite:///{SESSION_FOLDER}/session.db"
os.environ["SECRET_KEY"] = "test-secret-key-not-used-outside-tests"
os.environ["HANDOFF_SECRET"] = "s" * 48
os.environ["HANDOFF_ALLOW_STAFF"] = "true"
os.environ["HANDOFF_SYNC_ROLE"] = "true"
os.environ["HANDOFF_AUTO_CREATE"] = "true"


@pytest.fixture(scope="session", autouse=True)
def the_session_folder():
    """The folder of the session, removed when the session ends."""
    yield SESSION_FOLDER

    shutil.rmtree(SESSION_FOLDER, ignore_errors=True)
