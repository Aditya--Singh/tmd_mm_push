"""HTTP tests for Rewrite, Proofread, export and download (phase 3)."""

import io
import json
import re
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app import main
from app.core.session import current_session, require_admin
from app.tabs.document_assistant import router as da_router
from app.tabs.document_assistant import segments
from app.tabs.document_assistant.file_store import FileStore, get_store

from .fixtures import make_docx_with_tracked_change, make_rich_docx, make_xlsx
from .mock_ollama import FakeLanguageTool, FakeOllama
from .test_router import BASE, events, upload

LETTER_PATH = (
    Path(__file__).resolve().parents[3] / "samples" / "test_proofread_letter.docx"
)
_TEXT = re.compile(r"<text>\n(.*)\n</text>", re.DOTALL)


def model(body: dict) -> str:
    """Rewrite: prefix each paragraph. Proofread: suggest "kindly" for "please"."""
    sent = _TEXT.search(body["messages"][1]["content"]).group(1)
    if body["stream"]:
        return "\n\n".join(f"Kindly note: {p}" for p in sent.split("\n\n"))
    found = (
        [{"original": "Please", "replacement": "Kindly", "explanation": "More formal."}]
        if "Please" in sent
        else []
    )
    return json.dumps({"issues": found})


@pytest.fixture
def env(tmp_path):
    fake = FakeOllama(responder=model)
    lt = FakeLanguageTool({"manger": "manager", "websit": "website", "Teh": "The"})
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
    yield TestClient(main.app), fake, lt, store
    main.app.dependency_overrides.clear()


def result_of(resp) -> dict:
    evs = events(resp)
    assert evs[-1] == {"type": "done"}
    return next(e for e in evs if e["type"] == "result")


def download(client, file_id: str):
    resp = client.get(f"{BASE}/download/{file_id}")
    assert resp.status_code == 200
    return resp


def docx_texts(content: bytes) -> list[str]:
    return [p.text for p in Document(io.BytesIO(content)).paragraphs if p.text]


# ---------------------------------------------------------------- rewrite


def test_rewrite_pasted_text_streams_sections(env):
    client, fake, _, _ = env
    resp = client.post(
        f"{BASE}/rewrite", json={"text": "First.\n\nSecond.", "style": "polite"}
    )
    evs = events(resp)
    assert evs[0]["type"] == "source"
    assert evs[-1] == {"type": "done"}
    end = next(e for e in evs if e["type"] == "section_end")
    assert end["texts"] == ["Kindly note: First.", "Kindly note: Second."]
    assert "customer-friendly" in fake.requests[0]["messages"][0]["content"]


def test_rewrite_rejects_bad_style_and_over_length(env):
    client, fake, _, _ = env
    assert (
        client.post(
            f"{BASE}/rewrite", json={"text": "a", "style": "casual"}
        ).status_code
        == 422
    )
    resp = client.post(f"{BASE}/rewrite", json={"text": "word " * 11_001})
    assert resp.status_code == 413
    assert "Rewrite accepts" in resp.json()["detail"]
    assert fake.requests == []


def test_rewrite_rejects_data_files_and_tracked_changes(env):
    client, _, _, _ = env
    import pandas as pd

    data_id = upload(
        client, "d.xlsx", make_xlsx({"S": pd.DataFrame({"a": [1]})})
    ).json()["file_id"]
    assert client.post(f"{BASE}/rewrite", json={"file_id": data_id}).status_code == 422
    # A file with tracked changes is rejected at upload, so it never reaches Rewrite.
    assert upload(client, "t.docx", make_docx_with_tracked_change()).status_code == 422


def test_rewrite_ollama_down_gives_error_event(env):
    client, fake, _, _ = env
    fake.down = True
    evs = events(client.post(f"{BASE}/rewrite", json={"text": "Hello."}))
    assert evs[-1]["code"] == "llm_unavailable"


def test_rewrite_docx_then_export_in_place(env):
    client, _, _, _ = env
    file_id = upload(client, "letter.docx", make_rich_docx()).json()["file_id"]
    evs = events(client.post(f"{BASE}/rewrite", json={"file_id": file_id}))
    source = [p["text"] for p in evs[0]["paragraphs"]]
    for e in evs:
        if e["type"] == "section_end":
            for i, t in zip(e["paragraphs"], e["texts"]):
                source[i] = t
    resp = client.post(
        f"{BASE}/export",
        json={"text": "\n\n".join(source), "format": "docx", "source_file_id": file_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "letter-edited.docx"
    assert any("formatting" in w for w in body["warnings"])
    after = segments.from_docx(download(client, body["file_id"]).content)
    texts = [s.text for s in after.segments]
    assert texts[0] == "Kindly note: KYC Update"
    assert texts[3] == "Visit our websit today."  # link paragraph untouched
    assert texts[4:8] == ["Account", "Amount", "Savings", "1,000"]


def test_export_docx_paragraph_count_mismatch_is_rejected(env):
    client, _, _, _ = env
    file_id = upload(client, "letter.docx", make_rich_docx()).json()["file_id"]
    resp = client.post(
        f"{BASE}/export",
        json={
            "text": "Only one paragraph.",
            "format": "docx",
            "source_file_id": file_id,
        },
    )
    assert resp.status_code == 422
    assert "blank line between paragraphs" in resp.json()["detail"]


def test_export_txt_keeps_crlf_and_bom(env):
    client, _, _, _ = env
    file_id = upload(
        client, "n.txt", b"\xef\xbb\xbfLine one.\r\n\r\nLine two.\r\n"
    ).json()["file_id"]
    body = client.post(
        f"{BASE}/export",
        json={"text": "Line 1.\n\nLine 2.", "format": "txt", "source_file_id": file_id},
    ).json()
    assert body["filename"] == "n-edited.txt"
    resp = download(client, body["file_id"])
    assert resp.content == b"\xef\xbb\xbfLine 1.\r\n\r\nLine 2."
    assert resp.headers["content-type"].startswith("text/plain")
    assert 'filename="n-edited.txt"' in resp.headers["content-disposition"]


def test_export_pasted_text_as_new_docx(env):
    client, _, _, _ = env
    body = client.post(
        f"{BASE}/export", json={"text": "Dear Sir,\n\nThank you.", "format": "docx"}
    ).json()
    assert body["filename"] == "document-edited.docx"
    assert body["warnings"] == []
    assert docx_texts(download(client, body["file_id"]).content) == [
        "Dear Sir,",
        "Thank you.",
    ]


# ---------------------------------------------------------------- proofread


def test_proofread_text_and_apply(env):
    client, _, _, _ = env
    text = "Teh branch is open.\n\nPlease visit."
    result = result_of(client.post(f"{BASE}/proofread", json={"text": text}))
    assert result["text"] == text
    spans = [(text[s["start"] : s["end"]], s["source"]) for s in result["suggestions"]]
    assert spans == [("Teh", "languagetool"), ("Please", "llm")]
    accepted = [
        {"start": s["start"], "end": s["end"], "replacement": s["replacements"][0]}
        for s in result["suggestions"]
    ]
    resp = client.post(
        f"{BASE}/proofread/apply", json={"text": text, "accepted": accepted}
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "text": "The branch is open.\n\nKindly visit.",
        "warnings": [],
    }


def test_proofread_docx_apply_writes_file_in_place(env):
    client, _, _, _ = env
    file_id = upload(client, "circular.docx", make_rich_docx()).json()["file_id"]
    result = result_of(client.post(f"{BASE}/proofread", json={"file_id": file_id}))
    by_text = {result["text"][s["start"] : s["end"]]: s for s in result["suggestions"]}
    assert by_text["manger"]["applicable"] is True
    assert by_text["websit"]["applicable"] is False

    accepted = [
        {"start": s["start"], "end": s["end"], "replacement": s["replacements"][0]}
        for s in result["suggestions"]
    ]
    body = client.post(
        f"{BASE}/proofread/apply", json={"file_id": file_id, "accepted": accepted}
    ).json()
    assert body["filename"] == "circular-proofread.docx"
    assert "The branch manager will review it." in body["text"]
    assert "our websit" in body["text"]  # not applicable, so not applied
    doc = Document(io.BytesIO(download(client, body["file_id"]).content))
    p = doc.paragraphs[1]
    assert p.text == "The branch manager will review it."
    assert [r.bold for r in p.runs] == [None, True, None]
    assert (
        doc.sections[0].header.paragraphs[0].text == "Punjab National Bank - Letterhead"
    )


def test_proofread_apply_overlap_rejected(env):
    client, _, _, _ = env
    resp = client.post(
        f"{BASE}/proofread/apply",
        json={
            "text": "abcdef",
            "accepted": [
                {"start": 0, "end": 3, "replacement": "x"},
                {"start": 2, "end": 4, "replacement": "y"},
            ],
        },
    )
    assert resp.status_code == 422


def test_proofread_both_services_down(env):
    client, fake, lt, _ = env
    fake.down = True
    lt.down = True
    evs = events(client.post(f"{BASE}/proofread", json={"text": "Hello."}))
    assert evs[-1]["type"] == "error"
    assert evs[-1]["message"] == da_router.PROOFREAD_UNAVAILABLE


def test_proofread_languagetool_down_still_returns(env):
    client, _, lt, _ = env
    lt.down = True
    result = result_of(client.post(f"{BASE}/proofread", json={"text": "Please wait."}))
    assert [s["source"] for s in result["suggestions"]] == ["llm"]
    assert len(result["notices"]) == 1


# ---------------------------------------------------------------- download


def test_download_unknown_or_expired_is_410(env):
    client, _, _, store = env
    assert client.get(f"{BASE}/download/{'x' * 43}").status_code == 410
    old = store.save("a.txt", b"hi", now=0)
    assert client.get(f"{BASE}/download/{old.id}").status_code == 410


def test_download_original_upload(env):
    client, _, _, _ = env
    file_id = upload(client, "a.txt", b"hello").json()["file_id"]
    assert download(client, file_id).content == b"hello"


def test_export_docx_ignores_whitespace_only_edits(env):
    client, _, _, _ = env
    file_id = upload(client, "letter.docx", make_rich_docx()).json()["file_id"]
    doc = segments.from_docx(make_rich_docx())
    texts = [s.text for s in doc.segments]
    texts[1] = "The  branch manger will review it. "  # whitespace only
    body = client.post(
        f"{BASE}/export",
        json={"text": "\n\n".join(texts), "format": "docx", "source_file_id": file_id},
    ).json()
    p = Document(io.BytesIO(download(client, body["file_id"]).content)).paragraphs[1]
    assert [r.bold for r in p.runs] == [None, True, None]  # runs untouched


def test_export_saves_manual_edits_to_formalities(env):
    """Rewrite never changes formalities, but the user may edit them by hand."""
    client, _, _, _ = env
    letter = (LETTER_PATH).read_bytes()
    file_id = upload(client, "letter.docx", letter).json()["file_id"]
    texts = [s.text for s in segments.from_docx(letter).segments]
    texts[5] = "Dear Madam,"
    body = client.post(
        f"{BASE}/export",
        json={"text": "\n\n".join(texts), "format": "docx", "source_file_id": file_id},
    ).json()
    after = segments.from_docx(download(client, body["file_id"]).content)
    assert after.segments[5].text == "Dear Madam,"
    assert any("letter formalities" in w for w in body["warnings"])


# ------------------------------------- regression: letter formalities in the sample letter

FORMALITY_TEXTS = [
    "Ref: ZO/JPR/ADV/2026/112\t\t\tDate: 15.10.2026",
    "To,\nThe Branch Manager,\nUdaipur Main Branch",
    "Subject: Recovery of overdue NPA accounts and KYC compliance",
    "Dear Sir,",
    "Yours faithfully,",
    "(R. K. Verma)\nDeputy General Manager",
]


def careless_polite(body: dict) -> str:
    """A model that rewrites everything it sees, turns closings into "With warm regards,",
    and tacks a closing onto the last paragraph it is given."""
    sent = _TEXT.search(body["messages"][1]["content"]).group(1).split("\n\n")
    out = [
        "With warm regards," if p.startswith("Yours") else f"Kindly note: {p}"
        for p in sent
    ]
    out[-1] += "\nWith warm regards,"
    return "\n\n".join(out)


def rewrite_events(client, payload) -> list[dict]:
    evs = events(client.post(f"{BASE}/rewrite", json={**payload, "style": "polite"}))
    assert evs[-1] == {"type": "done"}
    return evs


def joined(evs) -> str:
    """The rewritten text exactly as the browser builds it."""
    src = evs[0]["paragraphs"]
    out = [p["text"] for p in src]
    for e in evs:
        if e["type"] == "section_end":
            for i, t in zip(e["paragraphs"], e["texts"]):
                out[i] = t
    return "".join(
        (p.get("before", "\n\n") if i else "") + t
        for i, (p, t) in enumerate(zip(src, out))
    )


def _paragraph_xml(content: bytes) -> dict[str, bytes]:
    from lxml import etree

    return {
        p.text: etree.tostring(p._p)
        for p in Document(io.BytesIO(content)).paragraphs
        if p.text in FORMALITY_TEXTS
    }


def test_sample_letter_formalities_byte_identical_after_polite_rewrite(env):
    client, fake, _, _ = env
    fake.responder = careless_polite
    letter = LETTER_PATH.read_bytes()
    file_id = upload(client, "letter.docx", letter).json()["file_id"]
    evs = rewrite_events(client, {"file_id": file_id})

    sent = "\n".join(b["messages"][1]["content"] for b in fake.requests)
    for text in FORMALITY_TEXTS:
        assert text not in sent
    text = joined(evs)
    assert "With warm regards," not in text  # the added closing was rejected
    for formality in FORMALITY_TEXTS:
        assert formality in text

    body = client.post(
        f"{BASE}/export",
        json={"text": text, "format": "docx", "source_file_id": file_id},
    ).json()
    exported = download(client, body["file_id"]).content
    before, after = _paragraph_xml(letter), _paragraph_xml(exported)
    assert sorted(before) == sorted(FORMALITY_TEXTS)
    assert after == before  # every formality paragraph is byte-identical XML


def test_sample_letter_pasted_without_blank_lines_keeps_formalities(env):
    client, fake, _, _ = env
    fake.responder = careless_polite
    paragraphs = [
        p.text for p in Document(io.BytesIO(LETTER_PATH.read_bytes())).paragraphs
    ]
    pasted = "\n".join(p for p in paragraphs if p.strip())  # as copied out of Word
    evs = rewrite_events(client, {"text": pasted})

    sent = "\n".join(b["messages"][1]["content"] for b in fake.requests)
    for line in ("Dear Sir,", "Yours faithfully,", "(R. K. Verma)", "To,"):
        assert line not in sent
    text = joined(evs)
    assert "With warm regards," not in text
    lines = text.split("\n")
    for formality in FORMALITY_TEXTS:
        for line in formality.split("\n"):
            assert line in lines  # each formality line survives byte for byte
    assert text.startswith(pasted.split("Dear Sir,")[0] + "Dear Sir,\n")
    assert text.endswith("\nYours faithfully,\n(R. K. Verma)\nDeputy General Manager")
