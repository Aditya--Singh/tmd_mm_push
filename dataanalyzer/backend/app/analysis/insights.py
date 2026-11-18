"""What was found in a document.

Two kinds of finding are made. The rules of this module look at the shape of the data and
say what is true of it whatever model is installed. The model is then asked to write the
summary and to add findings of its own, and what it says is kept beside the findings of the
rules.

When no model can be reached, the findings of the rules stand on their own and the summary
says so.
"""
from __future__ import annotations

import json
import logging

from app.analysis.profiling import KIND_DATE, KIND_NUMBER, KIND_TEXT, correlations_of

log = logging.getLogger("analyzer.insights")

#: How many findings are kept.
MAX_INSIGHTS = 12

SUMMARY_SYSTEM = (
    "You are an analyst for a bank. You are given the profile of a table: its columns, "
    "their types, how much is missing, and a few rows. Write a short summary of what the "
    "data is and what it looks like. Use plain sentences. Do not invent figures that are "
    "not in the profile. Answer with the summary only."
)

INSIGHT_SYSTEM = (
    "You are an analyst for a bank. You are given the profile of a table: its columns, "
    "their types, how much is missing, their statistics, and a few rows. Write the "
    "insights that a person who works with this data should know: what stands out, what "
    "is missing, what looks odd. Write one insight per line, each line starting with '- '. "
    "Do not invent figures that are not in the profile. Write at most eight lines."
)

ASK_SYSTEM = (
    "You are an analyst for a bank. You are given the profile of a table and a few rows, "
    "and a question about it. Answer the question from what is given. Say plainly when "
    "the profile does not hold the answer. Use plain sentences."
)


def _describe(profile: dict) -> str:
    """The profile as text, for a model to read."""
    lines = [
        f"rows: {profile.get('rows', 0)}",
        f"columns: {profile.get('columns', 0)}",
        f"duplicate rows: {profile.get('duplicateRows', 0)}",
        "",
    ]

    for column in profile.get("columnProfiles", []):
        line = f"- {column['name']} ({column['kind']}, {column['dtype']})"

        if column.get("missing"):
            line += f", missing {column['missing']} ({column['missingPct']}%)"

        if column.get("unique") is not None:
            line += f", {column['unique']} different values"

        for key in ("mean", "median", "std", "min", "max"):
            if column.get(key) is not None:
                line += f", {key} {column[key]}"

        top = column.get("topValues") or []

        if top:
            line += ", most frequent: " + ", ".join(
                f"{item['value']} ({item['count']})" for item in top[:5]
            )

        lines.append(line)

    return "\n".join(lines)


def _sample(preview: list[dict], rows: int = 12) -> str:
    """A few rows of the table, as text."""
    if not preview:
        return "no rows were read"

    chosen = preview[:rows]

    return "\n".join(json.dumps(row, default=str) for row in chosen)


def rule_based_insights(profile: dict, correlations: dict) -> list[dict]:
    """
    What the shape of the data says, whatever model is installed.

    Every finding says where it comes from, so that a person may look at the column it
    speaks of.
    """
    findings: list[dict] = []

    rows = int(profile.get("rows", 0))
    columns = profile.get("columnProfiles", [])

    if not rows:
        findings.append(
            {
                "kind": "note",
                "title": "The table is empty",
                "text": "The document holds no rows, so there is nothing to analyse.",
            }
        )

        return findings

    duplicates = int(profile.get("duplicateRows", 0))

    if duplicates:
        findings.append(
            {
                "kind": "warning",
                "title": f"{duplicates} rows are the same",
                "text": (
                    f"{duplicates} of the {rows} rows are exact copies of another row. "
                    "They may be counted twice in every report that follows."
                ),
            }
        )

    for column in columns:
        missing = int(column.get("missing", 0))
        pct = float(column.get("missingPct", 0))

        if pct >= 25 and missing:
            findings.append(
                {
                    "kind": "warning",
                    "title": f"{column['name']} is mostly empty",
                    "text": (
                        f"{missing} of the {rows} rows have no value in {column['name']} "
                        f"({pct}% of the column)."
                    ),
                }
            )

    for column in columns:
        if column.get("kind") == KIND_NUMBER:
            mean = column.get("mean")
            median = column.get("median")
            std = column.get("std")

            if mean is None or median is None or not std:
                continue

            if std and abs(mean - median) > std:
                side = "above" if mean > median else "below"

                findings.append(
                    {
                        "kind": "insight",
                        "title": f"{column['name']} is not evenly spread",
                        "text": (
                            f"The average of {column['name']} is {mean} and the middle is "
                            f"{median}, which is {side} the average by more than one standard "
                            "deviation. A few large values pull the average up."
                        ),
                    }
                )

    for column in columns:
        if column.get("kind") != KIND_TEXT:
            continue

        top = column.get("topValues") or []

        if not top or column.get("unique", 0) < 2:
            continue

        first = top[0]

        if first["count"] >= rows * 0.9:
            findings.append(
                {
                    "kind": "insight",
                    "title": f"{column['name']} holds one value",
                    "text": (
                        f"{first['count']} of the {rows} rows have '{first['value']}' in "
                        f"{column['name']}. The column carries little information."
                    ),
                }
            )

    pairs: list[dict] = []

    for left, row in correlations.items():
        for right, value in row.items():
            if left < right and abs(value) >= 0.7:
                pairs.append({"left": left, "right": right, "value": value})

    for pair in sorted(pairs, key=lambda item: abs(item["value"]), reverse=True)[:3]:
        direction = "together" if pair["value"] > 0 else "one after the other"

        findings.append(
            {
                "kind": "insight",
                "title": f"{pair['left']} and {pair['right']} move together",
                "text": (
                    f"The correlation between {pair['left']} and {pair['right']} is "
                    f"{pair['value']}, so they move {direction}."
                ),
            }
        )

    dates = [column for column in columns if column.get("kind") == KIND_DATE]

    for column in dates:
        if column.get("min") and column.get("max"):
            findings.append(
                {
                    "kind": "note",
                    "title": f"{column['name']} runs from {column['min']} to {column['max']}",
                    "text": f"The dates in {column['name']} lie between those two dates.",
                }
            )

    return findings[:MAX_INSIGHTS]


async def write_summary(profile: dict, preview: list[dict]) -> tuple[str, str]:
    """
    A summary of the document, and the reason it is the way it is.

    When no model can be reached, the summary is written from the profile alone, and the
    reason says that no model was used.
    """
    from app.llm.client import NoModelAvailable, get_llm

    llm = get_llm()

    if not llm.available:
        return _summary_from_rules(profile), llm.model_reason or "no model is available"

    try:
        text = await llm.complete(
            SUMMARY_SYSTEM,
            f"The profile of the table:\n{_describe(profile)}\n\nSome rows:\n{_sample(preview)}",
        )
    except NoModelAvailable as exc:
        return _summary_from_rules(profile), str(exc)

    if not text:
        return _summary_from_rules(profile), "the model answered with nothing"

    return text, llm.model_reason


async def write_insights(profile: dict, preview: list[dict]) -> tuple[list[dict], str]:
    """The findings of the model, beside the findings of the rules."""
    from app.llm.client import NoModelAvailable, get_llm

    llm = get_llm()
    findings: list[dict] = []

    if llm.available:
        try:
            text = await llm.complete(
                INSIGHT_SYSTEM,
                f"The profile of the table:\n{_describe(profile)}\n\nSome rows:\n{_sample(preview)}",
            )

            for line in (text or "").splitlines():
                line = line.strip()

                if not line.startswith("-"):
                    continue

                body = line.lstrip("- ").strip()

                if body:
                    findings.append({"kind": "insight", "title": body[:90], "text": body})
        except NoModelAvailable as exc:
            llm.last_error = str(exc)

    return findings[:MAX_INSIGHTS], llm.model_reason


async def answer_question(profile: dict, preview: list[dict], question: str) -> str:
    """The answer of the model to a question about the document."""
    from app.llm.client import NoModelAvailable, get_llm

    llm = get_llm()

    if not llm.available:
        return (
            "No model is available on this machine, so the question cannot be answered "
            "in words. The profile and the pictures of the document are shown above."
        )

    try:
        return await llm.complete(
            ASK_SYSTEM,
            f"The profile of the table:\n{_describe(profile)}\n\nSome rows:\n{_sample(preview)}\n\n"
            f"The question: {question}",
        )
    except NoModelAvailable as exc:
        return f"The model could not be reached: {exc}"


def _summary_from_rules(profile: dict) -> str:
    """A summary that is written from the profile alone."""
    rows = int(profile.get("rows", 0))
    columns = profile.get("columnProfiles", [])

    if not rows:
        return "The document holds no rows, so there is nothing to summarise."

    numbers = [column["name"] for column in columns if column.get("kind") == KIND_NUMBER]
    words = [column["name"] for column in columns if column.get("kind") == KIND_TEXT]
    dates = [column["name"] for column in columns if column.get("kind") == KIND_DATE]

    parts = [
        f"The table holds {rows} rows and {len(columns)} columns.",
        f"{len(numbers)} of the columns hold numbers"
        + (f" ({', '.join(numbers[:6])})" if numbers else "")
        + ".",
        f"{len(words)} hold words or codes"
        + (f" ({', '.join(words[:6])})" if words else "")
        + ".",
    ]

    if dates:
        parts.append(f"{len(dates)} hold dates ({', '.join(dates[:4])}).")

    missing = [
        column
        for column in columns
        if float(column.get("missingPct", 0)) >= 20
    ]

    if missing:
        parts.append(
            "The columns that are mostly empty are "
            + ", ".join(f"{column['name']} ({column['missingPct']}%)" for column in missing[:5])
            + "."
        )

    return " ".join(parts)
