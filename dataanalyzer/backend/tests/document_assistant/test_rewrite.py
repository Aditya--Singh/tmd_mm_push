import asyncio
import re
from pathlib import Path

import pytest

from app.core.ollama import estimate_tokens
from app.tabs.document_assistant import segments
from app.tabs.document_assistant.rewrite import (
    SECTION_MAX_CHARS,
    SECTION_MAX_PARAGRAPHS,
    STYLE_SYSTEM,
    DocumentTooLong,
    check_length,
    new_numbers,
    plain_characters,
    plan_sections,
    rewrite_document,
    split_paragraphs,
    validate,
)
from tests.docgen import make_document

from .fixtures import make_rich_docx
from .mock_ollama import FakeOllama

_TEXT = re.compile(r"<text>\n(.*)\n</text>", re.DOTALL)


def paragraphs_sent(body: dict) -> list[str]:
    return _TEXT.search(body["messages"][1]["content"]).group(1).split("\n\n")


def echo(body: dict) -> str:
    """A well-behaved model: rewrites each paragraph, keeping the count and numbers."""
    return "\n\n".join(f"Kindly note: {p}" for p in paragraphs_sent(body))


def run(doc, style="formal", fake=None, num_ctx=None):
    fake = fake or FakeOllama(responder=echo)

    async def collect():
        return [e async for e in rewrite_document(doc, style, fake.client(num_ctx))]

    return asyncio.run(collect()), fake


def final_paragraphs(events) -> list[str]:
    source = next(e for e in events if e["type"] == "source")
    result = [p["text"] for p in source["paragraphs"]]
    for e in events:
        if e["type"] == "section_end":
            for i, text in zip(e["paragraphs"], e["texts"]):
                result[i] = text
    return result


def test_sections_keep_paragraph_boundaries_and_limits():
    doc = segments.from_text(make_document(pages=20))
    sections = plan_sections(doc.segments)
    flat = [i for s in sections for i in s]
    assert flat == list(range(len(doc.segments)))
    for s in sections:
        assert len(s) <= SECTION_MAX_PARAGRAPHS
        size = sum(len(doc.segments[i].text) for i in s) + 2 * (len(s) - 1)
        assert size <= SECTION_MAX_CHARS or len(s) == 1


def test_long_paragraph_is_a_section_of_its_own():
    doc = segments.from_text("Short.\n\n" + "word " * 2000 + "\n\nShort again.")
    assert plan_sections(doc.segments) == [[0], [1], [2]]


def test_sections_never_span_skipped_paragraphs():
    doc = segments.from_docx(make_rich_docx())
    # 3 has a link, 4-7 are table cells: none are sent to the model.
    assert plan_sections(doc.segments) == [[0, 1, 2], [8, 9]]


def test_twenty_page_document_is_rewritten_in_sections_inside_num_ctx():
    text = make_document(pages=20, last_line="The final marker is ZX-4471.")
    doc = segments.from_text(text)
    events, fake = run(doc)
    sections = plan_sections(doc.segments)
    assert len(fake.requests) == len(sections) > 10
    for body in fake.requests:
        assert body["options"]["num_ctx"] == 32768
        assert len(paragraphs_sent(body)) <= SECTION_MAX_PARAGRAPHS
        assert estimate_tokens(body["messages"]) < 32768 // 4
    assert events[-1]["type"] == "section_end"
    out = final_paragraphs(events)
    assert len(out) == len(doc.segments)
    assert out[-1] == "Kindly note: The final marker is ZX-4471."
    assert all(o.startswith("Kindly note: ") for o in out)


def test_events_stream_chunks_per_section():
    doc = segments.from_text("One.\n\nTwo.")
    events, _ = run(doc)
    types = [e["type"] for e in events]
    assert types[:3] == ["source", "status", "section_start"]
    assert "chunk" in types
    chunks = "".join(e["text"] for e in events if e["type"] == "chunk")
    assert chunks == "Kindly note: One.\n\nKindly note: Two."


def test_paragraph_count_mismatch_is_retried_then_kept_unchanged():
    doc = segments.from_text("First paragraph.\n\nSecond paragraph.")
    fake = FakeOllama(responder=lambda body: "Both paragraphs merged into one.")
    events, fake = run(doc, fake=fake)
    assert len(fake.requests) == 2
    assert final_paragraphs(events) == ["First paragraph.", "Second paragraph."]
    notices = [e["text"] for e in events if e["type"] == "notice"]
    assert any("left unchanged" in n for n in notices)


def test_retry_succeeds_on_second_attempt():
    doc = segments.from_text("First paragraph.\n\nSecond paragraph.")
    replies = iter(["Merged.", "Para one.\n\nPara two."])
    fake = FakeOllama(responder=lambda body: next(replies))
    events, fake = run(doc, fake=fake)
    assert len(fake.requests) == 2
    assert final_paragraphs(events) == ["Para one.", "Para two."]
    assert sum(e["type"] == "section_start" for e in events) == 2
    assert not [e for e in events if e["type"] == "notice"]


def test_output_with_new_numbers_is_rejected():
    doc = segments.from_text("Your loan of Rs 5,00,000 is sanctioned.")
    fake = FakeOllama(
        responder=lambda body: (
            "Your loan of Rs 5,00,000 at 9.5% interest is sanctioned."
        )
    )
    events, fake = run(doc, fake=fake)
    assert len(fake.requests) == 2
    assert final_paragraphs(events) == ["Your loan of Rs 5,00,000 is sanctioned."]


def test_numbers_in_output_appear_in_input():
    source = "Pay Rs 1,00,000 by 05 March 2026 from account 0012345."
    assert (
        new_numbers(source, "Please pay Rs 100000 by 5 March 2026 from account 12345.")
        == set()
    )
    assert new_numbers(source, "Pay Rs 2,00,000 by 05 March 2026.") == {"200000"}
    assert new_numbers("Rate 7.50%", "Rate 7.5%") == {"7.5"}


def test_docx_skipped_paragraphs_pass_through_with_notice():
    doc = segments.from_docx(make_rich_docx())
    events, _ = run(doc)
    source = next(e for e in events if e["type"] == "source")["paragraphs"]
    assert [p["editable"] for p in source] == [
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        True,
        True,
    ]
    out = final_paragraphs(events)
    assert out[3] == "Visit our websit today."
    assert out[4:8] == ["Account", "Amount", "Savings", "1,000"]
    assert out[1] == "Kindly note: The branch manger will review it."
    assert any(e["type"] == "notice" and "table" in e["text"] for e in events)


@pytest.mark.parametrize(
    "style, phrase", [("formal", "formal, official"), ("polite", "customer-friendly")]
)
def test_style_prompts(style, phrase):
    _, fake = run(segments.from_text("Hello."), style=style)
    system = fake.requests[0]["messages"][0]["content"]
    assert system == STYLE_SYSTEM[style]
    assert phrase in system
    assert "Never add facts" in system
    assert "same number of paragraphs" in system


def test_unknown_style_rejected():
    with pytest.raises(ValueError):
        run(segments.from_text("Hello."), style="casual")


def test_over_length_document_rejected():
    check_length("word " * 11_000)
    with pytest.raises(DocumentTooLong, match="Rewrite accepts up to 11,000 words"):
        check_length("word " * 11_001)


def test_split_paragraphs_strips_echoed_tags():
    assert split_paragraphs("<text>\nOne.\n\n\nTwo.\n</text>") == ["One.", "Two."]


def test_lookalike_characters_are_made_plain_unless_in_source():
    doc = segments.from_text("Call 0294-2410000 about Rs 5,00,000.")
    fake = FakeOllama(
        responder=lambda body: "Please call 0294\u20112410000 about Rs\u202f5,00,000."
    )
    events, _ = run(doc, fake=fake)
    assert final_paragraphs(events) == ["Please call 0294-2410000 about Rs 5,00,000."]
    # The streamed chunks are the raw model output; the section result is cleaned.
    assert plain_characters("a\u00a0b", "a\u00a0b") == "a\u00a0b"


def test_whitespace_only_changes_keep_the_source_paragraph():
    doc = segments.from_text(
        "Branch        Udaipur, deposits        Rs. 5,000\n\nPlease comply."
    )
    fake = FakeOllama(
        responder=lambda body: "Branch Udaipur, deposits Rs. 5,000\n\nKindly comply."
    )
    events, _ = run(doc, fake=fake)
    assert final_paragraphs(events) == [
        "Branch        Udaipur, deposits        Rs. 5,000",
        "Kindly comply.",
    ]


# ---------------------------------------------------------------- letter formalities

LETTER = Path(__file__).resolve().parents[3] / "samples" / "test_proofread_letter.docx"
FORMALITIES = [
    "Ref: ZO/JPR/ADV/2026/112\t\t\tDate: 15.10.2026",
    "To,\nThe Branch Manager,\nUdaipur Main Branch",
    "Subject: Recovery of overdue NPA accounts and KYC compliance",
    "Dear Sir,",
    "Yours faithfully,",
    "(R. K. Verma)\nDeputy General Manager",
]


def test_letter_formalities_are_never_sent_or_changed():
    doc = segments.from_docx(LETTER.read_bytes())

    def careless_model(body):
        # Rewrites everything it is given, including any closing it sees.
        return "\n\n".join(
            "With warm regards," if p == "Yours faithfully," else f"Kindly note: {p}"
            for p in paragraphs_sent(body)
        )

    events, fake = run(doc, fake=FakeOllama(responder=careless_model))
    sent = "\n".join(b["messages"][1]["content"] for b in fake.requests)
    for formality in FORMALITIES:
        assert formality not in sent
    out = final_paragraphs(events)
    for formality in FORMALITIES:
        assert formality in out
    assert "With warm regards," not in out
    assert out[6].startswith("Kindly note: We have recieved")
    source = next(e for e in events if e["type"] == "source")["paragraphs"]
    assert source[17] == {
        "text": "Yours faithfully,",
        "editable": False,
        "reason": "letter formality",
        "before": "\n\n",
    }
    notices = [e["text"] for e in events if e["type"] == "notice"]
    assert any("8 letter formality paragraph(s)" in n for n in notices)


def test_pasted_letter_keeps_salutation_and_closing():
    text = "Dear Sir,\n\nWe got your letter.\n\nYours sincerely,\n\nBranch Manager"
    events, fake = run(segments.from_text(text))
    assert len(fake.requests) == 1
    assert paragraphs_sent(fake.requests[0]) == ["We got your letter."]
    assert final_paragraphs(events) == [
        "Dear Sir,",
        "Kindly note: We got your letter.",
        "Yours sincerely,",
        "Branch Manager",
    ]


def test_output_adding_a_closing_is_rejected():
    doc = segments.from_text("Please submit the report by Friday.")
    replies = iter(
        [
            "Kindly submit the report by Friday.\nWith warm regards,",
            "Kindly submit the report by Friday.",
        ]
    )
    events, fake = run(doc, fake=FakeOllama(responder=lambda body: next(replies)))
    assert len(fake.requests) == 2
    assert final_paragraphs(events) == ["Kindly submit the report by Friday."]
    assert validate(["Dear Sir,"], ["Dear Sir,"]) is None  # unchanged formality is fine
