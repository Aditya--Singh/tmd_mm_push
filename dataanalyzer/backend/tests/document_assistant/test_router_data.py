"""HTTP tests for phase 4: Ask about data, and Proofread of data-file text cells."""

import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.core.session import current_session, require_admin
from app.tabs.document_assistant import router as da_router
from app.tabs.document_assistant.data_chat import UNCHECKED_MESSAGE
from app.tabs.document_assistant.file_store import FileStore, get_store

from .mock_ollama import FakeLanguageTool, FakeOllama
from .test_router import BASE, events, upload
from .test_xlsx_writer import make_workbook

DEPOSITS = (
    b"Branch Code;Branch;Zone;CASA Deposits\n"
    b"0123;Udaipur Main;Jaipur;4,50,00,000\n"
    b"0456;Jaipur MI Road;Jaipur;7,80,00,000\n"
    b"0789;Dwarka Sec 10;Delhi;12,40,00,000\n"
)


class Replies:
    """JSON requests get the next plan, streamed requests the next answer. Proofread's
    JSON requests (they have an "issues" schema) get no issues."""

    def __init__(self):
        self.plans: list[dict] = []
        self.answers: list[str] = []

    def __call__(self, body):
        if body["stream"]:
            return self.answers.pop(0)
        if "issues" in body.get("format", {}).get("properties", {}):
            return json.dumps({"issues": []})
        return json.dumps(self.plans.pop(0))


@pytest.fixture
def env(tmp_path):
    replies = Replies()
    fake = FakeOllama(responder=replies)
    lt = FakeLanguageTool({"Udiapur": "Udaipur", "Pendng": "Pending"})
    store = FileStore(tmp_path / "uploads")
    main.app.dependency_overrides[get_store] = lambda: store
    # The routes need a session now: the hub signs the person in.
    main.app.dependency_overrides[current_session] = lambda: {
        "username": "analyst", "role": "user"
    }
    # Deleting a document needs an administrator.
    main.app.dependency_overrides[require_admin] = lambda: {
        "username": "admin", "role": "admin"
    }
    main.app.dependency_overrides[da_router.get_ollama] = lambda: fake.client()
    main.app.dependency_overrides[da_router.get_languagetool] = lambda: lt.client()
    yield TestClient(main.app), replies, fake, store
    main.app.dependency_overrides.clear()


def file_id(client, name: str, content: bytes) -> str:
    resp = upload(client, name, content)
    assert resp.status_code == 200, resp.text
    return resp.json()["file_id"]


# ---------------------------------------------------------------- ask about data


def test_ask_streams_operation_result_and_checked_answer(env):
    client, replies, fake, _ = env
    replies.plans.append(
        {"operation": "group_by", "aggregate": "sum", "column": "CASA Deposits"}
    )
    replies.answers.append("Total CASA deposits are 24,70,00,000.")
    fid = file_id(client, "deposits.csv", DEPOSITS)

    evs = events(
        client.post(
            f"{BASE}/data/ask",
            json={"file_id": fid, "question": "Total CASA deposits?"},
        )
    )
    types = [e["type"] for e in evs]
    assert types[0] == "status"
    assert types.index("operation") < types.index("table") < types.index("answer")
    assert evs[-1] == {"type": "done"}
    result = next(e for e in evs if e["type"] == "table")
    assert result["rows"] == [["24,70,00,000"]]
    assert result["kinds"] == ["number"]
    answer = next(e for e in evs if e["type"] == "answer")
    assert answer["text"] == "Total CASA deposits are 24,70,00,000."
    assert all("num_ctx" in r["options"] for r in fake.requests)


def test_ask_sends_history_to_the_model(env):
    client, replies, fake, _ = env
    replies.plans.append({"operation": "distinct", "column": "Zone"})
    replies.answers.append("There are 2 zones: Jaipur and Delhi.")
    fid = file_id(client, "deposits.csv", DEPOSITS)
    history = [
        {
            "question": "Which branches are there?",
            "operation": {"operation": "distinct", "column": "Branch"},
            "answer": "Three branches.",
        }
    ]
    evs = events(
        client.post(
            f"{BASE}/data/ask",
            json={"file_id": fid, "question": "And zones?", "history": history},
        )
    )
    assert next(e for e in evs if e["type"] == "answer")["text"].startswith(
        "There are 2"
    )
    plan = fake.requests[0]["messages"]
    assert "1. Question: Which branches are there?" in plan[1]["content"]
    assert '"column": "Branch"' in plan[1]["content"]
    assert "New question: And zones?" in plan[1]["content"]


def test_ask_answer_with_invented_figures_falls_back_to_table(env):
    client, replies, _, _ = env
    replies.plans.append({"operation": "top_n", "column": "CASA Deposits", "n": 1})
    replies.answers += ["Dwarka has 50% of deposits.", "Dwarka holds about 12 crore."]
    fid = file_id(client, "deposits.csv", DEPOSITS)
    evs = events(
        client.post(f"{BASE}/data/ask", json={"file_id": fid, "question": "Top?"})
    )
    answer = next(e for e in evs if e["type"] == "answer")
    assert answer == {"type": "answer", "text": None, "message": UNCHECKED_MESSAGE}
    result = next(e for e in evs if e["type"] == "table")
    assert result["rows"][0][1] == "Dwarka Sec 10"
    assert evs[-1] == {"type": "done"}


def test_ask_rejects_bad_requests(env):
    client, _, _, store = env
    fid = file_id(client, "deposits.csv", DEPOSITS)
    text_id = file_id(client, "note.txt", b"Branch audit is due.")

    resp = client.post(f"{BASE}/data/ask", json={"file_id": fid, "question": "  "})
    assert resp.status_code == 400
    resp = client.post(
        f"{BASE}/data/ask", json={"file_id": fid, "question": "x" * 2001}
    )
    assert resp.status_code == 400
    resp = client.post(
        f"{BASE}/data/ask", json={"file_id": text_id, "question": "Total?"}
    )
    assert resp.status_code == 422
    assert "Excel, CSV and JSON" in resp.json()["detail"]
    store.delete(fid)
    resp = client.post(f"{BASE}/data/ask", json={"file_id": fid, "question": "Total?"})
    assert resp.status_code == 410


def test_ask_when_ollama_is_down(env):
    client, _, fake, _ = env
    fid = file_id(client, "deposits.csv", DEPOSITS)
    fake.down = True
    evs = events(
        client.post(f"{BASE}/data/ask", json={"file_id": fid, "question": "Total?"})
    )
    assert evs[-1]["type"] == "error"
    assert evs[-1]["code"] == "llm_unavailable"


# ---------------------------------------------------------------- proofread text cells


def test_proofread_csv_cells_and_write_back_same_format(env):
    client, _, _, _ = env
    original = (
        b"Branch;Remarks;Amount\r\nUdiapur;Pendng;1,25,000\r\nJaipur;Done;98,000\r\n"
        b"Udiapur;Done;5,000\r\n"
    )
    fid = file_id(client, "branches.csv", original)
    evs = events(client.post(f"{BASE}/proofread", json={"file_id": fid}))
    result = next(e for e in evs if e["type"] == "result")
    assert result["text"] == "Udiapur\n\nJaipur\n\nPendng\n\nDone"
    assert "Only text columns were checked (Branch, Remarks)" in result["notices"][0]
    accepted = [
        {"start": s["start"], "end": s["end"], "replacement": s["replacements"][0]}
        for s in result["suggestions"]
    ]
    assert len(accepted) == 2

    resp = client.post(
        f"{BASE}/proofread/apply", json={"file_id": fid, "accepted": accepted}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Udaipur\n\nJaipur\n\nPending\n\nDone"
    assert body["filename"] == "branches-proofread.csv"
    assert body["warnings"] == [] and body["alternatives"] == []
    download = client.get(f"{BASE}/download/{body['file_id']}")
    assert download.content == (
        b"Branch;Remarks;Amount\r\nUdaipur;Pending;1,25,000\r\nJaipur;Done;98,000\r\n"
        b"Udaipur;Done;5,000\r\n"
    )


def test_proofread_json_warns_about_indentation(env):
    client, _, _, _ = env
    fid = file_id(client, "c.json", b'[{"city": "Udiapur", "amount": 5}]')
    result = next(
        e
        for e in events(client.post(f"{BASE}/proofread", json={"file_id": fid}))
        if e["type"] == "result"
    )
    s = result["suggestions"][0]
    body = client.post(
        f"{BASE}/proofread/apply",
        json={
            "file_id": fid,
            "accepted": [
                {"start": s["start"], "end": s["end"], "replacement": "Udaipur"}
            ],
        },
    ).json()
    assert "indentation" in body["warnings"][0]
    download = client.get(f"{BASE}/download/{body['file_id']}").content
    assert download == b'[\n  {\n    "city": "Udaipur",\n    "amount": 5\n  }\n]'


def test_proofread_xlsx_with_chart_offers_csv_of_edited_sheet(env):
    client, _, _, _ = env
    fid = file_id(client, "loans.xlsx", make_workbook(chart=True))
    result = next(
        e
        for e in events(client.post(f"{BASE}/proofread", json={"file_id": fid}))
        if e["type"] == "result"
    )
    start = result["text"].index("Pending verfication") + len("Pending ")
    body = client.post(
        f"{BASE}/proofread/apply",
        json={
            "file_id": fid,
            "accepted": [
                {"start": start, "end": start + 11, "replacement": "verification"}
            ],
        },
    ).json()
    assert body["filename"] == "loans-proofread.xlsx"
    assert "charts, images or shapes" in body["warnings"][0]
    assert any("single style" in w for w in body["warnings"])
    (alt,) = body["alternatives"]
    assert alt["filename"] == "loans-Loans-proofread.csv"
    assert alt["label"] == "CSV of Loans"
    csv_text = client.get(f"{BASE}/download/{alt['file_id']}").content.decode(
        "utf-8-sig"
    )
    assert "Udaipur,Pending verification,125000.5" in csv_text


def test_data_file_without_text_columns_cannot_be_proofread(env):
    client, _, _, _ = env
    fid = file_id(client, "n.csv", b"Code,Amount\n0123,100\n0456,200\n")
    resp = client.post(f"{BASE}/proofread", json={"file_id": fid})
    assert resp.status_code == 422
    assert "no text columns" in resp.json()["detail"]


def test_rewrite_still_rejects_data_files(env):
    client, _, _, _ = env
    fid = file_id(client, "deposits.csv", DEPOSITS)
    resp = client.post(f"{BASE}/rewrite", json={"file_id": fid})
    assert resp.status_code == 422
    assert "Ask about data" in resp.json()["detail"]
