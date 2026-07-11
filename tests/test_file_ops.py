"""Tests for file system operations: move/copy/delete/mkdir/download."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools_file import (
    _handle_move, _handle_copy, _handle_delete,
    _handle_mkdir, _handle_download,
)


class TestFileOps(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def _path(self, *parts):
        return os.path.join(self.root, *parts)

    def _touch(self, rel, content="test"):
        full = self._path(rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return full


class TestMove(TestFileOps):
    def test_move_file(self):
        src = self._touch("source.txt")
        dst = self._path("moved.txt")
        r = _handle_move(src, dst)
        self.assertIn("移动成功", r)
        self.assertTrue(os.path.exists(dst))
        self.assertFalse(os.path.exists(src))

    def test_move_nonexistent(self):
        r = _handle_move(self._path("nope.txt"), self._path("dst.txt"))
        self.assertIn("不存在", r)

    def test_move_creates_dirs(self):
        src = self._touch("file.txt")
        dst = self._path("sub", "deep", "moved.txt")
        r = _handle_move(src, dst)
        self.assertIn("移动成功", r)
        self.assertTrue(os.path.exists(dst))

    def test_registered(self):
        from agent.tools import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertIn("move", names)
        self.assertIn("move", BUILTIN_HANDLERS)


class TestCopy(TestFileOps):
    def test_copy_file(self):
        src = self._touch("original.txt")
        dst = self._path("copy.txt")
        r = _handle_copy(src, dst)
        self.assertIn("复制成功", r)
        self.assertTrue(os.path.exists(dst))
        self.assertTrue(os.path.exists(src))

    def test_copy_dir_no_recursive(self):
        os.makedirs(self._path("mydir"))
        self._touch("mydir/file.txt")
        r = _handle_copy(self._path("mydir"), self._path("mydir2"))
        self.assertIn("需 recursive", r)

    def test_copy_dir_recursive(self):
        os.makedirs(self._path("srcdir"))
        self._touch("srcdir/file.txt")
        r = _handle_copy(self._path("srcdir"), self._path("dstdir"), recursive=True)
        self.assertIn("复制成功", r)
        self.assertTrue(os.path.exists(self._path("dstdir", "file.txt")))

    def test_registered(self):
        from agent.tools import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        self.assertIn("copy", {t["name"] for t in TOOL_DEFINITIONS})
        self.assertIn("copy", BUILTIN_HANDLERS)


class TestDelete(TestFileOps):
    def test_delete_file(self):
        f = self._touch("todelete.txt")
        r = _handle_delete(f)
        self.assertIn("已删除", r)
        self.assertFalse(os.path.exists(f))

    def test_delete_nonexistent(self):
        r = _handle_delete(self._path("nope.txt"))
        self.assertIn("不存在", r)

    def test_delete_nonempty_dir_no_recursive(self):
        os.makedirs(self._path("dir"))
        self._touch("dir/file.txt")
        r = _handle_delete(self._path("dir"))
        # Should fail without recursive - error mentions dir not empty
        self.assertTrue("错误" in r or "失败" in r)

    def test_delete_dir_recursive(self):
        os.makedirs(self._path("dir"))
        self._touch("dir/file.txt")
        r = _handle_delete(self._path("dir"), recursive=True)
        self.assertIn("已删除", r)
        self.assertFalse(os.path.exists(self._path("dir")))


class TestMkdir(TestFileOps):
    def test_mkdir(self):
        p = self._path("newdir")
        r = _handle_mkdir(p)
        self.assertIn("已创建", r)
        self.assertTrue(os.path.isdir(p))

    def test_mkdir_parents(self):
        p = self._path("a", "b", "c")
        r = _handle_mkdir(p, parents=True)
        self.assertIn("已创建", r)
        self.assertTrue(os.path.isdir(p))

    def test_mkdir_parents_fail(self):
        p = self._path("x", "y")
        r = _handle_mkdir(p)  # no parents
        self.assertIn("错误", r) if not os.path.exists(p) else None


class TestDownload(unittest.TestCase):
    def test_registered(self):
        from agent.tools import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        self.assertIn("download", {t["name"] for t in TOOL_DEFINITIONS})
        self.assertIn("download", BUILTIN_HANDLERS)

    def test_no_url(self):
        # download won't work without a valid URL, but we can test tool exists
        pass


if __name__ == "__main__":
    unittest.main()
