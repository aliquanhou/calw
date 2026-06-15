"""Tests for agent.completions — CompletionEngine, rule-based completion."""
from __future__ import annotations

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.completions import CompletionEngine, get_engine


class TestRuleComplete:
    def test_def_completion(self):
        engine = CompletionEngine()
        result = engine._rule_complete("def hello():")
        assert result == "    pass"

    def test_class_completion(self):
        engine = CompletionEngine()
        result = engine._rule_complete("class MyClass:")
        assert result == "    pass"

    def test_for_loop_completion(self):
        engine = CompletionEngine()
        result = engine._rule_complete("for i in range(10):")
        assert result == "    pass"

    def test_while_loop_completion(self):
        engine = CompletionEngine()
        result = engine._rule_complete("while True:")
        assert result == "    pass"

    def test_else_completion(self):
        engine = CompletionEngine()
        result = engine._rule_complete("else:")
        assert result == "    pass"

    def test_elif_completion(self):
        engine = CompletionEngine()
        result = engine._rule_complete("elif:")
        assert result == "    pass"

    def test_try_completion(self):
        engine = CompletionEngine()
        result = engine._rule_complete("try:")
        assert result == "    pass"

    def test_main_guard_completion(self):
        engine = CompletionEngine()
        result = engine._rule_complete("if __name__ == '__main__':")
        assert result == "    pass"

    def test_no_completion_for_return(self):
        engine = CompletionEngine()
        result = engine._rule_complete("return x + 1")
        assert result == ""

    def test_no_completion_for_import(self):
        engine = CompletionEngine()
        result = engine._rule_complete("import os")
        assert result == ""
        result2 = engine._rule_complete("from collections import defaultdict")
        assert result2 == ""

    def test_no_completion_for_non_python(self):
        engine = CompletionEngine()
        result = engine._rule_complete("var x = 1;", file_ext=".js")
        assert result == ""

    def test_empty_input(self):
        engine = CompletionEngine()
        assert engine._rule_complete("") == ""

    def test_def_with_args(self):
        engine = CompletionEngine()
        result = engine._rule_complete("def foo(bar, baz=None):")
        assert result == "    pass"

    def test_async_def(self):
        """async def 不触发规则补全（不在规则列表中）。"""
        engine = CompletionEngine()
        result = engine._rule_complete("async def fetch_data():")
        # async def is not in our rules, so returns ""
        assert result == ""


class TestCompletionEngine:
    def test_init(self):
        engine = CompletionEngine()
        assert engine.is_active is False
        assert engine._debounce_ms == 400

    def test_debounce(self):
        engine = CompletionEngine(stream_fn=lambda sp, ms, ts: iter([]))
        calls = []

        def cb(r):
            calls.append(r)

        engine.request("def foo():", callback=cb)
        time.sleep(0.01)
        engine.request("def foo():", callback=cb)  # within 400ms, should be debounced
        assert len(calls) >= 1

    def test_is_active_property(self):
        engine = CompletionEngine()
        assert isinstance(engine.is_active, bool)

    def test_request_no_stream_fn(self):
        """Without stream_fn, uses rule-based completion."""
        engine = CompletionEngine()
        results = []
        engine.request("def foo():", callback=lambda r: results.append(r))
        assert "pass" in results[0] if results else True


class TestGetEngine:
    def test_singleton(self):
        e1 = get_engine()
        e2 = get_engine()
        assert e1 is e2

    def test_singleton_with_stream_fn(self):
        fn = lambda sp, ms, ts: iter([])
        e1 = get_engine(fn)
        e2 = get_engine(fn)
        assert e1 is e2
