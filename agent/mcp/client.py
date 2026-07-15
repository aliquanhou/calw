"""mcp/client — MCP stdio 客户端。

连接 MCP 服务器（子进程），通过 JSON-RPC 2.0 发现并调用工具。

协议：
  → {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"0.1.0"}}
  ← {"jsonrpc":"2.0","id":1,"result":{...}}

  → {"jsonrpc":"2.0","id":2,"method":"tools/list"}
  ← {"jsonrpc":"2.0","id":2,"result":{"tools":[{name,description,inputSchema},...]}}

  → {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"xxx","arguments":{...}}}
  ← {"jsonrpc":"2.0","id":3,"result":{"content":[{type:"text",text:"..."},...]}}
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from typing import Any


class McpServer:
    """管理一个 MCP stdio 服务器。"""

    def __init__(self, name: str, command: str, args: list[str] | None = None,
                 env: dict[str, str] | None = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = {**os.environ, **(env or {})}
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._req_id = 0
        self._tools: list[dict] = []
        self._connected = False

    # ── 连接管理 ──

    def connect(self) -> bool:
        """启动子进程并发送 initialize。"""
        if self._connected:
            return True

        try:
            self._proc = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.env,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        except Exception as e:
            raise RuntimeError(f"MCP 启动失败: {self.command} — {e}")

        # Initialize
        result = self._call("initialize", {
            "protocolVersion": "0.1.0",
            "capabilities": {},
        })
        if result is None:
            self._proc.terminate()
            self._proc = None
            return False

        self._connected = True
        return True

    def disconnect(self):
        """断开 MCP 连接。"""
        with self._lock:
            self._connected = False
            if self._proc:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=5)
                except Exception:
                    self._proc.kill()
                self._proc = None

    @property
    def connected(self) -> bool:
        return self._connected and self._proc is not None and self._proc.poll() is None

    # ── 工具发现 ──

    def discover_tools(self) -> list[dict]:
        """调用 tools/list 获取服务器提供的工具列表。"""
        result = self._call("tools/list")
        if not result:
            return []
        self._tools = result.get("tools", [])
        return self._tools

    def get_tools(self) -> list[dict]:
        """获取缓存的工具列表。"""
        if not self._tools:
            self.discover_tools()
        return self._tools

    # ── 工具调用 ──

    def call_tool(self, name: str, arguments: dict) -> str:
        """调用 MCP 工具，返回工具结果文本。"""
        result = self._call("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        if not result:
            return "[MCP 错误: 无响应]"

        # 提取 content 中的文本
        content = result.get("content", [])
        texts = []
        for block in content:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif block.get("type") == "resource":
                texts.append(str(block.get("resource", "")))
        return "\n".join(texts) if texts else json.dumps(result, ensure_ascii=False)[:2000]

    # ── JSON-RPC 通信 ──

    def _call(self, method: str, params: dict | None = None) -> dict | None:
        """发送 JSON-RPC 请求并获取响应。"""
        if not self._proc or self._proc.poll() is not None:
            return None

        self._req_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
        }
        if params:
            request["params"] = params

        with self._lock:
            try:
                req_str = json.dumps(request, ensure_ascii=False) + "\n"
                self._proc.stdin.write(req_str)
                self._proc.stdin.flush()

                # 读响应（逐行，直到找到对应 id）
                deadline = time.time() + 30
                while time.time() < deadline:
                    line = self._proc.stdout.readline()
                    if not line:
                        return None
                    try:
                        response = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if response.get("id") == self._req_id:
                        if "error" in response:
                            err = response["error"]
                            raise RuntimeError(f"MCP 错误: {err.get('message', '?')} (code={err.get('code', '?')})")
                        return response.get("result")
            except Exception as e:
                if "MCP 错误" in str(e):
                    raise
                raise RuntimeError(f"MCP 调用失败 ({method}): {e}")

        return None


# ── 服务器注册表 ──

_MCP_SERVERS: dict[str, McpServer] = {}
_MCP_LOCK = threading.Lock()


def register_server(name: str, command: str, args: list[str] | None = None,
                    env: dict[str, str] | None = None) -> McpServer:
    """注册一个 MCP 服务器。"""
    with _MCP_LOCK:
        server = McpServer(name, command, args, env)
        _MCP_SERVERS[name] = server
    return server


def get_server(name: str) -> McpServer | None:
    """获取已注册的 MCP 服务器。"""
    return _MCP_SERVERS.get(name)


def list_servers() -> list[dict]:
    """列出所有注册的 MCP 服务器。"""
    return [
        {
            "name": s.name,
            "connected": s.connected,
            "command": s.command,
            "tools": len(s.get_tools()),
        }
        for s in _MCP_SERVERS.values()
    ]


def disconnect_all():
    """断开所有 MCP 连接。"""
    for s in _MCP_SERVERS.values():
        try:
            s.disconnect()
        except Exception:
            pass
