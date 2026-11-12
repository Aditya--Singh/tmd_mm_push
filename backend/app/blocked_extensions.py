"""
Compiled parts of libraries, and the rules of the machine.

Some libraries are written partly in C, and those parts are shipped as compiled files that
the operating system loads. A machine with an application control policy (AppLocker, WDAC,
Smart App Control, or an antivirus that works the same way) can refuse to load such a
file, and the library then cannot be imported at all.

SQLAlchemy is one of them. From version 2.1 it imports its compiled part directly, so a
refused file stops the whole library from being imported. Every such library also ships a
version written in plain Python, which does the same work a little more slowly.

This module finds the compiled files that the machine refuses, and sets them aside, so
that the library uses its plain Python version instead. It is safe to run again: a file
that has already been set aside is left alone.

The repair happens when this module is imported, because it has to happen before
SQLAlchemy is imported anywhere else.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from loguru import logger


#: The libraries that are checked for compiled parts.
LIBRARIES = ("sqlalchemy",)

#: The name a file that was set aside is given.
SUFFIX = ".blocked"


def compiled_files(package_folder: Path) -> list[Path]:
    """
    The compiled files of a package that have a version written in plain Python beside them.

    Only those are touched. A compiled file without such a version is the only copy of
    that part, and setting it aside would break the library instead of slowing it down.
    """
    found = []

    for path in sorted(package_folder.rglob("*")):
        if path.suffix not in (".pyd", ".so"):
            continue

        # _cache_key_cy.cp312-win_amd64.pyd -> _cache_key_cy.py
        name = path.name.split(".")[0]

        if (path.parent / f"{name}.py").exists():
            found.append(path)

    return found


def module_name(package_folder: Path, path: Path) -> str:
    """The name a compiled file is imported by."""
    parts = path.relative_to(package_folder).parts

    return ".".join([package_folder.name, *parts[:-1], parts[-1].split(".")[0]])


def can_be_loaded(module: str) -> bool:
    """
    Whether a module can be loaded on this machine.

    It is tried in a separate process, because a file that the operating system refuses
    cannot be recovered from inside the process that tried to load it.
    """
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
    )

    return result.returncode == 0


def set_aside(path: Path) -> Path:
    """Move a compiled file out of the way, so the plain Python version is used."""
    moved = path.with_name(path.name + SUFFIX)

    path.replace(moved)

    return moved


def repair(libraries: tuple[str, ...] = LIBRARIES) -> list[str]:
    """
    Set aside the compiled files that the machine refuses.

    Returns the names of the files that were set aside.
    """
    set_aside_files = []

    for library in libraries:
        spec = importlib.util.find_spec(library)

        if spec is None or not spec.submodule_search_locations:
            continue

        package_folder = Path(list(spec.submodule_search_locations)[0])

        for path in compiled_files(package_folder):
            module = module_name(package_folder, path)

            if can_be_loaded(module):
                continue

            try:
                set_aside(path)
            except OSError as error:
                logger.warning(f"Could not set aside {path}: {error}")
                continue

            logger.warning(
                f"The machine would not load {module}, so the plain Python version "
                f"of it is used instead: {path.name} was set aside."
            )

            set_aside_files.append(str(path))

    return set_aside_files


def make_work(libraries: tuple[str, ...] = LIBRARIES) -> list[str]:
    """
    Make sure the libraries can be imported.

    Returns the names of the files that were set aside.
    """
    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        pass
    else:
        return []

    set_aside_files = repair(libraries)

    if not set_aside_files:
        return []

    # The plain Python versions are used now, so the library can be imported.
    import sqlalchemy  # noqa: F401

    return set_aside_files


#: The files that were set aside, for the record.
SET_ASIDE = make_work()
