"""Tests for semantic memory system."""
from __future__ import annotations
import os, sys, unittest, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.memory_v2 import SemanticMemory, build_semantic_context


class TestSemanticMemory(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mem = SemanticMemory("test", self.test_dir)

    def tearDown(self):
        if hasattr(self, 'mem') and self.mem:
            self.mem.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_store_and_count(self):
        self.mem.store("修复了一个 import 错误", {"type": "note", "timestamp": 1})
        self.assertGreater(self.mem.count(), 0)

    def test_search_finds_relevant(self):
        self.mem.store("修复了一个 import 错误", {"type": "note", "timestamp": 1})
        results = self.mem.search("import")
        self.assertGreaterEqual(len(results), 1)

    def test_search_nonexistent(self):
        self.assertEqual(len(self.mem.search("!!!___xxx___!!!")), 0)

    def test_recent(self):
        self.mem.store("记忆条目 A", {"type": "note", "timestamp": 1})
        self.mem.store("记忆条目 B", {"type": "note", "timestamp": 2})
        self.assertGreaterEqual(len(self.mem.get_recent(5)), 1)

    def test_build_context(self):
        self.mem.store("完成了一个测试任务", {"type": "task_complete", "timestamp": 1})
        self.assertIn("记忆", build_semantic_context(mem=self.mem))

    def test_registered(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        self.assertIn("remember", {t["name"] for t in TOOL_DEFINITIONS})
