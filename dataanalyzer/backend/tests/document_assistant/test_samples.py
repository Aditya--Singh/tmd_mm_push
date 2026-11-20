"""Regression tests on the shared sample files in samples/ (never private/)."""

from pathlib import Path

import pandas as pd
import pytest

from app.core.uploads import ValidatedFile
from app.tabs.document_assistant.data_stats import (
    format_indian,
    format_stats,
    sheet_stats,
)
from app.tabs.document_assistant.extraction import extract

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


def load_stats(filename: str):
    path = SAMPLES / filename
    extracted = extract(ValidatedFile(filename, path.suffix, path.read_bytes()))
    sheets = [sheet_stats(s.name, s.frame) for s in extracted.sheets]
    columns = {c.name: c for sheet in sheets for c in sheet.columns}
    return sheets, columns


def test_branch_deposits_totals():
    sheets, cols = load_stats("test_branch_deposits.csv")
    assert cols["CASA Deposits"].kind == "number"
    assert format_indian(cols["CASA Deposits"].total) == "33,95,00,000"
    assert cols["Term Deposits"].kind == "number"
    assert format_indian(cols["Term Deposits"].total) == "39,65,00,000"
    text = format_stats(sheets)
    assert "total 33,95,00,000" in text
    assert "total 39,65,00,000" in text


def test_loans_totals():
    _, cols = load_stats("test_loans.xlsx")
    assert cols["Sanctioned Amount"].kind == "number"
    assert format_indian(cols["Sanctioned Amount"].total) == "1,12,50,000"
    # "(5,000)" is a negative amount, so it reduces the total.
    assert cols["Outstanding"].kind == "number"
    assert format_indian(cols["Outstanding"].total) == "97,23,750"
    assert cols["Outstanding"].minimum == -5000


def test_loans_sanction_date_range():
    sheets, cols = load_stats("test_loans.xlsx")
    c = cols["Sanction Date"]
    assert c.kind == "date"
    assert c.minimum == pd.Timestamp(2024, 4, 5)
    assert c.maximum == pd.Timestamp(2025, 3, 30)
    assert "from 05 Apr 2024 to 30 Mar 2025" in format_stats(sheets)


@pytest.mark.parametrize(
    "filename, column",
    [
        ("test_loans.xlsx", "Account No"),
        ("test_loans.xlsx", "Customer ID"),
        ("test_loans.xlsx", "PIN Code"),
        ("test_branch_deposits.csv", "Branch Code"),
        ("test_branch_deposits.csv", "Mobile"),
    ],
)
def test_identifiers_never_summed(filename, column):
    sheets, cols = load_stats(filename)
    c = cols[column]
    assert c.kind == "identifier"
    assert c.total is None and c.mean is None
    assert c.minimum is None and c.maximum is None
    line = next(
        l for l in format_stats(sheets).splitlines() if l.startswith(f"- {column} (")
    )
    assert "total" not in line and "average" not in line
