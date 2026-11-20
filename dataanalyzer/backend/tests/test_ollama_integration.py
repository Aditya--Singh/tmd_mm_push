"""Real-Ollama context-window test (spec section 3.8).

Opt-in: run with `uv run pytest -m ollama`. Needs Ollama running with the configured model.
"""

import asyncio
import secrets

import pytest

from app.core.ollama import OllamaClient
from tests.docgen import make_document

pytestmark = pytest.mark.ollama


def test_twenty_page_document_is_not_truncated():
    # Ollama truncates from the START of an over-long prompt, so the first-line code is the
    # real proof. It is also random per run, which defeats Ollama's prompt-prefix cache
    # (a cached prefix would lower prompt_eval_count on reruns).
    first_code = f"REF-{secrets.token_hex(3).upper()}"
    last_code = f"PNB-{secrets.token_hex(3).upper()}"
    doc = make_document(
        pages=20,
        first_line=f"The reference code is {first_code}.",
        last_line=f"The verification code is {last_code}.",
    )
    messages = [
        {
            "role": "system",
            "content": "You read documents carefully and answer with exactly what is asked.",
        },
        {
            "role": "user",
            "content": doc
            + "\n\nWhat is the reference code in the first line of the document above, "
            "and what is the verification code in its last line? "
            "Reply with the two codes only, separated by a space.",
        },
    ]
    client = OllamaClient(timeout=900.0)
    data = asyncio.run(client.chat_response(messages, options={"temperature": 0}))
    reply = data["message"]["content"]
    # Every word is at least one token, so the word count is a safe lower bound.
    words = len(doc.split())
    print(
        f"\nchars={len(doc)} words={words} "
        f"prompt_eval_count={data.get('prompt_eval_count')} reply={reply!r}"
    )
    assert first_code in reply
    assert last_code in reply
    assert data["prompt_eval_count"] >= words


def test_rewrite_keeps_paragraphs_and_numbers():
    """Phase 3: the real model rewrites a section without merging paragraphs or adding
    numbers. The rewrite's own validation retries once; the result must pass it."""
    from app.tabs.document_assistant import segments
    from app.tabs.document_assistant.rewrite import (
        new_numbers,
        rewrite_document,
    )

    source = (
        "we got ur loan application for Rs 5,00,000 on 12 March 2026.\n\n"
        "pls send the KYC docs to the branch within 15 days or the file will be closed.\n\n"
        "call the branch on 0294-2410000 if u have questions."
    )
    doc = segments.from_text(source)

    async def collect():
        client = OllamaClient(timeout=900.0)
        return [e async for e in rewrite_document(doc, "formal", client)]

    events = asyncio.run(collect())
    ends = [e for e in events if e["type"] == "section_end"]
    notices = [e["text"] for e in events if e["type"] == "notice"]
    out = [t for e in ends for t in e["texts"]]
    print(f"\nrewrite={out!r} notices={notices!r}")
    assert not notices, "the model's rewrite failed validation twice"
    assert len(out) == 3
    assert out != [s.text for s in doc.segments]
    assert new_numbers(source, "\n\n".join(out)) == set()


def test_proofread_letter_flags_planted_errors_and_no_bank_terms():
    """Regression test on samples/test_proofread_letter.docx with real Ollama and real
    LanguageTool: all nine planted errors are flagged and no bank term is touched."""
    from app.core.languagetool import LanguageToolClient
    from app.tabs.document_assistant import segments
    from app.tabs.document_assistant.bank_terms import BankTerms
    from app.tabs.document_assistant.proofread import proofread_document
    from tests.document_assistant.test_proofread import LETTER, flagged, planted_spans

    lt = LanguageToolClient()
    if not asyncio.run(lt.is_available()):
        pytest.fail("LanguageTool is not running at the configured URL")
    doc = segments.from_docx(LETTER.read_bytes())

    async def collect():
        client = OllamaClient(timeout=900.0)
        return [e async for e in proofread_document(doc, client, lt)]

    result = asyncio.run(collect())[-1]
    assert result["type"] == "result", result
    text, suggestions = result["text"], result["suggestions"]
    print(
        "\n"
        + "\n".join(
            f"{s['source']:12} {s['category']:11} {text[s['start'] : s['end']]!r} -> "
            f"{s['replacements'][:2]}"
            for s in suggestions
        )
    )
    assert result["notices"] == []
    # Accept all must never pick "personal" for "personaly": the LLM's pick comes first,
    # and with several options it is auto-accepted only if the LLM confirmed it.
    personaly = next(
        s for s in suggestions if text[s["start"] : s["end"]] == "personaly"
    )
    assert personaly["replacements"][0] == "personally"
    for s in suggestions:
        if len(s["replacements"]) > 1 and s["auto_accept"]:
            assert s["recommended"]
    missed = [
        error
        for error, (start, end) in planted_spans(text).items()
        if not flagged(text, suggestions, start, end)
    ]
    assert missed == []
    touched = [
        term
        for start, end, term in BankTerms.load().spans(text)
        if flagged(text, suggestions, start, end)
    ]
    assert touched == []


def test_polite_rewrite_keeps_sample_letter_formalities_byte_identical():
    """Regression: Rewrite (Polite) once turned "Yours faithfully," into "With warm
    regards,". Rewrite the exact sample, uploaded and pasted, with the real model."""
    import io

    from docx import Document
    from lxml import etree

    from app.tabs.document_assistant import segments
    from app.tabs.document_assistant.docx_writer import replace_paragraphs
    from app.tabs.document_assistant.rewrite import rewrite_document
    from tests.document_assistant.test_proofread import LETTER
    from tests.document_assistant.test_router_edit import FORMALITY_TEXTS

    letter = LETTER.read_bytes()

    async def rewrite(doc):
        client = OllamaClient(timeout=900.0)
        events = [e async for e in rewrite_document(doc, "polite", client)]
        out = [s.text for s in doc.segments]
        for e in events:
            if e["type"] == "section_end":
                for i, t in zip(e["paragraphs"], e["texts"]):
                    out[i] = t
        return out

    # Uploaded DOCX, saved back in place.
    doc = segments.from_docx(letter)
    out = asyncio.run(rewrite(doc))
    print(f"\nrewritten body: {out[6][:100]!r}")
    assert "With warm regards," not in "\n".join(out)
    edited = replace_paragraphs(
        letter, {i: t for i, t in enumerate(out) if doc.segments[i].rewritable}
    )

    def xml(content):
        return {
            p.text: etree.tostring(p._p)
            for p in Document(io.BytesIO(content)).paragraphs
            if p.text in FORMALITY_TEXTS
        }

    assert sorted(xml(letter)) == sorted(FORMALITY_TEXTS)
    assert xml(edited) == xml(letter)

    # The same letter pasted from Word, one line per paragraph.
    paragraphs = [p.text for p in Document(io.BytesIO(letter)).paragraphs]
    pasted = "\n".join(p for p in paragraphs if p.strip())
    doc = segments.from_text(pasted)
    out = asyncio.run(rewrite(doc))
    text = "".join(
        (doc.separator_before(i) if i else "") + t for i, t in enumerate(out)
    )
    assert "With warm regards," not in text
    lines = text.split("\n")
    for formality in FORMALITY_TEXTS:
        for line in formality.split("\n"):
            assert line in lines


def test_data_chat_computes_with_pandas_and_answers_with_its_figures():
    """Phase 4: on samples/test_loans.xlsx the real model picks operations that pandas runs,
    a follow-up question uses the earlier turn, and each answer passes the number check
    (every figure copied from the result, in Indian digit grouping)."""
    from pathlib import Path

    from app.core.uploads import ValidatedFile
    from app.tabs.document_assistant.data_chat import ask
    from app.tabs.document_assistant.extraction import extract

    path = Path(__file__).resolve().parents[2] / "samples" / "test_loans.xlsx"
    sheets = extract(ValidatedFile(path.name, ".xlsx", path.read_bytes())).sheets

    def turn(question, history):
        async def collect():
            client = OllamaClient(timeout=900.0)
            return [e async for e in ask(sheets, question, history, client)]

        events = {e["type"]: e for e in asyncio.run(collect())}
        print(
            f"\n{question!r}: operation={events.get('operation')} "
            f"rows={events.get('table', {}).get('rows')} answer={events.get('answer')} "
            f"unsupported={events.get('unsupported')} error={events.get('error')}"
        )
        return events

    first = turn("What is the total outstanding amount across all loans?", [])
    assert first["table"]["rows"] == [["97,23,750"]]
    assert first["answer"]["text"] is not None, "the answer failed the number check twice"
    assert "97,23,750" in first["answer"]["text"]

    history = [
        {
            "question": "What is the total outstanding amount across all loans?",
            "operation": first["operation"]["operation"],
            "answer": first["answer"]["text"],
        }
    ]
    second = turn("And for the Udaipur branch only?", history)
    assert second["table"]["rows"] == [["27,45,750"]]
    assert second["answer"]["text"] is not None, "the answer failed the number check twice"
    assert "27,45,750" in second["answer"]["text"]
