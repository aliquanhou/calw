"""Tests for system control tools: service, registry, process."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools_system import _handle_service, _handle_registry, _handle_process_v2


class TestServiceTool(unittest.TestCase):
    """Service control tests (read-only operations only)."""

    def test_list_services(self):
        r = _handle_service(action="list")
        self.assertIn("服务列表", r)

    def test_search_services(self):
        r = _handle_service(action="search", name="Windows")
        self.assertIn("搜索服务", r)

    def test_status_known_service(self):
        r = _handle_service(action="status", name="Winmgmt")
        self.assertIn("服务状态", r)

    def test_unknown_action(self):
        r = _handle_service(action="xyz")
        self.assertIn("未知操作", r)

    def test_start_no_name(self):
        r = _handle_service(action="start")
        self.assertIn("需指定", r)

    def test_registered(self):
        from agent.tools import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertIn("service", names)
        self.assertIn("service", BUILTIN_HANDLERS)


class TestRegistryTool(unittest.TestCase):
    """Registry tests (read-only)."""

    def test_read_known_key(self):
        r = _handle_registry(action="read", key="HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion")
        self.assertTrue(len(r) > 50, f"Should read registry: {r[:100]}")

    def test_read_with_name(self):
        r = _handle_registry(action="read", key="HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion",
                             name="ProgramFilesDir")
        self.assertIn("ProgramFilesDir", r)

    def test_read_invalid_key(self):
        r = _handle_registry(action="read", key="HKLM:\\Nonexistent\\Path\\XYZ")
        self.assertTrue(len(r) > 0)

    def test_write_no_key(self):
        r = _handle_registry(action="write")
        self.assertIn("需指定", r)

    def test_delete_no_key(self):
        r = _handle_registry(action="delete")
        self.assertIn("需指定", r)

    def test_list_keys_known(self):
        r = _handle_registry(action="list_keys", key="HKLM:\\Software")
        self.assertTrue(len(r) > 50)

    def test_unknown_action(self):
        r = _handle_registry(action="xyz", key="HKLM:\\Software")
        self.assertIn("未知操作", r)

    def test_registered(self):
        from agent.tools import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertIn("registry", names)
        self.assertIn("registry", BUILTIN_HANDLERS)


class TestProcessV2Tool(unittest.TestCase):
    """Enhanced process tool tests (read-only)."""

    def test_list_processes(self):
        r = _handle_process_v2(action="list")
        self.assertIn("进程列表", r)

    def test_top_by_cpu(self):
        r = _handle_process_v2(action="top", sort_by="cpu")
        self.assertIn("CPU", r)

    def test_top_by_mem(self):
        r = _handle_process_v2(action="top", sort_by="mem")
        self.assertIn("内存", r)

    def test_tree(self):
        r = _handle_process_v2(action="tree")
        self.assertIn("进程树", r)

    def test_search_by_name(self):
        r = _handle_process_v2(action="list")
        self.assertIn("进程", r)

    def test_launch_no_name(self):
        r = _handle_process_v2(action="launch")
        self.assertIn("需指定", r)

    def test_kill_no_args(self):
        r = _handle_process_v2(action="kill")
        self.assertIn("需指定", r)

    def test_unknown_action(self):
        r = _handle_process_v2(action="xyz")
        self.assertIn("未知操作", r)

    def test_registered(self):
        from agent.tools import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertIn("process", names)
        self.assertIn("process", BUILTIN_HANDLERS)


if __name__ == "__main__":
    unittest.main()
