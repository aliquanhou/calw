"""tools_mcp — MCP 工具集成。

连接 MCP stdio 服务器，自动发现工具并注册到 Calw 工具系统。

注册方式：
  1. 通过 mcp 工具手动 connect
  2. 或通过 config.json 的 "mcp_servers" 字段自动连接

注册后的工具以 mcp__<server>__<tool> 命名，可与普通工具一样使用。
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from .mcp.client import McpServer, register_server, get_server, list_servers, disconnect_all
from .tools import register_tool, unregister_tool


# ── 正在连接的服务器锁 ──
_connecting_lock = threading.Lock()


def _handle_mcp(action: str = "list",
                 server: str = "",
                 command: str = "",
                 args: str = "",
                 tool_name: str = "",
                 **kwargs) -> str:
    """MCP 服务器管理：list/connect/disconnect/call。

    Args:
        action: list | connect | disconnect | call | servers
        server: 服务器名称
        command: 启动命令（connect 时必填）
        args: 命令参数（JSON 数组字符串，connect 时可选）
        tool_name: 工具名（call 时必填）

    Returns:
        操作结果字符串
    """
    if action == "list" or action == "servers":
        return _list_mcp_servers()

    if action == "connect":
        if not server or not command:
            return "[MCP 错误] connect 需要 server 和 command 参数"
        try:
            cmd_args = json.loads(args) if args else []
        except json.JSONDecodeError:
            cmd_args = []
        return _connect_mcp(server, command, cmd_args)

    if action == "disconnect":
        if not server:
            return "[MCP 错误] disconnect 需要 server 参数"
        return _disconnect_mcp(server)

    if action == "call":
        if not server or not tool_name:
            return "[MCP 错误] call 需要 server 和 tool_name 参数"
        # 从 kwargs 提取参数
        call_args = {k: v for k, v in kwargs.items() if k not in ("action", "server", "command", "args", "tool_name")}
        return _call_mcp_tool(server, tool_name, call_args)

    return f"[MCP 错误] 未知操作: {action}（可用: list/connect/disconnect/call）"


def _connect_mcp(name: str, command: str, args: list[str]) -> str:
    """连接 MCP 服务器并注册其工具。"""
    with _connecting_lock:
        # 检查是否已连接
        existing = get_server(name)
        if existing and existing.connected:
            return f"[MCP] ✅ {name} 已连接"

        server = register_server(name, command, args)
        try:
            if not server.connect():
                return f"[MCP ❌] {name} 连接失败（进程未启动）"
        except Exception as e:
            return f"[MCP ❌] {name} 连接失败: {e}"

        # 发现工具并注册
        tools = server.discover_tools()
        if not tools:
            server.disconnect()
            return f"[MCP ⚠] {name} 已连接，但未提供工具"

        registered = 0
        for tool_def in tools:
            mcp_tool_name = f"mcp__{name}__{tool_def.get('name', 'unknown')}"
            mcp_desc = tool_def.get("description", f"MCP 工具 ({name})")
            mcp_schema = tool_def.get("inputSchema", tool_def.get("input_schema", {"type": "object", "properties": {}}))

            # 注册到 Calw 工具系统
            register_tool(
                name=mcp_tool_name,
                handler=_make_mcp_handler(name, tool_def.get("name", "")),
                description=f"[MCP/{name}] {mcp_desc}",
                parameters=mcp_schema,
            )
            registered += 1

        return f"[MCP] ✅ {name} 已连接，注册 {registered} 个工具"


def _make_mcp_handler(server_name: str, tool_name: str):
    """创建一个 MCP 工具调用处理函数。"""
    def handler(**params) -> str:
        srv = get_server(server_name)
        if not srv or not srv.connected:
            return f"[MCP 错误] {server_name} 未连接"
        try:
            return srv.call_tool(tool_name, params)
        except Exception as e:
            return f"[MCP 错误] {server_name}/{tool_name}: {e}"
    return handler


def _disconnect_mcp(name: str) -> str:
    """断开 MCP 服务器并注销其工具。"""
    server = get_server(name)
    if not server:
        return f"[MCP] 未找到服务器: {name}"

    # 注销所有该服务器的工具
    for tool in server.get_tools():
        mcp_name = f"mcp__{name}__{tool.get('name', 'unknown')}"
        unregister_tool(mcp_name)

    server.disconnect()
    return f"[MCP] ✅ {name} 已断开"


def _call_mcp_tool(server_name: str, tool_name: str, arguments: dict) -> str:
    """直接调用 MCP 工具（绕过注册表）。"""
    server = get_server(server_name)
    if not server or not server.connected:
        return f"[MCP 错误] {server_name} 未连接"
    try:
        return server.call_tool(tool_name, arguments)
    except Exception as e:
        return f"[MCP 错误] {server_name}/{tool_name}: {e}"


def _list_mcp_servers() -> str:
    """列出 MCP 服务器。"""
    servers = list_servers()
    if not servers:
        return "[MCP] 无已注册的服务器。使用 mcp connect 命令连接"
    lines = ["[MCP] 服务器列表:"]
    for s in servers:
        status = "🟢" if s["connected"] else "🔴"
        lines.append(f"  {status} {s['name']} ({s['command']}) — {s['tools']} 个工具")
    return "\n".join(lines)


def auto_connect_servers(config: dict | None = None):
    """从配置自动连接 MCP 服务器。

    Args:
        config: 配置字典，应包含 "mcp_servers" 列表
    """
    if not config:
        return

    servers = config.get("mcp_servers", [])
    if not servers:
        return

    for svr in servers:
        name = svr.get("name", "")
        command = svr.get("command", "")
        args = svr.get("args", [])
        if name and command:
            try:
                _connect_mcp(name, command, args)
            except Exception as e:
                print(f"[MCP] 自动连接 {name} 失败: {e}")


def disconnect_all_mcp():
    """断开所有 MCP 服务器。"""
    disconnect_all()
