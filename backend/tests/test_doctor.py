"""
Tests for the platform check.

The doctor is the answer to "why does the sign-in not go through?". It has to
name the part that is wrong and the command that fixes it, and it has to show
what the backend said the last time it ran, because that is the only place the
real reason of a failure is written down.
"""

import importlib.util
import sqlite3
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
    monkeypatch.setattr(module, "BACKEND_DB", tmp_path / "backend" / "news.db")
    monkeypatch.setattr(
        module, "BACKEND_LOG", tmp_path / "backend" / "logs" / "backend.log"
    )

    return module


def test_the_doctor_reports_the_settings_that_are_missing(doctor, capsys):
    assert doctor.main(["--quick"]) == 1

    said = capsys.readouterr().out

    assert "backend/.env is missing" in said
    assert "setup.sh" in said


def test_the_doctor_is_happy_when_everything_is_in_place(doctor, tmp_path, capsys):
    (tmp_path / "backend").mkdir()
    (tmp_path / "benchmarking").mkdir()

    (tmp_path / "backend" / ".env").write_text(
        "JWT_SECRET_KEY=one\nKPI_HANDOFF_SECRET=shared\n", encoding="utf-8"
    )
    (tmp_path / "benchmarking" / ".env").write_text(
        "HANDOFF_SECRET=shared\n", encoding="utf-8"
    )

    connection = sqlite3.connect(tmp_path / "backend" / "news.db")
    connection.execute("create table users (username text)")
    connection.execute("insert into users values ('admin')")
    connection.commit()
    connection.close()

    (tmp_path / "backend" / ".venv").mkdir()
    (tmp_path / "benchmarking" / ".venv").mkdir()
    (tmp_path / "landing" / "node_modules").mkdir(parents=True)
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)

    assert doctor.main(["--quick"]) == 0

    said = capsys.readouterr().out

    assert "the two servers share the same secret" in said
    assert "the database holds 1 accounts" in said
    assert "Everything is in place" in said


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
