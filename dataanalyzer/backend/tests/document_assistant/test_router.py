import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.core.session import current_session, require_admin
from app.tabs.document_assistant import router as da_router
from app.tabs.document_assistant.file_store import FileStore, get_store

from .fixtures import make_pdf, make_xlsx
from .mock_ollama import FakeOllama

BASE = "/api/document-assistant"


@pytest.fixture
def env(tmp_path):
    fake = FakeOllama(reply="Here is the summary.")
    state = {"num_ctx": None}
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
    main.app.dependency_overrides[da_router.get_ollama] = lambda: fake.client(
        state["num_ctx"]
    )
    yield TestClient(main.app), fake, store, state
    main.app.dependency_overrides.clear()


def upload(client, name, content):
    return client.post(f"{BASE}/extract", files={"file": (name, content)})


def events(resp):
    assert resp.headers["content-type"].startswith("text/event-stream")
    return [
        json.loads(line[len("data: ") :])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]


def test_extract_text_then_summarize_by_file_id(env):
    client, fake, store, _ = env
    resp = upload(client, "note.txt", b"Branch audit is due on 31 March.")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "text"
    assert body["text"] == "Branch audit is due on 31 March."
    assert body["word_count"] == 7
    assert body["filename"] == "note.txt"
    assert body["expires_at"] > 0

    resp = client.post(f"{BASE}/summarize", json={"file_id": body["file_id"]})
    evs = events(resp)
    assert (
        "".join(e["text"] for e in evs if e["type"] == "chunk")
        == "Here is the summary."
    )
    assert evs[-1] == {"type": "done"}
    assert (
        "Branch audit is due on 31 March." in fake.requests[0]["messages"][1]["content"]
    )


def test_extract_data_file_and_summarize(env):
    client, fake, _, _ = env
    content = make_xlsx(
        {"Loans": pd.DataFrame({"Account No": [11, 12], "Amount": [100, 100]})}
    )
    body = upload(client, "loans.xlsx", content).json()
    assert body["kind"] == "data"
    assert body["row_count"] == 2
    assert body["sheets"][0]["columns"] == ["Account No", "Amount"]
    assert body["sheets"][0]["rows"] == [[11, 100], [12, 100]]

    evs = events(client.post(f"{BASE}/summarize", json={"file_id": body["file_id"]}))
    assert evs[-1]["type"] == "done"
    user = fake.requests[0]["messages"][1]["content"]
    assert "Amount (number): 2 values; total 200" in user


def test_pdf_notice_returned(env):
    client, _, _, _ = env
    body = upload(client, "doc.pdf", make_pdf(["Text page", None])).json()
    assert body["notices"] == [
        "Skipped page 2: no readable text. Scanned pages are not supported yet."
    ]


def test_summarize_pasted_text(env):
    client, fake, _, _ = env
    evs = events(client.post(f"{BASE}/summarize", json={"text": "Some pasted text."}))
    assert evs[-1]["type"] == "done"
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    "payload", [{}, {"text": "a", "file_id": "b"}, {"text": "   "}]
)
def test_summarize_bad_requests(env, payload):
    client, fake, _, _ = env
    resp = client.post(f"{BASE}/summarize", json=payload)
    assert resp.status_code == 400
    assert fake.requests == []


def test_summarize_too_long_rejected_before_sending(env):
    client, fake, _, _ = env
    resp = client.post(f"{BASE}/summarize", json={"text": "word " * 60_001})
    assert resp.status_code == 413
    assert "60,000" in resp.json()["detail"]
    assert fake.requests == []


def test_delete_then_summarize_is_expired(env):
    client, _, _, _ = env
    file_id = upload(client, "a.txt", b"hello").json()["file_id"]
    assert client.delete(f"{BASE}/files/{file_id}").status_code == 204
    assert client.delete(f"{BASE}/files/{file_id}").status_code == 204
    resp = client.post(f"{BASE}/summarize", json={"file_id": file_id})
    assert resp.status_code == 410
    assert resp.json()["detail"] == "This file has expired. Please upload it again."


def test_old_file_is_expired(env):
    client, _, store, _ = env
    saved = store.save("a.txt", b"hello", now=0)
    resp = client.post(f"{BASE}/summarize", json={"file_id": saved.id})
    assert resp.status_code == 410


def test_ollama_down_gives_plain_error_event(env):
    client, fake, _, _ = env
    fake.down = True
    evs = events(client.post(f"{BASE}/summarize", json={"text": "Hello there."}))
    assert evs == [
        {
            "type": "error",
            "code": "llm_unavailable",
            "message": da_router.LLM_UNAVAILABLE,
        }
    ]


def test_context_error_gives_too_long_event(env):
    client, fake, _, state = env
    state["num_ctx"] = 2100  # stats prompt plus the 2048-token output budget cannot fit
    content = b"a,b\n1,2\n3,3\n"
    file_id = upload(client, "d.csv", content).json()["file_id"]
    evs = events(client.post(f"{BASE}/summarize", json={"file_id": file_id}))
    assert evs[-1]["code"] == "too_long"
    assert fake.requests == []


@pytest.mark.parametrize(
    "name, content, status, phrase",
    [
        ("virus.exe", b"MZ", 415, "not allowed"),
        ("empty.txt", b"", 400, "empty"),
        ("fake.pdf", b"hello", 415, "does not match"),
        ("scan.pdf", make_pdf([None]), 422, "scanned"),
        ("big.csv", ("n\n" + "1\n" * 10_001).encode(), 413, "10,000"),
        ("list.json", b"[1, 2]", 422, "not a table"),
    ],
)
def test_upload_errors(env, name, content, status, phrase):
    client, _, store, _ = env
    resp = upload(client, name, content)
    assert resp.status_code == status
    assert phrase in resp.json()["detail"]
    assert not store.root.exists() or not any(store.root.iterdir())
