"""Round-trip tests for XLSX in-place cell edits: what spec 5.3 lists as "Kept" stays."""

import io
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from app.tabs.document_assistant.xlsx_writer import (
    CellNotEditable,
    apply_cell_edits,
    has_drawings,
)

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


def make_workbook(chart: bool = False) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Loans"
    ws.append(["Branch", "Remarks", "Amount"])
    ws.append(["Udaipur", "Pending verfication", 125000.5])
    ws.append(["Jaipur", "Approved", 98000])
    ws["A4"] = "Total"
    ws["C4"] = "=SUM(C2:C3)"
    ws["B2"].font = Font(bold=True, color="A6192E")
    ws["B2"].fill = PatternFill("solid", fgColor="F2A900")
    ws["C2"].number_format = "#,##0.00"
    ws.column_dimensions["B"].width = 32
    ws.merge_cells("A6:C6")
    ws["A6"] = "Merged note"
    dv = DataValidation(type="list", formula1='"Approved,Pending"')
    ws.add_data_validation(dv)
    dv.add("B2:B3")
    ws.conditional_formatting.add(
        "C2:C3",
        CellIsRule(operator="greaterThan", formula=["100000"], font=Font(bold=True)),
    )
    wb.create_sheet("Other")["A1"] = "Untouched"
    if chart:
        c = BarChart()
        c.add_data(
            Reference(ws, min_col=3, min_row=1, max_row=3), titles_from_data=True
        )
        ws.add_chart(c, "E2")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _load(content: bytes):
    return load_workbook(io.BytesIO(content))


def test_edit_changes_value_and_keeps_style():
    edited = apply_cell_edits(
        make_workbook(), {("Loans", "B2"): "Pending verification"}
    )
    ws = _load(edited)["Loans"]
    cell = ws["B2"]
    assert cell.value == "Pending verification"
    assert cell.font.bold and cell.font.color.rgb.endswith("A6192E")
    assert cell.fill.fgColor.rgb.endswith("F2A900")


def test_everything_else_is_kept():
    original = _load(make_workbook())["Loans"]
    wb = _load(apply_cell_edits(make_workbook(), {("Loans", "B2"): "Fixed"}))
    ws = wb["Loans"]
    assert ws["C4"].value == "=SUM(C2:C3)"
    assert ws["C2"].number_format == "#,##0.00"
    assert ws["C2"].value == 125000.5
    assert ws.column_dimensions["B"].width == 32
    assert [str(r) for r in ws.merged_cells.ranges] == ["A6:C6"]
    assert len(ws.data_validations.dataValidation) == 1
    assert [str(r.sqref) for r in ws.conditional_formatting] == ["C2:C3"]
    assert wb["Other"]["A1"].value == "Untouched"
    for row in original.iter_rows():
        for cell in row:
            if cell.coordinate != "B2":
                assert ws[cell.coordinate].value == cell.value


def test_formula_cell_is_refused():
    with pytest.raises(CellNotEditable, match="formula"):
        apply_cell_edits(make_workbook(), {("Loans", "C4"): "300000"})


def test_merged_cell_other_than_first_is_refused():
    with pytest.raises(CellNotEditable, match="merged"):
        apply_cell_edits(make_workbook(), {("Loans", "B6"): "x"})
    edited = apply_cell_edits(make_workbook(), {("Loans", "A6"): "New note"})
    assert _load(edited)["Loans"]["A6"].value == "New note"


def test_bad_sheet_or_reference_is_refused():
    with pytest.raises(CellNotEditable):
        apply_cell_edits(make_workbook(), {("Missing", "A1"): "x"})
    with pytest.raises(CellNotEditable):
        apply_cell_edits(make_workbook(), {("Loans", "not a cell"): "x"})
    with pytest.raises(CellNotEditable):
        apply_cell_edits(make_workbook(), {("Loans", "A1:B2"): "x"})


def test_refused_edit_changes_nothing():
    with pytest.raises(CellNotEditable):
        apply_cell_edits(
            make_workbook(), {("Loans", "B2"): "ok", ("Loans", "C4"): "no"}
        )


def test_has_drawings_detects_charts():
    assert has_drawings(make_workbook(chart=True))
    assert not has_drawings(make_workbook())


def test_sample_xlsx_round_trip():
    original = (SAMPLES / "test_loans.xlsx").read_bytes()
    wb = _load(original)
    ws = wb[wb.sheetnames[0]]
    target = next(c for row in ws.iter_rows() for c in row if isinstance(c.value, str))
    edited = _load(
        apply_cell_edits(original, {(ws.title, target.coordinate): target.value + "!"})
    )
    after = edited[ws.title]
    assert after[target.coordinate].value == target.value + "!"
    for row in ws.iter_rows():
        for c in row:
            if c.coordinate != target.coordinate:
                assert after[c.coordinate].value == c.value
                assert after[c.coordinate].number_format == c.number_format
