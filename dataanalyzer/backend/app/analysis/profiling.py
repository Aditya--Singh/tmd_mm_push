"""Reading a document, and describing what is in it.

Excel workbooks and CSV files are read into a table. The table is described: what the
columns are called, what they hold, how much is missing, and what the numbers look like.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

#: The kinds of column this app tells apart.
KIND_NUMBER = "number"
KIND_TEXT = "text"
KIND_DATE = "date"
KIND_BOOLEAN = "boolean"
KIND_EMPTY = "empty"

#: The suffixes of a file this app can read.
READABLE = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls")


class DocumentError(ValueError):
    """The document could not be read."""


def is_readable(filename: str) -> bool:
    return Path(str(filename or "")).suffix.lower() in READABLE


def read_document(path: Path, filename: str) -> tuple[pd.DataFrame, list[str]]:
    """
    Read a document into a table.

    An Excel workbook may hold several sheets. The first one is used, and the names of the
    others are returned, so that the person may be told what else is in the file.
    """
    suffix = Path(filename or path).suffix.lower()

    try:
        if suffix in (".xlsx", ".xlsm", ".xls"):
            sheets = pd.read_excel(path, sheet_name=None)

            if not sheets:
                raise DocumentError("The workbook holds no sheet.")

            first = list(sheets)[0]

            return sheets[first], list(sheets)
        if suffix == ".tsv":
            return pd.read_csv(path, sep="\t"), []
        if suffix == ".txt":
            return pd.read_csv(path, sep=r"\s+"), []
        if suffix == ".csv":
            return pd.read_csv(path), []
    except DocumentError:
        raise
    except ImportError as exc:
        raise DocumentError(
            "This kind of file cannot be read yet. Excel workbooks need the openpyxl library."
        ) from exc
    except Exception as exc:
        raise DocumentError(f"The document could not be read: {exc}") from exc

    raise DocumentError(
        "This kind of file is not read yet. Share an Excel workbook or a CSV file."
    )


def _kind_of(series: pd.Series) -> str:
    if len(series) == 0:
        return KIND_EMPTY

    if pd.api.types.is_bool_dtype(series):
        return KIND_BOOLEAN
    if pd.api.types.is_datetime64_any_dtype(series):
        return KIND_DATE
    if pd.api.types.is_numeric_dtype(series):
        return KIND_NUMBER

    return KIND_TEXT


def _clean(value) -> object:
    """A value that can be written as JSON."""
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()

    if hasattr(value, "item"):
        try:
            value = value.item()
        except (AttributeError, ValueError):
            pass

    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None

    if isinstance(value, (int, str, bool)):
        return value

    return str(value)


def profile_of(frame: pd.DataFrame, preview_rows: int = 50) -> dict:
    """What the table holds."""
    total = int(len(frame))
    columns = []

    for name in frame.columns:
        series = frame[name]

        missing = int(series.isna().sum())
        kind = _kind_of(series)

        entry: dict[str, object] = {
            "name": str(name),
            "kind": kind,
            "dtype": str(series.dtype),
            "missing": missing,
            "missingPct": round(missing * 100 / total, 1) if total else 0.0,
            "unique": int(series.nunique(dropna=True)),
        }

        if kind == KIND_NUMBER:
            numbers = pd.to_numeric(series, errors="coerce").dropna()

            if len(numbers):
                entry["mean"] = round(float(numbers.mean()), 4)
                entry["median"] = round(float(numbers.median()), 4)
                entry["std"] = round(float(numbers.std() or 0), 4)
                entry["min"] = _clean(numbers.min())
                entry["max"] = _clean(numbers.max())
                entry["sum"] = round(float(numbers.sum()), 4)

        if kind in (KIND_TEXT, KIND_BOOLEAN):
            values = series.dropna().astype(str)

            if len(values):
                counts = values.value_counts().head(8)

                entry["topValues"] = [
                    {"value": str(value), "count": int(count)}
                    for value, count in counts.items()
                ]

        if kind == KIND_DATE:
            values = series.dropna()

            if len(values):
                entry["min"] = _clean(values.min())
                entry["max"] = _clean(values.max())

        columns.append(entry)

    duplicates = int(frame.duplicated().sum())

    return {
        "rows": total,
        "columns": int(len(frame.columns)),
        "duplicateRows": duplicates,
        "columnProfiles": columns,
        "correlations": correlations_of(frame),
    }


def preview_of(frame: pd.DataFrame, rows: int = 50) -> list[dict]:
    """The first rows of the table, for the person to look at."""
    head = frame.head(max(1, rows))

    return [
        {str(name): _clean(value) for name, value in row.items()}
        for row in head.to_dict(orient="records")
    ]


def correlations_of(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    """How the numeric columns move with one another."""
    numbers = frame.select_dtypes(include="number")

    if numbers.shape[1] < 2:
        return {}

    matrix = numbers.corr(numeric_only=True)

    return {
        str(left): {
            str(right): round(float(value), 4)
            for right, value in row.items()
            if value == value and right != left
        }
        for left, row in matrix.to_dict(orient="index").items()
    }
