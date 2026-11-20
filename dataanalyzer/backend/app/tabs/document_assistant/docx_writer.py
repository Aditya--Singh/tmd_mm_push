"""Edit DOCX files in place, and build plain new DOCX files (spec section 5.1).

The editable paragraphs of a document are its non-empty body paragraphs and the paragraphs
inside table cells, in document order. Readers and writers both use `docx_paragraphs`, so a
paragraph index means the same paragraph everywhere.

Only "plain" runs are edited: runs holding nothing but text, tabs and line breaks. Runs with
fields, images, page breaks and similar content, and text inside hyperlinks, are never
touched, because python-docx would drop that content when it rewrites the run's text.
"""

import copy
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

_PLAIN_RUN_CHILDREN = {qn("w:rPr"), qn("w:t"), qn("w:tab"), qn("w:cr")}
_BR = qn("w:br")
_R = qn("w:r")


@dataclass(frozen=True)
class DocxParagraph:
    paragraph: Paragraph
    in_table: bool


def _iter_container(container, in_table: bool) -> Iterator[DocxParagraph]:
    for item in container.iter_inner_content():
        if isinstance(item, Table):
            seen: set[int] = set()
            for row in item.rows:
                for cell in row.cells:
                    # Merged cells appear once per grid column; visit each only once.
                    if id(cell._tc) in seen:
                        continue
                    seen.add(id(cell._tc))
                    yield from _iter_container(cell, in_table=True)
        else:
            yield DocxParagraph(item, in_table)


def docx_paragraphs(doc: DocumentObject) -> list[DocxParagraph]:
    """Non-empty body and table-cell paragraphs, in document order."""
    return [p for p in _iter_container(doc, False) if p.paragraph.text.strip()]


def is_plain_run(r) -> bool:
    for child in r:
        if child.tag == _BR:
            # A page or column break would come back as a plain line break.
            if child.get(qn("w:type")) not in (None, "textWrapping"):
                return False
        elif child.tag not in _PLAIN_RUN_CHILDREN:
            return False
    return True


def run_map(paragraph: Paragraph) -> list[tuple[object | None, int]]:
    """For each character of `paragraph.text`: (its run element, offset in that run).

    The element is None where the character cannot be edited (hyperlinks, non-plain runs).
    """
    chars: list[tuple[object | None, int]] = []
    for child in paragraph._p.xpath("w:r | w:hyperlink"):
        editable = child.tag == _R and is_plain_run(child)
        chars.extend((child if editable else None, i) for i in range(len(child.text)))
    return chars


def locked_spans(paragraph: Paragraph) -> list[tuple[int, int]]:
    """Character ranges of `paragraph.text` that cannot be edited."""
    spans: list[tuple[int, int]] = []
    for i, (elem, _) in enumerate(run_map(paragraph)):
        if elem is None:
            if spans and spans[-1][1] == i:
                spans[-1] = (spans[-1][0], i + 1)
            else:
                spans.append((i, i + 1))
    return spans


def _load(content: bytes) -> tuple[DocumentObject, list[DocxParagraph]]:
    doc = Document(io.BytesIO(content))
    return doc, docx_paragraphs(doc)


def _save(doc: DocumentObject) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _splice(paragraph: Paragraph, start: int, end: int, replacement: str) -> bool:
    """Replace paragraph.text[start:end]. Returns False if the span is not editable."""
    chars = run_map(paragraph)
    if not 0 <= start <= end <= len(chars):
        return False
    if start == end:
        # Pure insertion: attach to the character before, or the first one.
        anchor = start - 1 if start > 0 else 0
        if anchor >= len(chars) or chars[anchor][0] is None:
            return False
        elem, offset = chars[anchor]
        cut = offset + 1 if start > 0 else 0
        elem.text = elem.text[:cut] + replacement + elem.text[cut:]
        return True

    covered = chars[start:end]
    if any(elem is None for elem, _ in covered):
        return False
    first, a = covered[0]
    last, b = covered[-1]
    b += 1
    if first is last:
        first.text = first.text[:a] + replacement + first.text[b:]
        return True
    # Spec 5.1: a fix that spans several runs takes the formatting of the first run.
    middle = []
    for elem, _ in covered:
        if elem is not first and elem is not last and elem not in middle:
            middle.append(elem)
    first.text = first.text[:a] + replacement
    for elem in middle:
        elem.text = ""
    last.text = last.text[b:]
    return True


def apply_span_edits(
    content: bytes, edits: list[tuple[int, int, int, str]]
) -> tuple[bytes, int]:
    """Apply (paragraph index, start, end, replacement) edits in place.

    Returns the new file and the number of edits that were skipped because their text
    cannot be edited (inside a link, field or similar).
    """
    doc, paragraphs = _load(content)
    skipped = 0
    # Within a paragraph, apply from the end so earlier offsets stay valid.
    for index, start, end, replacement in sorted(
        edits, key=lambda e: (e[0], e[1], e[2]), reverse=True
    ):
        if not 0 <= index < len(paragraphs):
            skipped += 1
            continue
        if not _splice(paragraphs[index].paragraph, start, end, replacement):
            skipped += 1
    return _save(doc), skipped


_OFF = {"0", "false", "off", "none"}


def _emphasis(r) -> tuple[bool, bool, bool]:
    """(bold, italic, underline) set directly on a run."""
    rpr = r.find(qn("w:rPr"))

    def on(tag: str) -> bool:
        el = rpr.find(qn(tag)) if rpr is not None else None
        return el is not None and el.get(qn("w:val"), "true").lower() not in _OFF

    return on("w:b"), on("w:i"), on("w:u")


def _emphasised_phrases(
    runs: list, base: tuple[bool, bool, bool]
) -> list[tuple[str, object]]:
    """(phrase, template run) for each stretch of runs that is bold, italic or underlined
    differently from the paragraph's main formatting."""
    phrases: list[tuple[str, object]] = []
    group: list = []
    for r in [*runs, None]:
        if r is not None and group and _emphasis(r) == _emphasis(group[0]):
            group.append(r)
            continue
        if group and _emphasis(group[0]) != base and any(_emphasis(group[0])):
            phrase = "".join(g.text for g in group).strip()
            if len(phrase) >= 2:
                phrases.append((phrase, group[0]))
        group = [r] if r is not None else []
    return phrases


def _formatted_pieces(text: str, runs: list) -> list[tuple[str, object]]:
    """Split new paragraph text into (text, template run) pieces.

    The text takes the paragraph's main formatting (the one covering most characters).
    A bold, italic or underlined phrase from the original that still appears unchanged
    in the new text keeps its formatting (its first occurrence).
    """
    totals: dict[tuple[bool, bool, bool], int] = {}
    for r in runs:
        totals[_emphasis(r)] = totals.get(_emphasis(r), 0) + len(r.text)
    base = max(totals, key=lambda k: totals[k])
    base_run = next(r for r in runs if _emphasis(r) == base)

    pieces: list[tuple[str, object]] = [(text, base_run)]
    phrases = sorted(_emphasised_phrases(runs, base), key=lambda p: -len(p[0]))
    for phrase, template in phrases:
        pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)")
        for k, (piece, owner) in enumerate(pieces):
            m = pattern.search(piece) if owner is base_run else None
            if m:
                split = [
                    (piece[: m.start()], base_run),
                    (phrase, template),
                    (piece[m.end() :], base_run),
                ]
                pieces[k : k + 1] = [x for x in split if x[0]]
                break
    return pieces


def replace_paragraphs(content: bytes, new_texts: dict[int, str]) -> bytes:
    """Replace whole paragraphs' text, keeping each paragraph's style.

    The new text takes the paragraph's main character formatting. Bold, italic or
    underlined phrases from the original that appear unchanged in the new text get their
    formatting back. Only paragraphs made entirely of plain runs can be replaced; others
    are left unchanged.
    """
    doc, paragraphs = _load(content)
    for index, text in new_texts.items():
        if not 0 <= index < len(paragraphs):
            continue
        p = paragraphs[index].paragraph
        if p.text == text or locked_spans(p):
            continue
        runs = p._p.xpath("w:r")
        if not runs:
            continue
        for piece, template in _formatted_pieces(text, runs):
            new_run = copy.deepcopy(template)
            new_run.text = piece
            runs[0].addprevious(new_run)
        for r in runs:
            p._p.remove(r)
    return _save(doc)


def new_docx(text: str) -> bytes:
    """A plain new document with one paragraph per blank-line-separated block."""
    doc = Document()
    for block in text.replace("\r\n", "\n").split("\n\n"):
        if block.strip():
            doc.add_paragraph(block.strip("\n"))
    return _save(doc)
