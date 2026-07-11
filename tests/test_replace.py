"""Tests for SEARCH/REPLACE engine (multi-strategy)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools_file import _handle_replace
from agent.tools_core import _file_backups


class TestReplaceExact(unittest.TestCase):
    """Strategy 1: Exact match — search text appears exactly once."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        self.tmp.write("x = 1\ny = 2\nz = 3\n")
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_exact_match(self):
        r = _handle_replace(self.tmp.name, "y = 2", "y = 100")
        self.assertIn("替换成功", r)
        content = open(self.tmp.name).read()
        self.assertIn("y = 100", content)
        self.assertNotIn("\ny = 2\n", "\n" + content + "\n")

    def test_diff_output(self):
        r = _handle_replace(self.tmp.name, "y = 2", "y = 100")
        self.assertIn("-y = 2", r)
        self.assertIn("+y = 100", r)

    def test_exact_multi_line(self):
        r = _handle_replace(self.tmp.name, "y = 2\nz = 3", "y = 200\nz = 300")
        self.assertIn("替换成功", r)
        content = open(self.tmp.name).read()
        self.assertIn("y = 200", content)
        self.assertIn("z = 300", content)

    def test_exact_no_match(self):
        r = _handle_replace(self.tmp.name, "x = 999", "x = 0")
        self.assertIn("无法定位", r)

    def test_file_not_found(self):
        r = _handle_replace("/nonexistent/path/file.py", "x", "y")
        self.assertIn("不存在", r)

    def test_backup_created(self):
        _file_backups.clear()
        _handle_replace(self.tmp.name, "y = 2", "y = 100")
        self.assertIn(self.tmp.name, _file_backups)


class TestReplaceAnchor(unittest.TestCase):
    """Strategy 2: Anchor match — find unique substring to locate position."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        self.tmp.write("""def func1():
    \"\"\"This is function one.\"\"\"
    return 1

def func2():
    \"\"\"This is function two.\"\"\"
    return 2

def func3():
    \"\"\"This is function three.\"\"\"
    return 3
""")
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_anchor_unique_line(self):
        r = _handle_replace(
            self.tmp.name,
            'def func2():\n    """This is function two."""\n    return 2',
            'def func2():\n    """Updated function."""\n    return 200',
        )
        self.assertIn("替换成功", r)
        content = open(self.tmp.name).read()
        self.assertIn("return 200", content)

    def test_anchor_with_partial_context(self):
        r = _handle_replace(
            self.tmp.name,
            '"""This is function three."""\n    return 3',
            '"""Third function updated."""\n    return 300',
        )
        self.assertIn("替换成功", r)
        content = open(self.tmp.name).read()
        self.assertIn("return 300", content)


class TestReplaceFuzzy(unittest.TestCase):
    """Strategy 3: Fuzzy match — strip-based line matching."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        self.tmp.write("def foo():\n    pass\n\ndef bar():\n    return 42\n\ndef baz():\n    return 99\n")
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_fuzzy_with_indent_diff(self):
        r = _handle_replace(
            self.tmp.name,
            "def bar():\n    return 42",
            "def bar():\n    return 100",
        )
        self.assertIn("替换成功", r)
        content = open(self.tmp.name).read()
        self.assertIn("return 100", content)

    def test_fuzzy_low_confidence(self):
        r = _handle_replace(self.tmp.name, "does not exist in file", "nothing")
        self.assertIn("无法定位", r)

    def test_fuzzy_partial_fallback(self):
        r = _handle_replace(
            self.tmp.name,
            "nonexistent\ndef bar():\n    return 42\njunk",
            "def bar():\n    return 999",
        )
        self.assertIn("替换成功", r)
        content = open(self.tmp.name).read()
        self.assertIn("return 999", content)


class TestReplaceLineRef(unittest.TestCase):
    """Strategy 4: Line number reference (:line_number syntax)."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        self.tmp.write("line1\nline2\nline3\nline4\nline5\n")
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_line_number(self):
        r = _handle_replace(self.tmp.name, ":3", "REPLACED_LINE3")
        self.assertIn("替换成功", r)
        self.assertIn("行号替换", r)
        content = open(self.tmp.name).read()
        self.assertIn("REPLACED_LINE3", content)

    def test_line_number_invalid(self):
        r = _handle_replace(self.tmp.name, ":999", "nope")
        self.assertIn("无法定位", r)

    def test_line_number_first(self):
        r = _handle_replace(self.tmp.name, ":1", "FIRST")
        self.assertIn("替换成功", r)
        content = open(self.tmp.name).read()
        self.assertTrue(content.startswith("FIRST"))


class TestReplaceValidation(unittest.TestCase):
    """Rollback and validation behavior."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        self.tmp.write("x = 1\nprint('ok')\n")
        self.tmp.close()

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_rollback_on_syntax_error(self):
        content = open(self.tmp.name).read()
        r = _handle_replace(self.tmp.name, "print('ok')", "print('ok'")
        self.assertIn("验证失败", r)
        self.assertEqual(open(self.tmp.name).read(), content)


class TestReplaceEdgeCases(unittest.TestCase):
    """Edge cases and special situations."""

    def test_empty_search(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("content\n")
            tmp = f.name
        try:
            r = _handle_replace(tmp, "", "new")
            self.assertIn("no-op", r)
        finally:
            os.unlink(tmp)

    def test_replace_with_special_chars(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("path = 'C:\\\\Users\\\\test\\\\file.txt'\n")
            tmp = f.name
        try:
            r = _handle_replace(tmp, "'C:\\\\Users\\\\test\\\\file.txt'", "'/home/user/file.txt'")
            self.assertIn("替换成功", r)
            self.assertIn("/home/user/file.txt", open(tmp).read())
        finally:
            os.unlink(tmp)

    def test_unicode_content(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("# 你好世界\ndef hello():\n    print('你好')\n")
            tmp = f.name
        try:
            r = _handle_replace(tmp, "print('你好')", "print('Hello')")
            self.assertIn("替换成功", r)
            self.assertIn("Hello", open(tmp).read())
        finally:
            os.unlink(tmp)

    def test_large_search_block(self):
        original_lines = [f"line_{i} = {i}" for i in range(100)]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("\n".join(original_lines) + "\n")
            tmp = f.name
        try:
            search_block = "\n".join([f"line_{i} = {i}" for i in range(20, 30)])
            replace_block = "\n".join([f"line_{i} = REPLACED_{i}" for i in range(20, 30)])
            r = _handle_replace(tmp, search_block, replace_block)
            self.assertIn("替换成功", r)
            content = open(tmp).read()
            self.assertIn("REPLACED_20", content)
        finally:
            os.unlink(tmp)

    def test_no_trailing_newline(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("first\nsecond")
            tmp = f.name
        try:
            r = _handle_replace(tmp, "second", "updated")
            self.assertIn("替换成功", r)
            self.assertIn("updated", open(tmp).read())
        finally:
            os.unlink(tmp)

    def test_same_content_noop(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("keep\n")
            tmp = f.name
        try:
            r = _handle_replace(tmp, "keep", "keep")
            self.assertIn("no-op", r)
        finally:
            os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
