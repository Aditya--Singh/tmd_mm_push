"""Edit XLSX cells in place (spec section 5.3).

Only the edited cells' values change; their style, number format and everything else in the
workbook that openpyxl keeps are left as they were. Formula cells are never edited.

openpyxl drops charts, images and shapes when it saves, so `has_drawings` lets the caller
warn before such a download and offer a CSV instead.
"""

import io
import zipfile

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell


class CellNotEditable(ValueError):
    """The edit targets a formula cell, a missing sheet or a bad cell reference."""


def has_drawings(content: bytes) -> bool:
    """True if the workbook has charts, images or shapes that openpyxl would drop."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return any(
            name.startswith(("xl/drawings/", "xl/charts/", "xl/media/"))
            for name in zf.namelist()
        )


def apply_cell_edits(content: bytes, edits: dict[tuple[str, str], str]) -> bytes:
    """Set {(sheet name, cell reference such as "B4"): new text} and return the new file.

    Raises CellNotEditable, without saving anything, if any edit targets a formula cell,
    an unknown sheet or an invalid reference.
    """
    wb = load_workbook(io.BytesIO(content))
    targets = []
    for (sheet, ref), value in edits.items():
        if sheet not in wb.sheetnames:
            raise CellNotEditable(f"There is no sheet named {sheet!r}.")
        try:
            cell = wb[sheet][ref]
        except (ValueError, KeyError) as exc:
            raise CellNotEditable(f"{ref!r} is not a cell reference.") from exc
        if not hasattr(cell, "coordinate") or isinstance(cell, tuple):
            raise CellNotEditable(f"{ref!r} is not a single cell.")
        if isinstance(cell, MergedCell):
            raise CellNotEditable(
                f"Cell {sheet}!{ref} is inside a merged range; edit its first cell."
            )
        if cell.data_type == "f":
            raise CellNotEditable(
                f"Cell {sheet}!{ref} holds a formula and is not edited."
            )
        targets.append((cell, value))
    for cell, value in targets:
        cell.value = value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
