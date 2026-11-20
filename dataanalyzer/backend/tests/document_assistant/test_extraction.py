import json

import pandas as pd
import pytest

from app.core.uploads import ValidatedFile
from app.tabs.document_assistant.extraction import (
    MAX_DATA_ROWS,
    ExtractionError,
    extract,
    sheet_preview,
)

from .fixtures import (
    make_docx,
    make_docx_with_tracked_change,
    make_pdf,
    make_pptx,
    make_xlsx,
)


def vf(ext: str, content: bytes) -> ValidatedFile:
    return ValidatedFile(f"file{ext}", ext, content)


def test_txt_with_bom_and_crlf():
    r = extract(vf(".txt", "﻿Line one\r\nLine two".encode()))
    assert r.kind == "text"
    assert r.text == "Line one\nLine two"
    assert r.word_count == 4


def test_docx_paragraphs_and_table_in_order():
    content = make_docx(
        ["Dear Customer,", "Your loan is sanctioned."],
        table=[["Item", "Amount"], ["Loan", "5,00,000"]],
    )
    r = extract(vf(".docx", content))
    assert (
        r.text
        == "Dear Customer,\n\nYour loan is sanctioned.\n\nItem | Amount\n\nLoan | 5,00,000"
    )


def test_docx_tracked_changes_rejected():
    with pytest.raises(ExtractionError) as err:
        extract(vf(".docx", make_docx_with_tracked_change()))
    assert "tracked changes" in err.value.message


def test_pptx_text_and_table():
    content = make_pptx(
        [["Quarterly review", "Deposits grew"], ["Next steps"]],
        table=[["Zone", "Target"], ["North", "120"]],
    )
    r = extract(vf(".pptx", content))
    assert "Quarterly review\nDeposits grew" in r.text
    assert "Next steps" in r.text
    assert "Zone | Target" in r.text and "North | 120" in r.text


def test_pdf_text():
    r = extract(vf(".pdf", make_pdf(["First page text", "Second page"])))
    assert r.text == "First page text\n\nSecond page"
    assert r.notices == []


def test_pdf_with_no_text_is_rejected():
    with pytest.raises(ExtractionError) as err:
        extract(vf(".pdf", make_pdf([None, None])))
    assert "scanned" in err.value.message


def test_pdf_with_some_empty_pages_gives_notice():
    r = extract(vf(".pdf", make_pdf(["One", None, "Three", None])))
    assert r.text == "One\n\nThree"
    assert r.notices == [
        "Skipped pages 2 and 4: no readable text. Scanned pages are not supported yet."
    ]


def test_corrupt_file_gives_plain_message():
    with pytest.raises(ExtractionError) as err:
        extract(vf(".docx", b"PK\x03\x04 not really a zip"))
    assert "could not be read" in err.value.message


def test_empty_document_rejected():
    with pytest.raises(ExtractionError) as err:
        extract(vf(".txt", b"   \n "))
    assert "no text" in err.value.message


def test_csv_semicolon_keeps_text_codes():
    content = "Branch Code;Amount\n007;1,25,000\n010;2,50,000\n".encode()
    r = extract(vf(".csv", content))
    assert r.kind == "data"
    frame = r.sheets[0].frame
    assert list(frame.columns) == ["Branch Code", "Amount"]
    assert list(frame["Branch Code"]) == ["007", "010"]


def test_xlsx_all_sheets():
    content = make_xlsx(
        {
            "Loans": pd.DataFrame({"Account No": [1, 2], "Amount": [100, 200]}),
            "Staff": pd.DataFrame({"Name": ["A", "B", "C"]}),
        }
    )
    r = extract(vf(".xlsx", content))
    assert [s.name for s in r.sheets] == ["Loans", "Staff"]
    assert r.row_count == 5


def test_json_records_and_wrapper_and_columns():
    records = [{"name": "A", "amount": 1}, {"name": "B", "amount": 2}]
    for data in (records, {"data": records}, {"name": ["A", "B"], "amount": [1, 2]}):
        r = extract(vf(".json", json.dumps(data).encode()))
        assert list(r.sheets[0].frame.columns) == ["name", "amount"]
        assert r.row_count == 2


@pytest.mark.parametrize(
    "data", [{"a": 1}, [1, 2, 3], "text", [], {"a": [1], "b": [1, 2]}]
)
def test_json_not_a_table_rejected(data):
    with pytest.raises(ExtractionError) as err:
        extract(vf(".json", json.dumps(data).encode()))
    assert "not a table" in err.value.message


def test_too_many_rows_rejected():
    content = ("n\n" + "1\n" * (MAX_DATA_ROWS + 1)).encode()
    with pytest.raises(ExtractionError) as err:
        extract(vf(".csv", content))
    assert err.value.status_code == 413
    assert "10,000" in err.value.message


def test_too_many_json_rows_rejected():
    data = [{"n": i} for i in range(MAX_DATA_ROWS + 1)]
    with pytest.raises(ExtractionError) as err:
        extract(vf(".json", json.dumps(data).encode()))
    assert err.value.status_code == 413


def test_exactly_max_rows_accepted():
    content = ("n\n" + "1\n" * MAX_DATA_ROWS).encode()
    assert extract(vf(".csv", content)).row_count == MAX_DATA_ROWS


def test_header_only_csv_rejected():
    with pytest.raises(ExtractionError) as err:
        extract(vf(".csv", b"a,b\n"))
    assert "no data rows" in err.value.message


def test_sheet_preview_is_json_safe():
    content = make_xlsx(
        {
            "S": pd.DataFrame(
                {
                    "When": pd.to_datetime(["2026-01-02", None]),
                    "X": [1.5, None],
                    "Name": ["A", "B"],
                }
            )
        }
    )
    preview = sheet_preview(extract(vf(".xlsx", content)).sheets[0])
    json.dumps(preview)
    assert preview["columns"] == ["When", "X", "Name"]
    assert preview["rows"][0] == ["2026-01-02T00:00:00", 1.5, "A"]
    assert preview["rows"][1] == [None, None, "B"]
