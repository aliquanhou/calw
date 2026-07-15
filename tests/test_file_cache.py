"""Tests for MMAP file cache."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestFileCache(unittest.TestCase):
    def setUp(self):
        from agent.file_cache import reset_cache
        reset_cache()
        self.tmp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.tmp_dir, "test.txt")
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("hello world\nline 2\nline 3")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_read(self):
        from agent.file_cache import FileCache
        cache = FileCache(self.tmp_dir)
        content = cache.read("test.txt")
        self.assertIn("hello world", content)

    def test_read_line(self):
        from agent.file_cache import FileCache
        cache = FileCache(self.tmp_dir)
        line2 = cache.read_line("test.txt", 2)
        self.assertEqual(line2, "line 2")

    def test_read_line_outofrange(self):
        from agent.file_cache import FileCache
        cache = FileCache(self.tmp_dir)
        self.assertEqual(cache.read_line("test.txt", 999), "")

    def test_write_and_invalidate(self):
        from agent.file_cache import FileCache
        cache = FileCache(self.tmp_dir)
        cache.write("test.txt", "new content")
        content = cache.read("test.txt")
        self.assertEqual(content, "new content")

    def test_apply_diff(self):
        from agent.file_cache import FileCache
        cache = FileCache(self.tmp_dir)
        ok = cache.apply_diff("test.txt", "hello world", "hello cache")
        self.assertTrue(ok)
        content = cache.read("test.txt")
        self.assertIn("hello cache", content)

    def test_apply_diff_not_found(self):
        from agent.file_cache import FileCache
        cache = FileCache(self.tmp_dir)
        ok = cache.apply_diff("test.txt", "nonexistent", "replacement")
        self.assertFalse(ok)

    def test_get_cache(self):
        from agent.file_cache import get_cache, reset_cache
        reset_cache()
        c1 = get_cache(self.tmp_dir)
        c2 = get_cache(self.tmp_dir)
        self.assertIs(c1, c2)

    def test_cache_stats(self):
        from agent.file_cache import FileCache
        cache = FileCache(self.tmp_dir)
        cache.read("test.txt")
        self.assertGreaterEqual(cache.cache_size, 1)
        self.assertGreater(cache.cache_memory_usage, 0)


if __name__ == "__main__":
    unittest.main()
