"""Which model of this machine to write with.

A machine may hold several models, and the best one for writing is not the one that was
named in the settings when those settings were written. This module looks at what is
installed and picks the best of it, and says why.

The rules, in order:

1. A model that is for embeddings is never used for writing.
2. The newest family that is installed wins. The families are listed in
   `PREFERRED_FAMILIES`, newest first.
3. Within a family, the larger model wins.
4. A named tag is better than the rolling `:latest` of the same model.

A model that is named in the settings wins whenever it is installed. When it is not, the
best installed model is used instead, and the reason says so.
"""
from __future__ import annotations

import logging
import re

import httpx

from app.config import get_settings

log = logging.getLogger("sentinel.models")

#: The families of model, newest first. The first one that is installed is used.
PREFERRED_FAMILIES: tuple[str, ...] = (
    "qwen3",
    "qwen2.5",
    "qwen2",
    "llama3.3",
    "llama3.2",
    "llama3.1",
    "llama3",
    "mistral-nemo",
    "mistral",
    "gemma3",
    "gemma2",
    "phi4",
    "command-r",
    "deepseek-r1",
)

#: Words that mark a model as one for embeddings rather than one for writing.
EMBEDDING_WORDS: tuple[str, ...] = (
    "embed",
    "bge",
    "gte-",
    "e5-",
    "minilm",
    "mxbai",
)


def model_family(name: str) -> str:
    """The family of a model: `qwen3:8b` belongs to `qwen3`."""
    return str(name or "").split(":")[0].strip().lower()


def model_size_b(name: str) -> float:
    """The size of a model in billions of parameters, as far as the name says."""
    tag = str(name or "").split(":")[1] if ":" in str(name or "") else ""

    match = re.search(r"(\d+(?:\.\d+)?)\s*b\b", tag)

    if not match:
        return 0.0

    try:
        return float(match.group(1))
    except ValueError:
        return 0.0


def is_embedding_model(name: str) -> bool:
    """Whether a model is one for embeddings rather than one for writing."""
    lowered = str(name or "").lower()

    return any(word in lowered for word in EMBEDDING_WORDS)


def score_model(name: str) -> float:
    """
    How good a model is, in the order this app prefers.

    The family comes first: the newest family that is installed is the one that was
    meant. Within a family the larger model wins.
    """
    family = model_family(name)

    rank = (
        PREFERRED_FAMILIES.index(family)
        if family in PREFERRED_FAMILIES
        else len(PREFERRED_FAMILIES)
    )

    size = min(model_size_b(name), 999.0)

    # A named tag is better than the rolling `:latest` of the same model.
    specific = 0.0 if str(name).endswith(":latest") else 5.0

    return (len(PREFERRED_FAMILIES) - rank) * 10000.0 + size * 10.0 + specific


def pick_best_model(names: list[str]) -> str | None:
    """The best model of those installed on this machine, or nothing when there is none."""
    candidates = [
        name
        for name in (names or [])
        if name and not is_embedding_model(name)
    ]

    if not candidates:
        return None

    return max(candidates, key=score_model)


def installed_models(url: str | None = None) -> list[str] | None:
    """
    The models this machine holds, or nothing when the model server cannot be reached.

    The model server is asked on its own address, without the `/v1` that the chat
    endpoint uses.
    """
    settings = get_settings()

    address = (url or settings.ollama_url or "").rstrip("/")

    if not address:
        return None

    try:
        response = httpx.get(f"{address}/api/tags", timeout=4.0)
        response.raise_for_status()

        return [model["name"] for model in response.json().get("models", [])]
    except Exception:
        return None


def _matches(names: list[str], wanted: str) -> str | None:
    """Whether this machine holds a model, and under which name."""
    if wanted in names:
        return wanted

    if f"{wanted}:latest" in names:
        return f"{wanted}:latest"

    if ":" in wanted:
        # A particular tag was asked for; only that tag will do.
        return None

    matches = [name for name in names if name.split(":")[0] == wanted]

    return matches[0] if matches else None


def resolve(names: list[str] | None = None) -> tuple[str, str]:
    """
    Which model to write with, and why.

    The model named in the settings wins whenever it is installed. When it is not, the
    best model that is installed is used instead, and the reason says so.
    """
    settings = get_settings()

    configured = (settings.llm_model or "").strip()

    if configured and configured.lower() != "auto":
        held = names if names is not None else installed_models()

        if held is None:
            return configured, f"the model server could not be reached, so {configured} is used as it is named"

        found = _matches(held, configured)

        if found:
            return found, f"{found} is named in the settings and is installed"

        if settings.llm_strict_model:
            raise RuntimeError(
                f"The model {configured} is named in the settings but is not installed on this machine, "
                "and LLM_STRICT_MODEL is set. Install it, or name another one."
            )

        best = pick_best_model(held)

        if best:
            return best, f"{configured} is not installed, so {best} is used instead"

        return configured, f"{configured} is not installed and no other model was found"

    # "auto": the best model that is installed.
    held = names if names is not None else installed_models()

    if held is None:
        return "", "the model server could not be reached, so no model is used"

    best = pick_best_model(held)

    if not best:
        return "", "no model for writing is installed on this machine"

    return best, f"{best} is the best model installed on this machine"
