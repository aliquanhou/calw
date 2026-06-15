"""Tests for providers: cost tracking, MODEL_PRICING."""
from __future__ import annotations
import sys,os
sys.path.insert(0,os.path.join(os.path.dirname(__file__),".."))
from agent.providers import reset_usage,track_usage,get_usage_summary,estimate_cost,MODEL_PRICING,get_provider,get_default_provider,get_models_for
class TestCost:
    def setup_method(self):reset_usage()
    def test_reset(self):track_usage(100,50);reset_usage();assert"暂无"in get_usage_summary()
    def test_track(self):track_usage(1000,200);track_usage(2000,400);s=get_usage_summary();assert"2次"in s;assert"3,000"in s
    def test_deepseek(self):c=estimate_cost("deepseek-chat",1000,500);assert 0<c<0.01
    def test_opus(self):c=estimate_cost("claude-opus-4-7",1000,500);assert 0.01<c<0.1
    def test_unknown(self):c=estimate_cost("unknown",1000,500);assert c>0
class TestPricing:
    def test_all(self):
        for m in["claude-opus-4-7","claude-sonnet-4-6","claude-haiku-4-5","deepseek-chat","deepseek-reasoner","gpt-4o","gpt-4o-mini"]:assert m in MODEL_PRICING
    def test_positive(self):assert all(p["input"]>0 and p["output"]>0 for p in MODEL_PRICING.values())
class TestGet:
    def test_anthropic(self):
        from agent.providers import AnthropicProvider;assert isinstance(get_provider("Anthropic Claude","sk-t","opus"),AnthropicProvider)
    def test_deepseek(self):
        from agent.providers import OpenAIProvider;assert isinstance(get_provider("DeepSeek","sk-t","deepseek-chat"),OpenAIProvider)
    def test_unknown(self):
        import pytest
        with pytest.raises(ValueError):get_provider("Unknown","k","m")
    def test_default(self):assert isinstance(get_default_provider(),str)
    def test_models(self):assert"claude-opus-4-7"in get_models_for("Anthropic Claude")
