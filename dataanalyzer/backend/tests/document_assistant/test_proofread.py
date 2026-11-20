import asyncio
import json
from pathlib import Path

import pytest

from app.tabs.document_assistant import segments
from app.tabs.document_assistant.bank_terms import BankTerms
from app.tabs.document_assistant.proofread import (
    CHOICES_SCHEMA,
    ISSUES_SCHEMA,
    LLM_DOWN_NOTICE,
    LT_DOWN_NOTICE,
    ProofreadUnavailable,
    Suggestion,
    apply_to_text,
    llm_fix_for_span,
    merge,
    parse_issues,
    proofread_document,
)
from app.tabs.document_assistant.rewrite import DocumentTooLong
from tests.docgen import make_document

from .fixtures import make_rich_docx
from .mock_ollama import FakeLanguageTool, FakeOllama


def issues(*items) -> str:
    return json.dumps(
        {
            "issues": [
                {"original": o, "replacement": r, "explanation": e} for o, r, e in items
            ]
        }
    )


def llm(reply: str) -> FakeOllama:
    """A fake model that always gives `reply` to non-streaming requests."""
    return FakeOllama(responder=lambda body: reply)


def run(doc, fake=None, lt=None):
    fake = fake or llm(issues())
    lt = lt or FakeLanguageTool()

    async def collect():
        return [e async for e in proofread_document(doc, fake.client(), lt.client())]

    events = asyncio.run(collect())
    return events, events[-1], fake


def sug(start, end, source="llm"):
    return Suggestion(start, end, "x", "m", ["r"], source)


def test_merge_prefers_languagetool_and_drops_overlaps():
    lt = [sug(0, 5, "languagetool"), sug(20, 25, "languagetool")]
    llm = [sug(3, 10), sug(10, 15), sug(12, 18), sug(24, 30), sug(40, 41)]
    merged = merge(lt, llm)
    assert [(s.start, s.end, s.source) for s in merged] == [
        (0, 5, "languagetool"),
        (10, 15, "llm"),
        (20, 25, "languagetool"),
        (40, 41, "llm"),
    ]
    assert [s.id for s in merged] == ["s1", "s2", "s3", "s4"]


def test_merge_treats_insertions_as_one_character():
    merged = merge([sug(5, 5, "languagetool")], [sug(5, 8)])
    assert len(merged) == 1


def test_combines_both_sources_with_offsets():
    text = "Teh branch will do the needful at the earliest.\n\nAll is well."
    fake = llm(
        issues(("do the needful", "take the necessary action", "Unclear idiom."))
    )
    lt = FakeLanguageTool({"Teh": "The"})
    _, result, fake = run(segments.from_text(text), fake, lt)
    assert result["type"] == "result"
    assert result["text"] == text
    found = [
        (text[s["start"] : s["end"]], s["category"], s["source"])
        for s in result["suggestions"]
    ]
    assert found == [
        ("Teh", "spelling", "languagetool"),
        ("do the needful", "clarity", "llm"),
    ]
    assert result["suggestions"][1]["replacements"] == ["take the necessary action"]
    assert all(s["applicable"] for s in result["suggestions"])
    assert result["notices"] == []
    body = fake.requests[0]
    assert body["format"] == ISSUES_SCHEMA
    assert body["options"]["num_ctx"] == 32768
    assert lt.requests[0]["language"] == "en-GB"


def test_llm_issues_not_found_or_adding_numbers_are_dropped():
    text = "Please pay the amount soon."
    fake = llm(
        issues(
            ("not in the text", "x", "Hallucinated."),
            ("the amount", "Rs 500", "Adds a number."),
            ("soon", "soon", "No change."),
            ("pay", "remit", "Formal."),
        )
    )
    _, result, _ = run(segments.from_text(text), fake)
    assert [(s["start"], s["end"]) for s in result["suggestions"]] == [(7, 10)]


def test_invalid_json_is_retried_once():
    replies = iter(["not json at all", issues(("pay", "remit", "Formal."))])
    fake = FakeOllama(responder=lambda body: next(replies))
    _, result, fake = run(segments.from_text("Please pay."), fake)
    assert len(fake.requests) == 2
    assert len(result["suggestions"]) == 1


def test_invalid_json_twice_gives_notice_and_keeps_languagetool():
    fake = llm("still not json")
    lt = FakeLanguageTool({"Teh": "The"})
    _, result, fake = run(segments.from_text("Teh text."), fake, lt)
    assert len(fake.requests) == 2
    assert len(result["suggestions"]) == 1
    assert any(
        "Clarity could not be checked for part(s) 1" in n for n in result["notices"]
    )


def test_parse_issues_accepts_wrapped_json_and_skips_bad_items():
    reply = 'Here you go: {"issues": [{"original": "a", "replacement": "b"}, 5]}'
    assert parse_issues(reply) == [
        {
            "original": "a",
            "replacement": "b",
            "category": "clarity",
            "explanation": "Clearer wording.",
        }
    ]
    with pytest.raises(ValueError):
        parse_issues('{"problems": []}')


def test_languagetool_down_returns_llm_with_notice():
    fake = llm(issues(("pay", "remit", "Formal.")))
    _, result, _ = run(
        segments.from_text("Please pay."), fake, FakeLanguageTool(down=True)
    )
    assert [s["source"] for s in result["suggestions"]] == ["llm"]
    assert result["notices"] == [LT_DOWN_NOTICE]


def test_llm_down_returns_languagetool_with_notice():
    lt = FakeLanguageTool({"Teh": "The"})
    _, result, _ = run(segments.from_text("Teh text."), FakeOllama(down=True), lt)
    assert [s["source"] for s in result["suggestions"]] == ["languagetool"]
    assert result["notices"] == [LLM_DOWN_NOTICE]


def test_both_down_raises():
    with pytest.raises(ProofreadUnavailable):
        run(
            segments.from_text("Some text."),
            FakeOllama(down=True),
            FakeLanguageTool(down=True),
        )


def test_long_document_is_checked_in_sections():
    doc = segments.from_text(make_document(pages=20))
    events, _, fake = run(doc)
    assert len(fake.requests) > 10
    statuses = [e["text"] for e in events if e["type"] == "status"]
    assert statuses[0] == "Checking spelling and grammar…"
    assert statuses[-1].startswith(
        f"Checking grammar and clarity, part {len(fake.requests)} of"
    )


def test_over_length_document_rejected():
    with pytest.raises(DocumentTooLong, match="Proofread"):
        run(segments.from_text("word " * 11_001))


def test_docx_suggestions_in_links_are_not_applicable():
    doc = segments.from_docx(make_rich_docx())
    lt = FakeLanguageTool({"websit": "website", "manger": "manager"})
    _, result, _ = run(doc, lt=lt)
    by_text = {
        doc.text[s["start"] : s["end"]]: s["applicable"] for s in result["suggestions"]
    }
    assert by_text == {"manger": True, "websit": False}
    assert any("cannot be applied" in n for n in result["notices"])


def test_apply_to_text():
    text = "Teh branch is closd."
    assert (
        apply_to_text(text, [(14, 19, "closed"), (0, 3, "The")])
        == "The branch is closed."
    )
    assert apply_to_text("ab", [(1, 1, "X")]) == "aXb"
    with pytest.raises(ValueError):
        apply_to_text(text, [(0, 5, "a"), (3, 8, "b")])
    with pytest.raises(ValueError):
        apply_to_text(text, [(0, 99, "a")])


# ------------------------------------------------- bank terms and agreement (sample letter)

LETTER = Path(__file__).resolve().parents[3] / "samples" / "test_proofread_letter.docx"

# The nine planted errors: (text to find in the letter, text the suggestion must overlap).
PLANTED = [
    ("recieved", "recieved"),
    ("are below", "are below"),
    ("borrowers has", "borrowers has"),
    ("personaly", "personaly"),
    ("lower then", "lower then"),
    ("atleast", "atleast"),
    ("policy ,", " ,"),
    ("Bellow", "Bellow"),
    ("acounts", "acounts"),
]


def planted_spans(text: str) -> dict[str, tuple[int, int]]:
    spans = {}
    for context, error in PLANTED:
        start = text.index(context) + context.index(error)
        spans[error] = (start, start + len(error))
    return spans


def flagged(text: str, suggestions: list[dict], start: int, end: int) -> bool:
    return any(
        s["start"] < end and start < max(s["end"], s["start"] + 1) for s in suggestions
    )


def test_letter_bank_terms_are_never_flagged_mocked():
    """LanguageTool and the model both 'flag' bank terms; none of those reach the user."""
    doc = segments.from_docx(LETTER.read_bytes())
    terms = BankTerms.load()
    lt = FakeLanguageTool(
        {
            "recieved": "received",
            "personaly": "personally",
            "atleast": "at least",
            "acounts": "accounts",
            "updation": "update",
            "lakh": "lake",
            "CASA": "CASE",
            "SARFAESI": "",
        }
    )
    fake = llm(
        issues(
            ("borrowers has", "borrowers have", "Subject-verb agreement."),
            ("issued vide our letter", "issued in our letter", "Archaic."),
            ("may please be updated", "should be updated", "Awkward."),
            ("failing which", "otherwise", "Awkward."),
            ("positively", "without fail", "Odd usage."),
            ("at the earliest", "as soon as possible", "Wordy."),
        )
    )
    _, result, fake = run(doc, fake, lt)
    text = result["text"]
    found = {text[s["start"] : s["end"]] for s in result["suggestions"]}
    assert {"recieved", "personaly", "atleast", "acounts", "borrowers has"} <= found
    for start, end, term in terms.spans(text):
        assert not flagged(text, result["suggestions"], start, end), term

    system = fake.requests[0]["messages"][0]["content"]
    assert "subject-verb agreement" in system
    assert (
        "Standard Indian banking and RBI usage is correct and must not be flagged"
        in system
    )
    for term in ("vide", "updation", "may please", "SARFAESI", "CGM"):
        assert f"'{term}'" in system


def test_llm_categories_are_mapped():
    fake = llm(
        json.dumps(
            {
                "issues": [
                    {
                        "original": "has",
                        "replacement": "have",
                        "category": "grammar",
                        "explanation": "x",
                    },
                    {
                        "original": "Bellow",
                        "replacement": "Below",
                        "category": "wrong word",
                        "explanation": "x",
                    },
                    {
                        "original": "very",
                        "replacement": "",
                        "category": "nonsense",
                        "explanation": "x",
                    },
                ]
            }
        )
    )
    _, result, _ = run(segments.from_text("Borrowers has very Bellow target."), fake)
    assert [s["category"] for s in result["suggestions"]] == [
        "grammar",
        "clarity",
        "spelling",
    ]


# ---------------------------------------------------------------- choosing between options


def model_for(issues_reply: str, choices: dict[str, str] | None = None):
    """Answers the main check with `issues_reply` and the ranking request with `choices`
    (option text by flagged word)."""

    def respond(body):
        if body["format"] == CHOICES_SCHEMA:
            items = json.loads(
                body["messages"][1]["content"].split("\n", 1)[1].split(":\n", 1)[1]
            )
            return json.dumps(
                {
                    "choices": [
                        {
                            "id": it["id"],
                            "choice": (choices or {}).get(it["flagged"], ""),
                        }
                        for it in items
                    ]
                }
            )
        return issues_reply

    return FakeOllama(responder=respond)


def by_text(result) -> dict[str, dict]:
    return {result["text"][s["start"] : s["end"]]: s for s in result["suggestions"]}


def test_several_options_are_ranked_but_not_auto_accepted():
    text = "Please contact them personaly about the loan."
    lt = FakeLanguageTool({"personaly": ["personal", "personally"]})
    fake = model_for(issues(), {"personaly": "personally"})
    _, result, fake = run(segments.from_text(text), fake, lt)
    s = by_text(result)["personaly"]
    assert s["replacements"] == ["personally", "personal"]
    assert s["recommended"] is True
    assert s["auto_accept"] is False  # the user still chooses
    ranking = fake.requests[-1]
    assert ranking["format"] == CHOICES_SCHEMA
    assert "[[personaly]]" in ranking["messages"][1]["content"]


def test_llm_independent_fix_confirms_option_for_accept_all():
    text = "Please contact them personaly about the loan."
    lt = FakeLanguageTool({"personaly": ["personal", "personally"]})
    fake = model_for(
        issues(("contact them personaly", "contact them personally", "Adverb."))
    )
    _, result, fake = run(segments.from_text(text), fake, lt)
    s = by_text(result)["personaly"]
    assert s["replacements"] == ["personally", "personal"]
    assert s["auto_accept"] is True
    assert all(
        b["format"] != CHOICES_SCHEMA for b in fake.requests
    )  # no ranking needed


def test_llm_fix_that_differs_does_not_confirm():
    text = "Please contact them personaly about the loan."
    lt = FakeLanguageTool({"personaly": ["personal", "personally"]})
    fake = model_for(issues(("contact them personaly", "meet them", "Shorter.")))
    _, result, _ = run(segments.from_text(text), fake, lt)
    assert by_text(result)["personaly"]["auto_accept"] is False


def test_single_replacements_are_auto_accepted():
    lt = FakeLanguageTool({"Teh": "The"})
    fake = model_for(issues(("is open", "is now open", "Clearer.")))
    _, result, _ = run(segments.from_text("Teh branch is open."), fake, lt)
    assert [s["auto_accept"] for s in result["suggestions"]] == [True, True]
    assert [s["recommended"] for s in result["suggestions"]] == [False, False]


def test_ranking_choice_outside_options_is_ignored():
    lt = FakeLanguageTool({"personaly": ["personal", "personally"]})
    fake = model_for(issues(), {"personaly": "personalised"})
    _, result, _ = run(segments.from_text("Meet them personaly."), fake, lt)
    s = by_text(result)["personaly"]
    assert s["replacements"] == ["personal", "personally"]
    assert s["recommended"] is False
    assert s["auto_accept"] is False


def test_llm_fix_for_span():
    text = "contact them personaly today"
    lt = sug(13, 22, "languagetool")
    llm_wide = Suggestion(8, 22, "grammar", "m", ["them personally"], "llm")
    llm_narrow = Suggestion(13, 22, "grammar", "m", ["personally"], "llm")
    llm_off = Suggestion(0, 7, "grammar", "m", ["call"], "llm")
    assert llm_fix_for_span(text, lt, llm_wide) == "personally"
    assert llm_fix_for_span(text, lt, llm_narrow) == "personally"
    assert llm_fix_for_span(text, lt, llm_off) is None
