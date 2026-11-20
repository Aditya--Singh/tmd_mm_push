"""One "Ask about data" turn: plan, compute, explain, with the number check (Ollama mocked)."""

import asyncio
import json

import pandas as pd
import pytest

from app.tabs.document_assistant.data_chat import (
    NOT_UNDERSTOOD_MESSAGE,
    PROMPT_ROWS,
    UNCHECKED_MESSAGE,
    UNSUPPORTED_MESSAGE,
    ask,
    figures,
    unsupported_figures,
)
from app.tabs.document_assistant.extraction import DataSheet

from .mock_ollama import FakeOllama

TOTAL = {
    "operation": "group_by",
    "group_by": [],
    "aggregate": "sum",
    "column": "Outstanding",
}


def sheets() -> list[DataSheet]:
    frame = pd.DataFrame(
        {
            "Branch": ["Udaipur", "Jaipur", "Udaipur", "Delhi"],
            "Outstanding": ["21,40,500", "98,000", "6,10,250", "68,75,000"],
        },
        dtype=object,
    )
    return [DataSheet("Loans", frame)]


class Model:
    """Plays the model: `plans` answer the JSON requests, `answers` the streamed ones."""

    def __init__(self, plans, answers=()):
        self.plans = [p if isinstance(p, str) else json.dumps(p) for p in plans]
        self.answers = list(answers)
        self.fake = FakeOllama(responder=self.respond)

    def respond(self, body):
        return (self.answers if body["stream"] else self.plans).pop(0)

    @property
    def plan_requests(self):
        return [r for r in self.fake.requests if not r["stream"]]

    @property
    def answer_requests(self):
        return [r for r in self.fake.requests if r["stream"]]


def turn(model, question="What is the total outstanding?", history=()):
    async def collect():
        return [
            e async for e in ask(sheets(), question, list(history), model.fake.client())
        ]

    return asyncio.run(collect())


def only(events, kind):
    found = [e for e in events if e["type"] == kind]
    assert len(found) == 1, events
    return found[0]


def test_compute_then_explain():
    model = Model([TOTAL], ["The total outstanding is 97,23,750 across 4 loans."])
    events = turn(model)

    assert only(events, "operation")["operation"] == {
        "operation": "group_by",
        "sheet": "Loans",
        "group_by": [],
        "aggregate": "sum",
        "column": "Outstanding",
    }
    result = only(events, "table")
    assert result["rows"] == [["97,23,750"]]
    assert result["columns"] == ["Total of Outstanding"]
    assert only(events, "answer")["text"] == (
        "The total outstanding is 97,23,750 across 4 loans."
    )
    chunks = "".join(e["text"] for e in events if e["type"] == "chunk")
    assert chunks == "The total outstanding is 97,23,750 across 4 loans."

    plan = model.plan_requests[0]
    assert plan["format"]["properties"]["operation"]["enum"][-1] == "unsupported"
    assert plan["options"]["temperature"] == 0
    assert plan["options"]["num_ctx"] == 32768
    # The model sees the columns and their kinds, never computed figures.
    system = plan["messages"][0]["content"]
    assert "'Outstanding': number" in system
    assert "'Branch': text; values: 'Udaipur', 'Jaipur', 'Delhi'" in system
    assert "97,23,750" not in json.dumps(plan)

    answer = model.answer_requests[0]
    assert answer["options"]["num_ctx"] == 32768
    assert (
        "<result>\nTotal of Outstanding, over 4 rows."
        in answer["messages"][1]["content"]
    )
    assert "97,23,750" in answer["messages"][1]["content"]


def test_invalid_operation_is_sent_back_once_with_the_reason():
    bad = {"operation": "group_by", "aggregate": "sum", "column": "Balance"}
    model = Model([bad, TOTAL], ["The total is 97,23,750."])
    events = turn(model)
    assert only(events, "answer")["text"] == "The total is 97,23,750."
    retry = model.plan_requests[1]["messages"]
    assert retry[-2] == {"role": "assistant", "content": json.dumps(bad)}
    assert "no column named 'Balance'" in retry[-1]["content"]


def test_operation_that_fails_twice_is_not_run():
    model = Model(["not json", {"operation": "eval", "code": "1+1"}])
    events = turn(model)
    assert only(events, "unsupported")["message"] == NOT_UNDERSTOOD_MESSAGE
    assert not [e for e in events if e["type"] in ("table", "answer")]
    assert model.answer_requests == []


def test_unsupported_question_gets_a_plain_message():
    model = Model([{"operation": "unsupported"}])
    events = turn(model, "What percentage of loans are overdue compared to last year?")
    assert only(events, "unsupported")["message"] == UNSUPPORTED_MESSAGE
    assert len(model.fake.requests) == 1


def test_answer_with_a_new_number_is_retried_with_the_reason():
    model = Model(
        [
            {
                "operation": "group_by",
                "group_by": ["Branch"],
                "aggregate": "sum",
                "column": "Outstanding",
            }
        ],
        [
            "Udaipur has 27,50,750, which is 28% of the total.",
            "Udaipur has the most outstanding, 27,50,750.",
        ],
    )
    events = turn(model, "Which branch has the most outstanding?")
    assert (
        only(events, "answer")["text"] == "Udaipur has the most outstanding, 27,50,750."
    )
    assert len([e for e in events if e["type"] == "answer_start"]) == 2
    retry = model.answer_requests[1]["messages"]
    assert retry[-2]["content"] == "Udaipur has 27,50,750, which is 28% of the total."
    assert "28" in retry[-1]["content"]
    assert "27,50,750" not in retry[-1]["content"].split(":")[1]


def test_amounts_must_keep_indian_grouping():
    model = Model([TOTAL], ["The total is 9,723,750.", "The total is 97,23,750."])
    events = turn(model)
    assert only(events, "answer")["text"] == "The total is 97,23,750."
    assert "9,723,750" in model.answer_requests[1]["messages"][-1]["content"]


def test_answer_failing_twice_shows_only_the_table():
    model = Model([TOTAL], ["About 97 lakh.", "Roughly 1 crore in total."])
    events = turn(model)
    answer = only(events, "answer")
    assert answer == {"type": "answer", "text": None, "message": UNCHECKED_MESSAGE}
    assert only(events, "table")["rows"] == [["97,23,750"]]
    assert events.index(only(events, "table")) < events.index(answer)


def test_empty_answer_is_retried():
    model = Model([TOTAL], ["", "The total is 97,23,750."])
    assert only(turn(model), "answer")["text"] == "The total is 97,23,750."
    assert "empty" in model.answer_requests[1]["messages"][-1]["content"]


def test_follow_up_questions_see_earlier_turns():
    history = [
        {"question": "Total outstanding?", "operation": TOTAL, "answer": "97,23,750."},
        {"question": "Something odd", "operation": None, "answer": None},
    ]
    follow_up = {
        **TOTAL,
        "filters": [{"column": "Branch", "op": "=", "value": "Udaipur"}],
    }
    model = Model([follow_up], ["For Udaipur it is 27,50,750."])
    events = turn(model, "And for Udaipur only?", history)

    plan = model.plan_requests[0]["messages"]
    assert [m["role"] for m in plan] == ["system", "user"]
    context = plan[1]["content"]
    assert context.startswith(
        "Earlier in this conversation:\n1. Question: Total outstanding?"
    )
    assert f"   Operation: {json.dumps(TOTAL)}" in context
    assert (
        '2. Question: Something odd\n   Operation: {"operation": "unsupported"}'
        in context
    )
    assert "New question: And for Udaipur only?" in context
    assert only(events, "table")["rows"] == [["27,50,750"]]
    assert "- Total outstanding?" in model.answer_requests[0]["messages"][1]["content"]


def test_model_sees_only_the_first_rows_of_a_long_result():
    model = Model(
        [{"operation": "sort", "column": "Outstanding"}],
        ["The smallest outstanding is 98,000."] * 2,
    )
    big = pd.DataFrame({"Outstanding": [str(n) for n in range(1, PROMPT_ROWS + 20)]})

    async def collect():
        return [
            e
            async for e in ask(
                [DataSheet("S", big)], "Sort them", [], model.fake.client()
            )
        ]

    events = asyncio.run(collect())
    content = model.answer_requests[0]["messages"][1]["content"]
    assert f"Only the first {PROMPT_ROWS} of {PROMPT_ROWS + 19} rows" in content
    # 98,000 is not in this file, so the answer fails both times.
    assert only(events, "answer")["text"] is None


@pytest.mark.parametrize(
    ("answer", "bad"),
    [
        ("The total is 97,23,750.", set()),
        ("The total is 97,23,750.00, dated 5 April 2024.", set()),
        ("The total is 9723750.", {"9723750"}),
        ("That is 12% more.", {"12"}),
        ("Top 3 branches", {"3"}),
    ],
)
def test_number_check(answer, bad):
    result = "Total of Outstanding, over 4 rows.\n97,23,750\nDated 05 Apr 2024"
    assert unsupported_figures(answer, result) == bad


def test_figures_ignore_leading_and_trailing_zeros_only():
    assert figures("05 and 1,234.50 and 0.5, then 97,23,750,") == {
        "5",
        "1,234.5",
        "0.5",
        "97,23,750",
    }


def test_echoed_result_block_is_removed_from_the_answer():
    model = Model(
        [TOTAL],
        [
            "The total is 97,23,750.\n\n<result>\nTotal of Outstanding\n97,23,750\n</result>"
        ],
    )
    assert only(turn(model), "answer")["text"] == "The total is 97,23,750."


def test_prompts_explain_follow_ups_and_mismatched_results():
    model = Model([TOTAL], ["The total is 97,23,750."])
    turn(model)
    assert (
        "take the previous operation"
        in model.plan_requests[0]["messages"][0]["content"]
    )
    answer_system = model.answer_requests[0]["messages"][0]["content"]
    assert "say what the result covers instead" in answer_system
