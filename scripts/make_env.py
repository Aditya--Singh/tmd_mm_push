"""Create or update the environment files of the platform.

Servers have to agree on a secret: the backend of the hub, which signs people in, and
each application the hub opens in its workspace. Peer Benchmarking and the Data
Summarizer are two such applications, each with a secret of its own, so that one being
leaked does not open the other. This script writes those secrets into the environment
files, so that a person never has to copy them by hand.

It also points the applications at the language model on the machine. Ollama is asked
whether it is running; if it is, they are set to use it, and the model is left to be
chosen from the ones that are installed.

It is safe to run again. Existing values are kept, unless a placeholder
is still in place.
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

BACKEND_ENV = ROOT / "backend" / ".env"
BACKEND_EXAMPLE = ROOT / "backend" / ".env.example"
BENCH_ENV = ROOT / "benchmarking" / ".env"
BENCH_EXAMPLE = ROOT / "benchmarking" / ".env.example"
SENTINEL_ENV = ROOT / "sentinel" / ".env"
SENTINEL_EXAMPLE = ROOT / "sentinel" / ".env.example"
LANDING_ENV = ROOT / "landing" / ".env"
LANDING_EXAMPLE = ROOT / "landing" / ".env.example"
NEWS_ENV = ROOT / "frontend" / ".env"
NEWS_EXAMPLE = ROOT / "frontend" / ".env.example"

#: The port the backend of the hub listens on, when the settings do not say.
DEFAULT_BACKEND_PORT = "8000"

#: The value that means "not set yet" in the example files.
PLACEHOLDERS = {
    "JWT_SECRET_KEY": "change-me-generate-a-random-secret",
    "SECRET_KEY": "",
    "JWT_SECRET": "replace-with-a-long-random-string",
    "HANDOFF_SECRET": "",
    "KPI_HANDOFF_SECRET": "",
    "SENTINEL_HANDOFF_SECRET": "",
}

#: The addresses the hub is served from. The applications that are opened in its
#: workspace may be framed and driven from these and from nowhere else.
HUB_ORIGINS = "http://localhost:5174,http://127.0.0.1:5174"


def read(path: Path) -> str:
    if not path.exists():
        return ""

    return path.read_text(encoding="utf-8")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def get_value(content: str, key: str) -> str | None:
    """The value of a key in an environment file, or None when it is absent."""

    for line in content.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if "=" not in stripped:
            continue

        name, _, value = stripped.partition("=")

        if name.strip() == key:
            return value.strip().strip('"').strip("'")

    return None


def set_value(content: str, key: str, value: str) -> str:
    """Set a key in an environment file, keeping the comments around it."""

    lines = content.splitlines()

    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=)(.*)$")

    for index, line in enumerate(lines):
        if pattern.match(line):
            lines[index] = f"{key}={value}"

            return "\n".join(lines) + "\n"

    # The key is not there yet: add it at the end.
    if content and not content.endswith("\n"):
        content += "\n"

    return f"{content}\n{key}={value}\n"


def needs_a_secret(content: str, key: str) -> bool:
    """Whether the key still holds a placeholder."""

    value = get_value(content, key)

    if value is None:
        return True

    return value == PLACEHOLDERS.get(key, value) or not value


def ollama_is_running(url: str) -> bool:
    """Whether the language model server answers."""
    try:
        with urllib.request.urlopen(
            f"{url.rstrip('/')}/api/tags", timeout=2.5
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def set_up_the_language_model(bench: str) -> tuple[str, str]:
    """
    Point Peer Benchmarking at the language model on this machine.

    A model server that is running is used, and the model is left to be chosen from the
    ones that are installed. A model server that is not running leaves the app in template
    mode, which still works.
    """
    provider = (get_value(bench, "LLM_PROVIDER") or "").strip().lower()
    url = (get_value(bench, "OLLAMA_URL") or "http://localhost:11434").strip()

    # The model to use: "auto" means the best one that is installed.
    model = (get_value(bench, "OLLAMA_MODEL") or "").strip()

    if not model:
        bench = set_value(bench, "OLLAMA_MODEL", "auto")
        model = "auto"

    running = ollama_is_running(url)

    # A provider that was chosen on purpose is left alone.
    if provider in ("ollama", "openai_compatible"):
        if provider == "ollama" and not running:
            return bench, (
                "Ollama is not running, so Peer Benchmarking writes its reports from the "
                "fixed template. Start Ollama and run this script again to use a model."
            )

        if provider == "ollama":
            return bench, (
                f"Ollama is running, so Peer Benchmarking will write its reports with it "
                f"({model})."
            )

        return bench, ""

    if running:
        bench = set_value(bench, "LLM_PROVIDER", "ollama")

        return bench, (
            f"Ollama is running, so Peer Benchmarking will write its reports with it "
            f"({model})."
        )

    bench = set_value(bench, "LLM_PROVIDER", "none")

    return bench, (
        "Ollama is not running, so Peer Benchmarking writes its reports from the fixed "
        "template. Start Ollama and run this script again to use a model."
    )


def set_up_the_summarizer(sentinel: str, ollama_running: bool) -> str:
    """
    Point the Data Summarizer at the language model on this machine.

    The model is left to be chosen from the ones that are installed, which is what
    "auto" means. The embeddings come from the same server, so that nothing has to be
    downloaded. A machine without a model server still works: the retrieval falls back
    to a plain method of its own, and the interface says so.
    """
    model = (get_value(sentinel, "LLM_MODEL") or "").strip()

    if not model or model.lower() == "gpt-oss:20b":
        # The model that was named before was the one the machine happened to have.
        # From now on the best model that is installed is used.
        sentinel = set_value(sentinel, "LLM_MODEL", "auto")
        model = "auto"

    if ollama_running:
        sentinel = set_value(sentinel, "LLM_PROVIDER", "openai_compat")
        sentinel = set_value(sentinel, "LLM_BASE_URL", "http://localhost:11434/v1")
        sentinel = set_value(sentinel, "OLLAMA_URL", "http://localhost:11434")
        sentinel = set_value(sentinel, "EMBEDDING_PROVIDER", "openai_compat")
        sentinel = set_value(sentinel, "EMBEDDING_BASE_URL", "http://localhost:11434/v1")

        if not get_value(sentinel, "EMBEDDING_MODEL"):
            sentinel = set_value(sentinel, "EMBEDDING_MODEL", "bge-m3")
    else:
        # Nothing is downloaded, so the app is ready to start at once.
        sentinel = set_value(sentinel, "EMBEDDING_PROVIDER", "hash")

    return sentinel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the environment files of the platform.",
    )
    parser.add_argument(
        "--force-secret",
        action="store_true",
        help="Replace the shared secret even when one is already set.",
    )
    args = parser.parse_args(argv)

    if not BACKEND_EXAMPLE.exists() or not BENCH_EXAMPLE.exists():
        print("The example environment files are missing.", file=sys.stderr)
        return 1

    backend = read(BACKEND_ENV) or read(BACKEND_EXAMPLE)
    bench = read(BENCH_ENV) or read(BENCH_EXAMPLE)

    # The Data Summarizer is optional: the platform works without it.
    sentinel = ""
    sentinel_example = ""

    if SENTINEL_EXAMPLE.exists():
        sentinel = read(SENTINEL_ENV) or read(SENTINEL_EXAMPLE)
        sentinel_example = read(SENTINEL_EXAMPLE)

    # The port the backend listens on. It is written into the landing page's
    # settings as well, so that the landing page keeps talking to the backend
    # when the port is changed because the old one was taken.
    port = (get_value(backend, "PORT") or "").strip() or DEFAULT_BACKEND_PORT

    if not get_value(backend, "PORT"):
        backend = set_value(backend, "PORT", port)

    # The backend's own signing key.
    if needs_a_secret(backend, "JWT_SECRET_KEY"):
        backend = set_value(
            backend, "JWT_SECRET_KEY", secrets.token_urlsafe(48)
        )
        print("Gave the backend a new JWT_SECRET_KEY.")

    # The benchmarking app's own signing key.
    if needs_a_secret(bench, "SECRET_KEY"):
        bench = set_value(bench, "SECRET_KEY", secrets.token_urlsafe(48))
        print("Gave Peer Benchmarking a new SECRET_KEY.")

    # The secret the two servers share.
    shared = get_value(bench, "HANDOFF_SECRET") or ""

    if args.force_secret or not shared or len(shared) < 32:
        shared = secrets.token_urlsafe(48)
        bench = set_value(bench, "HANDOFF_SECRET", shared)
        print("Gave the two servers a new shared secret.")

    backend = set_value(backend, "KPI_HANDOFF_SECRET", shared)

    # The peer benchmarking app must be allowed to be framed and driven by
    # the hub, in the places the hub is served from.
    bench = set_value(
        bench,
        "EMBED_PARENT_ORIGINS",
        "http://localhost:5174,http://127.0.0.1:5174",
    )
    bench = set_value(
        bench,
        "FRAME_ANCESTORS",
        "'self' http://localhost:5174 http://127.0.0.1:5174",
    )

    # The hub signs people in, so the app has to accept a sign-in ticket
    # for the staff roles as well. Its own password sign-in is untouched:
    # this only says who the hub may vouch for.
    bench = set_value(bench, "HANDOFF_ALLOW_STAFF", "true")
    bench = set_value(bench, "HANDOFF_AUTO_CREATE", "true")
    bench = set_value(bench, "HANDOFF_SYNC_ROLE", "true")
    bench = set_value(bench, "DASHBOARD_URL", "http://localhost:5174/")
    bench = set_value(bench, "DASHBOARD_NAME", "Executive Intelligence Hub")

    # The language model on this machine.
    bench, message = set_up_the_language_model(bench)

    if sentinel:
        # The summarizer's own signing key.
        if needs_a_secret(sentinel, "JWT_SECRET"):
            sentinel = set_value(sentinel, "JWT_SECRET", secrets.token_urlsafe(48))
            print("Gave the Data Summarizer a new JWT_SECRET.")

        # The secret the hub and the summarizer share. It is a secret of their own,
        # so that the benchmarking secret stays a secret of its own.
        summarizer_secret = get_value(sentinel, "HANDOFF_SECRET") or ""

        if args.force_secret or not summarizer_secret or len(summarizer_secret) < 32:
            summarizer_secret = secrets.token_urlsafe(48)
            sentinel = set_value(sentinel, "HANDOFF_SECRET", summarizer_secret)
            print("Gave the hub and the Data Summarizer a new shared secret.")

        backend = set_value(backend, "SENTINEL_HANDOFF_SECRET", summarizer_secret)

        # The hub must be allowed to frame and drive the summarizer, in the places
        # the hub is served from.
        sentinel = set_value(sentinel, "EMBED_PARENT_ORIGINS", HUB_ORIGINS)
        sentinel = set_value(
            sentinel, "FRAME_ANCESTORS", f"http://localhost:5174 http://127.0.0.1:5174"
        )

        # The hub signs people in, so the summarizer keeps its own sign-in switched
        # on and its own accounts: the person who signs in at the hub is signed in
        # here as well, by a ticket that is spent once.
        sentinel = set_value(sentinel, "AUTH_ENABLED", "true")
        sentinel = set_value(sentinel, "CORS_ORIGINS", "http://localhost:5174,http://127.0.0.1:5174")

        sentinel = set_up_the_summarizer(sentinel, ollama_is_running("http://localhost:11434"))

        write(SENTINEL_ENV, sentinel)

    # The two web applications forward the API to the backend. They have to be
    # told where the backend is, or the sign-in cannot go through.
    for env_path, example_path in (
        (LANDING_ENV, LANDING_EXAMPLE),
        (NEWS_ENV, NEWS_EXAMPLE),
    ):
        web = read(env_path) or read(example_path)

        if not web:
            continue

        web = set_value(web, "VITE_API_PROXY_TARGET", f"http://127.0.0.1:{port}")

        write(env_path, web)

    write(BACKEND_ENV, backend)
    write(BENCH_ENV, bench)

    print("")
    print("Environment files ready:")
    print("  backend/.env")
    print("  benchmarking/.env")

    if sentinel:
        print("  sentinel/.env")

    if read(LANDING_ENV):
        print("  landing/.env")

    if read(NEWS_ENV):
        print("  frontend/.env")

    print("")
    print(f"The backend of the hub listens on port {port}.")

    print("")
    print("The hub and Peer Benchmarking share one secret, so one sign-in opens both.")
    print("Peer Benchmarking accepts the hub for every role: analyst,")
    print("approver, general manager and administrator.")

    if sentinel:
        print("")
        print("The hub and the Data Summarizer share a secret of their own, so one")
        print("sign-in opens the Data Summarizer as well.")

    if message:
        print("")
        print(message)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
