import asyncio

import httpx
import pytest

from app.core.languagetool import (
    LanguageToolClient,
    LanguageToolError,
    split_for_requests,
)
from tests.document_assistant.mock_ollama import FakeLanguageTool


def test_check_sends_en_gb_and_returns_matches():
    fake = FakeLanguageTool({"Teh": "The"})
    matches = asyncio.run(fake.client().check("Teh branch is open."))
    assert fake.requests[0]["language"] == "en-GB"
    assert fake.requests[0]["disabledRules"] == "OXFORD_SPELLING_Z_NOT_S"
    assert len(matches) == 1
    m = matches[0]
    assert (m.offset, m.length) == (0, 3)
    assert m.replacements == ["The"]
    assert m.issue_type == "misspelling"


def test_utf16_offsets_are_converted_to_python_offsets():
    fake = FakeLanguageTool({"Teh": "The"})
    text = "Smile 😀 please. Teh end."
    m = asyncio.run(fake.client().check(text))[0]
    assert text[m.offset : m.offset + m.length] == "Teh"


def test_long_text_is_split_at_paragraphs_and_offsets_shifted():
    paragraphs = [f"Paragraph {i} has Teh word." + " filler" * 400 for i in range(12)]
    text = "\n\n".join(paragraphs)
    fake = FakeLanguageTool({"Teh": "The"})
    matches = asyncio.run(fake.client().check(text))
    assert len(fake.requests) > 1
    assert all(len(r["text"]) <= 20_000 for r in fake.requests)
    assert len(matches) == 12
    assert all(text[m.offset : m.offset + m.length] == "Teh" for m in matches)


def test_split_keeps_an_oversized_paragraph_whole():
    text = "a" * 50 + "\n\n" + "b" * 300 + "\n\n" + "c" * 50
    starts = split_for_requests(text, max_chars=100)
    parts = [text[s:e] for s, e in zip(starts, starts[1:] + [len(text)])]
    assert "".join(parts) == text
    assert any(p.strip() == "b" * 300 for p in parts)


def test_unreachable_raises_languagetool_error():
    with pytest.raises(LanguageToolError):
        asyncio.run(FakeLanguageTool(down=True).client().check("Some text."))


def test_server_error_raises_languagetool_error():
    client = LanguageToolClient(
        base_url="http://localhost:8120",
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")),
    )
    with pytest.raises(LanguageToolError):
        asyncio.run(client.check("Some text."))


def test_only_local_hosts_allowed():
    with pytest.raises(ValueError):
        LanguageToolClient(base_url="http://languagetool.org")


def test_is_available():
    assert asyncio.run(FakeLanguageTool().client().is_available()) is True
    assert asyncio.run(FakeLanguageTool(down=True).client().is_available()) is False
