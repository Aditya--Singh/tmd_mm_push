"""The documents a person shares, and what is found in them."""
from __future__ import annotations

import io

import pandas as pd
import pytest


def a_workbook() -> bytes:
    """A small table, as an Excel workbook."""
    frame = pd.DataFrame(
        {
            "branch": ["Delhi", "Mumbai", "Chennai", "Delhi", "Kolkata", "Delhi"],
            "balance": [1000.0, 2500.5, 800.0, 1200.0, 640.25, 1100.0],
            "opened": ["2023-01-01", "2023-02-01", "2023-03-01", None, "2023-05-01", None],
        }
    )

    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False, sheet_name="Accounts")

    return buffer.getvalue()


def a_csv() -> bytes:
    return b"branch,balance\nDelhi,1000\nMumbai,2500\nChennai,800\n"


def test_a_document_is_read_and_described(the_app, a_signed_in_person):
    answer = the_app.post(
        "/api/documents",
        files={"file": ("accounts.xlsx", a_workbook(), "application/vnd.ms-excel")},
        headers=a_signed_in_person["headers"],
    )

    assert answer.status_code == 201, answer.text

    body = answer.json()

    assert body["rows"] == 6
    assert body["columns"] == 3
    assert body["uploadedBy"] == "analyst"

    profile = body["profile"]

    assert profile["duplicateRows"] == 0

    names = [column["name"] for column in profile["columnProfiles"]]

    assert names == ["branch", "balance", "opened"]

    balance = profile["columnProfiles"][1]

    assert balance["kind"] == "number"
    assert balance["mean"] == pytest.approx((1000 + 2500.5 + 800 + 1200 + 640.25 + 1100) / 6, rel=1e-3)

    # The column with the gaps is reported as such.
    opened = profile["columnProfiles"][2]

    assert opened["missing"] == 2
    assert opened["missingPct"] == pytest.approx(33.3, abs=0.1)


def test_a_csv_is_read_as_well(the_app, a_signed_in_person):
    answer = the_app.post(
        "/api/documents",
        files={"file": ("accounts.csv", a_csv(), "text/csv")},
        headers=a_signed_in_person["headers"],
    )

    assert answer.status_code == 201, answer.text

    body = answer.json()

    assert body["rows"] == 3
    assert body["columns"] == 2


def test_the_pictures_are_made(the_app, a_signed_in_person):
    answer = the_app.post(
        "/api/documents",
        files={"file": ("accounts.csv", a_csv(), "text/csv")},
        headers=a_signed_in_person["headers"],
    )

    assert answer.status_code == 201, answer.text

    plots = answer.json()["plots"]

    assert plots, "no picture was made"

    # Every picture may be fetched, and it is a picture.
    for plot in plots:
        picture = the_app.get(f"/api/plots/{answer.json()['id']}/{plot['file']}")

        assert picture.status_code == 200
        assert picture.headers["content-type"] == "image/png"


def test_a_summary_is_written_without_a_model(the_app, a_signed_in_person):
    """A machine without a model still gets a summary, from the figures."""
    answer = the_app.post(
        "/api/documents",
        files={"file": ("accounts.csv", a_csv(), "text/csv")},
        headers=a_signed_in_person["headers"],
    )

    assert answer.status_code == 201, answer.text

    body = answer.json()

    assert body["summary"]
    assert "3 rows" in body["summary"]

    # The reason says that no model was used, so that a person is not misled.
    assert body["summaryReason"]


def test_the_findings_are_made(the_app, a_signed_in_person):
    answer = the_app.post(
        "/api/documents",
        files={"file": ("accounts.xlsx", a_workbook(), "application/vnd.ms-excel")},
        headers=a_signed_in_person["headers"],
    )

    assert answer.status_code == 201, answer.text

    findings = answer.json()["insights"]

    assert findings

    # The column with the gaps is named in one of the findings.
    assert any("opened" in finding["text"] for finding in findings)


def test_a_file_that_cannot_be_read_is_refused(the_app, a_signed_in_person):
    answer = the_app.post(
        "/api/documents",
        files={"file": ("notes.docx", b"not a table", "application/octet-stream")},
        headers=a_signed_in_person["headers"],
    )

    assert answer.status_code == 400
    assert "Excel" in answer.json()["detail"]


def test_a_person_without_a_session_is_refused(the_app):
    answer = the_app.get("/api/documents")

    assert answer.status_code == 401


def test_the_documents_are_listed(the_app, a_signed_in_person):
    the_app.post(
        "/api/documents",
        files={"file": ("accounts.csv", a_csv(), "text/csv")},
        headers=a_signed_in_person["headers"],
    )

    answer = the_app.get("/api/documents", headers=a_signed_in_person["headers"])

    assert answer.status_code == 200
    assert len(answer.json()["documents"]) == 1


def test_only_an_administrator_may_remove_a_document(the_app, a_signed_in_person):
    created = the_app.post(
        "/api/documents",
        files={"file": ("accounts.csv", a_csv(), "text/csv")},
        headers=a_signed_in_person["headers"],
    )

    document_id = created.json()["id"]

    # A reader may not remove it.
    refused = the_app.delete(
        f"/api/documents/{document_id}", headers=a_signed_in_person["headers"]
    )

    assert refused.status_code == 403

    # An administrator may.
    answer = the_app.post(
        "/api/auth/handoff",
        json={"username": "admin", "role": "admin"},
        headers={"X-Handoff-Secret": "a-shared-secret-of-at-least-thirty-two-characters"},
    )

    ticket = answer.json()["ticket"]

    exchanged = the_app.post("/api/auth/exchange", json={"ticket": ticket})

    headers = {"Authorization": f"Bearer {exchanged.json()['access_token']}"}

    assert the_app.delete(f"/api/documents/{document_id}", headers=headers).status_code == 200
    assert the_app.get("/api/documents", headers=headers).json()["documents"] == []


def test_a_question_is_answered_without_a_model(the_app, a_signed_in_person):
    created = the_app.post(
        "/api/documents",
        files={"file": ("accounts.csv", a_csv(), "text/csv")},
        headers=a_signed_in_person["headers"],
    )

    document_id = created.json()["id"]

    answer = the_app.post(
        f"/api/documents/{document_id}/ask",
        json={"question": "Which branch has the highest balance?"},
        headers=a_signed_in_person["headers"],
    )

    assert answer.status_code == 200
    assert answer.json()["answer"]
