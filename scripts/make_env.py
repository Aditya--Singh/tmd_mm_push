"""Create or update the environment files of the platform.

Two servers have to agree on a secret: the backend of the hub, which
signs people in, and Peer Benchmarking, which the hub opens in its
workspace. This script writes that secret into both environment files,
so that a person never has to copy it by hand.

It is safe to run again. Existing values are kept, unless a placeholder
is still in place.
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

BACKEND_ENV = ROOT / "backend" / ".env"
BACKEND_EXAMPLE = ROOT / "backend" / ".env.example"
BENCH_ENV = ROOT / "benchmarking" / ".env"
BENCH_EXAMPLE = ROOT / "benchmarking" / ".env.example"

#: The value that means "not set yet" in the example files.
PLACEHOLDERS = {
    "JWT_SECRET_KEY": "change-me-generate-a-random-secret",
    "SECRET_KEY": "",
    "HANDOFF_SECRET": "",
    "KPI_HANDOFF_SECRET": "",
}


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the environment files of the platform.",
    )
    parser.add_argument(
        "--force-secret",
        action="store_true",
        help="Replace the shared secret even when one is already set.",
    )
    args = parser.parse_args()

    if not BACKEND_EXAMPLE.exists() or not BENCH_EXAMPLE.exists():
        print("The example environment files are missing.", file=sys.stderr)
        return 1

    backend = read(BACKEND_ENV) or read(BACKEND_EXAMPLE)
    bench = read(BENCH_ENV) or read(BENCH_EXAMPLE)

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

    write(BACKEND_ENV, backend)
    write(BENCH_ENV, bench)

    print("")
    print("Environment files ready:")
    print("  backend/.env")
    print("  benchmarking/.env")
    print("")
    print("The two servers now share one secret, so one sign-in opens both.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
