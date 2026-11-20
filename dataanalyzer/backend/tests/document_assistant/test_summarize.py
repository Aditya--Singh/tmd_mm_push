import asyncio

import pandas as pd
import pytest

from app.core.ollama import estimate_tokens
from app.tabs.document_assistant.extraction import DataSheet
from app.tabs.document_assistant.summarize import (
    MAX_SUMMARY_WORDS,
    SUMMARY_OUTPUT_TOKENS,
    SummaryTooLong,
    check_length,
    data_prompt,
    split_into_chunks,
    summarize_data,
    summarize_text,
)
from tests.docgen import make_document

from .mock_ollama import FakeOllama


def collect(agen):
    async def run():
        return [e async for e in agen]

    return asyncio.run(run())


def text_of(events):
    return "".join(e.text for e in events if e.type == "chunk")


def test_short_text_is_one_streamed_request():
    fake = FakeOllama(reply="A short summary.")
    events = collect(summarize_text("The branch opened on Monday.", fake.client()))
    assert text_of(events) == "A short summary."
    assert len(fake.requests) == 1
    req = fake.requests[0]
    assert req["stream"] is True
    assert req["options"]["num_ctx"] == 32768
    assert "The branch opened on Monday." in req["messages"][1]["content"]
    assert "Never add" in req["messages"][0]["content"]


def test_twenty_page_document_is_sent_in_full_in_one_request():
    marker = "The closing reference code is ZX-4417."
    doc = make_document(pages=20, last_line=marker)
    fake = FakeOllama()
    collect(summarize_text(doc, fake.client()))
    assert len(fake.requests) == 1
    assert marker in fake.requests[0]["messages"][1]["content"]


def test_long_text_is_chunked_and_every_request_fits():
    num_ctx = 4096
    marker = "The final marker sentence is QW-9031."
    doc = make_document(pages=6, last_line=marker)
    fake = FakeOllama(reply="Combined summary.")
    events = collect(summarize_text(doc, fake.client(num_ctx=num_ctx)))

    chunk_reqs = [r for r in fake.requests if not r["stream"]]
    final = [r for r in fake.requests if r["stream"]]
    assert len(chunk_reqs) > 1
    assert len(final) == 1
    for req in fake.requests:
        assert req["options"]["num_ctx"] == num_ctx
        assert estimate_tokens(req["messages"]) < num_ctx
    # Nothing is lost: the last line reaches the model, and every word is sent once.
    assert marker in chunk_reqs[-1]["messages"][1]["content"]
    sent = sum(len(r["messages"][1]["content"].split()) for r in chunk_reqs)
    assert sent >= len(doc.split())
    # The combine step sees every partial summary.
    combined = final[0]["messages"][1]["content"]
    for i in range(1, len(chunk_reqs) + 1):
        assert f"- partial {i}" in combined
    statuses = [e.text for e in events if e.type == "status"]
    assert statuses[0] == f"Reading part 1 of {len(chunk_reqs)}…"
    assert statuses[-1] == "Combining the parts…"
    assert text_of(events) == "Combined summary."


def test_split_into_chunks_respects_limit_and_keeps_text():
    text = "\n\n".join(["word " * 50, "x" * 500, "short"])
    chunks = split_into_chunks(text, 120)
    assert all(len(c) <= 120 for c in chunks)
    assert "".join(chunks).replace("\n", "").replace(" ", "") == text.replace(
        "\n", ""
    ).replace(" ", "")


def test_over_length_text_rejected():
    with pytest.raises(SummaryTooLong) as err:
        check_length("word " * (MAX_SUMMARY_WORDS + 1))
    assert "60,000" in str(err.value)
    with pytest.raises(SummaryTooLong):
        collect(
            summarize_text("word " * (MAX_SUMMARY_WORDS + 1), FakeOllama().client())
        )


def _loans():
    return pd.DataFrame(
        {
            "Account No": ["1001", "1002", "1003"],
            "Customer": [f"Customer Name {i}" for i in range(3)],
            "Amount": ["1,25,000", "₹ 2,50,000.00", "(5,000)"],
            "Opened": ["05/01/2026", "20/03/2026", "01/02/2026"],
        }
    )


def test_data_prompt_uses_stats_not_rows():
    prompt = data_prompt([DataSheet("Loans", _loans())])
    user = prompt[1]["content"]
    assert "Rows: 3" in user
    assert "Amount (number): 3 values; total 3,70,000" in user
    assert "Account No (identifier): 3 values; 3 distinct" in user
    assert "from 05 Jan 2026 to 20 Mar 2026" in user
    # Identifier values never appear.
    assert "1001" not in user


def test_data_prompt_omits_free_text_values():
    frame = pd.DataFrame({"Remarks": [f"unique remark {i}" for i in range(60)]})
    user = data_prompt([DataSheet("S", frame)])[1]["content"]
    assert "60 distinct" in user
    assert "unique remark" not in user


def test_summarize_data_streams():
    fake = FakeOllama(reply="Three loans.")
    events = collect(summarize_data([DataSheet("Loans", _loans())], fake.client()))
    assert text_of(events) == "Three loans."
    assert fake.requests[0]["options"]["num_ctx"] == 32768
    assert fake.requests[0]["options"]["num_ctx"] >= SUMMARY_OUTPUT_TOKENS
