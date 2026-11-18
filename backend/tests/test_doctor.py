"""
Tests for the platform check.

The doctor is the answer to "why does the sign-in not go through?". It has to
name the part that is wrong and the command that fixes it, and it has to show
what the backend said the last time it ran, because that is the only place the
real reason of a failure is written down.
"""

import importlib.machinery
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_doctor():
    """The doctor, loaded from the root of the repository."""

    spec = importlib.util.spec_from_file_location(
        "doctor", ROOT / "scripts" / "doctor.py"
    )

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    return module


@pytest.fixture()
def doctor(monkeypatch, tmp_path):
    """The doctor, pointed at an empty folder of its own."""

    module = load_doctor()

    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "BACKEND_ENV", tmp_path / "backend" / ".env")
    monkeypatch.setattr(module, "BENCH_ENV", tmp_path / "benchmarking" / ".env")
    monkeypatch.setattr(module, "SENTINEL_ENV", tmp_path / "sentinel" / ".env")
    monkeypatch.setattr(module, "ANALYZER_ENV", tmp_path / "dataanalyzer" / ".env")
    monkeypatch.setattr(module, "BACKEND_DB", tmp_path / "backend" / "news.db")
    monkeypatch.setattr(
        module, "BACKEND_LOG", tmp_path / "backend" / "logs" / "backend.log"
    )

    # What is running on this machine must not decide what the doctor says.
    def refuse(url, timeout=None):
        raise OSError("nothing is running on this machine")

    monkeypatch.setattr(module.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(module, "port_is_open", lambda *a, **k: False)

    return module


def test_the_doctor_reports_the_settings_that_are_missing(doctor, capsys):
    assert doctor.main(["--quick"]) == 1

    said = capsys.readouterr().out

    assert "backend/.env is missing" in said
    assert "setup.sh" in said


def test_the_doctor_is_happy_when_everything_is_in_place(doctor, tmp_path, capsys):
    (tmp_path / "backend").mkdir()
    (tmp_path / "benchmarking").mkdir()
    (tmp_path / "sentinel").mkdir()
    (tmp_path / "dataanalyzer").mkdir()

    (tmp_path / "backend" / ".env").write_text(
        "JWT_SECRET_KEY=one\nKPI_HANDOFF_SECRET=shared\n"
        "SENTINEL_HANDOFF_SECRET=shared-too\n"
        "ANALYZER_HANDOFF_SECRET=shared-analyzer\n",
        encoding="utf-8",
    )
    (tmp_path / "benchmarking" / ".env").write_text(
        "HANDOFF_SECRET=shared\n", encoding="utf-8"
    )
    (tmp_path / "sentinel" / ".env").write_text(
        "HANDOFF_SECRET=shared-too\n", encoding="utf-8"
    )
    (tmp_path / "dataanalyzer" / ".env").write_text(
        "HANDOFF_SECRET=shared-analyzer\n", encoding="utf-8"
    )

    connection = sqlite3.connect(tmp_path / "backend" / "news.db")
    connection.execute("create table users (username text)")
    connection.execute("insert into users values ('admin')")
    connection.commit()
    connection.close()

    (tmp_path / "backend" / ".venv").mkdir()
    (tmp_path / "benchmarking" / ".venv").mkdir()
    (tmp_path / "sentinel" / ".venv").mkdir()
    (tmp_path / "dataanalyzer" / ".venv").mkdir()
    (tmp_path / "landing" / "node_modules").mkdir(parents=True)
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)

    assert doctor.main(["--quick"]) == 0

    said = capsys.readouterr().out

    assert "the two servers share the same secret" in said
    assert "the hub and the Data Summarizer share the same secret" in said
    assert "the hub and the Data Analyzer share the same secret" in said
    assert "the database holds 1 accounts" in said
    assert "Everything is in place" in said


def test_the_doctor_says_when_the_backend_cannot_import_its_libraries(
    doctor, tmp_path, monkeypatch, capsys
):
    """
    A machine that refuses a compiled file of a library.

    The library then cannot be imported at all, and the backend stops before it has
    said anything, so the doctor has to be able to see it.
    """
    # An environment of its own, whose python is the one running the test.
    environment = tmp_path / "backend" / ".venv" / "bin"
    environment.mkdir(parents=True)

    (environment / "python").symlink_to(sys.executable)

    # SQLAlchemy, whose compiled part cannot be loaded.
    library = tmp_path / "site" / "sqlalchemy"
    library.mkdir(parents=True)

    (library / "_part.py").write_text("value = 1\n", encoding="utf-8")
    (library / f"_part{importlib.machinery.EXTENSION_SUFFIXES[0]}").write_bytes(
        b"blocked by policy"
    )
    (library / "__init__.py").write_text("from . import _part\n", encoding="utf-8")

    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "site"))

    can_import, said = doctor.the_backend_can_import_its_libraries()

    assert can_import is False
    assert "sqlalchemy" in said
    assert "ImportError" in said


def test_the_doctor_asks_the_backend_on_the_port_it_is_set_to(
    doctor, tmp_path, monkeypatch
):
    """
    A machine where port 8000 is taken uses another port.

    The doctor has to ask on that port, or it says the backend is not running
    when it is.
    """
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / ".env").write_text("PORT=8010\n", encoding="utf-8")

    assert doctor.the_backend_port() == 8010

    asked = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(url, timeout=None):
        asked.append(url)
        return FakeResponse()

    monkeypatch.setattr(doctor.urllib.request, "urlopen", fake_urlopen)

    assert doctor.the_backend_answers() is True
    assert "8010" in asked[0], asked


def test_the_doctor_falls_back_to_the_default_port(doctor, tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / ".env").write_text("PORT=nonsense\n", encoding="utf-8")

    assert doctor.the_backend_port() == 8000


def test_the_doctor_shows_what_the_backend_said(doctor, tmp_path, capsys):
    log = tmp_path / "backend" / "logs" / "backend.log"

    log.parent.mkdir(parents=True)
    log.write_text(
        "Traceback (most recent call last):\n"
        "  File \"app/main.py\", line 10, in <module>\n"
        "RuntimeError: the settings file is missing\n",
        encoding="utf-8",
    )

    doctor.main([])

    said = capsys.readouterr().out

    assert "the backend of the hub is not running" in said
    assert "RuntimeError: the settings file is missing" in said


def test_the_doctor_says_nothing_about_the_backend_when_it_has_not_run(
    doctor, tmp_path, capsys
):
    doctor.main([])

    said = capsys.readouterr().out

    assert "the backend of the hub is not running" in said
    assert "This is what it said the last time it ran" not in said
