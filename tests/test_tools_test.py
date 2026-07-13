"""Tests for test driver tool."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools_test import discover_tests, run_tests, _handle_test


class TestDiscoverTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def _touch(self, rel_path: str, content: str = ""):
        full = os.path.join(self.root, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)

    def test_discover_empty(self):
        info = discover_tests(self.root)
        self.assertEqual(info["total"], 0)

    def test_discover_pytest_files(self):
        self._touch("tests/test_foo.py")
        self._touch("tests/test_bar.py")
        info = discover_tests(self.root)
        self.assertEqual(info["total"], 2)
        self.assertEqual(info["framework"], "pytest")

    def test_discover_with_conftest(self):
        self._touch("conftest.py")
        self._touch("test_app.py")
        info = discover_tests(self.root)
        self.assertEqual(info["total"], 1)

    def test_skips_node_modules(self):
        self._touch("node_modules/test_ignore.py")
        self._touch("tests/test_real.py")
        info = discover_tests(self.root)
        self.assertEqual(info["total"], 1)

    def test_handle_test_discover(self):
        self._touch("tests/test_x.py")
        result = _handle_test(action="discover", path=self.root)
        self.assertIn("框架", result)
        self.assertIn("test_x.py", result)

    def test_handle_test_discover_empty(self):
        result = _handle_test(action="discover", path=self.root)
        self.assertIn("未发现", result)

    def test_run_passes_when_all_pass(self):
        self._touch("test_ok.py", """
def test_pass():
    assert 1 + 1 == 2
""")
        result = run_tests(self.root, timeout=30)
        self.assertGreaterEqual(result["passed"], 1, f"Should have passes: {result}")
        self.assertEqual(result["failed"], 0)

    def test_run_detects_failures(self):
        self._touch("test_fail.py", """
def test_pass():
    assert 1 == 1

def test_fail():
    assert 1 == 2, "故意失败"
""")
        result = run_tests(self.root, timeout=30)
        self.assertGreaterEqual(result["passed"], 1)
        self.assertGreaterEqual(result["failed"], 1)

    def test_handle_test_run(self):
        self._touch("test_simple.py", "def test_ok(): assert True")
        result = _handle_test(action="run", path=self.root, timeout=30)
        self.assertIn("[测试]", result)

    def test_unknown_action(self):
        result = _handle_test(action="xyz")
        self.assertIn("未知操作", result)


class TestHandleTestTool(unittest.TestCase):
    """Test the tool dispatch path."""

    def test_tool_registered(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertIn("test", names)


if __name__ == "__main__":
    unittest.main()
