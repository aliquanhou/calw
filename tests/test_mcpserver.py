"""Tests for agent.mcpserver — MCPManager, MCPServerConfig, MCPTool."""
from __future__ import annotations

import sys
import os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.mcpserver import MCPManager, MCPTool, MCPServerConfig, get_mcp


class TestMCPTool:
    def test_defaults(self):
        t = MCPTool(name="test", description="a test tool", input_schema={"type": "object"})
        assert t.name == "test"
        assert t.handler is None

    def test_with_handler(self):
        def h(p): return "ok"
        t = MCPTool(name="test", description="test", input_schema={}, handler=h)
        assert t.handler({"x": 1}) == "ok"


class TestMCPServerConfig:
    def test_defaults(self):
        c = MCPServerConfig(name="test", command="echo", args=["hello"])
        assert c.name == "test"
        assert c.enabled is True
        assert c.tools == []
        assert c.env == {}

    def test_disabled(self):
        c = MCPServerConfig(name="test", command="echo", args=[], enabled=False)
        assert c.enabled is False


class TestMCPManager:
    def test_init(self):
        m = MCPManager()
        assert m.list_servers() == []

    def test_register(self):
        m = MCPManager()
        c = MCPServerConfig(name="test-server", command="echo", args=["hello"])
        m.register(c)
        servers = m.list_servers()
        assert len(servers) == 1
        assert servers[0]["name"] == "test-server"

    def test_register_multiple(self):
        m = MCPManager()
        m.register(MCPServerConfig(name="s1", command="cmd1", args=[]))
        m.register(MCPServerConfig(name="s2", command="cmd2", args=[]))
        assert len(m.list_servers()) == 2

    def test_list_servers_structure(self):
        m = MCPManager()
        m.register(MCPServerConfig(name="test", command="echo", args=["hi"]))
        s = m.list_servers()[0]
        assert "name" in s
        assert "description" in s
        assert "enabled" in s
        assert "running" in s
        assert s["running"] is False

    def test_stop_nonexistent_server(self):
        """Stopping a non-existent server should not raise."""
        m = MCPManager()
        m.stop_server("nonexistent")  # should not raise

    def test_start_nonexistent_server(self):
        m = MCPManager()
        result = m.start_server("nonexistent")
        assert "错误" in result or "未找到" in result

    def test_start_duplicate(self):
        m = MCPManager()
        c = MCPServerConfig(name="test", command="cmd_not_found_xyz", args=[])
        m.register(c)
        result1 = m.start_server("test")
        result2 = m.start_server("test")  # second call
        assert "已在运行" in result2 or "失败" in result2

    def test_get_all_tools_empty(self):
        """没有工具注册时返回空列表。"""
        m = MCPManager()
        assert m.get_all_tools() == []

    def test_get_all_tools_with_registered_tools(self):
        m = MCPManager()
        tool = MCPTool(name="read_file", description="read a file", input_schema={"type": "object"})
        config = MCPServerConfig(name="fs", command="test", args=[], tools=[tool])
        m.register(config)
        tools = m.get_all_tools()
        assert len(tools) == 1
        assert "mcp_fs_read_file" in tools[0]["name"]

    def test_disabled_server_tools_excluded(self):
        m = MCPManager()
        tool = MCPTool(name="x", description="x", input_schema={})
        config = MCPServerConfig(name="disabled", command="test", args=[], tools=[tool], enabled=False)
        m.register(config)
        assert m.get_all_tools() == []

    def test_list_servers_counts_tools(self):
        m = MCPManager()
        tool = MCPTool(name="t1", description="d1", input_schema={})
        config = MCPServerConfig(name="srv", command="cmd", args=[], tools=[tool])
        m.register(config)
        servers = m.list_servers()
        assert servers[0]["tool_count"] == 1

    def test_stop_server_cleans_up(self):
        m = MCPManager()
        config = MCPServerConfig(name="test", command="cmd_not_found_xyz", args=[])
        m.register(config)
        m.start_server("test")
        m.stop_server("test")
        servers = m.list_servers()
        assert servers[0]["running"] is False

    def test_concurrent_register(self):
        """并发注册不应该出问题。"""
        m = MCPManager()
        errors = []

        def reg():
            try:
                for i in range(10):
                    m.register(MCPServerConfig(name=f"c{i}", command="echo", args=[]))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reg) for _ in range(3)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
        assert len(m.list_servers()) >= 10


class TestGetMCP:
    def test_singleton(self):
        m1 = get_mcp()
        m2 = get_mcp()
        assert m1 is m2

    def test_has_builtin_servers(self):
        m = get_mcp()
        servers = m.list_servers()
        names = [s["name"] for s in servers]
        assert "filesystem" in names
        assert "git" in names
