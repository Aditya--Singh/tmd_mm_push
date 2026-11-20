"""Fake Ollama and LanguageTool servers for tests, built on httpx.MockTransport."""

import json

import httpx

from app.core.languagetool import LanguageToolClient
from app.core.ollama import OllamaClient


class FakeOllama:
    """`responder(body) -> str`, if given, picks the reply for each request."""

    def __init__(
        self,
        reply: str = "Summary text.",
        chunk_replies=None,
        down=False,
        responder=None,
    ):
        self.reply = reply
        self.chunk_replies = chunk_replies
        self.down = down
        self.responder = responder
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("connection refused")
        body = json.loads(request.content)
        self.requests.append(body)
        reply = self.responder(body) if self.responder else self.reply
        if body["stream"]:
            words = reply.split(" ")
            lines = [
                json.dumps(
                    {"message": {"content": w + (" " if i < len(words) - 1 else "")}}
                )
                for i, w in enumerate(words)
            ]
            lines.append(json.dumps({"done": True}))
            return httpx.Response(200, content="\n".join(lines).encode())
        n = sum(1 for r in self.requests if not r["stream"])
        if self.responder:
            content = reply
        elif self.chunk_replies is None:
            content = f"- partial {n}"
        else:
            content = self.chunk_replies
        return httpx.Response(200, json={"message": {"content": content}})

    def client(self, num_ctx: int | None = None) -> OllamaClient:
        return OllamaClient(
            base_url="http://localhost:11434",
            model="gpt-oss:20b",
            num_ctx=num_ctx or 32768,
            transport=httpx.MockTransport(self.handler),
        )


class FakeLanguageTool:
    """Reports every occurrence of each word in `errors` as a misspelling.

    A value is the replacement, or a list of replacements in LanguageTool's order.
    """

    def __init__(self, errors: dict[str, str | list[str]] | None = None, down=False):
        self.errors = errors or {}
        self.down = down
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("connection refused")
        if request.url.path == "/v2/languages":
            return httpx.Response(200, json=[{"code": "en-GB"}])
        form = dict(httpx.QueryParams(request.content.decode()))
        self.requests.append(form)
        text = form["text"]
        matches = []
        for wrong, right in self.errors.items():
            start = text.find(wrong)
            while start >= 0:
                matches.append(
                    {
                        "message": f"Possible spelling mistake: {wrong}",
                        "replacements": [
                            {"value": r}
                            for r in ([right] if isinstance(right, str) else right)
                        ],
                        # LanguageTool counts UTF-16 code units.
                        "offset": len(text[:start].encode("utf-16-le")) // 2,
                        "length": len(wrong.encode("utf-16-le")) // 2,
                        "rule": {"id": "MORFOLOGIK", "issueType": "misspelling"},
                    }
                )
                start = text.find(wrong, start + 1)
        return httpx.Response(200, json={"matches": matches})

    def client(self) -> LanguageToolClient:
        return LanguageToolClient(
            base_url="http://localhost:8120",
            language="en-GB",
            transport=httpx.MockTransport(self.handler),
        )
