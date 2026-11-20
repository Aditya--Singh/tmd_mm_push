"""Ask-about-data operations: every allowed operation, and rejection of everything else."""

from pathlib import Path

import pandas as pd
import pytest

from app.core.uploads import ValidatedFile
from app.tabs.document_assistant.data_ops import (
    DISPLAY_ROWS,
    InvalidOperation,
    Operation,
    display,
    parse_operation,
    prepare,
    run,
)
from app.tabs.document_assistant.extraction import DataSheet, extract

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


def loans() -> pd.DataFrame:
    # Read as text, as a CSV upload is: amounts in Indian format, dates day first.
    return pd.DataFrame(
        {
            "Account No": [
                "100245678901",
                "100245678902",
                "100245678903",
                "100245678904",
            ],
            "Branch": ["Udaipur", "Jaipur", "udaipur ", "Delhi"],
            "Loan Type": ["Home", "Personal", "Vehicle", "Home"],
            "Amount": ["25,00,000", "1,25,000", "8,50,000", "45,00,000"],
            "Sanction Date": ["05/04/2024", "12/06/2024", "20/07/2024", "01/09/2024"],
            "Remarks": ["Regular", None, "Overdue", "Regular"],
        },
        dtype=object,
    )


@pytest.fixture
def tables():
    return [prepare(DataSheet("Loans", loans()))]


def ask(tables, **op):
    return run(parse_operation(op, tables), tables)


def column(result, name):
    return [row[result.columns.index(name)] for row in result.rows]


# ---------------------------------------------------------------- preparation


def test_columns_are_read_like_summarize(tables):
    assert tables[0].kinds == {
        "Account No": "identifier",
        "Branch": "text",
        "Loan Type": "text",
        "Amount": "number",
        "Sanction Date": "date",
        "Remarks": "text",
    }
    assert tables[0].frame["Amount"].tolist() == [2500000, 125000, 850000, 4500000]


def test_display_uses_indian_grouping_and_keeps_identifiers_plain():
    assert display(9723750.0, "number") == "97,23,750"
    assert display(1215468.75, "number") == "12,15,468.75"
    assert display(100245678901.0, "identifier") == "100245678901"
    assert display(float("nan"), "number") == ""
    assert display(pd.Timestamp("2024-04-05"), "date") == "05 Apr 2024"


# ---------------------------------------------------------------- every operation


def test_filter_by_number_text_and_date(tables):
    result = ask(
        tables,
        operation="filter",
        filters=[
            {"column": "Amount", "op": ">=", "value": "500000"},
            {
                "column": "branch",
                "op": "=",
                "value": "UDAIPUR",
            },  # names and text ignore case
        ],
    )
    assert column(result, "Account No") == ["100245678901", "100245678903"]
    assert column(result, "Amount") == ["25,00,000", "8,50,000"]
    assert result.description == (
        "Rows where Amount is at least 5,00,000 and Branch is 'UDAIPUR': 2 of 4 rows match."
    )

    result = ask(
        tables,
        operation="filter",
        filters=[{"column": "Sanction Date", "op": ">", "value": "2024-06-12"}],
    )
    assert column(result, "Sanction Date") == ["20 Jul 2024", "01 Sep 2024"]
    assert "is after 12 Jun 2024" in result.description


def test_filter_number_values_may_be_written_the_indian_way(tables):
    result = ask(
        tables,
        operation="filter",
        filters=[{"column": "Amount", "op": "<", "value": "₹ 10,00,000"}],
    )
    assert column(result, "Amount") == ["1,25,000", "8,50,000"]


def test_filter_contains_and_not_equal(tables):
    result = ask(
        tables,
        operation="filter",
        filters=[{"column": "Remarks", "op": "contains", "value": "over"}],
    )
    assert column(result, "Remarks") == ["Overdue"]
    result = ask(
        tables,
        operation="filter",
        filters=[{"column": "Remarks", "op": "!=", "value": "regular"}],
    )
    assert column(result, "Remarks") == ["Overdue"]  # the empty cell does not match


def test_group_by_sum_is_sorted_largest_first(tables):
    result = ask(
        tables,
        operation="group_by",
        group_by=["Loan Type"],
        aggregate="sum",
        column="Amount",
    )
    assert result.columns == ["Loan Type", "Total of Amount"]
    assert result.rows == [
        ["Home", "70,00,000"],
        ["Vehicle", "8,50,000"],
        ["Personal", "1,25,000"],
    ]
    assert result.kinds == ["text", "number"]


def test_group_by_with_no_groups_gives_one_figure(tables):
    result = ask(
        tables, operation="group_by", group_by=[], aggregate="sum", column="Amount"
    )
    assert result.rows == [["79,75,000"]]
    assert result.description == "Total of Amount, over 4 rows."


def test_group_by_count_mean_min_max(tables):
    count = ask(tables, operation="group_by", group_by=["Loan Type"], aggregate="count")
    assert count.rows[0] == ["Home", "2"]
    assert count.columns == ["Loan Type", "Number of rows"]
    # Counting a column counts its non-empty cells.
    remarks = ask(tables, operation="group_by", aggregate="count", column="Remarks")
    assert remarks.rows == [["3"]]
    mean = ask(tables, operation="group_by", aggregate="mean", column="Amount")
    assert mean.rows == [["19,93,750"]]
    lowest = ask(tables, operation="group_by", aggregate="min", column="Amount")
    assert lowest.rows == [["1,25,000"]]
    latest = ask(tables, operation="group_by", aggregate="max", column="Sanction Date")
    assert latest.rows == [["01 Sep 2024"]]


def test_sort_numbers_and_text(tables):
    result = ask(tables, operation="sort", column="Amount", ascending=False)
    assert column(result, "Amount") == [
        "45,00,000",
        "25,00,000",
        "8,50,000",
        "1,25,000",
    ]
    assert "largest first" in result.description
    result = ask(tables, operation="sort", column="Loan Type")  # ascending by default
    assert column(result, "Loan Type") == ["Home", "Home", "Personal", "Vehicle"]


def test_top_n_largest_and_smallest(tables):
    result = ask(tables, operation="top_n", column="Amount", n=2)
    assert column(result, "Amount") == ["45,00,000", "25,00,000"]
    assert result.description == "The 2 rows with the highest Amount."
    result = ask(tables, operation="top_n", column="Amount", n=1, ascending=True)
    assert column(result, "Amount") == ["1,25,000"]


def test_distinct_values_with_counts(tables):
    result = ask(tables, operation="distinct", column="Loan Type")
    assert result.rows == [["Home", "2"], ["Personal", "1"], ["Vehicle", "1"]]
    assert result.total_rows == 3


def test_describe_number_and_text_columns(tables):
    result = ask(tables, operation="describe", column="Amount")
    stats = dict(result.rows)
    assert stats["Total"] == "79,75,000"
    assert stats["Highest"] == "45,00,000"
    assert stats["Values"] == "4"
    result = ask(tables, operation="describe", column="Remarks")
    assert ["Most common", "Regular (2 rows)"] in result.rows
    assert dict(result.rows)["Missing"] == "1"


def test_filters_narrow_every_operation(tables):
    result = ask(
        tables,
        operation="group_by",
        aggregate="sum",
        column="Amount",
        filters=[{"column": "Loan Type", "op": "=", "value": "home"}],
    )
    assert result.rows == [["70,00,000"]]
    assert "where Loan Type is 'home'" in result.description


def test_sample_loans_total_outstanding_in_indian_format():
    content = (SAMPLES / "test_loans.xlsx").read_bytes()
    sheets = extract(ValidatedFile("test_loans.xlsx", ".xlsx", content)).sheets
    tables = [prepare(s) for s in sheets]
    result = ask(tables, operation="group_by", aggregate="sum", column="Outstanding")
    assert result.rows == [["97,23,750"]]


def test_sample_csv_codes_are_never_added_up():
    content = (SAMPLES / "test_branch_deposits.csv").read_bytes()
    tables = [
        prepare(s) for s in extract(ValidatedFile("d.csv", ".csv", content)).sheets
    ]
    result = ask(tables, operation="group_by", aggregate="sum", column="CASA Deposits")
    assert result.rows == [["33,95,00,000"]]
    with pytest.raises(InvalidOperation, match="identifier"):
        ask(tables, operation="group_by", aggregate="sum", column="Branch Code")
    # Codes keep their leading zeros.
    result = ask(tables, operation="sort", column="Branch Code")
    assert column(result, "Branch Code")[0] == "0123"


def test_results_keep_at_most_display_rows_but_count_all():
    frame = pd.DataFrame({"Amount": list(range(DISPLAY_ROWS + 50))})
    tables = [prepare(DataSheet("Big", frame))]
    result = ask(tables, operation="sort", column="Amount")
    assert len(result.rows) == DISPLAY_ROWS
    assert result.total_rows == DISPLAY_ROWS + 50
    text = result.as_text(10)
    assert "Only the first 10 of 150 rows" in text
    assert text.count("\n") == 12  # description, header, 10 rows, note


def test_empty_result_says_no_rows(tables):
    result = ask(
        tables,
        operation="filter",
        filters=[{"column": "Branch", "op": "=", "value": "Mumbai"}],
    )
    assert result.total_rows == 0
    assert result.as_text(10).endswith("No rows.")


def test_operation_round_trips_through_its_json(tables):
    op = parse_operation(
        {
            "operation": "top_n",
            "column": "amount",
            "n": 3,
            "filters": [{"column": "Branch", "op": "=", "value": "Jaipur"}],
        },
        tables,
    )
    assert op == Operation(
        "top_n",
        "Loans",
        filters=(op.filters[0],),
        column="Amount",
        n=3,
        ascending=False,
    )
    assert parse_operation(op.to_dict(), tables) == op


def test_unused_empty_fields_are_ignored(tables):
    op = parse_operation(
        {
            "operation": "group_by",
            "aggregate": "count",
            "column": "",
            "group_by": ["Branch"],
            "filters": [],
            "sheet": "",
        },
        tables,
    )
    assert op.column is None


def test_unsupported_is_not_an_error(tables):
    assert parse_operation({"operation": "unsupported"}, tables) is None


# ---------------------------------------------------------------- rejection


@pytest.mark.parametrize(
    ("op", "message"),
    [
        ({"operation": "eval", "column": "Amount"}, "Unknown operation"),
        ({"operation": "__import__('os')"}, "Unknown operation"),
        ({}, "Unknown operation"),
        ({"operation": "sort", "column": "Balance"}, "no column named 'Balance'"),
        ({"operation": "sort"}, "must be a column name"),
        ({"operation": "sort", "column": "Amount", "sheet": "Other"}, "no sheet"),
        (
            {"operation": "sort", "column": "Amount", "ascending": "yes"},
            "true or false",
        ),
        ({"operation": "group_by", "column": "Amount"}, "needs 'aggregate'"),
        (
            {"operation": "group_by", "aggregate": "median", "column": "Amount"},
            "aggregate",
        ),
        (
            {
                "operation": "group_by",
                "aggregate": "sum",
                "column": "Amount",
                "group_by": ["X"],
            },
            "no column named 'X'",
        ),
        ({"operation": "group_by", "aggregate": "sum"}, "must be a column name"),
        ({"operation": "top_n", "column": "Amount"}, "needs 'n'"),
        ({"operation": "top_n", "column": "Amount", "n": 0}, "needs 'n'"),
        ({"operation": "top_n", "column": "Amount", "n": 101}, "needs 'n'"),
        ({"operation": "top_n", "column": "Amount", "n": True}, "needs 'n'"),
        ({"operation": "filter"}, "at least one filter"),
        (
            {
                "operation": "filter",
                "filters": [{"column": "Amount", "op": "~", "value": "1"}],
            },
            "Unknown filter op",
        ),
        (
            {
                "operation": "filter",
                "filters": [{"column": "Nope", "op": "=", "value": "1"}],
            },
            "no column named 'Nope'",
        ),
        (
            {"operation": "filter", "filters": [{"column": "Amount", "op": "="}]},
            "value",
        ),
        (
            {
                "operation": "filter",
                "filters": [{"column": "Amount", "op": "=", "value": "1"}] * 6,
            },
            "at most 5",
        ),
        ({"operation": "filter", "filters": "Amount > 5"}, "must be a list"),
    ],
)
def test_bad_operations_are_rejected(tables, op, message):
    with pytest.raises(InvalidOperation, match=message):
        run(parse_operation(op, tables), tables)


def test_reply_must_be_an_object(tables):
    with pytest.raises(InvalidOperation, match="JSON object"):
        parse_operation(["sort"], tables)


@pytest.mark.parametrize(
    ("op", "message"),
    [
        (
            {"operation": "group_by", "aggregate": "sum", "column": "Account No"},
            "identifier",
        ),
        (
            {"operation": "group_by", "aggregate": "mean", "column": "Branch"},
            "text column",
        ),
        (
            {"operation": "group_by", "aggregate": "max", "column": "Remarks"},
            "text column",
        ),
        ({"operation": "top_n", "column": "Branch", "n": 2}, "text column"),
        (
            {
                "operation": "filter",
                "filters": [{"column": "Amount", "op": ">", "value": "five"}],
            },
            "must be a number",
        ),
        (
            {
                "operation": "filter",
                "filters": [{"column": "Amount", "op": "contains", "value": "5"}],
            },
            "use =, !=",
        ),
        (
            {
                "operation": "filter",
                "filters": [{"column": "Branch", "op": ">", "value": "J"}],
            },
            "only with =, != or contains",
        ),
        (
            {
                "operation": "filter",
                "filters": [{"column": "Sanction Date", "op": ">", "value": "soon"}],
            },
            "not a date",
        ),
    ],
)
def test_values_that_do_not_fit_the_column_are_rejected(tables, op, message):
    with pytest.raises(InvalidOperation, match=message):
        run(parse_operation(op, tables), tables)


def test_several_sheets_need_a_sheet_name():
    tables = [
        prepare(DataSheet("Loans", loans())),
        prepare(DataSheet("Deposits", pd.DataFrame({"Amount": [1, 2]}))),
    ]
    with pytest.raises(InvalidOperation, match="several sheets"):
        parse_operation({"operation": "sort", "column": "Amount"}, tables)
    result = ask(tables, operation="sort", column="Amount", sheet="deposits")
    assert result.rows == [["1"], ["2"]]


def test_filters_come_last_in_schema_and_operation_json(tables):
    """Ollama emits keys in schema order; a follow-up must be able to append filters."""
    from app.tabs.document_assistant.data_ops import OPERATION_SCHEMA

    assert list(OPERATION_SCHEMA["properties"])[-1] == "filters"
    op = parse_operation(
        {
            "operation": "group_by",
            "aggregate": "sum",
            "column": "Amount",
            "filters": [{"column": "Branch", "op": "=", "value": "Jaipur"}],
        },
        tables,
    )
    assert list(op.to_dict())[-1] == "filters"


def test_every_schema_key_is_required_and_unused_ones_are_ignored(tables):
    from app.tabs.document_assistant.data_ops import OPERATION_SCHEMA

    assert OPERATION_SCHEMA["required"] == list(OPERATION_SCHEMA["properties"])
    # A full reply for a sort: the group-by, aggregate, n and blank filter are ignored.
    op = parse_operation(
        {
            "operation": "sort",
            "sheet": "Loans",
            "group_by": ["Branch"],
            "aggregate": "sum",
            "column": "Amount",
            "ascending": False,
            "n": 0,
            "filters": [{"column": "", "op": "=", "value": ""}],
        },
        tables,
    )
    assert op == Operation("sort", "Loans", column="Amount", ascending=False)
