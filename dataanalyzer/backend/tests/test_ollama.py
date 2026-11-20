import asyncio
import json

import httpx
import pytest

from app.core.ollama import (
    OllamaClient,
    OllamaContextError,
    OllamaError,
    estimate_tokens,
)
from tests.docgen import WORDS_PER_PAGE, make_document


@pytest.fixture(autouse=True)
def _default_num_ctx(monkeypatch):
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)


def run(coro):
    return asyncio.run(coro)


def make_client(handler, **kw):
    return OllamaClient(
        base_url="http://localhost:11434",
        model="gpt-oss:20b",
        transport=httpx.MockTransport(handler),
        **kw,
    )


def test_list_models_and_is_available():
    def handler(req):
        assert req.url.path == "/api/tags"
        return httpx.Response(
            200, json={"models": [{"name": "gpt-oss:20b"}, {"name": "x"}]}
        )

    c = make_client(handler)
    assert run(c.list_models()) == ["gpt-oss:20b", "x"]
    assert run(c.is_available()) is True


def test_is_available_false_when_down():
    def handler(req):
        raise httpx.ConnectError("refused")

    assert run(make_client(handler).is_available()) is False


def test_chat_sends_payload_and_returns_content():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": "Hi"}}
        )

    out = run(
        make_client(handler).chat(
            [{"role": "user", "content": "Hello"}],
            options={"temperature": 0},
            format="json",
        )
    )
    assert out == "Hi"
    assert seen == {
        "model": "gpt-oss:20b",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 32768},
        "format": "json",
    }


def test_chat_http_error_raises():
    c = make_client(lambda req: httpx.Response(404, text="model not found"))
    with pytest.raises(OllamaError, match="404"):
        run(c.chat([{"role": "user", "content": "x"}]))


def test_chat_connection_error_raises():
    def handler(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(OllamaError, match="Could not reach"):
        run(make_client(handler).chat([{"role": "user", "content": "x"}]))


@pytest.mark.parametrize("url", ["https://api.example.com", "http://10.0.0.5:11434"])
def test_non_local_url_rejected(url):
    with pytest.raises(ValueError, match="this machine"):
        OllamaClient(base_url=url)


def test_model_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "gpt-oss:20b")
    assert OllamaClient().model == "gpt-oss:20b"


def test_default_model_is_gpt_oss_20b(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert OllamaClient().model == "gpt-oss:20b"


# --- num_ctx is always sent -------------------------------------------------


def ndjson(*objs):
    return "\n".join(json.dumps(o) for o in objs) + "\n"


def collect(aiter):
    async def go():
        return [chunk async for chunk in aiter]

    return run(go())


def capturing_handler(seen, stream=False):
    def handler(req):
        seen.append(json.loads(req.content))
        if stream:
            return httpx.Response(
                200,
                text=ndjson(
                    {"message": {"content": "ok"}, "done": False},
                    {"message": {"content": ""}, "done": True},
                ),
            )
        return httpx.Response(200, json={"message": {"content": "ok"}})

    return handler


def test_chat_always_sends_num_ctx():
    seen = []
    run(make_client(capturing_handler(seen)).chat([{"role": "user", "content": "x"}]))
    assert seen[0]["options"] == {"num_ctx": 32768}


def test_chat_stream_always_sends_num_ctx():
    seen = []
    c = make_client(capturing_handler(seen, stream=True))
    assert collect(c.chat_stream([{"role": "user", "content": "x"}])) == ["ok"]
    assert seen[0]["stream"] is True
    assert seen[0]["options"] == {"num_ctx": 32768}


def test_caller_cannot_override_num_ctx():
    seen = []
    c = make_client(capturing_handler(seen))
    run(
        c.chat(
            [{"role": "user", "content": "x"}],
            options={"num_ctx": 2048, "temperature": 0.2},
        )
    )
    assert seen[0]["options"] == {"num_ctx": 32768, "temperature": 0.2}


def test_num_ctx_from_env_and_constructor(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_CTX", "49152")
    assert OllamaClient().num_ctx == 49152
    assert OllamaClient(num_ctx=8192).num_ctx == 8192


def test_default_num_ctx():
    assert OllamaClient().num_ctx == 32768


# --- streaming ----------------------------------------------------------------


def test_chat_stream_yields_chunks_in_order():
    body = ndjson(
        {"message": {"content": "Dear "}, "done": False},
        {"message": {"content": "Sir,"}, "done": False},
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 12},
    )
    c = make_client(lambda req: httpx.Response(200, text=body))
    assert collect(c.chat_stream([{"role": "user", "content": "x"}])) == [
        "Dear ",
        "Sir,",
    ]


def test_chat_stream_error_line_raises():
    body = ndjson(
        {"message": {"content": "Hi"}, "done": False},
        {"error": "model crashed"},
    )
    c = make_client(lambda req: httpx.Response(200, text=body))
    with pytest.raises(OllamaError, match="model crashed"):
        collect(c.chat_stream([{"role": "user", "content": "x"}]))


def test_chat_stream_http_error_raises():
    c = make_client(lambda req: httpx.Response(500, text="out of memory"))
    with pytest.raises(OllamaError, match="500: out of memory"):
        collect(c.chat_stream([{"role": "user", "content": "x"}]))


def test_chat_stream_connection_error_raises():
    def handler(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(OllamaError, match="Could not reach"):
        collect(make_client(handler).chat_stream([{"role": "user", "content": "x"}]))


def test_chat_response_returns_full_json():
    c = make_client(
        lambda req: httpx.Response(
            200, json={"message": {"content": "hi"}, "prompt_eval_count": 42}
        )
    )
    data = run(c.chat_response([{"role": "user", "content": "x"}]))
    assert data["prompt_eval_count"] == 42


# --- size guard and long documents ------------------------------------------------


def test_estimate_tokens_is_high_side():
    msgs = [{"role": "user", "content": "a" * 300}, {"role": "system", "content": ""}]
    assert estimate_tokens(msgs) == 100 + 8 + 8


def test_twenty_page_document_is_sent_in_full():
    marker = "FINAL MARKER SENTENCE 7Q4Z: the last line of the document."
    doc = make_document(pages=20, last_line=marker)
    assert len(doc.split()) >= 20 * WORDS_PER_PAGE
    messages = [
        {"role": "system", "content": "Summarise the document."},
        {"role": "user", "content": doc},
    ]
    seen = []
    run(make_client(capturing_handler(seen)).chat(messages))
    sent = seen[0]["messages"][-1]["content"]
    assert sent == doc
    assert sent.endswith(marker)
    assert seen[0]["options"]["num_ctx"] == 32768


def test_twenty_page_document_is_streamed_in_full():
    marker = "FINAL MARKER SENTENCE 9X2K."
    doc = make_document(pages=20, last_line=marker)
    seen = []
    c = make_client(capturing_handler(seen, stream=True))
    collect(c.chat_stream([{"role": "user", "content": doc}]))
    assert seen[0]["messages"][0]["content"].endswith(marker)


def never_called(req):
    raise AssertionError("request must not be sent")


def test_over_limit_document_is_rejected_not_sent():
    doc = make_document(pages=40)
    c = make_client(never_called)
    with pytest.raises(OllamaContextError) as exc:
        run(c.chat([{"role": "user", "content": doc}]))
    assert exc.value.limit == 32768
    assert exc.value.estimated_tokens > 32768


def test_over_limit_stream_is_rejected_not_sent():
    doc = make_document(pages=40)
    c = make_client(never_called)
    with pytest.raises(OllamaContextError):
        collect(c.chat_stream([{"role": "user", "content": doc}]))


def test_expected_output_counts_towards_limit():
    doc = make_document(pages=20)
    c = make_client(never_called)
    with pytest.raises(OllamaContextError):
        run(
            c.chat(
                [{"role": "user", "content": doc}],
                expected_output_tokens=estimate_tokens(
                    [{"role": "user", "content": doc}]
                ),
            )
        )
