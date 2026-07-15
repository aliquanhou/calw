"""Tests for project_map module."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.project_map import ProjectMap


class TestProjectMapScan(unittest.TestCase):

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

    def test_empty_dir(self):
        pm = ProjectMap(self.root)
        m = pm.scan()
        self.assertEqual(m["project_name"], os.path.basename(self.root))
        self.assertEqual(m["total_files"], 0)

    def test_detects_python_files(self):
        self._touch("main.py", "print('hello')")
        self._touch("agent/core.py", "# core")
        m = ProjectMap(self.root).scan()
        self.assertEqual(len(m["source_files"]), 2)
        self.assertIn("Python", m["language_stats"])

    def test_detects_entry_points(self):
        self._touch("main.py")
        self._touch("index.js")
        m = ProjectMap(self.root).scan()
        self.assertIn("main.py", m["entry_points"])
        self.assertIn("index.js", m["entry_points"])

    def test_detects_test_files(self):
        self._touch("tests/test_main.py")
        self._touch("agent/core.py")
        m = ProjectMap(self.root).scan()
        expected = os.path.normpath("tests/test_main.py")
        self.assertIn(expected, m["test_files"])

    def test_detects_dependencies(self):
        self._touch("requirements.txt", "pytest>=7.0")
        self._touch("pyproject.toml", "[tool.pytest]")
        m = ProjectMap(self.root).scan()
        self.assertIn("requirements.txt", m["dependencies"])
        self.assertIn("pytest>=7.0", m["dependencies"]["requirements.txt"])

    def test_detects_build_scripts(self):
        self._touch("build.bat", "@echo off")
        self._touch("Makefile", "all:")
        m = ProjectMap(self.root).scan()
        self.assertGreaterEqual(len(m["build_scripts"]), 1)

    def test_skips_node_modules(self):
        self._touch("node_modules/pkg/index.js")
        self._touch("main.py")
        m = ProjectMap(self.root).scan()
        py_files = [s for s in m["source_files"] if s["language"] == "Python"]
        self.assertEqual(len(py_files), 1)

    def test_cache_returns_same(self):
        pm = ProjectMap(self.root)
        m1 = pm.scan()
        m2 = pm.scan()
        self.assertIs(m1, m2)

    def test_invalidate_works(self):
        pm = ProjectMap(self.root)
        m1 = pm.scan()
        pm.invalidate()
        m2 = pm.scan()
        self.assertIsNot(m1, m2)

    def test_multiple_languages(self):
        self._touch("server.py")
        self._touch("client.js")
        self._touch("app.ts")
        m = ProjectMap(self.root).scan()
        self.assertIn("Python", m["language_stats"])
        self.assertIn("JavaScript", m["language_stats"])
        self.assertIn("TypeScript", m["language_stats"])

    def test_to_prompt_block_non_empty(self):
        self._touch("main.py", "def main(): pass")
        self._touch("requirements.txt", "flask")
        result = ProjectMap(self.root).to_prompt_block()
        self.assertIn("项目地图", result)
        self.assertIn("Python", result)

    def test_to_prompt_block_empty_dir(self):
        result = ProjectMap(self.root).to_prompt_block()
        self.assertEqual(result, "")

    def test_skip_dirs_excluded(self):
        self._touch(".git/HEAD")
        self._touch("__pycache__/cache.pyc")
        self._touch("real.py")
        m = ProjectMap(self.root).scan()
        self.assertEqual(len(m["source_files"]), 1)

    def test_large_project_perf(self):
        for i in range(100):
            self._touch(f"src/module_{i}.py", f"x = {i}\n")
        for i in range(50):
            self._touch(f"tests/test_module_{i}.py", f"def test_{i}(): pass\n")
        import time
        pm = ProjectMap(self.root)
        t0 = time.time()
        m = pm.scan()
        elapsed = time.time() - t0
        self.assertEqual(len(m["source_files"]), 150)
        self.assertLess(elapsed, 2.0)

    def test_directory_counts(self):
        self._touch("src/main.py")
        self._touch("src/utils/helper.py")
        self._touch("tests/test_main.py")
        m = ProjectMap(self.root).scan()
        self.assertGreater(m["total_dirs"], 0)


if __name__ == "__main__":
    unittest.main()
