"""Tests for extra tools: schedule, watch, websocket."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools_extra import _handle_schedule, _handle_watch, _handle_websocket


class TestScheduleTool(unittest.TestCase):
    def test_list_empty(self):
        r = _handle_schedule(action="list")
        self.assertTrue(len(r) > 0)

    def test_add(self):
        r = _handle_schedule(action="add", name="test", cron="*/5 * * * *", command="echo hello")
        self.assertIn("已创建", r)
        # Cleanup
        import agent.scheduler as sched_mod
        s = sched_mod.get_scheduler()
        tasks = s.list_tasks()
        for t in tasks:
            if t.name == "test_schedule":
                s.remove_task(t.id)

    def test_remove_no_id(self):
        r = _handle_schedule(action="remove")
        self.assertIn("错误", r)

    def test_unknown_action(self):
        r = _handle_schedule(action="xyz")
        self.assertIn("未知操作", r)

    def test_registered(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        self.assertIn("schedule", {t["name"] for t in TOOL_DEFINITIONS})


class TestWatchTool(unittest.TestCase):
    def test_list_empty(self):
        r = _handle_watch(action="list")
        self.assertTrue(len(r) > 0)

    def test_add_no_path(self):
        r = _handle_watch(action="add", name="test")
        self.assertIn("错误", r)

    def test_unknown_action(self):
        r = _handle_watch(action="xyz")
        self.assertIn("未知操作", r)

    def test_registered(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        self.assertIn("watch", {t["name"] for t in TOOL_DEFINITIONS})


class TestWebSocketTool(unittest.TestCase):
    def test_connect_no_url(self):
        r = _handle_websocket(action="connect")
        self.assertIn("错误", r)

    def test_send_no_url(self):
        r = _handle_websocket(action="send")
        self.assertIn("错误", r)

    def test_ping_no_url(self):
        r = _handle_websocket(action="ping")
        self.assertIn("错误", r)

    def test_unknown_action(self):
        r = _handle_websocket(action="xyz")
        self.assertIn("未知操作", r)

    def test_registered(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        self.assertIn("websocket", {t["name"] for t in TOOL_DEFINITIONS})


if __name__ == "__main__":
    unittest.main()
