"""Tests for command execution tool."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestBashTool(unittest.TestCase):
    def setUp(self):
        from agent.tools import register_tool
        from agent.tools_file import _handle_read
        from agent.command import _handle_bash
        # Ensure bash tool is registered
        register_tool("bash", _handle_bash, "执行命令", {
            "type": "object",
            "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}},
            "required": ["command"],
        })
        register_tool("read", _handle_read, "读取文件", {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        })

    def test_empty_command(self):
        from agent.command import _handle_bash
        result = _handle_bash()
        self.assertIn("错误", result)
        self.assertIn("command", result)

    def test_echo(self):
        from agent.command import _handle_bash
        result = _handle_bash("echo hello123")
        self.assertIn("hello123", result)

    def test_timeout(self):
        from agent.command import _handle_bash
        result = _handle_bash("ping -n 10 127.0.0.1", timeout=1)
        self.assertIn("超时", result)

    def test_nonexistent_command(self):
        from agent.command import _handle_bash
        result = _handle_bash("nonexistent_command_xyz")
        # Should return error, not crash
        self.assertTrue(isinstance(result, str))

    def test_execute_via_tools(self):
        from agent.tools import execute_tool
        result = execute_tool("bash", {"command": "echo tool_test", "timeout": 5})
        if isinstance(result, str):
            self.assertTrue("tool_test" in result or "退出码" in result)


if __name__ == "__main__":
    unittest.main()
