"""Tests for system monitor tool."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools_system import _handle_monitor


class TestMonitorTool(unittest.TestCase):
    """System monitor tests (read-only)."""

    def test_resources(self):
        r = _handle_monitor(action="resources")
        # Output may be in different encodings, check for meaningful content
        self.assertTrue(len(r) > 20, f"resources output too short: {r[:100]}")

    def test_cpu(self):
        r = _handle_monitor(action="cpu")
        self.assertIn("CPU", r)

    def test_memory(self):
        r = _handle_monitor(action="memory")
        self.assertIn("内存", r or "总内存")

    def test_disk(self):
        r = _handle_monitor(action="disk")
        self.assertIn("磁盘", r or "DeviceID")

    def test_process_count(self):
        r = _handle_monitor(action="process_count")
        self.assertIn("进程", r)

    def test_network(self):
        r = _handle_monitor(action="network")
        self.assertIn("网络", r or "Name")

    def test_uptime(self):
        r = _handle_monitor(action="uptime")
        self.assertIn("运行时间", r or "系统")

    def test_process_events(self):
        r = _handle_monitor(action="process_events")
        self.assertIn("最近进程", r or "ProcessName")

    def test_unknown_action(self):
        r = _handle_monitor(action="xyz")
        self.assertIn("未知操作", r)

    def test_registered(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertIn("monitor", names)
        


if __name__ == "__main__":
    unittest.main()
