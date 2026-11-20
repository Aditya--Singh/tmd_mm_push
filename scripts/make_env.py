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
import json
import re
import secrets
import socket
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

ANALYZER_ENV = ROOT / "dataanalyzer" / ".env"
ANALYZER_EXAMPLE = ROOT / "dataanalyzer" / ".env.example"
LANDING_ENV = ROOT / "landing" / ".env"
LANDING_EXAMPLE = ROOT / "landing" / ".env.example"
NEWS_ENV = ROOT / "frontend" / ".env"
NEWS_EXAMPLE = ROOT / "frontend" / ".env.example"

#: The port the backend of the hub listens on, when the settings do not say.
DEFAULT_BACKEND_PORT = "8000"

#: Where the SQL Genie is served, when the settings do not say. It is an
#: application of its own, so this is only a guess that the setup script
#: writes down, so that it may be changed.
DEFAULT_SQL_GENIE_URL = "http://localhost:8080/"

#: The value that means "not set yet" in the example files.
PLACEHOLDERS = {
    "JWT_SECRET_KEY": "change-me-generate-a-random-secret",
    "SECRET_KEY": "",
    "JWT_SECRET": "replace-with-a-long-random-string",
    "HANDOFF_SECRET": "",
    "KPI_HANDOFF_SECRET": "",
    "SENTINEL_HANDOFF_SECRET": "",
    "ANALYZER_HANDOFF_SECRET": "",
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


#: The families of model this platform prefers, best first. A machine usually holds
#: one or two families, and the newest one of them is usually the one that was meant.
#: This is the same order the applications use when they choose for themselves.
PREFERRED_FAMILIES: tuple[str, ...] = (
    "qwen3",
    "qwen2.5",
    "qwen2",
    "llama3.3",
    "llama3.2",
    "llama3.1",
    "llama3",
    "mistral-nemo",
    "mistral",
    "gemma3",
    "gemma2",
    "phi4",
    "command-r",
    "deepseek-r1",
)

#: Words that mark a model as one for embeddings rather than one for text.
EMBEDDING_WORDS: tuple[str, ...] = (
    "embed",
    "bge",
    "gte-",
    "e5-",
    "minilm",
    "mxbai",
)


def model_family(name: str) -> str:
    """The family of a model: `qwen3:8b` belongs to `qwen3`."""
    return str(name or "").split(":")[0].strip().lower()


def model_size_b(name: str) -> float:
    """The size of a model in billions of parameters, as far as the name says."""
    tag = str(name or "").split(":")[1] if ":" in str(name or "") else ""

    match = re.search(r"(\d+(?:\.\d+)?)\s*b\b", tag)

    if not match:
        return 0.0

    try:
        return float(match.group(1))
    except ValueError:
        return 0.0


def is_embedding_model(name: str) -> bool:
    """Whether a model is one for embeddings rather than one for writing."""
    lowered = str(name or "").lower()

    return any(word in lowered for word in EMBEDDING_WORDS)


def score_model(name: str) -> float:
    """
    How good a model is, in the order this platform prefers.

    The family comes first: the newest family that is installed is the one that
    was meant. Within a family the larger model wins.
    """
    family = model_family(name)

    rank = (
        PREFERRED_FAMILIES.index(family)
        if family in PREFERRED_FAMILIES
        else len(PREFERRED_FAMILIES)
    )

    size = min(model_size_b(name), 999.0)

    # A named tag is better than the rolling `:latest` of the same model.
    specific = 0.0 if str(name).endswith(":latest") else 5.0

    return (len(PREFERRED_FAMILIES) - rank) * 10000.0 + size * 10.0 + specific


def ollama_models(url: str) -> list[str]:
    """
    The models that are installed on the model server of this machine.

    An empty list means the server is not running, or answers in a way that cannot
    be read. Either way, nothing is written into the settings.
    """
    try:
        with urllib.request.urlopen(
            f"{url.rstrip('/')}/api/tags", timeout=5
        ) as response:
            if response.status != 200:
                return []

            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return []

    names: list[str] = []

    for model in payload.get("models", []) or []:
        name = (model.get("model") or model.get("name") or "").strip()

        if name and name not in names:
            names.append(name)

    return names


def port_is_free(port: int) -> bool:
    """Whether nothing is listening on a port yet."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False

    return True


def our_own_service_answers(port: int, path: str) -> bool:
    """
    Whether one of our own services is already answering on a port.

    A port that our own service is using is not a problem and is left alone. A port
    that something else is using - a model server, for instance - has to be moved,
    because the service could not start there.
    """
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{path}", timeout=2
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


#: Where each service says that it is well. The backend answers on /health, Peer
#: Benchmarking on /healthz, and the Data Summarizer on /api/meta.
HEALTH_PATHS = {
    "backend": "/health",
    "benchmarking": "/healthz",
    "sentinel": "/api/meta",
    "analyzer": "/api/meta",
}


def a_free_port(preferred: int, taken: set[int]) -> int:
    """
    A port to use, when the preferred one is already taken.

    The ports near the preferred one are tried first, so that the addresses a
    person has written down keep working as much as possible.
    """
    for offset in range(0, 100):
        for candidate in (preferred + offset, preferred - offset):
            if candidate in taken or candidate <= 0 or candidate > 65535:
                continue

            if port_is_free(candidate):
                return candidate

    return preferred


def plan_the_ports(
    backend: str,
    bench: str,
    sentinel: str,
    analyzer: str = "",
) -> tuple[dict[str, int], list[str]]:
    """
    The port every service of the platform should use.

    The port that is asked for is kept when it is free, or when one of our own
    services is already answering on it. Otherwise another port nearby is chosen,
    so that a machine where the usual ports are taken still starts.
    """
    notes: list[str] = []

    def ask(content: str, key: str, preferred: int, service: str) -> int:
        raw = (get_value(content, key) or "").strip()

        wanted = int(raw) if raw.isdigit() else preferred

        if port_is_free(wanted) or our_own_service_answers(
            wanted, HEALTH_PATHS.get(service, "/health")
        ):
            return wanted

        replacement = a_free_port(wanted, taken=set())

        notes.append(
            f"Port {wanted} is already taken on this machine, so {key} moved to "
            f"port {replacement}."
        )

        return replacement

    ports = {
        "backend": ask(backend, "PORT", int(DEFAULT_BACKEND_PORT), "backend"),
        "benchmarking": ask(bench, "PORT", 8077, "benchmarking"),
    }

    if sentinel:
        ports["sentinel"] = ask(sentinel, "PORT", 8090, "sentinel")

    if analyzer:
        ports["analyzer"] = ask(analyzer, "PORT", 8095, "analyzer")

    return ports, notes


def the_model_to_use(installed: list[str]) -> str:
    """
    The model that is written into the settings.

    The best model that is installed on this machine is named, so that the
    settings say plainly what will be used. The applications still fall back to
    the best model that is there when the named one is gone, so a model that is
    removed later does not stop them.
    """
    if not installed:
        return "auto"

    candidates = [
        name for name in installed if name and not is_embedding_model(name)
    ]

    if not candidates:
        return "auto"

    return max(candidates, key=score_model)


def the_embedding_model_to_use(installed: list[str]) -> str | None:
    """
    The model for embeddings that is installed on this machine.

    A model that is not there cannot be used, so the one that is there is named.
    When there is none, the caller falls back to a method of its own that needs
    nothing to be downloaded.
    """
    candidates = [
        name for name in installed if name and is_embedding_model(name)
    ]

    if not candidates:
        return None

    # The bigger one is the better one, and the family is not important here.
    return max(candidates, key=model_size_b)


def origin_of(url: str) -> str:
    """The origin of an address: scheme, host and port, without the path."""
    match = re.match(r"^(https?://[^/?#]+)", str(url or "").strip())

    return match.group(1) if match else ""


def add_origins(content: str, origins: list[str]) -> str:
    """
    Add origins to the list of allowed origins, keeping the ones already there.

    The list holds the places the hub may be served from and the places the
    services it opens may be served from. What is already written is kept, so
    that an address that was added by hand survives.
    """
    current = [
        value.strip()
        for value in (get_value(content, "VITE_ALLOWED_CHILD_ORIGINS") or "").split(",")
        if value.strip()
    ]

    for origin in origins:
        if origin and origin not in current:
            current.append(origin)

    if not current:
        return content

    return set_value(content, "VITE_ALLOWED_CHILD_ORIGINS", ",".join(current))


def set_up_the_language_model(
    bench: str, installed: list[str], model: str
) -> tuple[str, str]:
    """
    Point Peer Benchmarking at the language model on this machine.

    A model server that is running is used, and the model is the best one that is
    actually installed. A model server that is not running leaves the app in template
    mode, which still works.
    """
    provider = (get_value(bench, "LLM_PROVIDER") or "").strip().lower()
    url = (get_value(bench, "OLLAMA_URL") or "http://localhost:11434").strip()

    running = bool(installed)

    if running:
        # The model that is installed on this machine is named, so that the
        # settings say plainly what will be used.
        bench = set_value(bench, "OLLAMA_MODEL", model)

        embedding_model = the_embedding_model_to_use(installed)

        if embedding_model:
            bench = set_value(bench, "EMBED_MODEL", embedding_model)

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


def set_up_the_analyzer(analyzer: str, installed: list[str], model: str) -> str:
    """
    Point the Data Analyzer at the language model on this machine.

    The model is the best one that is installed, which is what most machines want. A
    machine without a model server still works: the tool starts, says that the model is
    not running, and the grammar check, which needs no model for its spelling, still
    runs.

    The grammar checker is optional. Its address is written so that the tool can say
    where to start it, but nothing is installed for it.
    """
    analyzer = set_value(analyzer, "OLLAMA_URL", "http://localhost:11434")

    if installed:
        analyzer = set_value(analyzer, "OLLAMA_MODEL", model)
    else:
        # No model on this machine. The setting is left empty, so that the tool says
        # which model is missing, rather than naming one that is not there.
        analyzer = set_value(analyzer, "OLLAMA_MODEL", "")

    analyzer = set_value(analyzer, "LANGUAGETOOL_URL", "http://localhost:8120")
    analyzer = set_value(analyzer, "MAX_UPLOAD_MB", "20")

    return analyzer


def set_up_the_summarizer(
    sentinel: str, installed: list[str], model: str
) -> str:
    """
    Point the Data Summarizer at the language model on this machine.

    The model is the best one that is installed, which is what "auto" means at run
    time. The embeddings come from the same server, so that nothing has to be
    downloaded. A machine without a model server still works: the retrieval falls back
    to a plain method of its own, and the interface says so.
    """
    embedding_model = the_embedding_model_to_use(installed)

    if installed:
        sentinel = set_value(sentinel, "LLM_MODEL", model)

        sentinel = set_value(sentinel, "LLM_PROVIDER", "openai_compat")
        sentinel = set_value(sentinel, "LLM_BASE_URL", "http://localhost:11434/v1")
        sentinel = set_value(sentinel, "OLLAMA_URL", "http://localhost:11434")

        if embedding_model:
            sentinel = set_value(sentinel, "EMBEDDING_PROVIDER", "openai_compat")
            sentinel = set_value(
                sentinel, "EMBEDDING_BASE_URL", "http://localhost:11434/v1"
            )
            sentinel = set_value(sentinel, "EMBEDDING_MODEL", embedding_model)
        else:
            # No model for embeddings is installed, so the retrieval falls back to
            # a plain method of its own. Nothing is downloaded, so the app is
            # ready to start at once.
            sentinel = set_value(sentinel, "EMBEDDING_PROVIDER", "hash")
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

    # The Data Analyzer is optional as well: the platform works without it.
    analyzer = ""

    if ANALYZER_EXAMPLE.exists():
        analyzer = read(ANALYZER_ENV) or read(ANALYZER_EXAMPLE)

    # The ports every service uses. A port that is taken on this machine by
    # something else - a model server, for instance - is moved, and the new port
    # is written everywhere the old one was named.
    ports, port_notes = plan_the_ports(backend, bench, sentinel, analyzer)

    for note in port_notes:
        print(note)

    port = str(ports["backend"])
    backend = set_value(backend, "PORT", port)

    bench = set_value(bench, "PORT", str(ports["benchmarking"]))
    backend = set_value(
        backend, "KPI_APP_URL", f"http://127.0.0.1:{ports['benchmarking']}"
    )

    if sentinel:
        sentinel = set_value(sentinel, "PORT", str(ports["sentinel"]))
        backend = set_value(
            backend, "SENTINEL_APP_URL", f"http://127.0.0.1:{ports['sentinel']}"
        )

    if analyzer:
        analyzer = set_value(analyzer, "PORT", str(ports["analyzer"]))
        backend = set_value(
            backend, "ANALYZER_APP_URL", f"http://127.0.0.1:{ports['analyzer']}"
        )

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

    # The language model on this machine. The models that are installed are asked
    # for, so that the settings name the model that will really be used.
    installed = ollama_models("http://localhost:11434")
    model = the_model_to_use(installed)

    bench, message = set_up_the_language_model(bench, installed, model)

    # The backend writes its news summaries with a model too, so the same model
    # is named there.
    if model != "auto":
        backend = set_value(backend, "OLLAMA_MODEL", model)

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

        sentinel = set_up_the_summarizer(sentinel, installed, model)

        write(SENTINEL_ENV, sentinel)

    if analyzer:
        # The analyzer's own signing key.
        if needs_a_secret(analyzer, "JWT_SECRET"):
            analyzer = set_value(analyzer, "JWT_SECRET", secrets.token_urlsafe(48))
            print("Gave the Data Analyzer a new JWT_SECRET.")

        # The secret the hub and the analyzer share. It is a secret of their own, so
        # that the secret of the summarizer stays a secret of its own.
        analyzer_secret = get_value(analyzer, "HANDOFF_SECRET") or ""

        if args.force_secret or not analyzer_secret or len(analyzer_secret) < 32:
            analyzer_secret = secrets.token_urlsafe(48)
            analyzer = set_value(analyzer, "HANDOFF_SECRET", analyzer_secret)
            print("Gave the hub and the Data Analyzer a new shared secret.")

        backend = set_value(backend, "ANALYZER_HANDOFF_SECRET", analyzer_secret)

        # The hub must be allowed to frame and drive the analyzer, in the places the
        # hub is served from.
        analyzer = set_value(analyzer, "EMBED_PARENT_ORIGINS", HUB_ORIGINS)
        analyzer = set_value(
            analyzer, "FRAME_ANCESTORS", "http://localhost:5174,http://127.0.0.1:5174"
        )
        analyzer = set_value(
            analyzer, "CORS_ORIGINS", "http://localhost:5174,http://127.0.0.1:5174"
        )

        # The model of this machine is named in the settings of the analyzer, so
        # that it says plainly what it will write with.
        analyzer = set_up_the_analyzer(analyzer, installed, model)

        write(ANALYZER_ENV, analyzer)

    # The two web applications forward the API to the backend. They have to be
    # told where the backend is, or the sign-in cannot go through. The landing
    # page is also told where the other services are, so that it opens them at
    # the address they really listen on.
    for env_path, example_path in (
        (LANDING_ENV, LANDING_EXAMPLE),
        (NEWS_ENV, NEWS_EXAMPLE),
    ):
        web = read(env_path) or read(example_path)

        if not web:
            continue

        web = set_value(web, "VITE_API_PROXY_TARGET", f"http://127.0.0.1:{port}")

        if env_path == LANDING_ENV:
            # The landing page opens the other services in its workspace, so it
            # has to know where they listen.
            web = set_value(
                web,
                "VITE_BENCHMARKING_APP_URL",
                f"http://localhost:{ports['benchmarking']}/",
            )

            if "sentinel" in ports:
                web = set_value(
                    web,
                    "VITE_SUMMARIZER_APP_URL",
                    f"http://localhost:{ports['sentinel']}/",
                )

            if "analyzer" in ports:
                web = set_value(
                    web,
                    "VITE_ANALYZER_APP_URL",
                    f"http://localhost:{ports['analyzer']}/",
                )

            # The SQL Genie is an application of its own, so its address is
            # written down here, so that it may be changed.
            if not get_value(web, "VITE_SQL_GENIE_APP_URL"):
                web = set_value(
                    web, "VITE_SQL_GENIE_APP_URL", DEFAULT_SQL_GENIE_URL
                )

            # The hub only accepts session messages from the origins in this
            # list, so the place every service is served from is added to it.
            # What is already written is kept.
            web = add_origins(
                web,
                [
                    origin_of(get_value(web, "VITE_NEWS_APP_URL") or ""),
                    origin_of(get_value(web, "VITE_BENCHMARKING_APP_URL") or ""),
                    origin_of(get_value(web, "VITE_SUMMARIZER_APP_URL") or ""),
                    origin_of(get_value(web, "VITE_ANALYZER_APP_URL") or ""),
                    origin_of(get_value(web, "VITE_SQL_GENIE_APP_URL") or ""),
                ],
            )

        write(env_path, web)

    write(BACKEND_ENV, backend)
    write(BENCH_ENV, bench)

    print("")
    print("Environment files ready:")
    print("  backend/.env")
    print("  benchmarking/.env")

    if sentinel:
        print("  sentinel/.env")

    if analyzer:
        print("  dataanalyzer/.env")

    if read(LANDING_ENV):
        print("  landing/.env")

    if read(NEWS_ENV):
        print("  frontend/.env")

    print("")
    print("The ports of this platform:")
    print(f"  Backend of the hub   {ports['backend']}")
    print(f"  Peer Benchmarking    {ports['benchmarking']}")

    if "sentinel" in ports:
        print(f"  Data Summarizer      {ports['sentinel']}")

    if "analyzer" in ports:
        print(f"  Data Analyzer        {ports['analyzer']}")

    print("")
    print("The hub and Peer Benchmarking share one secret, so one sign-in opens both.")
    print("Peer Benchmarking accepts the hub for every role: analyst,")
    print("approver, general manager and administrator.")

    if sentinel:
        print("")
        print("The hub and the Data Summarizer share a secret of their own, so one")
        print("sign-in opens the Data Summarizer as well.")

    if analyzer:
        print("")
        print("The hub and the Data Analyzer share a secret of their own, so one")
        print("sign-in opens the Data Analyzer as well.")

    if message:
        print("")
        print(message)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
