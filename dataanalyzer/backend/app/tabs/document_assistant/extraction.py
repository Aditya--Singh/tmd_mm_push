"""Text and table extraction for every upload type the Document Assistant accepts.

Documents (TXT, DOCX, PDF, PPTX) become plain text. Data files (XLSX, CSV, JSON) become one
pandas DataFrame per sheet. Scanned PDFs are not supported until OCR ships (phase 7).
"""

import csv
import io
import json
import logging
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.core.uploads import ValidatedFile

MAX_DATA_ROWS = 10_000
PREVIEW_ROWS = 20
TEXT_TYPES = frozenset({".txt", ".docx", ".pdf", ".pptx"})
DATA_TYPES = frozenset({".xlsx", ".csv", ".json"})

_TRACKED_CHANGE_RE = re.compile(rb"<w:(?:ins|del)[\s>/]")

log = logging.getLogger(__name__)


class ExtractionError(ValueError):
    """A file that passed validation but cannot be used. The message is shown to users."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class DataSheet:
    name: str
    frame: pd.DataFrame


@dataclass
class Extracted:
    kind: str  # "text" or "data"
    text: str = ""
    sheets: list[DataSheet] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return count_words(self.text)

    @property
    def row_count(self) -> int:
        return sum(len(s.frame) for s in self.sheets)


def count_words(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------- documents


def _txt(content: bytes) -> str:
    text = content.decode("utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _docx(content: bytes) -> str:
    from docx import Document
    from docx.table import Table

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        body = zf.read("word/document.xml")
    if _TRACKED_CHANGE_RE.search(body):
        raise ExtractionError(
            "This document contains tracked changes. Please accept or reject them in "
            "Word, save the file, and upload it again."
        )

    doc = Document(io.BytesIO(content))
    blocks: list[str] = []
    for item in doc.iter_inner_content():
        if isinstance(item, Table):
            blocks.extend(_table_rows(item))
        elif item.text.strip():
            blocks.append(item.text)
    return "\n\n".join(blocks)


def _table_rows(table: Any) -> list[str]:
    rows = []
    for row in table.rows:
        cells, seen = [], set()
        for cell in row.cells:
            # Merged cells appear once per grid column; keep only the first.
            if id(cell._tc) in seen:
                continue
            seen.add(id(cell._tc))
            if cell.text.strip():
                cells.append(cell.text.strip())
        if cells:
            rows.append(" | ".join(cells))
    return rows


def _pptx(content: bytes) -> str:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(content))
    slides: list[str] = []
    for slide in prs.slides:
        parts: list[str] = []
        # Grouped shapes, charts, SmartArt and notes are out of scope in v1 (spec 5.2).
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text.strip())
            elif getattr(shape, "has_table", False) and shape.has_table:
                parts.extend(_pptx_table_rows(shape.table))
        if parts:
            slides.append("\n".join(parts))
    return "\n\n".join(slides)


def _pptx_table_rows(table: Any) -> list[str]:
    rows = []
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells if c.text.strip()]
        if cells:
            rows.append(" | ".join(cells))
    return rows


def _pdf(content: bytes) -> tuple[str, list[str]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ExtractionError(
            "This PDF is password-protected. Please upload a copy without a password."
        )
    pages, empty = [], []
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(text)
        else:
            empty.append(number)
    if not pages:
        raise ExtractionError(
            "This PDF has no text that can be read. It may be a scanned copy. "
            "Please upload a text-based PDF, or the original Word file."
        )
    notices = []
    if empty:
        noun = "page" if len(empty) == 1 else "pages"
        notices.append(
            f"Skipped {noun} {_list_numbers(empty)}: no readable text. "
            "Scanned pages are not supported yet."
        )
    return "\n\n".join(pages), notices


def _list_numbers(numbers: list[int]) -> str:
    if len(numbers) == 1:
        return str(numbers[0])
    return ", ".join(map(str, numbers[:-1])) + f" and {numbers[-1]}"


# ---------------------------------------------------------------- data files


def _csv(content: bytes) -> list[DataSheet]:
    text = content.decode("utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|")
        sep = dialect.delimiter
    except csv.Error:
        sep = ","
    # Read every cell as text so codes such as "007" keep their leading zeros.
    frame = pd.read_csv(io.StringIO(text), sep=sep, dtype=str)
    return [DataSheet("Sheet1", frame)]


def _xlsx(content: bytes) -> list[DataSheet]:
    sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, engine="openpyxl")
    return [DataSheet(str(name), frame) for name, frame in sheets.items()]


def _json(content: bytes) -> list[DataSheet]:
    data = json.loads(content.decode("utf-8-sig"))
    # Accept {"records": [...]} style wrappers with a single list inside.
    if isinstance(data, dict) and len(data) == 1:
        (only,) = data.values()
        if isinstance(only, list):
            data = only
    if isinstance(data, list) and data and all(isinstance(r, dict) for r in data):
        if len(data) > MAX_DATA_ROWS:
            raise _too_many_rows(len(data))
        frame = pd.json_normalize(data)
    elif (
        isinstance(data, dict)
        and data
        and all(isinstance(v, list) for v in data.values())
        and len({len(v) for v in data.values()}) == 1
    ):
        frame = pd.DataFrame(data)
    else:
        raise ExtractionError(
            "This JSON file is not a table. It must be a list of records, for example "
            '[{"name": "...", "amount": 100}, ...].'
        )
    return [DataSheet("Sheet1", frame)]


def _too_many_rows(rows: int) -> ExtractionError:
    return ExtractionError(
        f"This file has {rows:,} rows. The limit is {MAX_DATA_ROWS:,} rows. "
        "Please split it into smaller files.",
        status_code=413,
    )


# ---------------------------------------------------------------- entry points


def extract(file: ValidatedFile) -> Extracted:
    """Extract text or tables. Raises ExtractionError with a user-facing message."""
    try:
        result = _extract(file)
    except ExtractionError:
        raise
    except Exception as exc:  # parser libraries raise many unrelated exception types
        log.info("Could not read %s upload: %r", file.ext, exc)
        raise ExtractionError(
            "This file could not be read. It may be damaged or in an unusual format."
        ) from exc

    if result.kind == "text" and not result.text.strip():
        raise ExtractionError("This file contains no text.")
    if result.kind == "data":
        if result.row_count > MAX_DATA_ROWS:
            raise _too_many_rows(result.row_count)
        if result.row_count == 0:
            raise ExtractionError("This file contains no data rows.")
    return result


def _extract(file: ValidatedFile) -> Extracted:
    ext, content = file.ext, file.content
    if ext == ".txt":
        return Extracted("text", text=_txt(content))
    if ext == ".docx":
        return Extracted("text", text=_docx(content))
    if ext == ".pptx":
        return Extracted("text", text=_pptx(content))
    if ext == ".pdf":
        text, notices = _pdf(content)
        return Extracted("text", text=text, notices=notices)
    if ext == ".csv":
        return Extracted("data", sheets=_csv(content))
    if ext == ".xlsx":
        return Extracted("data", sheets=_xlsx(content))
    if ext == ".json":
        return Extracted("data", sheets=_json(content))
    raise ExtractionError(f"Files of type {ext} are not supported.", status_code=415)


def _json_safe(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalars
        value = value.item()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def sheet_preview(sheet: DataSheet, rows: int = PREVIEW_ROWS) -> dict[str, Any]:
    head = sheet.frame.head(rows)
    return {
        "name": sheet.name,
        "columns": [str(c) for c in sheet.frame.columns],
        "row_count": len(sheet.frame),
        "rows": [[_json_safe(v) for v in row] for row in head.itertuples(index=False)],
    }
