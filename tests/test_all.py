"""Tests for Claw agent — core tool dispatch and analysis tools."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestToolDispatch(unittest.TestCase):
    """Test that all tools can be dispatched without crashing."""

    def test_all_tools_registered(self):
        from agent.tools import TOOL_DEFINITIONS, BUILTIN_HANDLERS, PLUGIN_HANDLERS
        def_names = {t["name"] for t in TOOL_DEFINITIONS}
        all_handlers = set(BUILTIN_HANDLERS.keys()) | set(PLUGIN_HANDLERS.keys())
        missing = def_names - all_handlers
        self.assertEqual(set(), missing,
                         f"Tools missing handlers: {missing}")

    def test_tool_definitions_valid(self):
        from agent.tools import TOOL_DEFINITIONS
        for t in TOOL_DEFINITIONS:
            self.assertIn("name", t)
            self.assertIn("description", t)
            self.assertIn("input_schema", t)
            self.assertIsInstance(t["input_schema"].get("properties"), dict)

    def test_unknown_tool(self):
        from agent.tools import handle_tool_call
        result = handle_tool_call("nonexistent_tool", {})
        self.assertIn("未知", result)


class TestReadTool(unittest.TestCase):
    def test_read_existing(self):
        from agent.tools import handle_tool_call
        result = handle_tool_call("read", {"file_path": __file__})
        self.assertIn("TestToolDispatch", result)
        self.assertTrue(len(result) > 100)

    def test_read_nonexistent(self):
        from agent.tools import handle_tool_call
        result = handle_tool_call("read", {"file_path": "/nonexistent/path"})
        self.assertIn("不存在", result)


class TestWriteEditTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
        self.tmp.write("hello world")
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_write_and_edit(self):
        from agent.tools import handle_tool_call
        # Write
        r1 = handle_tool_call("write", {"file_path": self.tmp.name, "content": "new content"})
        self.assertIn("写入", r1)
        # Verify via read
        r2 = handle_tool_call("read", {"file_path": self.tmp.name})
        self.assertIn("new content", r2)
        # Edit
        r3 = handle_tool_call("edit", {
            "file_path": self.tmp.name,
            "old_string": "new content",
            "new_string": "edited content",
        })
        self.assertIn("替换", r3)  # edit returns success msg in Chinese
        # Verify via read
        r4 = handle_tool_call("read", {"file_path": self.tmp.name})
        self.assertIn("edited", r4)


class TestGlobGrepTool(unittest.TestCase):
    def test_glob(self):
        from agent.tools import handle_tool_call
        result = handle_tool_call("glob", {"pattern": os.path.join(os.path.dirname(__file__), "*.py")})
        self.assertIn("test_", result)

    def test_grep(self):
        from agent.tools import handle_tool_call
        result = handle_tool_call("grep", {
            "pattern": "def test_",
            "path": os.path.dirname(__file__),
            "glob_pattern": "test_*.py",
        })
        self.assertTrue("test_" in result or "def" in result)


class TestASTTool(unittest.TestCase):
    def test_ast_self_analysis(self):
        from agent.tools import handle_tool_call
        result = handle_tool_call("ast", {"file_path": __file__})
        self.assertIn("class TestASTTool", result)
        self.assertIn("def test_ast_self_analysis", result)
        self.assertIn("import", result.lower())


class TestDepGraphTool(unittest.TestCase):
    def test_dep_graph_agent(self):
        from agent.tools import handle_tool_call
        result = handle_tool_call("dep_graph", {"path": os.path.join(os.path.dirname(__file__), "..", "agent")})
        self.assertIn("core.py", result)
        self.assertIn("tools.py", result)
        self.assertIn("外部依赖", result)


class TestCallChainTool(unittest.TestCase):
    def test_call_chain_forward(self):
        from agent.tools import handle_tool_call
        path = os.path.join(os.path.dirname(__file__), "..", "agent")
        result = handle_tool_call("call_chain", {
            "function_name": "_handle_read",
            "direction": "forward",
            "path": path,
        })
        self.assertIn("_handle_read", result)

    def test_call_chain_backward(self):
        from agent.tools import handle_tool_call
        path = os.path.join(os.path.dirname(__file__), "..", "agent")
        result = handle_tool_call("call_chain", {
            "function_name": "handle_tool_call",
            "direction": "backward",
            "path": path,
        })
        self.assertTrue(len(result) > 10)


class TestThinkTool(unittest.TestCase):
    def test_think(self):
        from agent.tools import handle_tool_call
        r1 = handle_tool_call("think", {"thought": "testing"})
        self.assertIn("记录", r1)
        r2 = handle_tool_call("think", {"content": "test"})
        self.assertIn("记录", r2)
        r3 = handle_tool_call("think", {"thought": "planning", "title": "analysis"})
        self.assertIn("记录", r3)


class TestBashTool(unittest.TestCase):
    def test_bash_echo(self):
        from agent.tools import handle_tool_call
        result = handle_tool_call("bash", {"command": "echo hello"})
        self.assertIn("hello", result)

    def test_bash_timeout(self):
        from agent.tools import handle_tool_call
        result = handle_tool_call("bash", {"command": "echo quick", "timeout": 5})
        self.assertIn("quick", result)


class TestMemory(unittest.TestCase):
    def setUp(self):
        # Use temp dir for memory
        self._orig_dir = os.environ.get("CLAW_MEMORY_DIR")
        self.tmp_dir = tempfile.mkdtemp()
        # Patch memory module's dir
        import agent.memory
        self._old_mem_dir = agent.memory.MEMORY_DIR
        agent.memory.MEMORY_DIR = self.tmp_dir
        agent.memory.CONVERSATIONS_DIR = os.path.join(self.tmp_dir, "conversations")
        agent.memory.CODEBASE_DIR = os.path.join(self.tmp_dir, "codebase")
        agent.memory.INDEX_FILE = os.path.join(self.tmp_dir, "index.json")

    def tearDown(self):
        import agent.memory
        agent.memory.MEMORY_DIR = self._old_mem_dir
        agent.memory.CONVERSATIONS_DIR = os.path.join(self._old_mem_dir, "conversations")
        agent.memory.CODEBASE_DIR = os.path.join(self._old_mem_dir, "codebase")
        agent.memory.INDEX_FILE = os.path.join(self._old_mem_dir, "index.json")
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_save_and_load(self):
        from agent.memory import save_turn, load_recent_context, get_conversation_stats
        save_turn("hello", "hi there", None, None)
        save_turn("analyze this", "found bugs", [{"function": {"name": "ast"}}], None)
        context = load_recent_context(max_turns=10)
        self.assertIn("hello", context)
        self.assertIn("analyze", context)
        stats = get_conversation_stats()
        self.assertGreaterEqual(stats["total_turns"], 2)

    def test_code_analysis_cache(self):
        from agent.memory import save_code_analysis, load_code_context
        # Use a path that will be keyed as "module"
        test_path = os.path.join(self.tmp_dir, "module.py")
        save_code_analysis(test_path, "ast", "class Foo: pass")
        cached = load_code_context(test_path)
        self.assertIn("Foo", cached)


class TestRetry(unittest.TestCase):
    def test_retry_success(self):
        from agent.retry import with_retry
        call_count = 0

        def succeeds():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = with_retry(succeeds)
        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 1)

    def test_retry_then_succeed(self):
        from agent.retry import with_retry
        call_count = 0

        def fails_then_works():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("transient")
            return "recovered"

        result = with_retry(fails_then_works, max_retries=3, base_delay=0.01)
        self.assertEqual(result, "recovered")
        self.assertEqual(call_count, 2)

    def test_retry_exhausted(self):
        from agent.retry import with_retry
        def always_fails():
            raise ConnectionError("always fails")
        with self.assertRaises(ConnectionError):
            with_retry(always_fails, max_retries=1, base_delay=0.01)

    def test_is_retryable(self):
        from agent.retry import is_retryable
        self.assertTrue(is_retryable(TimeoutError("timed out")))
        self.assertTrue(is_retryable(ConnectionError("connection reset")))
        self.assertFalse(is_retryable(ValueError("invalid input")))


class TestPlugin(unittest.TestCase):
    def test_plugin_loading(self):
        from agent.plugin import load_plugins, _discover_plugins
        plugins = _discover_plugins()
        self.assertGreaterEqual(len(plugins), 1)  # hash_file plugin
        defs, dispatch = load_plugins()
        self.assertIn("hash_file", dispatch)
        # Test it
        result = dispatch["hash_file"]({"file_path": __file__})
        self.assertIn(".py", result)


class TestContextManager(unittest.TestCase):
    """Test context window management — token estimation, truncation, compression."""

    def test_estimate_tokens(self):
        from agent.context import estimate_tokens
        self.assertGreater(estimate_tokens("hello world"), 0)
        self.assertEqual(estimate_tokens(""), 0)
        self.assertGreater(estimate_tokens("中文字符测试"), 0)
        # ~4 chars per token
        long_text = "a" * 400
        est = estimate_tokens(long_text)
        self.assertGreaterEqual(est, 98)
        self.assertLessEqual(est, 110)

    def test_get_context_limit(self):
        from agent.context import get_context_limit
        self.assertEqual(get_context_limit("deepseek-chat"), 65536)
        self.assertEqual(get_context_limit("claude-opus-4-7"), 200000)
        self.assertEqual(get_context_limit("gpt-4o"), 128000)
        self.assertEqual(get_context_limit(""), 65536)  # default

    def test_truncate_tool_results(self):
        from agent.context import truncate_tool_results
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "tool", "content": "x" * 8000},
            {"role": "tool", "content": "short"},
        ]
        result = truncate_tool_results(msgs)
        # User message unchanged
        self.assertEqual(result[0]["content"], "hello")
        # Long tool result truncated (smart_truncate adds truncation marker)
        self.assertIn("...", result[1]["content"])
        self.assertLess(len(result[1]["content"]), 6500)
        # Short tool result unchanged
        self.assertEqual(result[2]["content"], "short")

    def test_compress_under_limit(self):
        from agent.context import compress_messages
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = compress_messages(msgs, "[system]", "deepseek-chat")
        # Under limit, should be unchanged
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["content"], "hello")

    def test_compress_empty_messages(self):
        from agent.context import compress_messages
        self.assertEqual(compress_messages([], "system", "deepseek-chat"), [])

    def test_compact_messages(self):
        from agent.context import compact_messages
        # Create enough messages to trigger compaction
        msgs = []
        for i in range(20):
            msgs.append({"role": "user", "content": f"user message number {i} that is long enough to need truncation of content " * 6})
            msgs.append({"role": "assistant", "content": f"assistant response number {i} that is also quite verbose and long " * 6})
        result = compact_messages(msgs)
        self.assertLessEqual(len(result), len(msgs))
        # At least one old message should be compacted
        first_content = result[0].get("content", "")
        if "压缩" not in first_content:
            first_content = result[1].get("content", "")
        self.assertIn("压缩", first_content)

    def test_count_total_tokens(self):
        from agent.context import count_total_tokens
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        total = count_total_tokens(msgs, "system prompt")
        self.assertGreater(total, 0)


class TestSanitizeMessages(unittest.TestCase):
    """Test message integrity preservation after compression."""

    def test_keeps_valid_pairs(self):
        from agent.context import sanitize_messages
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call1", "function": {"name": "bash", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "call1", "content": "done"},
        ]
        result = sanitize_messages(msgs)
        self.assertEqual(len(result), 3)
        self.assertEqual(len(result[1]["tool_calls"]), 1)

    def test_strips_orphan_tool_calls(self):
        from agent.context import sanitize_messages
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call1", "function": {"name": "bash", "arguments": "{}"}}
            ]},
            # No tool result for call1 — entire empty assistant should be dropped
        ]
        result = sanitize_messages(msgs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["role"], "user")

    def test_drops_orphan_tool_result(self):
        from agent.context import sanitize_messages
        msgs = [
            {"role": "user", "content": "run something"},
            {"role": "tool", "tool_call_id": "orphan_call", "content": "result"},
        ]
        result = sanitize_messages(msgs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["role"], "user")

    def test_partial_orphan_keeps_valid(self):
        from agent.context import sanitize_messages
        msgs = [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "valid", "function": {"name": "bash", "arguments": "{}"}},
                {"id": "orphan", "function": {"name": "read", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "valid", "content": "output"},
            # No result for "orphan"
        ]
        result = sanitize_messages(msgs)
        # Should keep valid, strip orphan
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0]["tool_calls"]), 1)
        self.assertEqual(result[0]["tool_calls"][0]["id"], "valid")


class TestAgentCore(unittest.TestCase):
    """Test agent core — _call_with_timeout, StreamHandler, Agent initialization."""

    def test_call_with_timeout_success(self):
        from agent.core import _call_with_timeout
        result = _call_with_timeout(lambda x: x + 1, 10, 41)
        self.assertEqual(result, 42)

    def test_call_with_timeout_retry_then_success(self):
        from agent.core import _call_with_timeout
        call_count = [0]
        def flaky(x):
            call_count[0] += 1
            if call_count[0] < 2:
                raise ConnectionError("transient")
            return x
        result = _call_with_timeout(flaky, 10, "ok")
        self.assertEqual(result, "ok")
        self.assertEqual(call_count[0], 2)

    def test_call_with_timeout_exhausted(self):
        from agent.core import _call_with_timeout
        def always_fails():
            raise ConnectionError("always")
        with self.assertRaises(ConnectionError):
            _call_with_timeout(always_fails, 10)

    def test_call_with_timeout_timeout(self):
        from agent.core import _call_with_timeout
        def slow():
            import time
            time.sleep(100)
            return "never"
        with self.assertRaises(TimeoutError):
            _call_with_timeout(slow, 0.1)

    def test_stream_handler_base(self):
        from agent.core import StreamHandler
        h = StreamHandler()
        # All methods should be no-ops (not raise)
        h.on_text("hello")
        h.on_thinking("thinking")
        h.on_tool_start("read", {})
        h.on_tool_result("result")
        h.on_error("error")
        h.on_turn_end()
        h.on_complete()
        # If we got here, no exception was raised

    def test_agent_init(self):
        from unittest.mock import MagicMock
        from agent.core import Agent
        mock_provider = MagicMock()
        mock_provider.model = "deepseek-chat"
        agent = Agent(mock_provider)
        self.assertIsNotNone(agent.system_prompt)
        self.assertEqual(agent.messages, [])

    def test_agent_init_with_custom_prompt(self):
        from unittest.mock import MagicMock
        from agent.core import Agent
        mock_provider = MagicMock()
        mock_provider.model = "deepseek-chat"
        agent = Agent(mock_provider, system_prompt="custom prompt")
        self.assertIn("custom", agent.system_prompt)

    def test_agent_run_text_only(self):
        from unittest.mock import MagicMock, patch
        from agent.providers import StreamEvent
        from agent.core import Agent, StreamHandler

        mock_provider = MagicMock()
        mock_provider.model = "deepseek-chat"
        # stream_chat yields a text_delta followed by done
        mock_provider.stream_chat.return_value = [
            StreamEvent(type="text_delta", delta="Hello!"),
            StreamEvent(type="done", stop_reason="end_turn"),
        ]
        mock_provider.make_tool_result_messages.return_value = []

        agent = Agent(mock_provider, system_prompt="test")
        handler = StreamHandler()  # capture by checking messages after

        with patch("agent.core.compress_messages", side_effect=lambda msgs, sysp, model: msgs):
            with patch("agent.core.sanitize_messages", side_effect=lambda msgs: msgs):
                agent.run_iteration("test input", handler)

        # Should have user + assistant messages
        self.assertGreaterEqual(len(agent.messages), 2)
        self.assertEqual(agent.messages[-1]["role"], "assistant")

    def test_agent_run_tool_call(self):
        from unittest.mock import MagicMock, patch
        from agent.providers import StreamEvent
        from agent.core import Agent, StreamHandler
        import json

        mock_provider = MagicMock()
        mock_provider.model = "deepseek-chat"
        tool_id = "call_abc123"
        # stream_chat yields a tool_use_start + delta + done
        mock_provider.stream_chat.return_value = [
            StreamEvent(type="tool_use_start", tool_id=tool_id, tool_name="bash"),
            StreamEvent(type="tool_use_delta", tool_id=tool_id, partial_json=json.dumps({"command": "echo hi"})),
            StreamEvent(type="done", stop_reason="tool_use"),
        ]
        mock_provider.make_tool_result_messages.return_value = [
            {"role": "tool", "tool_call_id": tool_id, "content": "hi"}
        ]

        agent = Agent(mock_provider, system_prompt="test")
        handler = StreamHandler()

        with patch("agent.core.compress_messages", side_effect=lambda msgs, sysp, model: msgs):
            with patch("agent.core.sanitize_messages", side_effect=lambda msgs: msgs):
                with patch("agent.core.handle_tool_call", return_value="mocked result"):
                    agent.run_iteration("run command", handler)

        # Should have user + assistant (with tool_calls) + tool result
        roles = [m["role"] for m in agent.messages]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)
        self.assertIn("tool", roles)

    def test_agent_run_error(self):
        from unittest.mock import MagicMock, patch
        from agent.providers import StreamEvent
        from agent.core import Agent, StreamHandler

        mock_provider = MagicMock()
        mock_provider.model = "deepseek-chat"
        mock_provider.stream_chat.return_value = [
            StreamEvent(type="error", error_msg="API error"),
        ]

        agent = Agent(mock_provider, system_prompt="test")
        handler = StreamHandler()

        with patch("agent.core.compress_messages", side_effect=lambda msgs, sysp, model: msgs):
            with patch("agent.core.sanitize_messages", side_effect=lambda msgs: msgs):
                agent.run_iteration("test", handler)

        # Error should not crash, message list still valid
        self.assertGreaterEqual(len(agent.messages), 1)


class TestProviders(unittest.TestCase):
    """Test provider abstraction — StreamEvent, message helpers, factory."""

    def test_stream_event_defaults(self):
        from agent.providers import StreamEvent
        e = StreamEvent(type="text_delta")
        self.assertEqual(e.type, "text_delta")
        self.assertEqual(e.delta, "")
        self.assertEqual(e.tool_id, "")
        self.assertEqual(e.tool_name, "")
        self.assertEqual(e.partial_json, "")
        self.assertIsNone(e.stop_reason)
        self.assertEqual(e.error_msg, "")

    def test_stream_event_complete(self):
        from agent.providers import StreamEvent
        e = StreamEvent(
            type="tool_use_start", tool_id="t1", tool_name="read",
            tool_input={"file_path": "/test"},
        )
        self.assertEqual(e.type, "tool_use_start")
        self.assertEqual(e.tool_id, "t1")
        self.assertEqual(e.tool_input["file_path"], "/test")

    def test_make_assistant_msg_text(self):
        from agent.providers import make_assistant_msg
        msg = make_assistant_msg("hello")
        self.assertEqual(msg["role"], "assistant")
        self.assertEqual(msg["content"], "hello")
        self.assertNotIn("tool_calls", msg)

    def test_make_assistant_msg_tool_calls(self):
        from agent.providers import make_assistant_msg
        tcs = [{"id": "c1", "function": {"name": "bash"}}]
        msg = make_assistant_msg(None, tcs)
        self.assertEqual(msg["role"], "assistant")
        self.assertIsNone(msg["content"])
        self.assertEqual(msg["tool_calls"], tcs)

    def test_make_tool_result_msg(self):
        from agent.providers import make_tool_result_msg
        msg = make_tool_result_msg("call1", "result text")
        self.assertEqual(msg["role"], "tool")
        self.assertEqual(msg["tool_call_id"], "call1")
        self.assertEqual(msg["content"], "result text")

    def test_make_anthropic_tool_results(self):
        from agent.providers import make_anthropic_tool_results
        results = [{"tool_call_id": "c1", "content": "out"}]
        msgs = make_anthropic_tool_results(results)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"][0]["type"], "tool_result")

    def test_get_provider(self):
        from unittest.mock import patch
        from agent.providers import get_provider, AnthropicProvider, OpenAIProvider
        # Test known providers
        p1 = get_provider("Anthropic Claude", "sk-test", "claude-opus-4-7")
        self.assertIsInstance(p1, AnthropicProvider)
        p2 = get_provider("DeepSeek", "sk-test", "deepseek-chat", "https://api.deepseek.com")
        self.assertIsInstance(p2, OpenAIProvider)

    def test_get_provider_unknown(self):
        from agent.providers import get_provider
        with self.assertRaises(ValueError):
            get_provider("UnknownAI", "key", "model")

    def test_get_default_provider(self):
        from agent.providers import get_default_provider
        self.assertIsInstance(get_default_provider(), str)

    def test_get_models_for(self):
        from agent.providers import get_models_for
        models = get_models_for("Anthropic Claude")
        self.assertGreater(len(models), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestSmartTruncate(unittest.TestCase):
    """Test smart_truncate function."""

    def test_short_text_unchanged(self):
        from agent.tools import smart_truncate
        text = "hello world" * 10
        self.assertEqual(smart_truncate(text, 1000), text)

    def test_truncate_no_error(self):
        from agent.tools import smart_truncate
        text = "a" * 5000
        result = smart_truncate(text, 1000)
        self.assertIn("截断", result)
        self.assertLessEqual(len(result), 1100)

    def test_truncate_with_error_keeps_tail(self):
        from agent.tools import smart_truncate
        head = "a" * 1500
        tail = "Error: something failed in the build process"
        text = head + tail
        result = smart_truncate(text, 1000)
        self.assertIn("Error:", result)
        self.assertIn("failed in the build", result)

    def test_empty_string(self):
        from agent.tools import smart_truncate
        self.assertEqual(smart_truncate(""), "")

    def test_error_keyword_preserves_tail_chars(self):
        from agent.tools import smart_truncate
        text = "info line\n" * 100 + "Traceback (most recent call last):\n" + "error line\n" * 20
        result = smart_truncate(text, 500)
        self.assertIn("most recent call", result)


class TestPatternEngine(unittest.TestCase):
    """Test build error pattern recognition."""

    def setUp(self):
        from agent.build_patterns import PatternEngine
        self.engine = PatternEngine()

    def test_match_known_pattern(self):
        output = "Module parse failed: Unexpected token (10:2)\nYou may need an appropriate loader to handle this file type.\n> 'styles.css'"
        match = self.engine.match(output)
        self.assertIsNotNone(match)
        self.assertIn("label", match)
        self.assertIn("fix", match)

    def test_match_nativewind_pattern(self):
        output = "NativeWind: unrecognized style property 'some-nonexistent-class' is not compatible"
        match = self.engine.match(output)
        self.assertIsNotNone(match)
        self.assertIn("NativeWind", match["label"])

    def test_no_match_for_clean_output(self):
        output = "Build succeeded in 2.5s\nAll tests passed!"
        match = self.engine.match(output)
        self.assertIsNone(match)

    def test_no_match_for_empty(self):
        self.assertIsNone(self.engine.match(""))
        self.assertIsNone(self.engine.match(None))  # type: ignore

    def test_record_new_pattern(self):
        output = "FatalError: Something completely new and unexpected happened in module X"
        label = self.engine.record(output, "npx build")
        self.assertIsNotNone(label)

    def test_get_stats(self):
        stats = self.engine.get_stats()
        self.assertIn("total_patterns", stats)
        self.assertIn("matched_patterns", stats)
        self.assertIn("categories", stats)
        self.assertGreater(stats["total_patterns"], 0)

    def test_port_in_use_matches(self):
        output = "Error: listen EADDRINUSE: address already in use :::8081"
        match = self.engine.match(output)
        self.assertIsNotNone(match)
        self.assertIn("端口", match["label"])


class TestBuildRunnerRetry(unittest.TestCase):
    """Test BuildRunner retry detection logic."""

    def test_retryable_port_in_use(self):
        from agent.tools import BuildRunner
        runner = BuildRunner()
        self.assertTrue(runner._is_retryable("Error: listen EADDRINUSE :::8081"))

    def test_retryable_timeout(self):
        from agent.tools import BuildRunner
        runner = BuildRunner()
        self.assertTrue(runner._is_retryable("watchdog timeout: process did not respond"))

    def test_non_retryable_compile_error(self):
        from agent.tools import BuildRunner
        runner = BuildRunner()
        self.assertFalse(runner._is_retryable("SyntaxError: Unexpected token 'export'"))


class TestSummarizeProjectState(unittest.TestCase):
    """Test project state snapshot generation."""

    def test_empty_messages(self):
        from agent.context import summarize_project_state
        result = summarize_project_state([], 0)
        self.assertEqual(result, "")

    def test_basic_snapshot(self):
        from agent.context import summarize_project_state
        messages = [
            {"role": "user", "content": "创建一个 React Native 登录页面"},
            {"role": "assistant", "content": "我来创建。", "tool_calls": [
                {"id": "call1", "type": "function", "function": {"name": "write", "arguments": '{"file_path": "/tmp/login.tsx"}'}}
            ]},
            {"role": "tool", "tool_call_id": "call1", "content": "成功写入 200 字节"},
        ]
        result = summarize_project_state(messages, 3)
        self.assertIn("项目状态快照", result)
        self.assertIn("login.tsx", result)
        self.assertIn("React Native", result)

    def test_with_errors(self):
        from agent.context import summarize_project_state
        messages = [
            {"role": "user", "content": "修复构建错误"},
            {"role": "tool", "tool_call_id": "c1", "content": "STDERR:\nError: Build failed with exit code 1"},
        ]
        result = summarize_project_state(messages, 2)
        self.assertIn("项目状态快照", result)
        self.assertIn("Build failed", result)

