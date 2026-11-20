from pathlib import Path

from app.tabs.document_assistant import segments

from .fixtures import make_docx, make_rich_docx


def test_text_paragraphs_keep_offsets_into_original():
    text = "  First para\nsame para.\n\n\n   Second para.  \n \nThird."
    doc = segments.from_text(text)
    assert [s.text for s in doc.segments] == [
        "First para\nsame para.",
        "Second para.",
        "Third.",
    ]
    for s in doc.segments:
        assert text[s.start : s.end] == s.text
    assert doc.text == text


def test_text_segments_are_all_rewritable():
    doc = segments.from_text("One.\n\nTwo.")
    assert all(s.rewritable for s in doc.segments)


def test_locate_maps_offsets_and_rejects_cross_paragraph_spans():
    doc = segments.from_text("Alpha beta.\n\nGamma delta.")
    start = doc.text.index("delta")
    assert doc.locate(start, start + 5) == (1, 6, 11)
    assert doc.locate(5, start) is None


def test_docx_segments_cover_body_and_table_paragraphs():
    doc = segments.from_docx(
        make_docx(["First.", "", "Second."], table=[["A", "B"], ["C", "D"]])
    )
    assert [s.text for s in doc.segments] == ["First.", "Second.", "A", "B", "C", "D"]
    assert [s.in_table for s in doc.segments] == [False, False, True, True, True, True]
    assert doc.text == "First.\n\nSecond.\n\nA\n\nB\n\nC\n\nD"
    for s in doc.segments:
        assert doc.text[s.start : s.end] == s.text


def test_docx_hyperlink_text_is_locked():
    doc = segments.from_docx(make_rich_docx())
    link_para = doc.segments[3]
    assert link_para.text == "Visit our websit today."
    assert link_para.locked == ((6, 16),)
    assert not link_para.rewritable
    assert link_para.skip_reason == "contains a link, field or image"
    start = doc.text.index("websit")
    assert not doc.is_applicable(start, start + 6)
    today = doc.text.index("today")
    assert doc.is_applicable(today, today + 5)


def test_table_cells_are_not_rewritable_but_can_be_proofread():
    doc = segments.from_docx(make_rich_docx())
    cell = doc.segments[4]
    assert cell.in_table and not cell.rewritable
    assert doc.is_applicable(cell.start, cell.end)


# ---------------------------------------------------------------- letter formalities

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


def formal_texts(doc) -> list[str]:
    return [s.text for s in doc.segments if s.formality]


def test_letter_formalities_in_sample_letter():
    doc = segments.from_docx((SAMPLES / "test_proofread_letter.docx").read_bytes())
    assert [i for i, s in enumerate(doc.segments) if s.formality] == [
        0,
        1,
        2,
        3,
        4,
        5,
        17,
        18,
    ]
    assert [i for i, s in enumerate(doc.segments) if s.rewritable] == [6, 7, 8, 9, 10]
    assert "Yours faithfully," in formal_texts(doc)
    assert doc.segments[17].skip_reason == "letter formality"
    # Formalities can still be proofread and replaced by hand; only Rewrite skips them.
    assert doc.segments[17].replaceable


def test_circular_without_salutation():
    doc = segments.from_docx((SAMPLES / "test_kyc_circular.docx").read_bytes())
    formal = [i for i, s in enumerate(doc.segments) if s.formality]
    assert formal == [
        0,
        1,
        2,
        3,
        4,
        26,
    ]  # letterhead, number/date, To:, Subject:, signature
    assert doc.segments[26].text.startswith("(A. B. Sharma)")


def test_pasted_letter_formalities():
    body = (
        "Thanking you for your support during the audit, we have extended the deadline "
        "for submission of the branch returns by two weeks."
    )
    text = "\n\n".join(
        [
            "Ref. No. PNB/UDR/45",
            "Date: 15.10.2026",
            "To,\nThe Manager,\nABC Traders",
            "Sub: Renewal of cash credit limit",
            "Dear Madam,",
            body,
            "Please comply.",
            "Thanking you,",
            "Yours sincerely,",
            "Branch Manager\nUdaipur Main Branch",
        ]
    )
    doc = segments.from_text(text)
    rewritable = [s.text for s in doc.segments if s.rewritable]
    assert rewritable == [body, "Please comply."]


def test_plain_text_has_no_formalities():
    doc = segments.from_text(
        "The branch met its deposit target.\n\nRecovery of NPA accounts improved.\n\n"
        "Regards to the audit, no issues were found in the sample of accounts checked."
        "\n\nDear customer, your account is now active."
    )
    assert formal_texts(doc) == []


def test_late_dear_sir_quote_is_not_a_salutation():
    paragraphs = [f"Body paragraph {i} about deposits and loans." for i in range(14)]
    doc = segments.from_text("\n\n".join([*paragraphs, "Dear Sir,", "More body text."]))
    assert formal_texts(doc) == ["Dear Sir,"]


def test_pasted_letter_with_single_line_breaks_is_split_into_lines():
    text = (
        "Ref: ABC/12\r\nTo,\nThe Manager,\nABC Traders\nDear Sir,\n"
        "We refer to your letter.\nPlease reply soon.\nYours faithfully,\n(R. K. Verma)\nDGM"
    ).replace("\r\n", "\n")
    doc = segments.from_text(text)
    assert [s.text for s in doc.segments if s.rewritable] == [
        "We refer to your letter.",
        "Please reply soon.",
    ]
    assert len(doc.segments) == 10
    for i, s in enumerate(doc.segments):
        assert text[s.start : s.end] == s.text
        assert doc.separator_before(i) == ("" if i == 0 else "\n")


def test_hard_wrapped_prose_without_formalities_stays_one_paragraph():
    text = (
        "The branch met its target\nfor deposits this quarter\nand will review loans."
    )
    assert [s.text for s in segments.from_text(text).segments] == [text]


def test_split_blocks_keeps_line_breaks_inside_blocks():
    text = "To,\nThe Manager\n\nDear Sir,\n\n\nBody."
    assert segments.split_blocks(text) == ["To,\nThe Manager", "Dear Sir,", "Body."]
