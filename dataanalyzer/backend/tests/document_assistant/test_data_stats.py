import pandas as pd
import pytest

from app.tabs.document_assistant.data_stats import (
    column_stats,
    format_indian,
    format_stats,
    is_id_name,
    name_tokens,
    parse_indian_number,
    sheet_stats,
)


# ------------------------------------------------------------ Indian number formats


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1,25,000", 125000.0),
        ("₹ 2,50,000.00", 250000.0),
        ("₹2,50,000.50", 250000.5),
        ("(5,000)", -5000.0),
        ("(₹ 5,000.75)", -5000.75),
        ("-12,34,567", -1234567.0),
        ("Rs. 1,00,00,000", 10000000.0),
        ("INR 45,000", 45000.0),
        ("45,000 INR", 45000.0),
        ("125,000", 125000.0),  # Western grouping also accepted
        ("1250", 1250.0),
        ("0.5", 0.5),
        (" 1,000 ", 1000.0),
    ],
)
def test_parse_indian_number(text, expected):
    assert parse_indian_number(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "abc", "1,,000", ",100", "100,", "1.2.3", "(-5)", "12 apples", "₹", "1e5"],
)
def test_parse_indian_number_rejects(text):
    assert parse_indian_number(text) is None


def test_text_column_of_indian_numbers_is_converted_and_summed():
    s = pd.Series(["1,25,000", "₹ 2,50,000.00", "(5,000)", None])
    c = column_stats("Amount", s)
    assert c.kind == "number"
    assert c.total == 370000.0
    assert c.minimum == -5000.0
    assert c.maximum == 250000.0
    assert c.count == 3 and c.missing == 1


def test_mixed_real_numbers_and_text_numbers_are_converted():
    s = pd.Series([1000, "1,25,000", 2500.5], dtype=object)
    c = column_stats("Balance", s)
    assert c.kind == "number"
    assert c.total == 128500.5


def test_column_with_one_non_number_stays_text():
    s = pd.Series(["1,25,000", "2,50,000", "not available"])
    c = column_stats("Amount", s)
    assert c.kind == "text"
    assert c.total is None


def test_format_indian():
    assert format_indian(1234567) == "12,34,567"
    assert format_indian(125000) == "1,25,000"
    assert format_indian(999) == "999"
    assert format_indian(-1234567.5) == "-12,34,567.50"
    assert format_indian(10000000) == "1,00,00,000"


# ------------------------------------------------------------ identifier columns


@pytest.mark.parametrize(
    "name",
    [
        "Account No",
        "account_number",
        "customer_id",
        "CustomerID",
        "customerId",
        "Mobile",
        "Phone Number",
        "PIN Code",
        "Branch Code",
        "Sr. No.",
        "ID",
        "AccountNo",
    ],
)
def test_id_names(name):
    assert is_id_name(name)


@pytest.mark.parametrize(
    "name", ["Amount", "Notes", "Shipping", "Annotation", "Pinnacle", "Paid", "Video"]
)
def test_not_id_names(name):
    assert not is_id_name(name)


def test_name_tokens():
    assert name_tokens("customerID") == ["customer", "id"]
    assert name_tokens("Account_No.") == ["account", "no"]


def test_id_named_numeric_column_is_never_summed():
    s = pd.Series([1001, 1002, 1001, 1003])
    c = column_stats("Account No", s)
    assert c.kind == "identifier"
    assert c.total is None and c.mean is None
    assert c.minimum is None and c.maximum is None
    assert c.count == 4
    assert c.distinct == 3


def test_id_named_text_column_keeps_leading_zeros_in_distinct_count():
    s = pd.Series(["007", "7", "110001"])
    c = column_stats("PIN Code", s)
    assert c.kind == "identifier"
    assert c.distinct == 3


def test_mobile_numbers_as_text_are_identifiers():
    s = pd.Series(["98765 43210", "98765 43211", "98765 43210"])
    c = column_stats("Mobile", s)
    assert c.kind == "identifier"
    assert c.total is None
    assert c.distinct == 2


def test_unique_integer_column_is_identifier_whatever_its_name():
    s = pd.Series([501234, 501235, 501240, 501299])
    c = column_stats("Ref", s)
    assert c.kind == "identifier"
    assert c.total is None


def test_values_with_thousands_separators_are_never_identifiers():
    indian = pd.Series(["4,50,00,000", "7,80,00,000", "12,40,00,000"])
    western = pd.Series(["45,000,000", "78,000,000", "124,000,000"])
    for s in (indian, western):
        c = column_stats("Figures", s)
        assert c.kind == "number"
        assert c.total == 247_000_000


def test_unique_codes_with_leading_zero_are_identifiers():
    c = column_stats("Ref", pd.Series(["0123", "0456", "1011"]))
    assert c.kind == "identifier"
    assert c.total is None


def test_unique_same_length_six_digit_codes_are_identifiers():
    assert (
        column_stats("Ref", pd.Series(["313001", "302001", "110075"])).kind
        == "identifier"
    )
    assert (
        column_stats("Ref", pd.Series([100245678901, 100245678902])).kind
        == "identifier"
    )


@pytest.mark.parametrize(
    "values",
    [
        [12500, 25000, 37500],  # unique but only five digits
        [125000, 1250000, 75000],  # unique but different lengths
        [450000.5, 780000.25, 990000.75],  # decimals
        ["0123", "0123", "0456"],  # leading zero but not unique
    ],
)
def test_unique_rule_needs_code_shape(values):
    assert column_stats("Ref", pd.Series(values)).kind == "number"


@pytest.mark.parametrize(
    "name",
    [
        "CASA Deposits",
        "Advances",
        "Loan",
        "Credit",
        "Debit",
        "Income",
        "Expenses",
        "Cost",
        "Fees",
        "Interest",
        "Limit",
        "Value",
        "Profit",
        "NPA",
        "Premium",
        "Sanctioned",
        "Outstanding",
        "Disbursed",
    ],
)
def test_money_names_are_never_read_as_codes(name):
    # Same-length six-digit unique values would otherwise look like codes.
    c = column_stats(name, pd.Series([450000, 780000, 125000]))
    assert c.kind == "number"
    assert c.total == 1_355_000


def test_unique_whole_amounts_are_numbers_when_named_as_amounts():
    s = pd.Series([125000, 250000, 75000])
    c = column_stats("Loan Amount", s)
    assert c.kind == "number"
    assert c.total == 450000


def test_unique_whole_amounts_with_rupee_sign_are_numbers():
    s = pd.Series(["₹ 1,25,000", "₹ 2,50,000", "₹ 75,000"])
    c = column_stats("Sanctioned", s)
    assert c.kind == "number"
    assert c.total == 450000


def test_negative_unique_integers_are_numbers():
    assert column_stats("Change", pd.Series([-5, 10, 20])).kind == "number"


def test_id_name_wins_over_amount_name():
    assert column_stats("Amount Code", pd.Series([10, 10, 20])).kind == "identifier"


def test_repeated_integers_are_numbers():
    s = pd.Series([100, 200, 100, 300])
    c = column_stats("Quantity", s)
    assert c.kind == "number"
    assert c.total == 700


def test_unique_non_integers_are_numbers():
    s = pd.Series([100.5, 200.25, 300.0])
    assert column_stats("Rate", s).kind == "number"


def test_identifier_line_in_prompt_has_no_total():
    df = pd.DataFrame({"Account No": [1, 2, 3], "Amount": [10, 10, 30]})
    text = format_stats([sheet_stats("Sheet1", df)])
    assert "Account No (identifier): 3 values; 3 distinct" in text
    assert "Amount (number)" in text and "total 50" in text
    account_line = next(l for l in text.splitlines() if "Account No" in l)
    assert "total" not in account_line and "average" not in account_line


# ------------------------------------------------------------ dates


def test_datetime_column_reports_range():
    s = pd.Series(pd.to_datetime(["2026-03-15", "2026-01-02", "2026-12-31"]))
    c = column_stats("Opened", s)
    assert c.kind == "date"
    assert c.minimum == pd.Timestamp("2026-01-02")
    assert c.maximum == pd.Timestamp("2026-12-31")


def test_text_dates_are_parsed_day_first():
    s = pd.Series(["05/01/2026", "20/03/2026", "01/02/2026"])
    c = column_stats("Txn Date", s)
    assert c.kind == "date"
    assert c.minimum == pd.Timestamp("2026-01-05")
    assert c.maximum == pd.Timestamp("2026-03-20")


def test_date_range_in_prompt():
    df = pd.DataFrame({"Opened": pd.to_datetime(["2026-01-02", "2026-12-31"])})
    text = format_stats([sheet_stats("S", df)])
    assert "from 02 Jan 2026 to 31 Dec 2026" in text


def test_words_are_not_dates():
    s = pd.Series(["Delhi", "Mumbai", "Delhi"])
    c = column_stats("City", s)
    assert c.kind == "text"
    assert c.top_values == [("Delhi", 2), ("Mumbai", 1)]


# ------------------------------------------------------------ other


def test_empty_column():
    c = column_stats("Remarks", pd.Series([None, "", "  "], dtype=object))
    assert c.kind == "empty"
    assert c.missing == 3


def test_bool_column_is_text_not_number():
    c = column_stats("Active", pd.Series([True, False, True]))
    assert c.kind == "text"
