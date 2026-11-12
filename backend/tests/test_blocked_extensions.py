"""
Tests for the repair of libraries whose compiled parts the machine refuses.

A machine with an application control policy can refuse to load a compiled file of a
library. The library then cannot be imported at all, and the backend stops before it
has said anything. These tests check that the repair finds such a file, sets it aside,
and leaves the library working on its plain Python part.
"""

import importlib.util
import importlib.machinery
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_blocked_extensions():
    """The repair, loaded from the backend of the repository."""

    spec = importlib.util.spec_from_file_location(
        "blocked_extensions", ROOT / "backend" / "app" / "blocked_extensions.py"
    )

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    return module


@pytest.fixture()
def repair():
    """The repair, loaded on its own."""

    return load_blocked_extensions()


def test_only_files_with_a_plain_python_version_are_touched(repair, tmp_path):
    package = tmp_path / "library"
    package.mkdir()

    # A compiled file with a plain Python version beside it.
    (package / "_part.cp312-win_amd64.pyd").write_bytes(b"")
    (package / "_part.py").write_text("value = 1\n", encoding="utf-8")

    # A compiled file that is the only copy of its part.
    (package / "_only.cp312-win_amd64.pyd").write_bytes(b"")

    found = repair.compiled_files(package)

    assert [path.name for path in found] == ["_part.cp312-win_amd64.pyd"]


def test_a_file_that_is_set_aside_cannot_be_imported_any_more(repair, tmp_path):
    package = tmp_path / "library"
    package.mkdir()

    compiled = package / "_part.cp312-win_amd64.pyd"
    compiled.write_bytes(b"")

    moved = repair.set_aside(compiled)

    assert not compiled.exists()
    assert moved.exists()
    assert moved.name.endswith(".blocked")


def test_the_name_a_compiled_file_is_imported_by(repair, tmp_path):
    package = tmp_path / "library"
    (package / "inner").mkdir(parents=True)

    path = package / "inner" / "_part.cp312-win_amd64.pyd"

    assert repair.module_name(package, path) == "library.inner._part"


def test_a_library_whose_compiled_part_is_refused_is_set_aside_and_works(
    tmp_path, monkeypatch
):
    """
    The whole repair, on a library that cannot be imported.

    The compiled file here is not a real one, so loading it fails the way a machine
    with an application control policy fails. The plain Python version beside it has
    to take over.
    """
    # The repair looks for the library itself, and its own subprocesses have to find
    # it as well.
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    library = tmp_path / "blockedlib"
    library.mkdir()

    # The plain Python version, which is what has to be used afterwards.
    (library / "_part.py").write_text("value = 'the plain python part'\n", encoding="utf-8")

    # A compiled file that cannot be loaded, standing in for a refused one. It is
    # imported first, the way SQLAlchemy imports its compiled part, and the operating
    # system prefers a compiled file over the plain Python one beside it.
    compiled = library / f"_part{importlib.machinery.EXTENSION_SUFFIXES[0]}"
    compiled.write_bytes(b"not a real library")

    (library / "__init__.py").write_text(
        "from . import _part\n\n\ndef value():\n    return _part.value\n",
        encoding="utf-8",
    )

    # The import has to fail first, otherwise nothing is repaired.
    environment = {**os.environ}

    refused = subprocess.run(
        [sys.executable, "-c", "import blockedlib"],
        capture_output=True,
        text=True,
        env=environment,
    )

    assert refused.returncode != 0, "the broken file should not be loadable"

    repair = load_blocked_extensions()

    set_aside = repair.repair(("blockedlib",))

    assert set_aside, "the compiled file should have been set aside"

    worked = subprocess.run(
        [sys.executable, "-c", "import blockedlib; print(blockedlib.value())"],
        capture_output=True,
        text=True,
        env=environment,
    )

    assert worked.returncode == 0, worked.stderr
    assert "the plain python part" in worked.stdout


def test_the_repair_leaves_a_library_that_works_alone(repair, tmp_path):
    library = tmp_path / "goodlib"
    library.mkdir()

    (library / "__init__.py").write_text("value = 1\n", encoding="utf-8")
    (library / f"_part{importlib.machinery.EXTENSION_SUFFIXES[0]}").write_bytes(
        b"not a real library"
    )
    (library / "_part.py").write_text("value = 2\n", encoding="utf-8")

    set_aside = repair.repair(("goodlib",))

    # The library can be imported as it is, so nothing is touched.
    assert set_aside == []
    assert (library / f"_part{importlib.machinery.EXTENSION_SUFFIXES[0]}").exists()


def test_the_backend_environment_can_import_its_libraries(repair):
    """The repair must not break the environment it is used in."""

    import sqlalchemy

    assert sqlalchemy is not None
