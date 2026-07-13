"""Tests for GUI automation tool."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools_system import _handle_gui


class TestGuiTool(unittest.TestCase):
    """GUI automation tests (read-only operations only)."""

    def test_info(self):
        r = _handle_gui(action="info")
        self.assertIn("[GUI]", r)

    def test_get_window(self):
        r = _handle_gui(action="get_window")
        self.assertTrue(len(r) > 0)

    def test_screenshot(self):
        r = _handle_gui(action="screenshot")
        self.assertIn("GUI_SCREENSHOT", r)

    def test_unknown_action(self):
        r = _handle_gui(action="xyz")
        self.assertIn("未知", r)

    def test_type_no_text(self):
        r = _handle_gui(action="type")
        self.assertTrue(len(r) > 0)

    def test_keypress_no_key(self):
        r = _handle_gui(action="keypress")
        self.assertIn("错误", r)

    def test_locate_no_query(self):
        r = _handle_gui(action="locate")
        self.assertIn("错误", r)

    def test_registered(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertIn("gui", names)


if __name__ == "__main__":
    unittest.main()
