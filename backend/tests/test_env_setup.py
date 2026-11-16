"""
Tests for the setup of the environment files.

The two servers have to agree on a secret, and the benchmarking app has
to accept the hub for every role. Both are easy to break by hand, so
they are checked here.
"""

import importlib.util
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_make_env():
    """The setup script, loaded from the root of the repository."""

    spec = importlib.util.spec_from_file_location(
        "make_env", ROOT / "scripts" / "make_env.py"
    )

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    return module


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A copy of the two example files, in a folder of its own."""

    module = load_make_env()

    (tmp_path / "backend").mkdir()
    (tmp_path / "benchmarking").mkdir()

    for folder, name in (
        ("backend", "backend"),
        ("benchmarking", "benchmarking"),
    ):
        shutil.copy(
            ROOT / folder / ".env.example",
            tmp_path / folder / ".env.example",
        )

    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "BACKEND_ENV", tmp_path / "backend" / ".env")
    monkeypatch.setattr(module, "BENCH_ENV", tmp_path / "benchmarking" / ".env")
    monkeypatch.setattr(
        module,
        "BACKEND_EXAMPLE",
        tmp_path / "backend" / ".env.example",
    )
    monkeypatch.setattr(
        module,
        "BENCH_EXAMPLE",
        tmp_path / "benchmarking" / ".env.example",
    )
    monkeypatch.setattr(module, "SENTINEL_ENV", tmp_path / "sentinel" / ".env")
    monkeypatch.setattr(
        module, "SENTINEL_EXAMPLE", tmp_path / "sentinel" / ".env.example"
    )
    monkeypatch.setattr(module, "LANDING_ENV", tmp_path / "landing" / ".env")
    monkeypatch.setattr(
        module, "LANDING_EXAMPLE", tmp_path / "landing" / ".env.example"
    )
    monkeypatch.setattr(module, "NEWS_ENV", tmp_path / "frontend" / ".env")
    monkeypatch.setattr(
        module, "NEWS_EXAMPLE", tmp_path / "frontend" / ".env.example"
    )

    return module


def value_of(path, key):
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if stripped.startswith(f"{key}="):
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")

    return None


def test_the_two_servers_are_given_the_same_secret(workspace, tmp_path, capsys):
    workspace.main([])

    backend = tmp_path / "backend" / ".env"
    bench = tmp_path / "benchmarking" / ".env"

    shared = value_of(backend, "KPI_HANDOFF_SECRET")

    assert shared
    assert len(shared) >= 32
    assert shared == value_of(bench, "HANDOFF_SECRET")


def test_both_servers_are_given_a_signing_key(workspace, tmp_path):
    workspace.main([])

    assert value_of(tmp_path / "backend" / ".env", "JWT_SECRET_KEY")
    assert value_of(tmp_path / "benchmarking" / ".env", "SECRET_KEY")


def test_the_hub_may_vouch_for_every_role(workspace, tmp_path):
    workspace.main([])

    bench = tmp_path / "benchmarking" / ".env"

    # Without this the benchmarking app refuses analysts, approvers and
    # administrators, and only the read-only view can be reached.
    assert value_of(bench, "HANDOFF_ALLOW_STAFF") == "true"
    assert value_of(bench, "HANDOFF_SYNC_ROLE") == "true"
    assert value_of(bench, "HANDOFF_AUTO_CREATE") == "true"


def test_the_hub_may_frame_and_drive_the_benchmarking_app(workspace, tmp_path):
    workspace.main([])

    bench = tmp_path / "benchmarking" / ".env"

    parents = value_of(bench, "EMBED_PARENT_ORIGINS")

    assert "http://localhost:5174" in parents
    assert "http://127.0.0.1:5174" in parents

    ancestors = value_of(bench, "FRAME_ANCESTORS")

    assert "http://localhost:5174" in ancestors
    assert "http://127.0.0.1:5174" in ancestors


def test_the_web_applications_are_told_where_the_backend_is(workspace, tmp_path):
    """
    Both web applications forward the API to the backend.

    Without this, a sign-in cannot go through, and the reason is not obvious.
    """
    for folder in ("landing", "frontend"):
        example = tmp_path / folder / ".env.example"
        example.parent.mkdir(parents=True, exist_ok=True)
        example.write_text(
            "VITE_API_PROXY_TARGET=http://127.0.0.1:8000\n", encoding="utf-8"
        )

    workspace.main([])

    for folder in ("landing", "frontend"):
        target = value_of(tmp_path / folder / ".env", "VITE_API_PROXY_TARGET")

        assert target == "http://127.0.0.1:8000", folder


def test_the_port_of_the_backend_is_kept_in_step(workspace, tmp_path):
    """
    A machine where port 8000 is taken uses another port.

    The web applications have to be told, or they keep talking to a port that
    is not the backend.
    """
    (tmp_path / "backend" / ".env").write_text("PORT=8010\n", encoding="utf-8")

    for folder in ("landing", "frontend"):
        example = tmp_path / folder / ".env.example"
        example.parent.mkdir(parents=True, exist_ok=True)
        example.write_text(
            "VITE_API_PROXY_TARGET=http://127.0.0.1:8000\n", encoding="utf-8"
        )

    workspace.main([])

    for folder in ("landing", "frontend"):
        target = value_of(tmp_path / folder / ".env", "VITE_API_PROXY_TARGET")

        assert target == "http://127.0.0.1:8010", folder


def test_running_the_setup_again_keeps_the_secret(workspace, tmp_path):
    workspace.main([])

    backend = tmp_path / "backend" / ".env"

    first = value_of(backend, "KPI_HANDOFF_SECRET")

    workspace.main([])

    assert value_of(backend, "KPI_HANDOFF_SECRET") == first


def test_an_existing_secret_is_kept(workspace, tmp_path):
    bench = tmp_path / "benchmarking" / ".env"

    existing = "an-existing-secret-of-more-than-thirty-two-characters"

    bench.write_text(
        f"SECRET_KEY=already-set\nHANDOFF_SECRET={existing}\n",
        encoding="utf-8",
    )

    workspace.main([])

    assert value_of(bench, "HANDOFF_SECRET") == existing
    assert (
        value_of(tmp_path / "backend" / ".env", "KPI_HANDOFF_SECRET")
        == existing
    )


def test_a_port_that_is_taken_is_moved(workspace, tmp_path):
    """
    A machine where the port is taken needs another one.

    The port that is asked for is kept when it is free.
    """
    module = workspace

    taken = 8000

    def fake_port_is_free(port):
        return port != taken

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(module, "port_is_free", fake_port_is_free)
    # Nothing of ours is answering on the port: something else has it.
    monkeypatch.setattr(module, "our_own_service_answers", lambda port, path: False)

    try:
        ports, notes = module.plan_the_ports("", "", "")
    finally:
        monkeypatch.undo()

    assert ports["backend"] != taken
    assert ports["backend"] in range(taken + 1, taken + 100)
    assert notes, "the move was not reported"


def test_a_free_port_is_kept(workspace):
    """The port that is asked for is used when it is free."""
    module = workspace

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(module, "port_is_free", lambda port: True)

    try:
        ports, notes = module.plan_the_ports("PORT=8010\n", "PORT=8077\n", "")
    finally:
        monkeypatch.undo()

    assert ports["backend"] == 8010
    assert ports["benchmarking"] == 8077
    assert notes == []


def test_our_own_service_keeps_its_port(workspace):
    """
    A port that one of our own services is using is left alone.

    Otherwise the setup would move the port every time it is run while the
    platform is up.
    """
    module = workspace

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(module, "port_is_free", lambda port: False)
    monkeypatch.setattr(module, "our_own_service_answers", lambda port, path: True)

    try:
        ports, notes = module.plan_the_ports("PORT=8000\n", "", "")
    finally:
        monkeypatch.undo()

    assert ports["backend"] == 8000
    assert notes == []


def test_the_model_of_this_machine_is_named(workspace, tmp_path):
    """
    The settings name the model that is really installed.

    Otherwise the application would look for a model that is not there.
    """
    module = workspace

    # A model server with a few models on it.
    class FakeResponse:
        status = 200

        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    body = (
        b'{"models": [{"name": "llama3.3:70b"}, {"name": "qwen3:32b"}, '
        b'{"name": "nomic-embed-text"}]}'
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        module.urllib.request, "urlopen", lambda *a, **k: FakeResponse(body)
    )

    try:
        installed = module.ollama_models("http://localhost:11434")
    finally:
        monkeypatch.undo()

    assert installed == ["llama3.3:70b", "qwen3:32b", "nomic-embed-text"]

    # The newest family that is installed wins, and a model for embeddings is
    # never used to write.
    assert module.the_model_to_use(installed) == "qwen3:32b"

    # Without a model server, nothing is named and "auto" is used.
    assert module.the_model_to_use([]) == "auto"


def test_the_model_is_written_into_the_settings(workspace, tmp_path):
    """The model that was found is written into the settings files."""
    module = workspace

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(module, "ollama_models", lambda url: ["qwen3:32b"])

    try:
        workspace.main([])
    finally:
        monkeypatch.undo()

    bench = (tmp_path / "benchmarking" / ".env").read_text(encoding="utf-8")
    backend = (tmp_path / "backend" / ".env").read_text(encoding="utf-8")

    assert "OLLAMA_MODEL=qwen3:32b" in bench
    assert "OLLAMA_MODEL=qwen3:32b" in backend
