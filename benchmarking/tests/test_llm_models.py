"""
Tests for the choice of the language model.

The app has to use the model that is actually installed on the machine. A model that is named
but not pulled is replaced by the best one that is there, and the reason is always reported so
that it can be shown in the interface.
"""

import os

import pytest


@pytest.fixture()
def llm():
    """The client, with the settings of the machine under test."""
    from kpibench.llm import LLM

    return LLM()


INSTALLED = [
    "nomic-embed-text:latest",
    "qwen3:8b",
    "qwen2.5:14b",
]


# ------------------------------------------------------------------ the choice
def test_the_newest_family_wins(llm):
    """The machine may hold more than one model; the newest family is the one that was meant."""
    assert llm.resolve(INSTALLED)[0] == "qwen3:8b"


def test_a_model_for_embeddings_is_never_used(llm):
    """A model for embeddings cannot write a report."""
    assert llm.resolve(["nomic-embed-text:latest"])[0] is None


def test_the_larger_model_of_a_family_wins():
    from kpibench.llm import pick_best_model

    assert pick_best_model(["qwen3:8b", "qwen3:30b-a3b"]) == "qwen3:30b-a3b"


def test_a_family_name_is_matched_to_the_tag_that_is_installed(llm):
    """`qwen3` names a family; the server holds it as `qwen3:8b`."""
    assert llm.resolve(INSTALLED) is not None

    assert llm._match(INSTALLED, "qwen3") == "qwen3:8b"
    assert llm._match(INSTALLED, "qwen3:8b") == "qwen3:8b"
    assert llm._match(INSTALLED, "qwen3:30b") is None


# ----------------------------------------------------------------- the settings
def test_the_named_model_is_used_when_it_is_installed(llm, monkeypatch):
    from kpibench import config

    monkeypatch.setattr(config.settings, "OLLAMA_MODEL", "qwen2.5:14b")
    monkeypatch.setattr(config.settings, "OLLAMA_STRICT_MODEL", False)

    model, reason = llm.resolve(INSTALLED)

    assert model == "qwen2.5:14b"
    assert "OLLAMA_MODEL" in reason


def test_a_model_that_is_not_installed_is_replaced(llm, monkeypatch):
    """The model named in the settings is not pulled; the best one that is there is used."""
    from kpibench import config

    monkeypatch.setattr(config.settings, "OLLAMA_MODEL", "qwen2.5:14b")
    monkeypatch.setattr(config.settings, "OLLAMA_STRICT_MODEL", False)

    model, reason = llm.resolve(["qwen3:8b"])

    assert model == "qwen3:8b"
    assert "not pulled" in reason


def test_a_strict_machine_refuses_another_model(llm, monkeypatch):
    from kpibench import config

    monkeypatch.setattr(config.settings, "OLLAMA_MODEL", "qwen2.5:14b")
    monkeypatch.setattr(config.settings, "OLLAMA_STRICT_MODEL", True)

    model, reason = llm.resolve(["qwen3:8b"])

    assert model is None
    assert "ollama pull" in reason


def test_auto_uses_the_best_model_that_is_installed(llm, monkeypatch):
    from kpibench import config

    monkeypatch.setattr(config.settings, "OLLAMA_MODEL", "auto")
    monkeypatch.setattr(config.settings, "OLLAMA_STRICT_MODEL", False)

    model, reason = llm.resolve(INSTALLED)

    assert model == "qwen3:8b"
    assert "best model" in reason


def test_the_reason_says_how_to_install_a_model(llm, monkeypatch):
    """When nothing is installed, the reason says what to run."""
    from kpibench import config

    monkeypatch.setattr(config.settings, "OLLAMA_MODEL", "auto")
    monkeypatch.setattr(config.settings, "OLLAMA_STRICT_MODEL", False)

    model, reason = llm.resolve([])

    assert model is None
    assert "ollama pull" in reason


# ------------------------------------------------------------------- the names
def test_the_family_and_the_size_are_read_from_the_name():
    from kpibench.llm import model_family, model_size_b

    assert model_family("qwen3:8b") == "qwen3"
    assert model_family("llama3.3:70b") == "llama3.3"
    assert model_size_b("qwen3:8b") == 8.0
    assert model_size_b("qwen2.5:14b") == 14.0
    assert model_size_b("qwen3:30b-a3b") == 30.0
    assert model_size_b("mystery") == 0.0


def test_a_model_for_embeddings_is_recognised():
    from kpibench.llm import is_embedding_model

    assert is_embedding_model("nomic-embed-text:latest")
    assert is_embedding_model("bge-m3:latest")
    assert not is_embedding_model("qwen3:8b")
