"""Operations for "Ask about data" (spec section 3.6).

The model never computes anything and no generated code is ever run. The model picks one
operation from a fixed allowlist and fills in its parameters as JSON; this module checks
every field (operation, sheet, column names, values) and runs the operation with pandas.
Every operation can first be narrowed by filter conditions.

Columns are read the way Summarize reads them (`data_stats`): numbers written as text
("4,50,00,000", "₹ 98,000.00") become numbers, day-first date text becomes dates, and
identifier columns (account numbers, codes) are never added up or averaged.

Results are tables of display strings. Amounts use Indian digit grouping (97,23,750), and
the same strings are what the model sees when it writes its answer.
"""

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .data_stats import (
    column_stats,
    format_indian,
    parse_indian_number,
    to_dates,
    to_numbers,
)
from .extraction import DataSheet

OPERATIONS = ("filter", "group_by", "sort", "top_n", "distinct", "describe")
UNSUPPORTED = "unsupported"
AGGREGATES = ("sum", "count", "mean", "min", "max")
COMPARISONS = ("=", "!=", ">", ">=", "<", "<=", "contains")
MAX_FILTERS = 5
MAX_GROUP_COLUMNS = 3
MAX_TOP_N = 100
# Rows kept in a result for the browser; the full row count is reported separately.
DISPLAY_ROWS = 100
MAX_CELL_CHARS = 200

AGGREGATE_LABEL = {
    "sum": "Total",
    "count": "Count",
    "mean": "Average",
    "min": "Lowest",
    "max": "Highest",
}
_WORDS = {
    "=": "is",
    "!=": "is not",
    ">": "is more than",
    ">=": "is at least",
    "<": "is less than",
    "<=": "is at most",
    "contains": "contains",
}
_DATE_WORDS = {
    ">": "is after",
    ">=": "is on or after",
    "<": "is before",
    "<=": "is on or before",
}
_ISO_DATE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}")

# Ollama's structured output emits keys in schema order. "filters" comes last so a model
# adapting an earlier operation for a follow-up ("and for Udaipur only?") can still add one.
# Every key is required: with optional keys, gpt-oss sometimes skips straight to the end
# ({"operation": "group_by", "filters": []}). Keys that do not apply to the chosen
# operation are ignored by `parse_operation`.
OPERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": [*OPERATIONS, UNSUPPORTED]},
        "sheet": {"type": "string"},
        "group_by": {"type": "array", "items": {"type": "string"}},
        "aggregate": {"type": "string", "enum": list(AGGREGATES)},
        "column": {"type": "string"},
        "ascending": {"type": "boolean"},
        "n": {"type": "integer"},
        "filters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "op": {"type": "string", "enum": list(COMPARISONS)},
                    "value": {"type": "string"},
                },
                "required": ["column", "op", "value"],
            },
        },
    },
    "required": [
        "operation",
        "sheet",
        "group_by",
        "aggregate",
        "column",
        "ascending",
        "n",
        "filters",
    ],
}


class InvalidOperation(ValueError):
    """The operation cannot be run. The message says what to fix, for the model."""


# ---------------------------------------------------------------- tables


@dataclass
class Table:
    """One sheet, ready for operations."""

    name: str
    original: pd.DataFrame  # as extracted, with string column names
    frame: pd.DataFrame  # numbers as floats, dates as datetimes
    kinds: dict[str, str]  # column -> "number", "identifier", "date", "text" or "empty"


def prepare(sheet: DataSheet) -> Table:
    original = sheet.frame.copy()
    original.columns = [str(c) for c in original.columns]
    frame = original.copy()
    kinds: dict[str, str] = {}
    for col in original.columns:
        kind = column_stats(col, original[col]).kind
        kinds[col] = kind
        if kind == "number":
            frame[col] = to_numbers(original[col])
        elif kind == "date":
            frame[col] = to_dates(original[col])
    return Table(sheet.name, original, frame, kinds)


def display(value: Any, kind: str) -> str:
    """One value as shown to users and to the model. Amounts get Indian digit grouping."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if kind == "number":
        return format_indian(float(value))
    if kind == "date":
        return pd.Timestamp(value).strftime("%d %b %Y")
    if hasattr(value, "item"):  # numpy scalar
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))  # an identifier read as a float, such as 100245678901.0
    return str(value)


# ---------------------------------------------------------------- operations


@dataclass(frozen=True)
class Condition:
    column: str
    op: str
    value: str


@dataclass(frozen=True)
class Operation:
    operation: str
    sheet: str
    filters: tuple[Condition, ...] = ()
    group_by: tuple[str, ...] = ()
    aggregate: str | None = None
    column: str | None = None
    ascending: bool = False
    n: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """The operation as JSON, for the browser to send back with follow-up questions."""
        data: dict[str, Any] = {"operation": self.operation, "sheet": self.sheet}
        if self.operation == "group_by":
            data["group_by"] = list(self.group_by)
            data["aggregate"] = self.aggregate
        if self.column is not None:
            data["column"] = self.column
        if self.operation in ("sort", "top_n"):
            data["ascending"] = self.ascending
        if self.n is not None:
            data["n"] = self.n
        # Last, in the same order as OPERATION_SCHEMA.
        if self.filters:
            data["filters"] = [
                {"column": c.column, "op": c.op, "value": c.value} for c in self.filters
            ]
        return data


def _sheet(tables: list[Table], name: Any) -> Table:
    if name is None or (isinstance(name, str) and not name.strip()):
        if len(tables) == 1:
            return tables[0]
        raise InvalidOperation(
            "This file has several sheets; set 'sheet' to one of: "
            + ", ".join(repr(t.name) for t in tables)
            + "."
        )
    if isinstance(name, str):
        for t in tables:
            if t.name == name or t.name.strip().casefold() == name.strip().casefold():
                return t
    raise InvalidOperation(
        f"There is no sheet named {name!r}. The sheets are: "
        + ", ".join(repr(t.name) for t in tables)
        + "."
    )


def _column(table: Table, name: Any, field_name: str = "column") -> str:
    if not isinstance(name, str) or not name.strip():
        raise InvalidOperation(f"'{field_name}' must be a column name.")
    if name in table.kinds:
        return name
    wanted = name.strip().casefold()
    for col in table.kinds:
        if col.strip().casefold() == wanted:
            return col
    raise InvalidOperation(
        f"There is no column named {name!r} in sheet {table.name!r}. The columns are: "
        + ", ".join(repr(c) for c in table.kinds)
        + "."
    )


def _optional(value: Any) -> Any:
    """Models fill unused fields with "" or null; treat both as absent."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return value


def parse_operation(data: Any, tables: list[Table]) -> Operation | None:
    """Validate the model's JSON. None means the model said the question is unsupported.

    Raises InvalidOperation for anything outside the allowlist or not in the file.
    """
    if not isinstance(data, dict):
        raise InvalidOperation("The reply must be a JSON object.")
    name = data.get("operation")
    if name == UNSUPPORTED:
        return None
    if name not in OPERATIONS:
        raise InvalidOperation(
            f"Unknown operation {name!r}. Use one of: {', '.join(OPERATIONS)}, "
            f"or {UNSUPPORTED!r}."
        )
    table = _sheet(tables, data.get("sheet"))

    raw_filters = _optional(data.get("filters")) or []
    if not isinstance(raw_filters, list):
        raise InvalidOperation("'filters' must be a list.")
    if len(raw_filters) > MAX_FILTERS:
        raise InvalidOperation(f"Use at most {MAX_FILTERS} filters.")
    filters = []
    for f in raw_filters:
        if not isinstance(f, dict):
            raise InvalidOperation("Each filter must be an object.")
        if _optional(f.get("column")) is None:
            continue  # a blank placeholder, as models write when a field is required
        op = f.get("op")
        if op not in COMPARISONS:
            raise InvalidOperation(
                f"Unknown filter op {op!r}. Use one of: {', '.join(COMPARISONS)}."
            )
        value = f.get("value")
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise InvalidOperation("Each filter needs a 'value'.")
        filters.append(
            Condition(_column(table, f.get("column")), op, str(value).strip())
        )

    column = _optional(data.get("column"))
    ascending = data.get("ascending")
    if ascending is not None and not isinstance(ascending, bool):
        raise InvalidOperation("'ascending' must be true or false.")
    fields: dict[str, Any] = {"filters": tuple(filters)}

    if name == "filter":
        if not filters:
            raise InvalidOperation("'filter' needs at least one filter.")
    elif name == "group_by":
        aggregate = data.get("aggregate")
        if aggregate not in AGGREGATES:
            raise InvalidOperation(
                f"'group_by' needs 'aggregate', one of: {', '.join(AGGREGATES)}."
            )
        groups = _optional(data.get("group_by")) or []
        if not isinstance(groups, list):
            raise InvalidOperation("'group_by' must be a list of column names.")
        if len(groups) > MAX_GROUP_COLUMNS:
            raise InvalidOperation(f"Group by at most {MAX_GROUP_COLUMNS} columns.")
        fields["group_by"] = tuple(
            dict.fromkeys(_column(table, g, "group_by") for g in groups)
        )
        fields["aggregate"] = aggregate
        if column is not None or aggregate != "count":
            fields["column"] = _column(table, column)
    elif name == "top_n":
        n = data.get("n")
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_TOP_N:
            raise InvalidOperation(
                f"'top_n' needs 'n', a whole number from 1 to {MAX_TOP_N}."
            )
        fields.update(column=_column(table, column), n=n, ascending=bool(ascending))
    else:  # sort, distinct, describe
        fields["column"] = _column(table, column)
        if name == "sort":
            fields["ascending"] = True if ascending is None else ascending
    return Operation(name, table.name, **fields)


# ---------------------------------------------------------------- filters


def _date_value(value: str) -> pd.Timestamp:
    try:
        ts = pd.to_datetime(value, dayfirst=not _ISO_DATE.match(value))
    except (ValueError, TypeError, OverflowError):
        ts = None
    if ts is None or pd.isna(ts):
        raise InvalidOperation(f"{value!r} is not a date. Write dates as YYYY-MM-DD.")
    return ts


def _compare(series: pd.Series, op: str, target: Any) -> pd.Series:
    present = series.notna()
    if op == "=":
        return present & (series == target)
    if op == "!=":
        return present & (series != target)
    if op == ">":
        return present & (series > target)
    if op == ">=":
        return present & (series >= target)
    if op == "<":
        return present & (series < target)
    return present & (series <= target)


def _condition(table: Table, cond: Condition) -> tuple[pd.Series, str]:
    """The rows matching one condition, and the condition in words."""
    kind = table.kinds[cond.column]
    series = table.frame[cond.column]
    if kind in ("number", "date"):
        if cond.op == "contains":
            raise InvalidOperation(
                f"{cond.column!r} holds {kind}s; use =, !=, >, >=, < or <= with it."
            )
        if kind == "number":
            target = parse_indian_number(cond.value)
            if target is None:
                raise InvalidOperation(
                    f"{cond.column!r} holds numbers, so the filter value must be a number "
                    f"written in digits, not {cond.value!r}."
                )
            shown = format_indian(target)
            words = _WORDS[cond.op]
        else:
            target = _date_value(cond.value)
            shown = target.strftime("%d %b %Y")
            words = _DATE_WORDS.get(cond.op, _WORDS[cond.op])
        return _compare(series, cond.op, target), f"{cond.column} {words} {shown}"

    if cond.op not in ("=", "!=", "contains"):
        raise InvalidOperation(
            f"{cond.column!r} holds text; compare it only with =, != or contains."
        )
    text = series.map(lambda v: display(v, kind)).str.strip().str.casefold()
    wanted = cond.value.casefold()
    present = text != ""
    if cond.op == "=":
        mask = text == wanted
    elif cond.op == "!=":
        mask = present & (text != wanted)
    else:
        mask = text.str.contains(wanted, regex=False)
    return mask, f"{cond.column} {_WORDS[cond.op]} '{cond.value}'"


def _apply_filters(
    table: Table, filters: tuple[Condition, ...]
) -> tuple[pd.Series, str]:
    mask = pd.Series(True, index=table.frame.index)
    parts = []
    for cond in filters:
        m, words = _condition(table, cond)
        mask &= m
        parts.append(words)
    return mask, (" where " + " and ".join(parts)) if parts else ""


# ---------------------------------------------------------------- results


@dataclass
class Result:
    description: str
    columns: list[str]
    kinds: list[str]  # "number" columns are right-aligned in the browser
    rows: list[list[str]]  # display strings, at most DISPLAY_ROWS
    total_rows: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "columns": self.columns,
            "kinds": self.kinds,
            "rows": self.rows,
            "total_rows": self.total_rows,
        }

    def as_text(self, max_rows: int) -> str:
        """The result as the model sees it."""
        lines = [self.description]
        if self.total_rows == 0:
            lines.append("No rows.")
            return "\n".join(lines)
        shown = self.rows[:max_rows]
        lines.append(" | ".join(self.columns))
        lines.extend(" | ".join(c[:MAX_CELL_CHARS] for c in row) for row in shown)
        if self.total_rows > len(shown):
            lines.append(
                f"(Only the first {len(shown)} of {format_indian(self.total_rows)} rows "
                "are shown here.)"
            )
        return "\n".join(lines)


def _rows(frame: pd.DataFrame, kinds: list[str]) -> list[list[str]]:
    head = frame.head(DISPLAY_ROWS)
    return [
        [display(v, k) for v, k in zip(row, kinds, strict=True)]
        for row in head.itertuples(index=False, name=None)
    ]


def _row_result(table: Table, frame: pd.DataFrame, description: str) -> Result:
    kinds = [table.kinds[c] for c in frame.columns]
    return Result(
        description, list(frame.columns), kinds, _rows(frame, kinds), len(frame)
    )


def _sort_key(table: Table, column: str):
    kind = table.kinds[column]
    if kind in ("number", "date"):
        return None
    return lambda s: s.map(lambda v: display(v, kind).casefold())


def _require(table: Table, column: str, kinds: tuple[str, ...], purpose: str) -> None:
    kind = table.kinds[column]
    if kind not in kinds:
        reason = {
            "identifier": "an identifier column (codes or account numbers)",
            "text": "a text column",
            "date": "a date column",
            "empty": "an empty column",
            "number": "a number column",
        }[kind]
        raise InvalidOperation(f"{column!r} is {reason}, so it cannot be {purpose}.")


def _group_by(table: Table, rows: pd.DataFrame, op: Operation, where: str) -> Result:
    agg, column = op.aggregate, op.column
    if agg in ("sum", "mean"):
        _require(table, column, ("number",), "added up or averaged")
    elif agg in ("min", "max"):
        _require(table, column, ("number", "date"), "used for lowest or highest")
    value_kind = (
        "date" if agg in ("min", "max") and table.kinds[column] == "date" else "number"
    )
    label = f"{AGGREGATE_LABEL[agg]} of {column}" if column else "Number of rows"
    keys = list(op.group_by)
    if label in keys:
        label += " (result)"

    if not keys:
        if column is None:
            value: Any = len(rows)
        elif agg == "count":
            value = int(rows[column].notna().sum())
        else:
            value = getattr(rows[column], agg)()
        description = f"{label}{where}, over {format_indian(len(rows))} rows."
        return Result(
            description, [label], [value_kind], [[display(value, value_kind)]], 1
        )

    grouped = rows.groupby(keys, dropna=False, sort=True)
    if column is None:
        series = grouped.size()
    elif agg == "count":
        series = grouped[column].count()
    else:
        series = getattr(grouped[column], agg)()
    out = series.rename(label).reset_index()
    out = out.sort_values(
        label, ascending=agg == "min", kind="stable", na_position="last"
    )
    kinds = [table.kinds[k] for k in keys] + [value_kind]
    description = f"{label} for each {', '.join(keys)}{where}."
    return Result(description, list(out.columns), kinds, _rows(out, kinds), len(out))


def _describe(table: Table, mask: pd.Series, column: str, where: str) -> Result:
    stats = column_stats(column, table.original.loc[mask, column])
    rows = [
        ["Values", format_indian(stats.count)],
        ["Missing", format_indian(stats.missing)],
        ["Distinct values", format_indian(stats.distinct)],
    ]
    if stats.kind == "number":
        rows += [
            ["Total", format_indian(stats.total)],
            ["Average", format_indian(stats.mean)],
            ["Lowest", format_indian(stats.minimum)],
            ["Highest", format_indian(stats.maximum)],
        ]
    elif stats.kind == "date":
        rows += [
            ["Earliest", display(stats.minimum, "date")],
            ["Latest", display(stats.maximum, "date")],
        ]
    elif stats.kind == "text":
        rows += [
            ["Most common", f"{v} ({format_indian(n)} rows)"]
            for v, n in stats.top_values
        ]
    elif stats.kind == "identifier":
        rows.append(["Note", "Identifier column (codes or numbers); not added up"])
    return Result(
        f"Statistics for {column}{where}.",
        ["Statistic", "Value"],
        ["text", "number"],
        rows,
        len(rows),
    )


def run(op: Operation, tables: list[Table]) -> Result:
    """Run a validated operation. Raises InvalidOperation if a value does not fit a column."""
    table = _sheet(tables, op.sheet)
    mask, where = _apply_filters(table, op.filters)
    rows = table.frame[mask]
    column = op.column

    if op.operation == "filter":
        return _row_result(
            table,
            rows,
            f"Rows{where}: {format_indian(len(rows))} of "
            f"{format_indian(len(table.frame))} rows match.",
        )
    if op.operation == "group_by":
        return _group_by(table, rows, op, where)
    if op.operation == "sort":
        order = "smallest first" if op.ascending else "largest first"
        if table.kinds[column] not in ("number", "date"):
            order = "A to Z" if op.ascending else "Z to A"
        out = rows.sort_values(
            column,
            ascending=op.ascending,
            kind="stable",
            na_position="last",
            key=_sort_key(table, column),
        )
        return _row_result(table, out, f"Rows{where}, sorted by {column} ({order}).")
    if op.operation == "top_n":
        _require(table, column, ("number", "date"), "used to pick the top rows")
        out = (
            rows.dropna(subset=[column])
            .sort_values(column, ascending=op.ascending, kind="stable")
            .head(op.n)
        )
        which = "lowest" if op.ascending else "highest"
        return _row_result(
            table, out, f"The {op.n} rows with the {which} {column}{where}."
        )
    if op.operation == "distinct":
        kind = table.kinds[column]
        values = rows[column].map(lambda v: display(v, kind))
        counts = values[values.str.strip() != ""].value_counts(sort=False)
        out = (
            counts.rename("Rows")
            .rename_axis(column)
            .reset_index()
            .sort_values(["Rows", column], ascending=[False, True], kind="stable")
        )
        result_rows = [[v, format_indian(n)] for v, n in out.head(DISPLAY_ROWS).values]
        return Result(
            f"Distinct values of {column}{where}: {format_indian(len(out))} values, with "
            "the number of rows for each.",
            [column, "Rows"],
            [kind, "number"],
            result_rows,
            len(out),
        )
    return _describe(table, mask, column, where)
