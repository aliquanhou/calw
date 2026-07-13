"""Tests for providers — model pricing, factory, provider instantiation."""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.providers import LLMProvider, AnthropicProvider, OpenAIProvider, create_llm_provider
from agent.router import _MODEL_PRICING, classify_task, recommend_model


class TestModelPricing:
    def test_all_models_present(self):
        models = [
            "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5",
            "deepseek-chat", "deepseek-reasoner", "gpt-4o", "gpt-4o-mini",
        ]
        for m in models:
            assert m in _MODEL_PRICING, f"Missing: {m}"

    def test_prices_positive(self):
        for p in _MODEL_PRICING.values():
            assert p["input"] > 0
            assert p["output"] > 0


class TestProviderFactory:
    def test_anthropic(self):
        provider = create_llm_provider({"model": "claude-sonnet-4-6"})
        assert isinstance(provider, AnthropicProvider)

    def test_openai(self):
        provider = create_llm_provider({"model": "gpt-4o"})
        assert isinstance(provider, OpenAIProvider)

    def test_deepseek(self):
        provider = create_llm_provider({"model": "deepseek-chat"})
        assert isinstance(provider, OpenAIProvider)
        assert "deepseek" in provider.base_url

    def test_unknown(self):
        import pytest
        with pytest.raises(ValueError):
            create_llm_provider({"model": "unknown-model-xyz"})

    def test_abstract_method(self):
        p = LLMProvider()
        import pytest
        with pytest.raises(NotImplementedError):
            p.complete("system", [])


class TestRouter:
    def test_classify_simple(self):
        assert classify_task("grep for something") == "simple"

    def test_classify_code_gen(self):
        assert classify_task("write a function") == "code_gen"

    def test_classify_debug(self):
        assert classify_task("fix this error") == "debug"

    def test_recommend_model(self):
        models = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"]
        r = recommend_model("simple search", models)
        assert r == "claude-haiku-4-5"  # cheapest for simple task
