"""Generate a realistic-length test document (about 20 pages) for context-window tests."""

import random

WORDS_PER_PAGE = 500
_VOCAB = [
    "the",
    "branch",
    "manager",
    "customer",
    "account",
    "loan",
    "deposit",
    "interest",
    "rate",
    "policy",
    "circular",
    "compliance",
    "review",
    "officer",
    "report",
    "quarterly",
    "annual",
    "balance",
    "credit",
    "debit",
    "transfer",
    "verification",
    "document",
    "approval",
    "sanction",
    "limit",
    "guideline",
    "procedure",
    "office",
    "staff",
    "region",
    "zone",
    "head",
    "department",
    "audit",
    "record",
    "statement",
    "payment",
    "schedule",
    "notice",
    "eligibility",
    "applicant",
    "collateral",
    "security",
    "nominee",
    "savings",
    "current",
    "fixed",
    "term",
    "should",
    "must",
    "will",
    "may",
    "within",
    "days",
    "of",
    "for",
    "and",
    "to",
    "in",
    "on",
    "with",
    "by",
    "from",
    "as",
    "per",
]


def make_document(
    pages: int = 20, first_line: str = "", last_line: str = "", seed: int = 7
) -> str:
    """Return about `pages` pages of filler prose, optionally framed by marker lines."""
    rng = random.Random(seed)
    paragraphs = []
    for _ in range(pages * 5):  # five paragraphs of 100 words per page
        sentences = []
        for _ in range(10):
            words = [rng.choice(_VOCAB) for _ in range(10)]
            sentences.append(" ".join(words).capitalize() + ".")
        paragraphs.append(" ".join(sentences))
    parts = (
        ([first_line] if first_line else [])
        + paragraphs
        + ([last_line] if last_line else [])
    )
    return "\n\n".join(parts)
