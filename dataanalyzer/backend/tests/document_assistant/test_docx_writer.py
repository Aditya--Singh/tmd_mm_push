"""Round-trip tests for DOCX in-place edits: what spec 5.1 lists as "Kept" stays unchanged."""

import io
import zipfile
from pathlib import Path

from docx import Document
from lxml import etree

from app.tabs.document_assistant import segments
from app.tabs.document_assistant.docx_writer import (
    apply_span_edits,
    docx_paragraphs,
    new_docx,
    replace_paragraphs,
)

from .fixtures import make_emphasis_docx, make_rich_docx

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


def _paragraphs(content: bytes):
    return [p.paragraph for p in docx_paragraphs(Document(io.BytesIO(content)))]


def _part(content: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return zf.read(name)


def _xml(element) -> bytes:
    return etree.tostring(element)


def _kept_parts(content: bytes) -> dict[str, bytes]:
    """Every part except the main document body."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return {n: zf.read(n) for n in zf.namelist() if n != "word/document.xml"}


def _edit(content: bytes, index: int, old: str, new: str) -> tuple[bytes, int]:
    text = _paragraphs(content)[index].text
    start = text.index(old)
    return apply_span_edits(content, [(index, start, start + len(old), new)])


def test_fix_inside_one_run_keeps_its_formatting():
    original = make_rich_docx()
    edited, skipped = _edit(original, 1, "manger", "manager")
    assert skipped == 0
    p = _paragraphs(edited)[1]
    assert p.text == "The branch manager will review it."
    assert [(r.text, bool(r.bold)) for r in p.runs] == [
        ("The branch ", False),
        ("manager", True),
        (" will review it.", False),
    ]


def test_fix_across_runs_takes_first_run_formatting():
    original = make_rich_docx()
    edited, skipped = _edit(original, 2, "accomodate", "accommodate")
    assert skipped == 0
    p = _paragraphs(edited)[2]
    assert p.text == "Please accommodate the request."
    assert [(r.text, bool(r.bold)) for r in p.runs] == [
        ("Please accommodate", True),
        (" the request.", False),
    ]


def test_unedited_content_is_unchanged():
    original = make_rich_docx()
    edited, _ = _edit(original, 1, "manger", "manager")
    before = Document(io.BytesIO(original))
    after = Document(io.BytesIO(edited))

    # Headers, footers, styles, numbering, settings, relationships: byte for byte.
    assert _kept_parts(edited) == _kept_parts(original)
    # Page setup, tables and every paragraph that was not edited.
    assert _xml(after.sections[0]._sectPr) == _xml(before.sections[0]._sectPr)
    assert _xml(after.tables[0]._tbl) == _xml(before.tables[0]._tbl)
    pb, pa = _paragraphs(original), _paragraphs(edited)
    for i in (0, 2, 3, 8, 9):
        assert _xml(pa[i]._p) == _xml(pb[i]._p)
    assert pa[0].style.name == "Heading 1"
    assert pa[9].style.name == "List Number"


def test_fix_inside_hyperlink_is_skipped():
    original = make_rich_docx()
    edited, skipped = _edit(original, 3, "websit", "website")
    assert skipped == 1
    assert _paragraphs(edited)[3].text == "Visit our websit today."


def test_fix_next_to_hyperlink_is_applied():
    original = make_rich_docx()
    edited, skipped = _edit(original, 3, "today", "now")
    assert skipped == 0
    assert _paragraphs(edited)[3].text == "Visit our websit now."


def test_several_fixes_in_one_paragraph_and_table_cell():
    original = make_rich_docx()
    text = _paragraphs(original)[1].text
    edits = [
        (1, text.index("branch"), text.index("branch") + 6, "office"),
        (1, text.index("manger"), text.index("manger") + 6, "manager"),
        (5, 0, 6, "Sum"),
    ]
    edited, skipped = apply_span_edits(original, edits)
    assert skipped == 0
    ps = _paragraphs(edited)
    assert ps[1].text == "The office manager will review it."
    assert ps[5].text == "Sum"


def test_insertion():
    original = make_rich_docx()
    edited, _ = apply_span_edits(original, [(0, 3, 3, " Status")])
    assert _paragraphs(edited)[0].text == "KYC Status Update"


def test_rewrite_replaces_paragraph_and_keeps_style():
    original = make_rich_docx()
    edited = replace_paragraphs(
        original,
        {
            0: "KYC Status Update",
            1: "The branch manager shall review it.",
            3: "Please see the website.",  # has a link: left unchanged
        },
    )
    ps = _paragraphs(edited)
    assert ps[0].text == "KYC Status Update"
    assert ps[0].style.name == "Heading 1"
    assert ps[1].text == "The branch manager shall review it."
    assert len(ps[1].runs) == 1
    assert ps[3].text == "Visit our websit today."
    assert _kept_parts(edited) == _kept_parts(original)


def test_segment_offsets_map_to_writer_paragraphs():
    original = make_rich_docx()
    doc = segments.from_docx(original)
    start = doc.text.index("accomodate")
    index, s, e = doc.locate(start, start + len("accomodate"))
    edited, _ = apply_span_edits(original, [(index, s, e, "accommodate")])
    assert "Please accommodate the request." in segments.from_docx(edited).text


def test_sample_docx_round_trip():
    original = (SAMPLES / "test_kyc_circular.docx").read_bytes()
    doc = segments.from_docx(original)
    target = next(i for i, s in enumerate(doc.segments) if s.rewritable)
    seg = doc.segments[target]
    edited = replace_paragraphs(original, {target: seg.text + " (edited)"})
    after = segments.from_docx(edited)
    assert after.segments[target].text == seg.text + " (edited)"
    others = [s.text for i, s in enumerate(after.segments) if i != target]
    assert others == [s.text for i, s in enumerate(doc.segments) if i != target]
    assert _kept_parts(edited) == _kept_parts(original)


def test_new_docx_one_paragraph_per_block():
    content = new_docx("Dear Sir,\n\nYour account is active.\nThank you.\n\n")
    texts = [p.text for p in Document(io.BytesIO(content)).paragraphs]
    assert texts == ["Dear Sir,", "Your account is active.\nThank you."]


# ---------------------------------------------------------------- emphasis after Rewrite


def _runs(content: bytes, index: int) -> list[tuple[str, bool, bool, bool]]:
    p = _paragraphs(content)[index]
    return [(r.text, bool(r.bold), bool(r.italic), bool(r.underline)) for r in p.runs]


def test_unchanged_bold_and_italic_phrases_keep_formatting():
    edited = replace_paragraphs(
        make_emphasis_docx(),
        {0: "In this quarter, recovery in the NPA accounts remains below target."},
    )
    assert _runs(edited, 0) == [
        ("In this quarter, recovery in the ", False, False, False),
        ("NPA accounts", True, False, False),
        (" remains ", False, False, False),
        ("below target", False, True, False),
        (".", False, False, False),
    ]


def test_changed_phrase_loses_emphasis_and_text_uses_main_formatting():
    # "NPA accounts" no longer appears as is; the paragraph is mostly plain text.
    edited = replace_paragraphs(
        make_emphasis_docx(),
        {0: "Recovery in non-performing accounts is below target."},
    )
    assert _runs(edited, 0) == [
        ("Recovery in non-performing accounts is ", False, False, False),
        ("below target", False, True, False),
        (".", False, False, False),
    ]


def test_leading_bold_word_does_not_make_whole_paragraph_bold():
    edited = replace_paragraphs(
        make_emphasis_docx(),
        {1: "Note: all branches are required to submit the report."},
    )
    assert _runs(edited, 1) == [
        ("Note:", True, False, False),
        (" all branches are required to ", False, False, False),
        ("submit", False, False, True),
        (" the report.", False, False, False),
    ]


def test_phrase_split_over_runs_and_whole_words_only():
    edited = replace_paragraphs(
        make_emphasis_docx(),
        {2: "Overdue loans and overdue loansheets are rising in every zone."},
    )
    assert _runs(edited, 2) == [
        ("Overdue loans", True, False, False),
        (" and overdue loansheets are rising in every zone.", False, False, False),
    ]


def test_sample_letter_npa_accounts_stays_bold():
    original = (SAMPLES / "test_proofread_letter.docx").read_bytes()
    doc = segments.from_docx(original)
    index = next(
        i for i, s in enumerate(doc.segments) if "NPA accounts of your" in s.text
    )
    new = (
        "We have received your report dated 05.10.2026 on the NPA accounts of your "
        "branch. Recovery in these accounts is below the target of Rs. 25 lakh."
    )
    edited = replace_paragraphs(original, {index: new})
    runs = _runs(edited, index)
    assert "".join(r[0] for r in runs) == new
    assert [r[0] for r in runs if r[1]] == ["NPA accounts"]
    assert _kept_parts(edited) == _kept_parts(original)
