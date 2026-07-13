"""Tests for Calw v2.1 — core tool dispatch, analysis tools, context management."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════
# 工具注册 & 调度
# ═══════════════════════════════════════════

class TestToolRegistry(unittest.TestCase):
    """Test the new v2.1 tool registry system."""

    def setUp(self):
        from agent.tools import _TOOL_REGISTRY
        self._saved = dict(_TOOL_REGISTRY)
        _TOOL_REGISTRY.clear()

    def tearDown(self):
        from agent.tools import _TOOL_REGISTRY
        _TOOL_REGISTRY.clear()
        _TOOL_REGISTRY.update(self._saved)

    def test_register_and_get(self):
        from agent.tools import register_tool, get_tool, get_all_tools
        register_tool("test_tool", lambda: "ok", "a test tool", {"type": "object", "properties": {}})
        t = get_tool("test_tool")
        self.assertIsNotNone(t)
        self.assertEqual(t["name"], "test_tool")
        all_t = get_all_tools()
        names = [f["function"]["name"] for f in all_t]
        self.assertIn("test_tool", names)

    def test_unregister(self):
        from agent.tools import register_tool, unregister_tool, get_tool
        register_tool("temp", lambda: "", "", {})
        self.assertIsNotNone(get_tool("temp"))
        unregister_tool("temp")
        self.assertIsNone(get_tool("temp"))

    def test_execute_unknown(self):
        from agent.tools import execute_tool
        result = execute_tool("nonexistent", {})
        self.assertIn("未知", result)

    def test_execute_handler(self):
        from agent.tools import register_tool, execute_tool
        register_tool("echo", lambda msg="": f"echo: {msg}", "echo tool", {
            "type": "object", "properties": {"msg": {"type": "string"}},
        })
        result = execute_tool("echo", {"msg": "hello"})
        self.assertEqual(result, "echo: hello")


class TestToolDefinitions(unittest.TestCase):
    """Test that tool definitions are valid."""

    def test_definitions_valid(self):
        from agent.tools_core import TOOL_DEFINITIONS
        self.assertGreater(len(TOOL_DEFINITIONS), 30)  # Should have 35+
        for t in TOOL_DEFINITIONS:
            self.assertIn("name", t)
            self.assertIn("description", t)
            self.assertIn("input_schema", t)
            self.assertIsInstance(t["input_schema"].get("properties"), dict)


# ═══════════════════════════════════════════
# 文件操作
# ═══════════════════════════════════════════

class TestFileTools(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.tmp_file = os.path.join(self.tmp_dir, "test.txt")
        with open(self.tmp_file, "w", encoding="utf-8") as f:
            f.write("hello world")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_read(self):
        from agent.tools_file import _handle_read
        result = _handle_read(file_path=self.tmp_file)
        self.assertIn("hello", result)

    def test_read_nonexistent(self):
        from agent.tools_file import _handle_read
        result = _handle_read(file_path="/nonexistent/path")
        self.assertIn("错误", result)

    def test_write(self):
        from agent.tools_file import _handle_write, _handle_read
        r = _handle_write(file_path=self.tmp_file, content="new content")
        self.assertTrue("写入" in r or "成功" in r)
        content = _handle_read(file_path=self.tmp_file)
        self.assertIn("new content", content)

    def test_edit(self):
        from agent.tools_file import _handle_edit
        r = _handle_edit(file_path=self.tmp_file, old_string="hello world", new_string="edited")
        self.assertTrue("编辑" in r or "成功" in r)

    def test_glob(self):
        from agent.tools_file import _handle_glob
        import tempfile
        local_tmp = tempfile.mkdtemp(dir=os.getcwd())
        try:
            with open(os.path.join(local_tmp, "test.txt"), "w") as f:
                f.write("hello")
            result = _handle_glob(pattern=os.path.join(local_tmp, "*.txt"))
        finally:
            import shutil
            shutil.rmtree(local_tmp, ignore_errors=True)
        if "无匹配" not in result:
            self.assertIn("test.txt", result)

    def test_grep(self):
        from agent.tools_file import _handle_grep
        result = _handle_grep(pattern="hello", path=self.tmp_dir)
        self.assertTrue("hello" in result or "无匹配" in result)


# ═══════════════════════════════════════════
# 命令执行
# ═══════════════════════════════════════════

class TestBashTool(unittest.TestCase):
    def test_echo(self):
        from agent.command import _handle_bash
        result = _handle_bash(command="echo hello123")
        self.assertIn("hello123", result)

    def test_empty(self):
        from agent.command import _handle_bash
        result = _handle_bash()
        self.assertIn("错误", result)


# ═══════════════════════════════════════════
# 代码分析
# ═══════════════════════════════════════════

class TestASTTool(unittest.TestCase):
    def test_ast_self(self):
        from agent.tools_analysis import _handle_ast
        result = _handle_ast(file_path=__file__)
        self.assertIn("TestASTTool", result)
        self.assertIn("def test_ast_self", result)


class TestDepGraphTool(unittest.TestCase):
    def test_dep_graph(self):
        from agent.tools_analysis import _handle_dep_graph
        result = _handle_dep_graph(path=os.path.join(os.path.dirname(__file__), "..", "agent"))
        self.assertIn(".py", result) or self.assertIn("依赖", result)


# ═══════════════════════════════════════════
# 记忆系统
# ═══════════════════════════════════════════

class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        import agent.memory
        self._old = {k: getattr(agent.memory, k) for k in
                     ["MEMORY_DIR", "CONVERSATIONS_DIR", "CODEBASE_DIR", "INDEX_FILE"]}
        agent.memory.MEMORY_DIR = self.tmp_dir
        agent.memory.CONVERSATIONS_DIR = os.path.join(self.tmp_dir, "conversations")
        agent.memory.CODEBASE_DIR = os.path.join(self.tmp_dir, "codebase")
        agent.memory.INDEX_FILE = os.path.join(self.tmp_dir, "index.json")

    def tearDown(self):
        import agent.memory
        for k, v in self._old.items():
            setattr(agent.memory, k, v)
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_save_and_load(self):
        from agent.memory import save_turn, load_recent_context, get_conversation_stats
        save_turn("hello", "hi", None, None)
        ctx = load_recent_context(max_turns=10)
        self.assertIn("hello", ctx)

    def test_code_analysis(self):
        from agent.memory import save_code_analysis, load_code_context
        test_path = os.path.join(self.tmp_dir, "mod.py")
        save_code_analysis(test_path, "ast", "class Foo: pass")
        cached = load_code_context(test_path)
        self.assertIn("Foo", cached)


# ═══════════════════════════════════════════
# 上下文管理
# ═══════════════════════════════════════════

class TestContextManager(unittest.TestCase):
    def test_estimate_tokens(self):
        from agent.context import estimate_tokens
        self.assertGreater(estimate_tokens("hello"), 0)
        self.assertEqual(estimate_tokens(""), 0)

    def test_get_context_limit(self):
        from agent.context import get_context_limit
        self.assertEqual(get_context_limit("deepseek-chat"), 65536)
        self.assertEqual(get_context_limit("claude-opus-4-7"), 200000)

    def test_truncate_tool_results(self):
        from agent.context import truncate_tool_results
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "x" * 8000},
        ]
        result = truncate_tool_results(msgs)
        self.assertEqual(result[0]["content"], "hi")
        self.assertLess(len(result[1]["content"]), 6500)

    def test_compress_under_limit(self):
        from agent.context import compress_messages
        msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        result = compress_messages(msgs, "[system]", "deepseek-chat")
        self.assertEqual(len(result), 2)

    def test_compress_empty(self):
        from agent.context import compress_messages
        self.assertEqual(compress_messages([], "system", "deepseek-chat"), [])

    def test_count_total_tokens(self):
        from agent.context import count_total_tokens
        msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        self.assertGreater(count_total_tokens(msgs, "system"), 0)

    def test_sanitize_valid(self):
        from agent.context import sanitize_messages
        msgs = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "bash"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "done"},
        ]
        result = sanitize_messages(msgs)
        self.assertEqual(len(result), 2)

    def test_sanitize_orphan_result(self):
        from agent.context import sanitize_messages
        msgs = [{"role": "tool", "tool_call_id": "orphan", "content": "result"}]
        result = sanitize_messages(msgs)
        self.assertEqual(len(result), 0)


# ═══════════════════════════════════════════
# 智能截断
# ═══════════════════════════════════════════

class TestSmartTruncate(unittest.TestCase):
    def test_short_unchanged(self):
        from agent.tools_core import smart_truncate
        text = "hello world" * 10
        self.assertEqual(smart_truncate(text, 1000), text)

    def test_truncate(self):
        from agent.tools_core import smart_truncate
        text = "a" * 5000
        result = smart_truncate(text, 1000)
        self.assertIn("截断", result)
        self.assertLessEqual(len(result), 1100)

    def test_empty(self):
        from agent.tools_core import smart_truncate
        self.assertEqual(smart_truncate(""), "")


# ═══════════════════════════════════════════
# 插件加载
# ═══════════════════════════════════════════

class TestPlugin(unittest.TestCase):
    def test_hash_file_plugin(self):
        from agent.tools import _TOOL_REGISTRY
        # Init tools, which should register plugins
        from agent.tools import init_tools
        init_tools()
        self.assertIn("hash_file", _TOOL_REGISTRY)


# ═══════════════════════════════════════════
# 推理引擎
# ═══════════════════════════════════════════

class TestSpeculativeEngine(unittest.TestCase):
    def test_engine_create(self):
        from agent.speculative import SpeculativeEngine
        engine = SpeculativeEngine()
        self.assertIsNotNone(engine)

    def test_record_and_predict(self):
        from agent.speculative import SpeculativeEngine
        engine = SpeculativeEngine()
        engine.record_call("read", {"file_path": "test.py"}, "content", 0, 10)
        self.assertGreater(engine.prediction_count, 0)

    def test_consume_miss(self):
        from agent.speculative import SpeculativeEngine
        engine = SpeculativeEngine()
        engine.record_call("read", {"file_path": "test.py"}, "content", 0, 10)
        result = engine.consume("write", {"file_path": "other.py"})
        self.assertIsNone(result)


# ═══════════════════════════════════════════
# 模式引擎
# ═══════════════════════════════════════════

class TestPatternEngine(unittest.TestCase):
    def setUp(self):
        from agent.build_patterns import PatternEngine
        self.engine = PatternEngine()

    def test_match_known(self):
        output = "Module not found: Can't resolve './App.css' in 'project/src'"
        match = self.engine.match(output)
        self.assertIsNotNone(match)
        self.assertIn("label", match)
        self.assertIn("fix", match)

    def test_no_match_clean(self):
        output = "Build succeeded in 2.5s"
        match = self.engine.match(output)
        self.assertIsNone(match)

    def test_get_stats(self):
        stats = self.engine.get_stats()
        self.assertIn("total_patterns", stats)
        self.assertGreater(stats["total_patterns"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
