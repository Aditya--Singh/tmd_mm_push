"""Check that the platform is set up and running.

    python scripts/doctor.py

It answers one question: why does the sign-in not go through? Every part of the platform
is looked at, and what is wrong is said plainly, with the command that fixes it.
"""

from __future__ import annotations

import argparse
import socket
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

BACKEND_ENV = ROOT / "backend" / ".env"
BENCH_ENV = ROOT / "benchmarking" / ".env"
SENTINEL_ENV = ROOT / "sentinel" / ".env"
BACKEND_DB = ROOT / "backend" / "news.db"
BACKEND_LOG = ROOT / "backend" / "logs" / "backend.log"

OK = "ok"
WRONG = "wrong"


def read_env(path: Path) -> dict[str, str]:
    """
    The values of an environment file.

    The first value of a name is the one that counts, which is how the applications read
    their settings. A file that names the same setting twice is ambiguous, so the later
    value is ignored here as well.
    """
    values: dict[str, str] = {}

    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        name, _, value = stripped.partition("=")

        name = name.strip()

        if name in values:
            continue

        values[name] = value.strip().strip('"').strip("'")

    return values


def port_is_open(port: int, host: str = "127.0.0.1") -> bool:
    """Whether something is listening on a port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.5)

        try:
            return sock.connect_ex((host, port)) == 0
        except OSError:
            return False


def the_backend_port() -> int:
    """
    The port the backend of the hub listens on.

    It is read from backend/.env, because a machine where the port is already
    taken uses another one.
    """
    value = read_env(BACKEND_ENV).get("PORT", "").strip()

    try:
        port = int(value)
    except ValueError:
        return 8000

    return port if 1 <= port <= 65535 else 8000


def the_backend_answers(url: str = "") -> bool:
    """Whether the backend of the hub answers."""
    if not url:
        url = f"http://127.0.0.1:{the_backend_port()}/health"

    try:
        with urllib.request.urlopen(url, timeout=2.5) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def the_last_words_of_the_backend(lines: int = 12) -> str:
    """
    The end of what the backend said the last time it ran.

    The start scripts keep this record, and it is the only place the real reason
    of a failure is written down.
    """
    if not BACKEND_LOG.exists():
        return ""

    try:
        text = BACKEND_LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    said = [line for line in text.splitlines() if line.strip()]

    if not said:
        return ""

    return "\n".join(said[-lines:])


def the_python_of(folder: Path) -> Path | None:
    """The python of an environment, or nothing when the environment is not there."""
    for name in (Path("bin") / "python", Path("Scripts") / "python.exe"):
        candidate = folder / name

        if candidate.exists():
            return candidate

    return None


def the_backend_can_import_its_libraries() -> tuple[bool, str]:
    """
    Whether the backend's own environment can import SQLAlchemy.

    A machine with an application control policy can refuse a compiled file of a
    library, and the library then cannot be imported at all. That stops the backend
    before it has said anything, so it is worth looking for.
    """
    python = the_python_of(ROOT / "backend" / ".venv")

    if python is None:
        return True, ""

    result = subprocess.run(
        [str(python), "-c", "import sqlalchemy"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return True, ""

    said = [line for line in result.stderr.splitlines() if line.strip()]

    return False, "\n".join(said[-6:])


class Report:
    """What was found, and what to do about it."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, str, str]] = []
        self.problems = 0

    def add(self, state: str, what: str, how: str = "") -> None:
        self.lines.append((state, what, how))

        if state != OK:
            self.problems += 1

    def print(self) -> None:
        mark = {OK: "ok     ", WRONG: "PROBLEM"}

        for state, what, how in self.lines:
            print(f"  [{mark.get(state, state)}] {what}")

            if how:
                for line in how.splitlines():
                    print(f"            {line}")

        print("")

        if self.problems:
            print(
                f"{self.problems} thing(s) to sort out. "
                "The sign-in will not go through until they are."
            )
        else:
            print("Everything is in place. The sign-in should work.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that the platform is set up and running.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="only check the settings and the accounts, not the running services",
    )
    args = parser.parse_args(argv)

    report = Report()

    print("")
    print("The Executive Intelligence Hub")
    print("")

    # ------------------------------------------------------------ the files
    backend = read_env(BACKEND_ENV)
    bench = read_env(BENCH_ENV)

    if not backend:
        report.add(
            WRONG,
            "backend/.env is missing",
            "Run ./setup.sh (or .\\setup.ps1 on Windows) to write it.",
        )
    else:
        report.add(OK, "backend/.env is there")

    if not bench:
        report.add(
            WRONG,
            "benchmarking/.env is missing",
            "Run ./setup.sh (or .\\setup.ps1 on Windows) to write it.",
        )
    else:
        report.add(OK, "benchmarking/.env is there")

    sentinel = read_env(SENTINEL_ENV)

    if not sentinel:
        report.add(
            WRONG,
            "sentinel/.env is missing",
            "Run ./setup.sh (or .\\setup.ps1 on Windows) to write it.",
        )
    else:
        report.add(OK, "sentinel/.env is there")

    if backend and not backend.get("JWT_SECRET_KEY", "").strip():
        report.add(
            WRONG,
            "the backend has no JWT_SECRET_KEY",
            "It will not start without one. Run ./setup.sh again.",
        )

    shared_backend = backend.get("KPI_HANDOFF_SECRET", "").strip()
    shared_bench = bench.get("HANDOFF_SECRET", "").strip()

    if backend and bench:
        if shared_backend and shared_bench and shared_backend == shared_bench:
            report.add(OK, "the two servers share the same secret")
        else:
            report.add(
                WRONG,
                "the two servers do not share the same secret",
                "Run ./setup.sh again, or put the same value in KPI_HANDOFF_SECRET "
                "(backend/.env) and HANDOFF_SECRET (benchmarking/.env).",
            )

    shared_sentinel = backend.get("SENTINEL_HANDOFF_SECRET", "").strip()
    shared_summarizer = sentinel.get("HANDOFF_SECRET", "").strip()

    if backend and sentinel:
        if shared_sentinel and shared_summarizer and shared_sentinel == shared_summarizer:
            report.add(OK, "the hub and the Data Summarizer share the same secret")
        else:
            report.add(
                WRONG,
                "the hub and the Data Summarizer do not share the same secret",
                "Run ./setup.sh again, or put the same value in SENTINEL_HANDOFF_SECRET "
                "(backend/.env) and HANDOFF_SECRET (sentinel/.env).",
            )

    # ---------------------------------------------------------- the accounts
    if BACKEND_DB.exists():
        try:
            connection = sqlite3.connect(BACKEND_DB)

            accounts = connection.execute(
                "select count(*) from users"
            ).fetchone()[0]

            connection.close()
        except sqlite3.Error:
            accounts = 0

        if accounts:
            report.add(OK, f"the database holds {accounts} accounts")
        else:
            report.add(
                WRONG,
                "the database holds no accounts",
                "Run: cd backend && uv run python seed_users.py",
            )
    else:
        report.add(
            WRONG,
            "the news database does not exist yet",
            "Run: cd backend && uv run python seed_users.py",
        )

    # ------------------------------------------------------- the environments
    for name, path in (
        ("the backend", ROOT / "backend" / ".venv"),
        ("Peer Benchmarking", ROOT / "benchmarking" / ".venv"),
        ("the Data Summarizer", ROOT / "sentinel" / ".venv"),
    ):
        if path.exists():
            report.add(OK, f"the environment of {name} is there")
        else:
            report.add(
                WRONG,
                f"the environment of {name} is missing",
                "Run ./setup.sh (or .\\setup.ps1 on Windows).",
            )

    for name, path in (
        ("the landing page", ROOT / "landing" / "node_modules"),
        ("the news application", ROOT / "frontend" / "node_modules"),
    ):
        if path.exists():
            report.add(OK, f"the libraries of {name} are there")
        else:
            report.add(
                WRONG,
                f"the libraries of {name} are missing",
                "Run: npm install in that folder.",
            )

    # ------------------------------------------------------ the running services
    if not args.quick:
        can_import, said = the_backend_can_import_its_libraries()

        if can_import:
            report.add(OK, "the backend can import its libraries")
        else:
            report.add(
                WRONG,
                "the backend cannot import SQLAlchemy",
                "The machine is refusing a compiled file of the library. This is what "
                "it says:\n"
                + said
                + "\nStart the backend and it will set the file aside and use the "
                "plain Python part instead: cd backend && .venv/bin/python -m uvicorn "
                f"app.main:app --port {the_backend_port()}",
            )

        port = the_backend_port()

        if the_backend_answers():
            report.add(OK, f"the backend of the hub is answering on port {port}")
        elif port_is_open(port):
            report.add(
                WRONG,
                f"something else is on port {port}, so the backend cannot start",
                "To see what it is:\n"
                f"    sudo ss -tlnp | grep :{port}\n"
                f"    sudo lsof -i :{port}\n"
                "Stop it, or give the backend another port in backend/.env (PORT=...)\n"
                "and run 'python scripts/make_env.py' again.",
            )
        else:
            said = the_last_words_of_the_backend()

            how = (
                f"Start it: cd backend && uv run python -m uvicorn app.main:app --port {port}"
            )

            if said:
                how += "\nThis is what it said the last time it ran:\n" + said

            report.add(WRONG, "the backend of the hub is not running", how)

        for port, what, folder in (
            (5174, "the landing page", "landing"),
            (5173, "the news application", "frontend"),
            (8077, "Peer Benchmarking", "benchmarking"),
            (8090, "the Data Summarizer", "sentinel"),
        ):
            if port_is_open(port):
                report.add(OK, f"{what} is listening on port {port}")
            else:
                report.add(
                    WRONG,
                    f"{what} is not running on port {port}",
                    "Start it: %s"
                    % {
                        "landing": "cd landing && npm run dev",
                        "frontend": "cd frontend && npm run dev",
                        "benchmarking": "cd benchmarking && .venv/bin/python -m kpibench.main",
                        "sentinel": (
                            "cd sentinel/backend && ../.venv/bin/python -m uvicorn "
                            "app.main:app --host 127.0.0.1 --port 8090"
                        ),
                    }.get(folder, "npm run dev"),
                )

    report.print()

    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
