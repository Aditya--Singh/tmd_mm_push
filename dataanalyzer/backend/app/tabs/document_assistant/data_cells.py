"""Text cells of data files for Proofread (spec section 3.6), and writing accepted fixes
back into the file (spec sections 5.3 and 5.4).

Only text columns are checked: columns that `data_stats.column_stats` reads as text, so
amounts, numbers, dates, identifiers and codes are never touched. Each distinct value in a
column is checked once, as one paragraph; an accepted fix is written to every cell in that
column holding that value.

- XLSX: cells are edited in place with `xlsx_writer`. Formula cells are never edited.
- CSV: the delimiter, quote character, quoting style, line endings and byte-order mark are
  detected and reused. Output is UTF-8.
- JSON: values and key order are kept; indentation becomes 2 spaces.
"""

import codecs
import csv
import datetime as dt
import io
import json
from dataclasses import dataclass
from typing import Any

import pandas as pd
from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell

from .data_stats import column_stats
from .segments import PARAGRAPH_SEPARATOR, Segment, SegmentedText
from .xlsx_writer import apply_cell_edits

CSV_SHEET = "Sheet1"  # the name extraction gives the single table of a CSV or JSON file


@dataclass(frozen=True)
class Cell:
    sheet: str
    key: Any  # XLSX: "B4"; CSV: (row, column); JSON: path of keys and list indices


@dataclass
class TextCells:
    doc: SegmentedText  # one segment per distinct value per text column
    cells: list[list[Cell]]  # for each segment, every cell holding that value
    columns: list[str]  # the columns that were checked


Column = tuple[str, str, list[tuple[Cell, Any]]]  # sheet, column name, (cell, value)


# ---------------------------------------------------------------- XLSX


def _xlsx_columns(content: bytes) -> list[Column]:
    """The first non-empty row of each sheet is its header, as when extracting."""
    wb = load_workbook(io.BytesIO(content))
    columns: list[Column] = []
    for ws in wb.worksheets:
        rows = ws.iter_rows()
        header = next((r for r in rows if any(c.value is not None for c in r)), None)
        if header is None:
            continue
        found: dict[int, tuple[str, list[tuple[Cell, Any]]]] = {
            c.column: (str(c.value).strip(), [])
            for c in header
            if c.value is not None and str(c.value).strip()
        }
        for row in rows:
            for c in row:
                if c.column not in found:
                    continue
                # Formula cells and the hidden parts of merged ranges are never edited.
                editable = not isinstance(c, MergedCell) and c.data_type != "f"
                found[c.column][1].append(
                    (Cell(ws.title, c.coordinate), c.value if editable else None)
                )
        columns.extend((ws.title, name, cells) for name, cells in found.values())
    return columns


def edited_sheet_csv(content: bytes, sheet: str, changes: dict[Cell, str]) -> bytes:
    """One sheet of the workbook as CSV, with the changes applied.

    For workbooks with charts or images, which openpyxl drops when it saves (spec 5.3).
    Formulas give their last calculated values.
    """
    wb = load_workbook(io.BytesIO(content), data_only=True)
    ws = wb[sheet]
    for cell, value in changes.items():
        if cell.sheet == sheet:
            ws[cell.key].value = value
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    for row in ws.iter_rows(values_only=True):
        writer.writerow([_csv_text(v) for v in row])
    # A byte-order mark lets Excel open UTF-8 text such as "₹" correctly.
    return codecs.BOM_UTF8 + buf.getvalue().encode("utf-8")


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime) and value.time() == dt.time():
        return value.date().isoformat()
    return str(value)


# ---------------------------------------------------------------- CSV


@dataclass
class _CsvFile:
    rows: list[list[str]]
    delimiter: str
    quotechar: str
    quote_all: bool
    newline: str
    trailing_newline: bool
    bom: bool


def _read_csv(content: bytes) -> _CsvFile:
    text = content.decode("utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|")
        delimiter, quotechar = dialect.delimiter, dialect.quotechar or '"'
    except csv.Error:
        delimiter, quotechar = ",", '"'
    rows = list(
        csv.reader(
            io.StringIO(text, newline=""), delimiter=delimiter, quotechar=quotechar
        )
    )
    first_line = text.split("\n", 1)[0].rstrip("\r")
    quote_all = bool(rows and rows[0]) and first_line == delimiter.join(
        quotechar + f.replace(quotechar, quotechar * 2) + quotechar for f in rows[0]
    )
    return _CsvFile(
        rows=rows,
        delimiter=delimiter,
        quotechar=quotechar,
        quote_all=quote_all,
        newline="\r\n" if "\r\n" in text else "\n",
        trailing_newline=text.endswith(("\n", "\r")),
        bom=content.startswith(codecs.BOM_UTF8),
    )


def _write_csv(f: _CsvFile) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(
        buf,
        delimiter=f.delimiter,
        quotechar=f.quotechar,
        quoting=csv.QUOTE_ALL if f.quote_all else csv.QUOTE_MINIMAL,
        lineterminator=f.newline,
    )
    writer.writerows(f.rows)
    text = buf.getvalue()
    if not f.trailing_newline and text.endswith(f.newline):
        text = text[: -len(f.newline)]
    return (codecs.BOM_UTF8 if f.bom else b"") + text.encode("utf-8")


def _csv_columns(content: bytes) -> list[Column]:
    rows = _read_csv(content).rows
    if not rows:
        return []
    header = rows[0]
    columns: list[Column] = []
    for c, name in enumerate(header):
        cells = [
            (Cell(CSV_SHEET, (r, c)), row[c] if c < len(row) and row[c] != "" else None)
            for r, row in enumerate(rows[1:], start=1)
            if row
        ]
        columns.append((CSV_SHEET, name.strip() or f"Column {c + 1}", cells))
    return columns


# ---------------------------------------------------------------- JSON


def _records(data: Any) -> tuple[tuple, Any]:
    """The table inside the JSON, as extraction reads it, and the path to it."""
    if isinstance(data, dict) and len(data) == 1:
        ((key, only),) = data.items()
        if isinstance(only, list):
            return (key,), only
    return (), data


def _scalar(value: Any) -> Any:
    return None if isinstance(value, (dict, list)) else value


def _json_columns(content: bytes) -> list[Column]:
    prefix, table = _records(json.loads(content.decode("utf-8-sig")))
    found: dict[str, list[tuple[Cell, Any]]] = {}

    def walk(record: dict, path: tuple, name: tuple) -> None:
        for key, value in record.items():
            if isinstance(value, dict):
                walk(value, (*path, key), (*name, key))
            else:
                column = ".".join(map(str, (*name, key)))
                found.setdefault(column, []).append(
                    (Cell(CSV_SHEET, (*path, key)), _scalar(value))
                )

    if isinstance(table, list):
        for i, record in enumerate(table):
            if isinstance(record, dict):
                walk(record, (*prefix, i), ())
    elif isinstance(table, dict):
        for key, values in table.items():
            if isinstance(values, list):
                found[str(key)] = [
                    (Cell(CSV_SHEET, (key, i)), _scalar(v))
                    for i, v in enumerate(values)
                ]
    return [(CSV_SHEET, name, cells) for name, cells in found.items()]


def _write_json(content: bytes, changes: dict[Cell, str]) -> bytes:
    text = content.decode("utf-8-sig")
    data = json.loads(text)
    for cell, value in changes.items():
        target = data
        *parents, last = cell.key
        for key in parents:
            target = target[key]
        target[last] = value
    out = json.dumps(data, ensure_ascii=False, indent=2)
    if text.endswith("\n"):
        out += "\n"
    return (
        codecs.BOM_UTF8 if content.startswith(codecs.BOM_UTF8) else b""
    ) + out.encode("utf-8")


# ---------------------------------------------------------------- entry points


_READERS = {".xlsx": _xlsx_columns, ".csv": _csv_columns, ".json": _json_columns}


def text_cells(ext: str, content: bytes) -> TextCells:
    columns = _READERS[ext](content)
    several_sheets = len({sheet for sheet, _, _ in columns}) > 1
    segments: list[Segment] = []
    cells: list[list[Cell]] = []
    names: list[str] = []
    pos = 0
    for sheet, name, entries in columns:
        kind = column_stats(name, pd.Series([v for _, v in entries])).kind
        if kind != "text":
            continue
        groups: dict[str, list[Cell]] = {}
        for cell, value in entries:
            if isinstance(value, str) and value.strip():
                groups.setdefault(value, []).append(cell)
        if not groups:
            continue
        names.append(f"{sheet} › {name}" if several_sheets else name)
        for value, where in groups.items():
            if segments:
                pos += len(PARAGRAPH_SEPARATOR)
            segments.append(Segment(pos, value))
            cells.append(where)
            pos += len(value)
    text = PARAGRAPH_SEPARATOR.join(s.text for s in segments)
    return TextCells(SegmentedText(text, segments), cells, names)


def write_back(ext: str, content: bytes, changes: dict[Cell, str]) -> bytes:
    """The file with the changed cells set to their new text. Raises CellNotEditable for
    XLSX cells that cannot be edited."""
    if ext == ".xlsx":
        return apply_cell_edits(
            content, {(c.sheet, c.key): v for c, v in changes.items()}
        )
    if ext == ".csv":
        f = _read_csv(content)
        for cell, value in changes.items():
            r, c = cell.key
            f.rows[r][c] = value
        return _write_csv(f)
    if ext == ".json":
        return _write_json(content, changes)
    raise ValueError(f"Cannot write {ext} files.")
