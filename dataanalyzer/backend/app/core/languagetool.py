"""Minimal async client for the local LanguageTool server.

Only local hosts are allowed, so no document data can leave this machine.

LanguageTool reports offsets in UTF-16 code units (it is a Java service). This client
converts them to Python string offsets, so callers can slice the text they sent directly.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.core.ollama import LOCAL_HOSTS

# LanguageTool servers often limit request size; long text is sent in parts.
MAX_REQUEST_CHARS = 20_000
MAX_REPLACEMENTS = 5
# Rules turned off by default. British bank style uses -ise ("organise", "mobilise"), so
# LanguageTool's suggestion to switch to Oxford -ize spelling is a false alarm.
DEFAULT_DISABLED_RULES = ("OXFORD_SPELLING_Z_NOT_S",)

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


class LanguageToolError(RuntimeError):
    """Raised when LanguageTool is unreachable or returns an error."""


@dataclass(frozen=True)
class Match:
    offset: int
    length: int
    message: str
    replacements: list[str]
    issue_type: str
    rule_id: str


def split_for_requests(text: str, max_chars: int = MAX_REQUEST_CHARS) -> list[int]:
    """Start offsets of parts of at most about `max_chars`, cut at paragraph breaks.

    A single paragraph longer than `max_chars` stays whole: cutting mid-sentence would
    produce false grammar errors.
    """
    starts = [0]
    last_break = None
    for m in _PARAGRAPH_BREAK.finditer(text):
        if m.end() - starts[-1] > max_chars and last_break and last_break > starts[-1]:
            starts.append(last_break)
        last_break = m.end()
    if len(text) - starts[-1] > max_chars and last_break and last_break > starts[-1]:
        starts.append(last_break)
    return starts


def _utf16_to_index(text: str) -> list[int] | None:
    """Map UTF-16 offsets to string indexes, or None when they are the same."""
    if all(ord(c) < 0x10000 for c in text):
        return None
    mapping: list[int] = []
    for i, c in enumerate(text):
        mapping.append(i)
        if ord(c) >= 0x10000:
            mapping.append(i)
    mapping.append(len(text))
    return mapping


class LanguageToolClient:
    def __init__(
        self,
        base_url: str | None = None,
        language: str | None = None,
        disabled_rules: tuple[str, ...] = DEFAULT_DISABLED_RULES,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.languagetool_url).rstrip("/")
        self.language = language or settings.languagetool_language
        self.disabled_rules = disabled_rules
        host = urlparse(self.base_url).hostname
        if host not in LOCAL_HOSTS:
            raise ValueError(
                f"LanguageTool URL must point to this machine, got host {host!r}"
            )
        self._timeout = timeout
        self._transport = transport

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout or self._timeout,
            transport=self._transport,
        )

    async def is_available(self, timeout: float = 3.0) -> bool:
        try:
            async with self._client(timeout) as client:
                resp = await client.get("/v2/languages")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def check(self, text: str) -> list[Match]:
        """Check `text` and return matches with offsets into `text`."""
        starts = split_for_requests(text)
        bounds = list(zip(starts, starts[1:] + [len(text)]))
        matches: list[Match] = []
        async with self._client() as client:
            for start, end in bounds:
                part = text[start:end]
                if part.strip():
                    matches.extend(await self._check_part(client, part, start))
        return matches

    def _form(self, text: str) -> dict[str, str]:
        form = {"text": text, "language": self.language}
        if self.disabled_rules:
            form["disabledRules"] = ",".join(self.disabled_rules)
        return form

    async def _check_part(
        self, client: httpx.AsyncClient, part: str, base: int
    ) -> list[Match]:
        try:
            resp = await client.post("/v2/check", data=self._form(part))
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LanguageToolError(
                f"LanguageTool returned {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LanguageToolError(f"Could not reach LanguageTool: {exc}") from exc

        mapping = _utf16_to_index(part)
        out = []
        for m in resp.json().get("matches", []):
            start, end = m["offset"], m["offset"] + m["length"]
            if mapping is not None:
                start, end = mapping[start], mapping[end]
            rule = m.get("rule", {})
            out.append(
                Match(
                    offset=base + start,
                    length=end - start,
                    message=m.get("message", ""),
                    replacements=[
                        r["value"] for r in m.get("replacements", [])[:MAX_REPLACEMENTS]
                    ],
                    issue_type=rule.get("issueType", "other"),
                    rule_id=rule.get("id", ""),
                )
            )
        return out
