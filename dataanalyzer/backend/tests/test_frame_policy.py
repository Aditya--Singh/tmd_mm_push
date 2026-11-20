"""Who may frame the Data Analyzer.

The hub shows this app inside a frame. The browser only allows that when the
`Content-Security-Policy` header names the hub's address, and a policy source list
is separated by spaces. A comma makes the browser drop the whole list, and the frame
stays empty, so this is checked here.
"""
from __future__ import annotations

from app.core.config import BACKEND_DIR, Settings


def _the_policy(sources: str) -> str:
    """The policy source list for a list of sites, read the way the app reads it."""
    settings = Settings(frame_ancestors=sources)
    return " ".join(settings.frame_ancestor_list) or "'none'"


def test_a_comma_separated_list_becomes_a_policy_the_browser_understands():
    policy = _the_policy("http://localhost:5174,http://127.0.0.1:5174")

    assert policy == "http://localhost:5174 http://127.0.0.1:5174"
    assert "," not in policy


def test_a_space_separated_list_is_kept_as_it_is():
    policy = _the_policy("'self' http://localhost:5174 http://127.0.0.1:5174")

    assert policy == "'self' http://localhost:5174 http://127.0.0.1:5174"


def test_an_empty_list_forbids_every_frame():
    assert _the_policy("") == "'none'"


def test_the_answer_travels_in_the_header(the_app):
    """The header a browser reads when the hub opens the app."""
    answer = the_app.get("/health")

    policy = answer.headers["content-security-policy"]

    assert policy.startswith("frame-ancestors ")
    assert "," not in policy
    assert "http://localhost:5174" in policy
    assert "http://127.0.0.1:5174" in policy


def test_the_app_says_who_may_frame_it(the_app):
    """The browser learns the list from the app itself, so it never guesses."""
    answer = the_app.get("/api/meta")

    assert "http://127.0.0.1:5174" in answer.json()["frame_ancestors"]


def test_the_apps_own_file_wins_over_the_one_beside_it(tmp_path):
    """The first occurrence of a key wins, the way the rest of the platform reads.

    pydantic-settings lets the last file of the list win, so the app's own file is
    written last in the model's list of files.
    """
    beside = tmp_path / "dataanalyzer"
    own = tmp_path / "backend"
    beside.mkdir()
    own.mkdir()

    (beside / ".env").write_text("CORS_ORIGINS=https://beside.example\n", encoding="utf-8")
    (own / ".env").write_text("CORS_ORIGINS=https://own.example\n", encoding="utf-8")

    settings = Settings(_env_file=(beside / ".env", own / ".env"))

    assert settings.cors_origins == "https://own.example"

    files = Settings.model_config["env_file"]

    assert files[0].parent == BACKEND_DIR.parent
    assert files[1].parent == BACKEND_DIR
