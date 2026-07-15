"""mcpserver — MCP (Model Context Protocol) 服务器管理。

允许 Calw 连接外部 MCP 工具服务（filesystem、git 等）。
v2.1 移植版：
  - 与 v2.1 的工具注册表集成（tools.py register_tool）
  - 惰性启动，不影响启动速度
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict
    handler: Callable | None = None


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    description: str = ""
    env: dict[str, str] = field(default_factory=dict)
    tools: list[MCPTool] = field(default_factory=list)
    enabled: bool = True


_BUILTIN_MCP_SERVERS: dict[str, MCPServerConfig] = {
    "filesystem": MCPServerConfig(
        name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", os.getcwd()],
        description="安全的文件系统操作（读/写/搜索/目录列表）",
    ),
    "git": MCPServerConfig(
        name="git",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-git"],
        description="Git 仓库操作（日志/差异/状态/提交）",
    ),
}


class MCPManager:
    """MCP 服务器管理器。"""

    def __init__(self):
        self._servers: dict[str, MCPServerConfig] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._tools: dict[str, MCPTool] = {}
        self._lock = threading.Lock()

    def register(self, config: MCPServerConfig):
        with self._lock:
            self._servers[config.name] = config

    def start_server(self, name: str) -> str:
        """启动一个 MCP 服务器。"""
        config = self._servers.get(name)
        if not config:
            return f"错误: 未找到 MCP 服务器 '{name}'"
        if name in self._processes:
            return f"MCP 服务器 '{name}' 已在运行"

        try:
            env = os.environ.copy()
            env.update(config.env)
            proc = subprocess.Popen(
                [config.command] + config.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            with self._lock:
                self._processes[name] = proc
            # 发送初始化请求
            proc.stdin.write(
                json.dumps({
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
                }) + "\n"
            )
            proc.stdin.flush()
            return f"已启动 MCP 服务器 '{name}' (PID {proc.pid})"
        except Exception as e:
            return f"启动失败: {e}"

    def stop_server(self, name: str):
        """停止一个 MCP 服务器。"""
        proc = self._processes.pop(name, None)
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    def list_servers(self) -> list[dict]:
        """列出所有 MCP 服务器。"""
        return [
            {
                "name": n, "description": c.description,
                "enabled": c.enabled,
                "running": n in self._processes,
                "tool_count": len(c.tools),
            }
            for n, c in self._servers.items()
        ]

    def get_all_tools(self) -> list[dict]:
        """获取所有 MCP 服务器提供的工具定义列表。"""
        tools = []
        with self._lock:
            configs = dict(self._servers)
        for n, c in configs.items():
            if not c.enabled:
                continue
            for t in c.tools:
                tools.append({
                    "name": f"mcp_{n}_{t.name}",
                    "description": f"[MCP:{n}] {t.description}",
                    "input_schema": t.input_schema,
                })
        return tools


# ── 全局单例 ──

_mcp_manager: MCPManager | None = None
_mcp_lock = threading.Lock()


def get_mcp() -> MCPManager:
    """获取 MCP 管理器全局单例。"""
    global _mcp_manager
    if _mcp_manager is None:
        with _mcp_lock:
            if _mcp_manager is None:
                _mcp_manager = MCPManager()
                for n, c in _BUILTIN_MCP_SERVERS.items():
                    _mcp_manager.register(c)
    return _mcp_manager
