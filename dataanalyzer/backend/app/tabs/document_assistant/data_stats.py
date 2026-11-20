"""Computed statistics for data files, used by Summarize instead of raw rows.

Before computing anything:
- Text columns that hold numbers written the Indian way ("1,25,000", "₹ 2,50,000.00",
  "(5,000)" for negatives) are converted to numbers.
- Identifier columns (account numbers, codes, phone numbers and so on) are never summed or
  averaged; only their count and distinct count are reported. A column is an identifier if
  its name says so, or if its values look like codes: plain digits with no separators, all
  unique, and either some have a leading zero ("0123") or all have the same length of six
  or more digits. Values written with thousands separators ("4,50,00,000" or
  "450,000,000"), and columns with a money word in their name, are never treated as codes
  by their values alone.
- Date columns report their earliest and latest date.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

ID_NAME_TOKENS = frozenset(
    {"id", "no", "number", "account", "code", "pin", "phone", "mobile"}
)
# Names that mark a column as an amount or quantity, so its values are never read as codes.
# Matched against singular word forms, so "Deposits" matches "deposit".
# fmt: off
AMOUNT_NAME_TOKENS = frozenset(
    {
        "amount", "amt", "balance", "bal", "total", "value", "price", "cost", "salary",
        "income", "expense", "sum", "rate", "limit", "fee", "charge", "interest",
        "principal", "emi", "outstanding", "deposit", "advance", "loan", "withdrawal",
        "credit", "debit", "profit", "npa", "premium", "sanctioned", "disbursed",
        "qty", "quantity", "count", "rs", "inr", "rupee", "lakh", "crore",
    }
)
# fmt: on
MIN_CODE_LENGTH = 6
TOP_VALUES = 5
MAX_CATEGORIES_FOR_TOP = 50

_CURRENCY_RE = re.compile(r"₹|\bINR\b|\bRs\b\.?", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^-?\d+(?:,\d+)*(?:\.\d+)?$")
_NAME_TOKEN_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


# ---------------------------------------------------------------- number parsing


def parse_indian_number(value: Any) -> float | None:
    """Parse a number written as text, Indian or Western grouping. None if not a number.

    Accepts an optional ₹, Rs., or INR prefix or suffix, commas in any grouping, decimals,
    a leading minus sign, and accounting brackets for negatives: "(5,000)" is -5000.
    """
    if not isinstance(value, str):
        return None
    s = _CURRENCY_RE.sub("", value)
    s = s.replace(" ", "").replace(" ", "")
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
        if s.startswith("-"):
            return None
    if not _NUMBER_RE.fullmatch(s):
        return None
    number = float(s.replace(",", ""))
    return -number if negative else number


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return parse_indian_number(value)


def _convert_numeric_text(series: pd.Series) -> pd.Series | None:
    """The series as floats if every non-empty value is a number, as text or as a number.

    Spreadsheets often mix real numbers with numbers typed as text, so both are accepted.
    """
    values = series.dropna()
    values = values[values.astype(str).str.strip() != ""]
    if values.empty or not any(isinstance(v, str) for v in values):
        return None
    parsed = [_as_number(v) for v in values]
    if any(p is None for p in parsed):
        return None
    result = pd.Series(float("nan"), index=series.index, dtype="float64")
    result[values.index] = parsed
    return result


# ---------------------------------------------------------------- column kinds


def name_tokens(name: str) -> list[str]:
    """Split a column name into lower-case words: "customerID" -> ["customer", "id"]."""
    return [t.lower() for t in _NAME_TOKEN_RE.findall(str(name))]


def is_id_name(name: str) -> bool:
    return any(t in ID_NAME_TOKENS for t in name_tokens(name))


def _singular(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


def is_amount_name(name: str) -> bool:
    return any(_singular(t) in AMOUNT_NAME_TOKENS for t in name_tokens(name))


def _plain_digits(value: Any) -> str | None:
    """The value as a string of digits, or None if it has anything else (",", ".", "₹"...)."""
    if hasattr(value, "item"):  # numpy scalar
        value = value.item()
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if not value.is_integer():
            return None
        text = str(int(value))
    elif isinstance(value, str):
        text = value.strip()
    else:
        return None
    return text if text.isascii() and text.isdigit() else None


def looks_like_codes(values: pd.Series) -> bool:
    """True if the values read as codes rather than quantities.

    Plain digits only (no thousands separators, decimals, signs or currency), all unique,
    and either at least one has a leading zero or all share one length of 6+ digits.
    """
    if len(values) < 2 or not values.is_unique:
        return False
    digits = [_plain_digits(v) for v in values]
    if any(d is None for d in digits):
        return False
    if len(set(digits)) != len(digits):
        return False
    if any(len(d) > 1 and d.startswith("0") for d in digits):
        return True
    lengths = {len(d) for d in digits}
    return len(lengths) == 1 and lengths.pop() >= MIN_CODE_LENGTH


def _parse_dates(series: pd.Series) -> pd.Series | None:
    """The series as datetimes if every non-empty text value is a date (day first)."""
    values = series.dropna()
    values = values[values.astype(str).str.strip() != ""]
    if values.empty or not all(isinstance(v, str) for v in values):
        return None
    if not values.str.contains(r"\d").all():
        return None
    parsed = pd.to_datetime(values, errors="coerce", dayfirst=True, format="mixed")
    if parsed.isna().any():
        return None
    return parsed


def to_numbers(series: pd.Series) -> pd.Series:
    """A "number" column (see `column_stats`) as floats; empty cells become NaN."""
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return series.astype("float64")
    result = pd.Series(float("nan"), index=series.index, dtype="float64")
    for index, value in series.items():
        number = _as_number(value)
        if number is not None:
            result[index] = number
    return result


def to_dates(series: pd.Series) -> pd.Series:
    """A "date" column (see `column_stats`) as datetimes; empty cells become NaT."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    parsed = _parse_dates(series)
    if parsed is not None:
        result[parsed.index] = parsed
    return result


# ---------------------------------------------------------------- statistics


@dataclass
class ColumnStats:
    name: str
    kind: str  # "number", "identifier", "date", "text" or "empty"
    count: int
    missing: int
    distinct: int
    total: float | None = None
    mean: float | None = None
    minimum: Any = None
    maximum: Any = None
    top_values: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class SheetStats:
    name: str
    rows: int
    columns: list[ColumnStats]


def _non_empty(series: pd.Series) -> pd.Series:
    values = series.dropna()
    if values.dtype == object or pd.api.types.is_string_dtype(values):
        values = values[values.astype(str).str.strip() != ""]
    return values


def column_stats(name: str, series: pd.Series) -> ColumnStats:
    values = _non_empty(series)
    count, missing = len(values), len(series) - len(values)
    base = dict(
        name=str(name),
        count=count,
        missing=missing,
        distinct=int(values.astype(str).nunique()),
    )
    if count == 0:
        return ColumnStats(kind="empty", **base)

    # Identifier names win before any conversion, so "007" PIN codes are never summed.
    if is_id_name(name):
        return ColumnStats(kind="identifier", **base)

    if pd.api.types.is_datetime64_any_dtype(values):
        return ColumnStats(
            kind="date", minimum=values.min(), maximum=values.max(), **base
        )

    numeric = None
    if pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values):
        numeric = values.astype("float64")
    else:
        converted = _convert_numeric_text(values)
        if converted is not None:
            numeric = converted

    if numeric is not None:
        if not is_amount_name(name) and looks_like_codes(values):
            return ColumnStats(kind="identifier", **base)
        return ColumnStats(
            kind="number",
            total=float(numeric.sum()),
            mean=float(numeric.mean()),
            minimum=float(numeric.min()),
            maximum=float(numeric.max()),
            **base,
        )

    dates = _parse_dates(values)
    if dates is not None:
        return ColumnStats(
            kind="date", minimum=dates.min(), maximum=dates.max(), **base
        )

    stats = ColumnStats(kind="text", **base)
    if stats.distinct <= MAX_CATEGORIES_FOR_TOP:
        counts = values.astype(str).value_counts().head(TOP_VALUES)
        stats.top_values = [(str(k), int(v)) for k, v in counts.items()]
    return stats


def sheet_stats(name: str, df: pd.DataFrame) -> SheetStats:
    return SheetStats(
        name=name,
        rows=len(df),
        columns=[column_stats(col, df[col]) for col in df.columns],
    )


# ---------------------------------------------------------------- formatting


def format_indian(value: float) -> str:
    """Format a number with Indian digit grouping: 1234567.5 -> "12,34,567.50"."""
    if math.isnan(value):
        return "n/a"
    negative = value < 0
    value = abs(value)
    if value == int(value):
        whole, frac = str(int(value)), ""
    else:
        whole, frac = f"{value:.2f}".split(".")
        frac = "." + frac
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if negative else "") + whole + frac


def _format_date(value: Any) -> str:
    return pd.Timestamp(value).strftime("%d %b %Y")


def format_stats(sheets: list[SheetStats]) -> str:
    """Plain-text statistics for the model prompt. Contains no raw rows."""
    lines: list[str] = []
    for sheet in sheets:
        lines.append(f"Sheet: {sheet.name}")
        lines.append(f"Rows: {sheet.rows}; columns: {len(sheet.columns)}")
        for c in sheet.columns:
            head = f"- {c.name} ({c.kind}): {c.count} values"
            if c.missing:
                head += f", {c.missing} missing"
            if c.kind == "number":
                head += (
                    f"; total {format_indian(c.total)}, average {format_indian(c.mean)}, "
                    f"min {format_indian(c.minimum)}, max {format_indian(c.maximum)}"
                )
            elif c.kind == "identifier":
                head += f"; {c.distinct} distinct"
            elif c.kind == "date":
                head += f"; from {_format_date(c.minimum)} to {_format_date(c.maximum)}"
            elif c.kind == "text":
                head += f"; {c.distinct} distinct"
                if c.top_values:
                    tops = ", ".join(f"{v} ({n})" for v, n in c.top_values)
                    head += f"; most common: {tops}"
            lines.append(head)
        lines.append("")
    return "\n".join(lines).strip()
