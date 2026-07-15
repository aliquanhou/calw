"""Tests for enhanced ask_user."""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools_web import _handle_ask_user


class TestAskUser(unittest.TestCase):
    def test_basic_question(self):
        r = _handle_ask_user(question="要继续吗?")
        self.assertIn("要继续吗", r)
        self.assertIn("需要你的决定", r)

    def test_with_options(self):
        options = json.dumps(["方案A：重试", "方案B：跳过", "方案C：终止"])
        r = _handle_ask_user(question="如何处理?", options=options)
        self.assertIn("方案A", r)
        self.assertIn("方案B", r)
        self.assertIn("方案C", r)
        self.assertIn("[A]", r)
        self.assertIn("[B]", r)
        self.assertIn("[C]", r)

    def test_with_analysis(self):
        r = _handle_ask_user(question="选哪个?", analysis="已尝试3次均失败")
        self.assertIn("分析", r)
        self.assertIn("已尝试3次", r)

    def test_with_recommendation(self):
        options = json.dumps(["重试", "跳过", "终止"])
        r = _handle_ask_user(question="如何处理?", options=options, recommended="B")
        self.assertIn("推荐", r)
        self.assertIn("B", r)

    def test_all_params(self):
        options = json.dumps(["方案1", "方案2"])
        r = _handle_ask_user(
            question="如何继续?",
            options=options,
            analysis="构建失败：端口被占用",
            recommended="方案2",
        )
        self.assertIn("构建失败", r)
        self.assertIn("方案1", r)
        self.assertIn("方案2", r)
        self.assertIn("推荐", r)

    def test_invalid_options_json(self):
        r = _handle_ask_user(question="继续?", options="不是json")
        self.assertFalse("Traceback" in r)

    def test_empty_question(self):
        r = _handle_ask_user(question="")
        self.assertIn("错误", r)

    def test_registered_in_tools(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertIn("ask_user", names)


if __name__ == "__main__":
    unittest.main()
