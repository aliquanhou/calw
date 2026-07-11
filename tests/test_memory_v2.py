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
        self.assertTrue(self.mem.store("测试内容", {"type": "note"}))
        self.assertGreater(self.mem.count(), 0)

    def test_search_finds_relevant(self):
        self.mem.store("修复了import报错", {"type": "error"})
        results = self.mem.search("import")
        self.assertGreaterEqual(len(results), 1)

    def test_search_nonexistent(self):
        self.assertEqual(len(self.mem.search("!!!___xxx___!!!")), 0)

    def test_recent(self):
        self.mem.store("第一条", {"type": "note"})
        self.mem.store("第二条", {"type": "note"})
        self.assertGreaterEqual(len(self.mem.get_recent(5)), 1)

    def test_build_context(self):
        self.mem.store("完成了登录功能", {"type": "task_complete"})
        self.assertIn("语义记忆", build_semantic_context(mem=self.mem))

    def test_registered(self):
        from agent.tools import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        self.assertIn("remember", {t["name"] for t in TOOL_DEFINITIONS})
        self.assertIn("remember", BUILTIN_HANDLERS)
