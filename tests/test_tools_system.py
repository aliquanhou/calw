"""Tests for system control: service, registry, process."""
from __future__ import annotations
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.tools_system import _handle_service, _handle_registry, _handle_process_v2


class TestServiceTool(unittest.TestCase):
    def test_list_services(self):
        self.assertIn("[服务]", _handle_service(action="list"))
    def test_search_services(self):
        self.assertIn("[服务]", _handle_service(action="search", name="Windows"))
    def test_status_known_service(self):
        self.assertIn("[服务]", _handle_service(action="status", name="Winmgmt"))
    def test_unknown_action(self):
        self.assertIn("未知", _handle_service(action="xyz"))
    def test_start_no_name(self):
        self.assertIn("错误", _handle_service(action="start"))
    def test_registered(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        self.assertIn("service", {t["name"] for t in TOOL_DEFINITIONS})


class TestRegistryTool(unittest.TestCase):
    def test_read_known_key(self):
        r = _handle_registry(action="read", key="HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion")
        self.assertTrue(len(r) > 50)
    def test_read_with_name(self):
        r = _handle_registry(action="read", key="HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion", name="ProgramFilesDir")
        self.assertIn("ProgramFilesDir", r)
    def test_read_invalid_key(self):
        self.assertTrue(len(_handle_registry(action="read", key="HKLM:\\Nonexistent\\Path\\XYZ")) > 0)
    def test_write_no_key(self):
        self.assertIn("错误", _handle_registry(action="write"))
    def test_delete_no_key(self):
        self.assertIn("错误", _handle_registry(action="delete"))
    def test_list_keys_known(self):
        self.assertTrue(len(_handle_registry(action="list_keys", key="HKLM:\\Software")) > 50)
    def test_unknown_action(self):
        self.assertIn("未知", _handle_registry(action="xyz", key="HKLM:\\Software"))
    def test_registered(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        self.assertIn("registry", {t["name"] for t in TOOL_DEFINITIONS})


class TestProcessV2Tool(unittest.TestCase):
    def test_list_processes(self):
        self.assertIn("[进程]", _handle_process_v2(action="list"))
    def test_top_by_cpu(self):
        self.assertIn("CPU", _handle_process_v2(action="top", sort_by="cpu"))
    def test_top_by_mem(self):
        self.assertIn("MEM", _handle_process_v2(action="top", sort_by="mem"))
    def test_tree(self):
        self.assertIn("[进程]", _handle_process_v2(action="tree"))
    def test_search_by_name(self):
        self.assertIn("进程", _handle_process_v2(action="list"))
    def test_launch_no_name(self):
        self.assertIn("错误", _handle_process_v2(action="launch"))
    def test_kill_no_args(self):
        self.assertIn("错误", _handle_process_v2(action="kill"))
    def test_unknown_action(self):
        self.assertIn("未知", _handle_process_v2(action="xyz"))
    def test_registered(self):
        from agent.tools_core import TOOL_DEFINITIONS, BUILTIN_HANDLERS
        names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertIn("process", names)
