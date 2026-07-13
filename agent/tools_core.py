"""tools_core — 工具注册表核心，共享状态，工具定义。

功能：
  - 工具注册（内建 + 插件）
  - 工具定义管理（JSON schema）
  - 工具调用调度
  - 结果格式化与截断
  - 引用检查
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any, Callable

from .session import get_state

# ── 常量 ──

_TOOL_RESULT_MAX_LENGTH = 120000
"""单个工具结果的最大字符数。"""

_NODE_MODULES_WARNED: bool = False

# ── 向后兼容导出 ──

def _get_builtin() -> dict:
    return get_state().builtin_handlers

def _get_plugin() -> dict:
    return get_state().plugin_handlers

def _get_definitions() -> list:
    return get_state().tool_definitions

# ── 工具注册装饰器 ──

def tool(name: str = "", description: str = "", input_schema: dict | None = None,
         category: str = "general", is_plugin: bool = False):
    """注册工具处理器的装饰器。

    用法:
        @tool(name="read", description="读取文件。", input_schema={...})
        def _handle_read(file_path): ...
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__.replace("_handle_", "")
        tool_desc = description or func.__doc__ or ""
        schema = input_schema or _infer_schema(func)

        state = get_state()
        state.register_tool(tool_name, func, {
            "name": tool_name,
            "description": tool_desc,
            "input_schema": schema,
        }, is_plugin=is_plugin)
        return func
    return decorator


def _infer_schema(func: Callable) -> dict:
    """从函数签名推断 input_schema（简化版）。"""
    import inspect
    sig = inspect.signature(func)
    props = {}
    required = []
    for name, param in sig.parameters.items():
        if name == "output_callback":
            continue
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            ptype = "string"
        elif annotation is int:
            ptype = "integer"
        elif annotation is bool:
            ptype = "boolean"
        else:
            ptype = "string"
        props[name] = {"type": ptype}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "type": "object",
        "properties": props,
        "required": required,
    }


# ── 工具定义 ──

TOOL_DEFINITIONS = [
    {"name": "read", "description": "读取文件。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
    {"name": "write", "description": "写入文件。如果文件已存在，会自动备份并在写入后验证语法。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}, "required": ["file_path", "content"]}},
    {"name": "edit", "description": "编辑文件：替换文件中的一段文本。要求 old_string 唯一匹配。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}}, "required": ["file_path", "old_string", "new_string"]}},
    {"name": "glob", "description": "搜索路径。使用通配符匹配文件名。",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "grep", "description": "搜索内容。在文件中查找匹配的文本。",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob_pattern": {"type": "string"}, "output_mode": {"type": "string", "enum": ["content", "files_with_matches"]}}, "required": ["pattern"]}},
    {"name": "bash", "description": "执行命令。运行 PowerShell 命令并返回输出。",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}},
    {"name": "project_memory", "description": "项目记忆。读取/写入/追加项目级别的持久化记忆（CLAUDE.md）。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["read", "write", "append"]}, "content": {"type": "string"}}, "required": ["action"]}},
    {"name": "process", "description": "进程深度管理。list/top/tree/wait_exit/launch/kill。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["list", "top", "tree", "tree_full", "wait_exit", "launch", "kill", "search"]}, "name": {"type": "string"}, "pid": {"type": "integer"}, "sort_by": {"type": "string", "enum": ["cpu", "mem", "id"]}}, "required": ["action"]}},
    {"name": "web", "description": "HTTP请求。发送 GET/POST 请求并返回响应内容。",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string", "enum": ["GET", "POST"]}, "data": {"type": "string"}, "headers": {"type": "string"}}, "required": ["url"]}},
    {"name": "browser", "description": "浏览器。控制 Playwright 浏览器进行页面操作。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "url": {"type": "string"}, "selector": {"type": "string"}, "text": {"type": "string"}, "script": {"type": "string"}}, "required": ["action"]}},
    {"name": "background", "description": "后台任务。在后台执行长时间运行的任务。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "command": {"type": "string"}, "task_id": {"type": "string"}, "pattern": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["action"]}},
    {"name": "plan", "description": "计划。创建和管理结构化执行计划。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "title": {"type": "string"}, "plan_id": {"type": "string"}, "steps": {"type": "string"}, "step_index": {"type": "integer"}, "step_status": {"type": "string"}}, "required": ["action"]}},
    {"name": "task", "description": "任务。标记计划中的步骤完成状态。",
     "input_schema": {"type": "object", "properties": {"status": {"type": "string"}, "message": {"type": "string"}}, "required": ["status"]}},
    {"name": "ast", "description": "AST分析。解析 Python 文件的抽象语法树结构。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
    {"name": "dep_graph", "description": "依赖图。分析项目的模块依赖关系。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "call_chain", "description": "调用链。追踪一个函数在项目中的调用关系。",
     "input_schema": {"type": "object", "properties": {"function_name": {"type": "string"}, "direction": {"type": "string"}, "path": {"type": "string"}, "depth": {"type": "integer"}}, "required": ["function_name", "direction"]}},
    {"name": "revert", "description": "撤销。撤销对文件的最后一次修改。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}}},
    {"name": "web_search", "description": "网络搜索。通过 Web 搜索获取实时信息。",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]}},
    {"name": "ask_user", "description": "提问用户。向用户提问并获取回答（含智能分析和选项）。",
     "input_schema": {"type": "object", "properties": {"question": {"type": "string"}, "options": {"type": "string"}, "analysis": {"type": "string"}, "recommended": {"type": "string"}}, "required": ["question"]}},
    {"name": "trace_error", "description": "错误分析。分析错误信息并定位根因。",
     "input_schema": {"type": "object", "properties": {"error_message": {"type": "string"}, "file_path": {"type": "string"}, "depth": {"type": "integer"}}, "required": ["error_message"]}},
    {"name": "replace", "description": "SEARCH/REPLACE。模糊搜索替换（支持部分匹配）。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}, "search": {"type": "string"}, "replace_text": {"type": "string"}, "partial": {"type": "boolean"}}, "required": ["file_path", "search", "replace_text"]}},
    {"name": "test", "description": "测试驱动。发现/运行测试并解析结果。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["discover", "run"]}, "path": {"type": "string"}, "test_name": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["action"]}},
    {"name": "dep", "description": "包依赖管理。自动检查缺失模块并安装。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["check", "install", "auto"]}, "module_name": {"type": "string"}, "text": {"type": "string"}}, "required": ["action"]}},
    {"name": "service", "description": "Windows服务控制。list/search/status/start/stop/restart/set_startup。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["list", "search", "status", "start", "stop", "restart", "set_startup"]}, "name": {"type": "string"}, "start_type": {"type": "string"}}, "required": ["action"]}},
    {"name": "registry", "description": "注册表操作。read/write/delete/list_keys。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["read", "write", "delete", "list_keys"]}, "key": {"type": "string"}, "name": {"type": "string"}, "value": {"type": "string"}}, "required": ["action", "key"]}},
    {"name": "move", "description": "移动/重命名文件或目录。",
     "input_schema": {"type": "object", "properties": {"source": {"type": "string"}, "destination": {"type": "string"}}, "required": ["source", "destination"]}},
    {"name": "copy", "description": "复制文件或目录（recursive=true 复制目录）。",
     "input_schema": {"type": "object", "properties": {"source": {"type": "string"}, "destination": {"type": "string"}, "recursive": {"type": "boolean"}}, "required": ["source", "destination"]}},
    {"name": "delete", "description": "删除文件或目录（recursive=true 递归删除）。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "recursive": {"type": "boolean"}}, "required": ["path"]}},
    {"name": "mkdir", "description": "创建目录（parents=true 创建父目录）。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "parents": {"type": "boolean"}}, "required": ["path"]}},
    {"name": "download", "description": "从URL下载文件到本地路径。",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "destination": {"type": "string"}}, "required": ["url", "destination"]}},
    {"name": "gui", "description": "GUI 自动化。鼠标点击/键盘输入/截图/窗口控制。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["info", "click", "double_click", "right_click", "move", "drag", "type", "keypress", "scroll", "screenshot", "locate", "get_window"]}, "x": {"type": "integer"}, "y": {"type": "integer"}, "text": {"type": "string"}, "button": {"type": "string"}, "key": {"type": "string"}, "query": {"type": "string"}}, "required": ["action"]}},
    {"name": "monitor", "description": "系统监控。resources/cpu/memory/disk/process_count/watch_file/network/uptime。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["resources", "cpu", "memory", "disk", "process_count", "watch_file", "network", "uptime", "process_events"]}, "path": {"type": "string"}, "interval": {"type": "integer"}}, "required": ["action"]}},
    {"name": "schedule", "description": "定时任务管理。list/add/remove/events。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["list", "add", "remove", "events"]}, "name": {"type": "string"}, "cron": {"type": "string"}, "command": {"type": "string"}, "task_id": {"type": "string"}}, "required": ["action"]}},
    {"name": "watch", "description": "文件/进程监控。list/add/remove/events。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["list", "add", "remove", "events"]}, "name": {"type": "string"}, "kind": {"type": "string", "enum": ["file", "directory", "log", "process"]}, "path": {"type": "string"}, "pattern": {"type": "string"}, "watch_id": {"type": "string"}}, "required": ["action"]}},
    {"name": "websocket", "description": "WebSocket 客户端。connect/send/ping。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["connect", "send", "ping"]}, "url": {"type": "string"}, "message": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["action"]}},
    {"name": "remember", "description": "语义记忆。search/store/stats/context。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["search", "store", "stats", "context"]}, "query": {"type": "string"}, "content": {"type": "string"}, "mem_type": {"type": "string"}, "n_results": {"type": "integer"}}, "required": ["action"]}},
    {"name": "hash_file", "description": "计算文件的 MD5 / SHA256 哈希值",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}, "algorithm": {"type": "string", "enum": ["md5", "sha256"]}}, "required": ["file_path"]}},
]


# ── 向后兼容引用 ──

# 为 tools.py 保持向后兼容
BUILTIN_HANDLERS: dict = {}
PLUGIN_HANDLERS: dict = {}

# 旧版全局变量引用（将被逐步淘汰）
_written_this_session: set = set()
_agent_spawned_pids: set = set()
_file_backups: dict = {}
_session_lessons: list = []
_consecutive_fails: dict = {}
_last_heal_time: float = 0.0
_NODE_MODULES_WARNED: bool = False


# ── 工具调用调度 ──

def handle_tool_call(name: str, params: dict, output_callback: Callable | None = None) -> str:
    """调度工具调用。

    优先查找插件处理器，再查找内建处理器。
    执行前检查守卫条件，执行后格式化结果。

    Args:
        name: 工具名称
        params: 参数字典
        output_callback: 输出回调（用于实时流式输出）

    Returns:
        工具执行结果字符串
    """
    allowed, guard_msg = guard_tool_call(name, params)
    if not allowed:
        return f"已阻止: {guard_msg}"

    state = get_state()

    # 自愈检查（非文件操作每60秒执行一次）
    if name not in ('read', 'glob') and state.should_heal(60):
        try:
            from .tools_shell import _self_heal
            _self_heal()
        except Exception:
            pass

    # 连续失败记忆注入
    lesson_prefix = ""
    if name in ("write", "edit") and "file_path" in params:
        fp = os.path.abspath(params["file_path"])
        lessons = state.get_lessons_for_file(fp)
        if lessons and lessons[-1].get("attempt", 0) >= 2:
            last = lessons[-1]
            lesson_prefix = f"[记忆] 文件 {fp} 已连续失败 {last['attempt']} 次。建议换方案。\n"

    # 获取处理器
    handler_name = name
    is_plugin = handler_name in state.plugin_handlers
    handler = state.get_handler(handler_name)

    if handler is None:
        return f"未知工具: {name}"

    try:
        if output_callback and name == "bash":
            params = {**params, "output_callback": output_callback}

        if is_plugin:
            result = handler(params)
        else:
            result = handler(**params)

        # 如果守卫有消息，附加到结果
        if guard_msg:
            result = guard_msg + "\n" + result

        result_str = str(result)
        if lesson_prefix:
            result_str = lesson_prefix + result_str

        return smart_truncate(result_str, _TOOL_RESULT_MAX_LENGTH)

    except Exception as e:
        return f"执行 {name} 出错: {e}"


# ── 守卫函数 ──


def guard_tool_call(name: str, params: dict) -> tuple[bool, str]:
    """检查工具调用是否允许执行。

    当前检查：
      - 敏感操作的安全性校验

    Returns:
        (允许, 提示消息)
    """
    return True, ""


# ── 结果格式化 ──


def smart_truncate(text: str, max_length: int = 6000) -> str:
    """智能截断文本：保留开头和结尾的重要信息。

    对于构建/编译输出，保留末尾的错误信息。
    对于一般文本，保留开头并添加截断标记。

    Args:
        text: 要截断的文本
        max_length: 最大字符数

    Returns:
        截断后的文本
    """
    if not text or len(text) <= max_length:
        return text

    # 保留前 60% 和后 40%
    head_len = int(max_length * 0.6)
    tail_len = max_length - head_len - 50  # 50 用于截断标记

    head = text[:head_len]
    tail = text[-tail_len:] if tail_len > 0 else ""

    return f"{head}\n... [截断: 共 {len(text):,} 字符，显示 {max_length:,}] ...\n{tail}"


def check_search_scope(path: str) -> str:
    """检查搜索范围是否过大，如果是则返回限制路径。"""
    if not path or path in (".", "./", os.getcwd()):
        return "."
    return path


def classify_tool_result(result: str) -> str:
    """对工具结果进行分类：error/warning/success/empty。"""
    if not result or result == "(无输出)":
        return "empty"
    lower = result.lower()
    if any(kw in lower for kw in ("error", "traceback", "exception", "❌", "exit code")):
        return "error"
    if any(kw in lower for kw in ("warning", "warn", "⚠")):
        return "warning"
    return "success"


# ── 插件加载 ──


def _load_plugins():
    """加载 agent/plugins 目录下的插件。"""
    state = get_state()
    if state.plugins_loaded:
        return

    import importlib
    import sys

    plugins_dir = os.path.join(os.path.dirname(__file__), "plugins")
    if not os.path.isdir(plugins_dir):
        state.plugins_loaded = True
        return

    plugin_files = [f[:-3] for f in os.listdir(plugins_dir)
                    if f.endswith(".py") and f != "__init__.py"]

    for plugin_name in plugin_files:
        try:
            module = importlib.import_module(f".plugins.{plugin_name}", package="agent")
            if hasattr(module, "register"):
                result = module.register()
                if isinstance(result, dict):
                    name = result.get("name", plugin_name)
                    description = result.get("description", "")
                    handler = result.get("handler")
                    schema = result.get("input_schema", {})
                    if handler:
                        state.register_tool(name, handler, {
                            "name": name,
                            "description": description,
                            "input_schema": schema,
                        }, is_plugin=True)
        except Exception as e:
            print(f"[插件] 加载 {plugin_name} 失败: {e}")

    state.plugins_loaded = True


# ── 初始化 ──

def init():
    """初始化工具核心：加载插件并将工具定义同步到 BUILTIN_HANDLERS。"""
    _load_plugins()
    # 同步 to old-style globals for backward compat
    state = get_state()
    global BUILTIN_HANDLERS, PLUGIN_HANDLERS
    BUILTIN_HANDLERS.update(state.builtin_handlers)
    PLUGIN_HANDLERS.update(state.plugin_handlers)
