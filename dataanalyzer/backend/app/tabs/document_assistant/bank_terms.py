"""Standard Indian banking and RBI usage that Proofread must never flag.

The list lives in ``reference/bank_terms.txt`` (one word or phrase per line, ``#`` starts a
comment) so staff can edit it without touching code. It is read on every request, so edits
take effect immediately. Set ``BANK_TERMS_FILE`` to use a different file.

Entries containing a capital letter (acronyms such as ``CO`` or ``NPA``) match exactly;
others ignore case, so ``kindly`` also matches "Kindly".
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import BACKEND_DIR

DEFAULT_FILE = BACKEND_DIR.parent / "reference" / "bank_terms.txt"


def terms_file() -> Path:
    return Path(os.getenv("BANK_TERMS_FILE", DEFAULT_FILE))


def load_terms(path: Path | None = None) -> list[str]:
    """The terms in the file, in order. A missing file means no terms."""
    try:
        lines = (path or terms_file()).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    terms = []
    for line in lines:
        term = " ".join(line.split())
        if term and not term.startswith("#") and term not in terms:
            terms.append(term)
    return terms


def _pattern(term: str) -> re.Pattern[str]:
    # Any run of whitespace between words; no letter or digit directly around the term.
    body = r"\s+".join(re.escape(w) for w in term.split())
    flags = 0 if any(c.isupper() for c in term) else re.IGNORECASE
    return re.compile(rf"(?<![\w]){body}(?![\w])", flags)


@dataclass(frozen=True)
class BankTerms:
    terms: list[str]

    @classmethod
    def load(cls, path: Path | None = None) -> "BankTerms":
        return cls(load_terms(path))

    def spans(self, text: str) -> list[tuple[int, int, str]]:
        """(start, end, term) for every occurrence of a term in `text`."""
        found = []
        for term in self.terms:
            found.extend(
                (m.start(), m.end(), term) for m in _pattern(term).finditer(text)
            )
        return found

    def is_false_alarm(
        self, text: str, start: int, end: int, replacements: list[str]
    ) -> bool:
        """True if a suggestion on text[start:end] would change or remove a bank term.

        A suggestion that touches a term but keeps it in its replacement (for example a
        sentence-level fix that keeps "Rs. 25 lakh") is not a false alarm.
        """
        touched = [
            term
            for s, e, term in self.spans(text)
            if s < max(end, start + 1) and start < e
        ]
        if not touched:
            return False
        return not any(
            all(_pattern(term).search(r) for term in touched) for r in replacements
        )
