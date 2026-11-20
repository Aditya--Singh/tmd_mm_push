"""Proofread text cells of data files and write fixes back (spec sections 3.6, 5.3, 5.4)."""

import codecs
import csv
import io
import json
from pathlib import Path

from openpyxl import load_workbook

from app.tabs.document_assistant.data_cells import (
    Cell,
    edited_sheet_csv,
    text_cells,
    write_back,
)

from .test_xlsx_writer import make_workbook

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


def values(cells) -> list[str]:
    return [s.text for s in cells.doc.segments]


def fix(cells, wrong: str, right: str) -> dict[Cell, str]:
    """Changes that replace one checked value, in every cell holding it."""
    index = values(cells).index(wrong)
    return {cell: right for cell in cells.cells[index]}


# ---------------------------------------------------------------- what is checked


def test_segments_are_distinct_text_values_with_offsets():
    content = b"Branch,Remarks,Amount\nUdaipur,Pendng,100\nJaipur,Pendng,200\nUdaipur,Done,300\n"
    cells = text_cells(".csv", content)
    assert values(cells) == ["Udaipur", "Jaipur", "Pendng", "Done"]
    assert cells.columns == ["Branch", "Remarks"]
    assert cells.doc.text == "Udaipur\n\nJaipur\n\nPendng\n\nDone"
    for seg in cells.doc.segments:
        assert cells.doc.text[seg.start : seg.end] == seg.text
    # "Pendng" is in two rows; one fix covers both.
    assert cells.cells[2] == [Cell("Sheet1", (1, 1)), Cell("Sheet1", (2, 1))]


def test_amounts_dates_and_codes_are_not_checked():
    content = (SAMPLES / "test_loans.xlsx").read_bytes()
    cells = text_cells(".xlsx", content)
    # Not "Sanctioned Amount" or "Outstanding" (numbers typed as text), "Sanction Date"
    # (dates typed as text), "Account No", "Customer ID" or "PIN Code".
    assert cells.columns == ["Borrower Name", "Branch", "Loan Type"]
    assert "Udaipur" in values(cells)
    assert not any(v.startswith("₹") for v in values(cells))


def test_sample_csv_checks_only_branch_and_zone():
    cells = text_cells(".csv", (SAMPLES / "test_branch_deposits.csv").read_bytes())
    assert cells.columns == ["Branch", "Zone"]


# ---------------------------------------------------------------- CSV


def test_csv_keeps_delimiter_quoting_line_endings_and_bom():
    original = (
        codecs.BOM_UTF8
        + '"Branch";"Remarks";"Amount"\r\n"Udaipur";"Pendng; urgent";"1,25,000"\r\n'
        '"Jaipur";"Done";"98,000"'.encode()
    )
    cells = text_cells(".csv", original)
    out = write_back(".csv", original, fix(cells, "Pendng; urgent", "Pending; urgent"))
    assert out == (
        codecs.BOM_UTF8
        + '"Branch";"Remarks";"Amount"\r\n"Udaipur";"Pending; urgent";"1,25,000"\r\n'
        '"Jaipur";"Done";"98,000"'.encode()
    )


def test_csv_minimal_quoting_is_kept():
    original = b'Branch,Remarks\nUdaipur,"Pendng, call back"\nJaipur,Done\n'
    cells = text_cells(".csv", original)
    out = write_back(
        ".csv", original, fix(cells, "Pendng, call back", "Pending, call back")
    )
    assert out == b'Branch,Remarks\nUdaipur,"Pending, call back"\nJaipur,Done\n'


def test_csv_fix_reaches_every_cell_with_that_value():
    original = b"Branch,Remarks\nUdiapur,a\nJaipur,b\nUdiapur,c\n"
    cells = text_cells(".csv", original)
    out = write_back(".csv", original, fix(cells, "Udiapur", "Udaipur"))
    rows = list(csv.reader(io.StringIO(out.decode())))
    assert [r[0] for r in rows] == ["Branch", "Udaipur", "Jaipur", "Udaipur"]


# ---------------------------------------------------------------- JSON


def test_json_keeps_values_and_key_order_with_two_space_indent():
    data = [
        {
            "id": "C1001",
            "name": "Ramesh",
            "address": {"city": "Udiapur", "pin": "313001"},
            "amount": 125000.5,
            "active": True,
        },
        {
            "id": "C1002",
            "name": "Sunita",
            "address": {"city": "Jaipur", "pin": "302001"},
            "amount": 98000,
            "active": False,
        },
    ]
    original = json.dumps(data).encode()
    cells = text_cells(".json", original)
    assert cells.columns == ["name", "address.city"]
    out = write_back(".json", original, fix(cells, "Udiapur", "Udaipur"))
    expected = json.loads(original)
    expected[0]["address"]["city"] = "Udaipur"
    assert out.decode() == json.dumps(expected, indent=2, ensure_ascii=False)
    assert list(json.loads(out)[0]) == ["id", "name", "address", "amount", "active"]


def test_json_wrapped_records_and_column_lists():
    wrapped = b'{"records": [{"remark": "Pendng"}, {"remark": "Done"}]}\n'
    cells = text_cells(".json", wrapped)
    out = write_back(".json", wrapped, fix(cells, "Pendng", "Pending"))
    assert json.loads(out) == {"records": [{"remark": "Pending"}, {"remark": "Done"}]}
    assert out.endswith(b"}\n")

    columns = b'{"remark": ["Pendng", "Done"], "amount": [1, 2]}'
    cells = text_cells(".json", columns)
    assert cells.columns == ["remark"]
    out = write_back(".json", columns, fix(cells, "Pendng", "Pending"))
    assert json.loads(out) == {"remark": ["Pending", "Done"], "amount": [1, 2]}


# ---------------------------------------------------------------- XLSX


def test_xlsx_skips_formulas_and_merged_parts_and_keeps_styles():
    original = make_workbook()
    cells = text_cells(".xlsx", original)
    assert cells.columns == ["Loans › Branch", "Loans › Remarks"]
    assert "=SUM(C2:C3)" not in values(cells)

    out = write_back(
        ".xlsx", original, fix(cells, "Pending verfication", "Pending verification")
    )
    before, after = load_workbook(io.BytesIO(original)), load_workbook(io.BytesIO(out))
    ws = after["Loans"]
    assert ws["B2"].value == "Pending verification"
    assert ws["B2"].font.bold and ws["B2"].fill.fgColor.rgb.endswith("F2A900")
    assert ws["C4"].value == "=SUM(C2:C3)"
    assert ws["C2"].number_format == "#,##0.00"
    for row in before["Loans"].iter_rows():
        for c in row:
            if c.coordinate != "B2":
                assert ws[c.coordinate].value == c.value


def test_edited_sheet_csv_for_workbooks_with_charts():
    original = make_workbook(chart=True)
    cells = text_cells(".xlsx", original)
    changes = fix(cells, "Pending verfication", "Pending verification")
    out = edited_sheet_csv(original, "Loans", changes)
    assert out.startswith(codecs.BOM_UTF8)
    rows = list(csv.reader(io.StringIO(out.decode("utf-8-sig"))))
    assert rows[0] == ["Branch", "Remarks", "Amount"]
    assert rows[1] == ["Udaipur", "Pending verification", "125000.5"]
