"""Tests for file operations: move/copy/delete/mkdir/download/replace."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools_file import (
    _handle_move, _handle_copy, _handle_delete,
    _handle_mkdir, _handle_download, _handle_replace,
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
        r = _handle_move(source=src, destination=dst)
        self.assertIn("移动", r)
        self.assertTrue(os.path.exists(dst))
        self.assertFalse(os.path.exists(src))

    def test_move_nonexistent(self):
        r = _handle_move(source=self._path("nope.txt"), destination=self._path("dst.txt"))
        self.assertIn("错误", r)


class TestCopy(TestFileOps):
    def test_copy_file(self):
        src = self._touch("original.txt")
        dst = self._path("copy.txt")
        r = _handle_copy(source=src, destination=dst)
        self.assertIn("复制", r)
        self.assertTrue(os.path.exists(dst))
        self.assertTrue(os.path.exists(src))

    def test_copy_dir_no_recursive(self):
        os.makedirs(self._path("mydir"))
        self._touch("mydir/file.txt")
        r = _handle_copy(source=self._path("mydir"), destination=self._path("mydir2"))
        self.assertIn("错误", r)

    def test_copy_dir_recursive(self):
        os.makedirs(self._path("srcdir"))
        self._touch("srcdir/file.txt")
        r = _handle_copy(source=self._path("srcdir"), destination=self._path("dstdir"), recursive=True)
        self.assertIn("复制", r)


class TestDelete(TestFileOps):
    def test_delete_file(self):
        f = self._touch("todelete.txt")
        r = _handle_delete(path=f)
        self.assertIn("删除", r)
        self.assertFalse(os.path.exists(f))

    def test_delete_nonexistent(self):
        r = _handle_delete(path=self._path("nope.txt"))
        self.assertIn("错误", r)

    def test_delete_dir_recursive(self):
        os.makedirs(self._path("dir"))
        self._touch("dir/file.txt")
        r = _handle_delete(path=self._path("dir"), recursive=True)
        self.assertIn("删除", r)


class TestMkdir(TestFileOps):
    def test_mkdir(self):
        p = self._path("newdir")
        r = _handle_mkdir(path=p)
        self.assertIn("创建", r)
        self.assertTrue(os.path.isdir(p))

    def test_mkdir_parents(self):
        p = self._path("a", "b", "c")
        r = _handle_mkdir(path=p, parents=True)
        self.assertIn("创建", r)
        self.assertTrue(os.path.isdir(p))


class TestReplace(TestFileOps):
    def test_exact_replace(self):
        f = self._touch("test.txt", "hello world\nsecond line")
        r = _handle_replace(file_path=f, search="hello world", replace_text="hi there")
        self.assertIn("替换", r)
        with open(f, "r") as fh:
            self.assertIn("hi there", fh.read())

    def test_replace_not_found(self):
        f = self._touch("test.txt", "hello")
        r = _handle_replace(file_path=f, search="nonexistent", replace_text="x")
        self.assertIn("错误", r)


class TestDownload(unittest.TestCase):
    def test_no_url(self):
        r = _handle_download(url="", destination="/tmp/x")
        self.assertIn("错误", r)


if __name__ == "__main__":
    unittest.main()
