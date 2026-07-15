"""Tests for dependency auto-fix tool."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools_deps import extract_missing_modules, resolve_package_name, is_stdlib, _handle_deps


class TestExtractMissingModules(unittest.TestCase):
    def test_modulenotfounderror(self):
        text = "ModuleNotFoundError: No module named 'requests'"
        modules = extract_missing_modules(text)
        self.assertIn("requests", modules)

    def test_importerror(self):
        text = "ImportError: No module named flask"
        modules = extract_missing_modules(text)
        self.assertIn("flask", modules)

    def test_nodejs_cannot_find(self):
        text = "Error: Cannot find module 'express'"
        modules = extract_missing_modules(text)
        self.assertIn("express", modules)

    def test_multiple_modules(self):
        text = "ModuleNotFoundError: No module named 'numpy'\nModuleNotFoundError: No module named 'pandas'"
        modules = extract_missing_modules(text)
        self.assertIn("numpy", modules)
        self.assertIn("pandas", modules)

    def test_dedup(self):
        text = "ModuleNotFoundError: No module named 'flask'\nModuleNotFoundError: No module named 'flask'"
        modules = extract_missing_modules(text)
        self.assertEqual(len(modules), 1)

    def test_no_match(self):
        self.assertEqual(extract_missing_modules("一切正常"), [])
        self.assertEqual(extract_missing_modules("SyntaxError: invalid syntax"), [])


class TestResolvePackageName(unittest.TestCase):
    def test_known_mapping(self):
        self.assertEqual(resolve_package_name("PIL"), "Pillow")
        self.assertEqual(resolve_package_name("cv2"), "opencv-python")
        self.assertEqual(resolve_package_name("sklearn"), "scikit-learn")
        self.assertEqual(resolve_package_name("bs4"), "beautifulsoup4")

    def test_default_same(self):
        self.assertEqual(resolve_package_name("some_obscure_pkg"), "some_obscure_pkg")


class TestIsStdlib(unittest.TestCase):
    def test_stdlib_modules(self):
        self.assertTrue(is_stdlib("os"))
        self.assertTrue(is_stdlib("sys"))
        self.assertTrue(is_stdlib("json"))
        self.assertTrue(is_stdlib("unittest"))

    def test_non_stdlib(self):
        self.assertFalse(is_stdlib("requests"))
        self.assertFalse(is_stdlib("flask"))
        self.assertFalse(is_stdlib("numpy"))


class TestHandleDeps(unittest.TestCase):
    def test_check_action(self):
        r = _handle_deps(action="check")
        self.assertIn("就绪", r)

    def test_unknown_action(self):
        r = _handle_deps(action="xyz")
        self.assertIn("未知操作", r)

    def test_install_no_module(self):
        r = _handle_deps(action="install")
        self.assertIn("错误", r)

    def test_auto_no_text(self):
        r = _handle_deps(action="auto")
        self.assertIn("错误", r)

    def test_auto_detects(self):
        r = _handle_deps(action="auto", text="ModuleNotFoundError: No module named 'nonexistent_test_module_xyz'")
        # Should detect and attempt to install (will fail since package doesn't exist)
        self.assertTrue("安装" in r or "失败" in r or "错误" in r)

    def test_registered_in_tools(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertIn("dep", names)


class TestStdlibSkip(unittest.TestCase):
    def test_stdlib_not_installed(self):
        """os/sys 等标准库不会被尝试安装。"""
        from agent.tools_deps import install_package
        r = install_package("os")
        self.assertIn("标准库", r)
        r = install_package("sys")
        self.assertIn("标准库", r)


if __name__ == "__main__":
    unittest.main()
