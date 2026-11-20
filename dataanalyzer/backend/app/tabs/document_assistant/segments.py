"""Split a document into paragraphs ("segments") that Rewrite and Proofread work on.

Each segment knows where it starts in the document text, so an offset in the document maps
to one paragraph and an offset inside it. For DOCX files a segment index is also the
paragraph index used by `docx_writer`, which is what lets edits go back into the file.

Letter formalities (letterhead, reference and date lines, address blocks, subject lines,
salutations, closings and signature blocks) are marked so Rewrite never changes them.
"""

import io
import re
from dataclasses import dataclass, field, replace

from .docx_writer import docx_paragraphs, locked_spans

PARAGRAPH_SEPARATOR = "\n\n"
_BREAK = re.compile(r"\n[ \t\r\f\v]*\n\s*")

# Formalities are short lines; a long paragraph that happens to start "Thanking you for
# your support, ..." is body text.
_SHORT = 80
# Salutations and closings must be the whole line: "Dear Sir," but not "Dear customer,
# your account is now active." and "Yours faithfully," but not "Regards to the audit, ...".
_SALUTATION = re.compile(
    r"^(?:(?:my\s+)?dear|respected)\b[^\n]{0,40}?[^.?\n]$"
    r"|^(?:sir|madam|sir\s*/\s*madam)\s*[,.:]?$",
    re.IGNORECASE,
)
_CLOSING = re.compile(
    r"^(?:yours\s+(?:faithfully|sincerely|truly)|(?:with\s+)?(?:warm\s+|kind\s+|best\s+)?"
    r"regards|thanking\s+you|sincerely)\s*[,.!]?$",
    re.IGNORECASE,
)
_REFERENCE = re.compile(
    r"^(?:our\s+|your\s+)?(?:ref(?:erence)?|date|dated)\.?\s*(?:no\.?\s*)?[:\-–]"
    r"|^(?:ref(?:erence)?|letter|circular|memo|office\s+note)\.?\s+no\b",
    re.IGNORECASE,
)
# "Date: 15.10.2026" anywhere on a short line, e.g. after a reference number.
_DATE_FIELD = re.compile(r"\bdate[d]?\s*[:\-–]", re.IGNORECASE)
# A signature: "(R. K. Verma)" on its own line, usually followed by a designation.
_SIGNATURE = re.compile(r"^\([^()\n]{2,60}\)\s*$")
_SUBJECT = re.compile(r"^(?:subject|sub|re)\s*[:.\-–]", re.IGNORECASE)
_ADDRESS = re.compile(r"^(?:to|from)\s*(?:[,:]|$)", re.IGNORECASE)
# Look for the salutation only near the top, so a quoted "Dear Sir" later is ignored.
_SALUTATION_WITHIN = 12


@dataclass(frozen=True)
class Segment:
    start: int
    text: str
    in_table: bool = False
    # Ranges of `text` that cannot be edited in the file (links, fields, images).
    locked: tuple[tuple[int, int], ...] = ()
    # A letter formality: salutation, closing, reference, address, subject or signature.
    formality: bool = False

    @property
    def end(self) -> int:
        return self.start + len(self.text)

    @property
    def replaceable(self) -> bool:
        """The whole paragraph's text can be replaced in the file (not a table cell, and no
        links, fields or images)."""
        return not self.in_table and not self.locked

    @property
    def rewritable(self) -> bool:
        """Rewrite may change it: replaceable, and not a letter formality."""
        return self.replaceable and not self.formality

    @property
    def skip_reason(self) -> str:
        if self.in_table:
            return "table cell"
        if self.locked:
            return "contains a link, field or image"
        if self.formality:
            return "letter formality"
        return ""


@dataclass
class SegmentedText:
    text: str
    segments: list[Segment] = field(default_factory=list)

    def locate(self, start: int, end: int) -> tuple[int, int, int] | None:
        """(segment index, local start, local end), or None if the span crosses paragraphs."""
        for i, seg in enumerate(self.segments):
            if seg.start <= start and end <= seg.end:
                return i, start - seg.start, end - seg.start
        return None

    def separator_before(self, index: int) -> str:
        """The original text between segment `index - 1` and segment `index`."""
        if index == 0:
            return ""
        return self.text[self.segments[index - 1].end : self.segments[index].start]

    def is_applicable(self, start: int, end: int) -> bool:
        located = self.locate(start, end)
        if located is None:
            return False
        i, s, e = located
        return not any(
            s < le and ls < max(e, s + 1) for ls, le in self.segments[i].locked
        )


def _kind(text: str) -> str | None:
    """ "header" (reference, date, address, subject, salutation), "closing", "signature",
    or None for body text."""
    first = text.lstrip().split("\n", 1)[0].strip()
    if _ADDRESS.match(first) or _SUBJECT.match(first):
        return "header"
    if len(text) > _SHORT * 2:
        return None
    if _SIGNATURE.match(first):
        return "signature"
    if len(text) > _SHORT:
        return None
    if _CLOSING.match(first):
        return "closing"
    if _SALUTATION.match(first) or _REFERENCE.match(first) or _DATE_FIELD.search(first):
        return "header"
    return None


def is_formal_line(line: str) -> bool:
    """True if one line looks like a letter formality (salutation, closing, Ref/Date,
    address, subject or signature)."""
    return _kind(line.strip()) is not None


def mark_formalities(segments: list[Segment]) -> list[Segment]:
    """Mark letter formalities.

    By pattern: reference and date lines, address blocks ("To," ...), subject lines,
    salutations, closings and "(Name)" signatures. By position:
    - the letterhead: short lines at the top, up to the last formality among them;
    - in a letter with a salutation, everything before it;
    - everything from the closing ("Yours faithfully," ...) to the end, which is the
      closing and signature block.
    """
    body = [i for i, seg in enumerate(segments) if not seg.in_table]
    kinds = {i: _kind(segments[i].text) for i in body}
    formal = {i for i in body if kinds[i]}

    header_end = None
    for i in body[:_SALUTATION_WITHIN]:
        if kinds[i] not in (None, "header") or (
            kinds[i] is None and len(segments[i].text) > _SHORT
        ):
            break
        if kinds[i] == "header":
            header_end = i
    if header_end is not None:
        formal.update(i for i in body if i <= header_end)

    def short_match(pattern: re.Pattern[str], i: int) -> bool:
        text = segments[i].text.strip()
        return len(text) <= _SHORT and bool(pattern.match(text))

    salutation = next(
        (i for i in body[:_SALUTATION_WITHIN] if short_match(_SALUTATION, i)), None
    )
    if salutation is not None:
        formal.update(i for i in body if i <= salutation)
    after = [i for i in body if salutation is None or i > salutation]
    closing = next((i for i in after if short_match(_CLOSING, i)), None)
    if closing is not None:
        formal.update(i for i in body if i >= closing)
    return [
        replace(seg, formality=True) if i in formal else seg
        for i, seg in enumerate(segments)
    ]


def _block_segments(start: int, block: str) -> list[Segment]:
    """One segment for a blank-line-separated block, or one per line if it is a letter.

    Text pasted from Word often has a single line break between paragraphs, so a whole
    letter arrives as one block. If any line of a block is a letter formality ("Dear Sir,",
    "Yours faithfully,", "Ref: ...", "To,", "Subject: ...", "(Name)"), every line becomes
    its own paragraph, so the formalities can be told apart from the body.
    """
    lines = []
    pos = 0
    for line in block.split("\n"):
        if line.strip():
            lines.append((start + pos + line.index(line.strip()), line.strip()))
        pos += len(line) + 1
    if len(lines) > 1 and any(_kind(text) for _, text in lines):
        return [Segment(offset, text) for offset, text in lines]
    return [Segment(start, block)]


def from_text(text: str) -> SegmentedText:
    """Paragraphs are separated by blank lines (or single line breaks in a pasted letter).
    Offsets point into `text` unchanged."""
    segments: list[Segment] = []
    pos = 0
    for m in [*_BREAK.finditer(text), None]:
        end = m.start() if m else len(text)
        chunk = text[pos:end]
        stripped = chunk.strip()
        if stripped:
            segments.extend(_block_segments(pos + chunk.index(stripped), stripped))
        if m:
            pos = m.end()
    return SegmentedText(text, mark_formalities(segments))


def split_blocks(text: str) -> list[str]:
    """Blank-line-separated blocks, stripped. Line breaks inside a block are kept, so a
    Word paragraph with line breaks (an address block) stays one block."""
    return [b.strip() for b in _BREAK.split(text) if b.strip()]


def from_docx(content: bytes) -> SegmentedText:
    """One segment per non-empty body or table-cell paragraph, joined by blank lines."""
    from docx import Document

    paragraphs = docx_paragraphs(Document(io.BytesIO(content)))
    segments = []
    pos = 0
    for p in paragraphs:
        text = p.paragraph.text
        segments.append(
            Segment(pos, text, p.in_table, tuple(locked_spans(p.paragraph)))
        )
        pos += len(text) + len(PARAGRAPH_SEPARATOR)
    return SegmentedText(
        PARAGRAPH_SEPARATOR.join(s.text for s in segments), mark_formalities(segments)
    )
