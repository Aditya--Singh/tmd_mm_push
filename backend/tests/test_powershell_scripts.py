"""The scripts of Windows.

PowerShell does not tell the difference between `$python` and `$Python`. A name
that is used in two places in one script takes the place of the other, and the
one that is used by accident is the one that breaks the setup: a function that
holds the name of the interpreter of a virtual environment, and a call that
asks for the python of the machine, are the same name to PowerShell.

These tests keep that from happening again, and keep the scripts readable by
PowerShell itself.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: The scripts of the platform. The applications that came from elsewhere keep
#: their own scripts, and they are not changed here.
SCRIPTS = [ROOT / "setup.ps1", ROOT / "run.ps1"]

#: A name that is given a value in a script.
ASSIGNED = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)")
#: A name that a function takes as an argument.
TAKEN = re.compile(r"function\s+[A-Za-z0-9_-]+\s*\(([^)]*)\)", re.DOTALL)


def names_in(script: Path) -> dict[str, set[str]]:
    """Every name a script uses, written the way the script writes it."""
    text = script.read_text(encoding="utf-8")

    found: dict[str, set[str]] = {}

    for name in ASSIGNED.findall(text):
        found.setdefault(name.lower(), set()).add(name)

    for arguments in TAKEN.findall(text):
        for name in re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", arguments):
            found.setdefault(name.lower(), set()).add(name)

    return found


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_no_two_names_differ_only_in_case(script: Path):
    """
    A name that is written in two ways is one name to PowerShell.

    The setup had one: a function held `$python`, the script held `$Python`,
    and the function was asked to make an environment with an interpreter that
    did not exist yet.
    """
    collisions = [
        sorted(written) for written in names_in(script).values() if len(written) > 1
    ]

    assert collisions == [], (
        f"{script.name} uses the same name in two ways, and PowerShell will not "
        f"tell them apart: {collisions}"
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_the_interpreter_is_found_through_the_helper(script: Path):
    """
    The interpreter of a virtual environment is in a different place on each
    system, so the scripts ask for it by name instead of writing it down.
    """
    text = script.read_text(encoding="utf-8")

    assert "function The-Interpreter" in text

    # The place of the interpreter is written down in the helper and nowhere else.
    helper = text.split("function The-Interpreter", 1)[1].split("\n}", 1)[0]
    elsewhere = text.replace(helper, "")

    assert ".venv\\Scripts\\python.exe" not in elsewhere
    assert ".venv/bin/python" not in elsewhere


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_powershell_can_read_the_script(script: Path):
    """The script is read by PowerShell without a word of complaint."""
    shell = shutil.which("powershell") or shutil.which("pwsh")

    if shell is None:
        pytest.skip("PowerShell is not installed on this machine")

    command = (
        "$errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{script}', [ref]$null, [ref]$errors) | Out-Null; "
        "if ($errors) { $errors | ForEach-Object { Write-Host $_.Message }; exit 1 }"
    )

    answer = subprocess.run(
        [shell, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert answer.returncode == 0, answer.stdout + answer.stderr
