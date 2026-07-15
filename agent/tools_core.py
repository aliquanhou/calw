"""tools_core — 工具核心（向后兼容层 + 共享函数）。

保留了 v2.0 的 TOOL_DEFINITIONS、handle_tool_call 等接口，
以便旧模块和测试代码可以继续工作。

新代码请使用 tools.py 的 register_tool / execute_tool 接口。
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


# ── 工具装饰器（v2.0 兼容）──

def tool(name: str = "", description: str = "", input_schema: dict | None = None,
         category: str = "general", is_plugin: bool = False):
    """注册工具处理器的装饰器。"""
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
    for pname, param in sig.parameters.items():
        if pname == "output_callback":
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
        props[pname] = {"type": ptype}
        if param.default is inspect.Parameter.empty:
            required.append(pname)
    return {"type": "object", "properties": props, "required": required}


# ── 工具定义列表（v2.0 兼容 + v2.1 新工具）──

TOOL_DEFINITIONS = [
    {"name": "read", "description": "读取文件。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
    {"name": "write", "description": "写入文件。自动备份并在写入后验证语法。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}, "required": ["file_path", "content"]}},
    {"name": "edit", "description": "编辑文件：替换文件中的一段文本。要求 old_string 唯一匹配。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}}, "required": ["file_path", "old_string", "new_string"]}},
    {"name": "glob", "description": "搜索路径。使用通配符匹配文件名。",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "grep", "description": "搜索内容。在文件中查找匹配的文本。",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob_pattern": {"type": "string"}, "output_mode": {"type": "string", "enum": ["content", "files_with_matches"]}}, "required": ["pattern"]}},
    {"name": "bash", "description": "执行命令。运行 shell 命令并返回输出。",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}},
    {"name": "process", "description": "进程管理：list/top/tree/wait_exit/launch/kill。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "name": {"type": "string"}, "pid": {"type": "integer"}, "sort_by": {"type": "string"}}, "required": ["action"]}},
    {"name": "web", "description": "HTTP 请求。发送 GET/POST 请求并返回响应内容。",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string"}, "data": {"type": "string"}, "headers": {"type": "string"}}, "required": ["url"]}},
    {"name": "browser", "description": "浏览器控制。使用 Playwright 控制 Chromium 浏览器。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "url": {"type": "string"}, "selector": {"type": "string"}, "text": {"type": "string"}, "script": {"type": "string"}}, "required": ["action"]}},
    {"name": "web_search", "description": "网络搜索。通过 Web 搜索获取实时信息。",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]}},
    {"name": "ast", "description": "AST 分析。解析 Python 文件的抽象语法树结构。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
    {"name": "dep_graph", "description": "依赖图。分析项目的模块依赖关系。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "call_chain", "description": "调用链。追踪函数在项目中的调用关系。",
     "input_schema": {"type": "object", "properties": {"function_name": {"type": "string"}, "direction": {"type": "string"}, "path": {"type": "string"}, "depth": {"type": "integer"}}, "required": ["function_name", "direction"]}},
    {"name": "trace_error", "description": "错误分析。分析错误信息并定位根因。",
     "input_schema": {"type": "object", "properties": {"error_message": {"type": "string"}, "file_path": {"type": "string"}, "depth": {"type": "integer"}}, "required": ["error_message"]}},
    {"name": "plan", "description": "计划。创建和管理结构化执行计划。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "title": {"type": "string"}, "plan_id": {"type": "string"}, "steps": {"type": "string"}, "step_index": {"type": "integer"}, "step_status": {"type": "string"}}, "required": ["action"]}},
    {"name": "task", "description": "任务。标记计划步骤完成状态。",
     "input_schema": {"type": "object", "properties": {"status": {"type": "string"}, "message": {"type": "string"}}, "required": ["status"]}},
    {"name": "project_memory", "description": "项目记忆。读写项目级持久化记忆（CLAUDE.md）。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "content": {"type": "string"}}, "required": ["action"]}},
    {"name": "background", "description": "后台任务。在后台执行长时间运行的任务。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "command": {"type": "string"}, "task_id": {"type": "string"}, "pattern": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["action"]}},
    {"name": "test", "description": "测试驱动。发现/运行测试并解析结果。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "path": {"type": "string"}, "test_name": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["action"]}},
    {"name": "dep", "description": "包依赖管理。自动检查缺失模块并安装。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "module_name": {"type": "string"}, "text": {"type": "string"}}, "required": ["action"]}},
    {"name": "service", "description": "Windows 服务控制。list/search/status/start/stop/restart/set_startup。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "name": {"type": "string"}, "start_type": {"type": "string"}}, "required": ["action"]}},
    {"name": "registry", "description": "注册表操作。read/write/delete/list_keys。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "key": {"type": "string"}, "name": {"type": "string"}, "value": {"type": "string"}}, "required": ["action", "key"]}},
    {"name": "move", "description": "移动/重命名文件或目录。",
     "input_schema": {"type": "object", "properties": {"source": {"type": "string"}, "destination": {"type": "string"}}, "required": ["source", "destination"]}},
    {"name": "copy", "description": "复制文件或目录（recursive=true 复制目录）。",
     "input_schema": {"type": "object", "properties": {"source": {"type": "string"}, "destination": {"type": "string"}, "recursive": {"type": "boolean"}}, "required": ["source", "destination"]}},
    {"name": "delete", "description": "删除文件或目录（recursive=true 递归删除）。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "recursive": {"type": "boolean"}}, "required": ["path"]}},
    {"name": "mkdir", "description": "创建目录（parents=true 创建父目录）。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "parents": {"type": "boolean"}}, "required": ["path"]}},
    {"name": "download", "description": "从 URL 下载文件到本地路径。",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "destination": {"type": "string"}}, "required": ["url", "destination"]}},
    {"name": "gui", "description": "GUI 自动化。鼠标点击/键盘输入/截图/窗口控制。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"}, "text": {"type": "string"}, "button": {"type": "string"}, "key": {"type": "string"}}, "required": ["action"]}},
    {"name": "monitor", "description": "系统监控。resources/cpu/memory/disk/process_count/watch_file/network/uptime/process_events。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "path": {"type": "string"}, "interval": {"type": "integer"}}, "required": ["action"]}},
    {"name": "schedule", "description": "定时任务管理。list/add/remove/events。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "name": {"type": "string"}, "cron": {"type": "string"}, "command": {"type": "string"}, "task_id": {"type": "string"}}, "required": ["action"]}},
    {"name": "watch", "description": "文件/进程监控。list/add/remove/events。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "name": {"type": "string"}, "kind": {"type": "string"}, "path": {"type": "string"}, "pattern": {"type": "string"}, "watch_id": {"type": "string"}}, "required": ["action"]}},
    {"name": "websocket", "description": "WebSocket 客户端。connect/send/ping。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "url": {"type": "string"}, "message": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["action"]}},
    {"name": "remember", "description": "语义记忆。search/store/stats/context。",
     "input_schema": {"type": "object", "properties": {"action": {"type": "string"}, "query": {"type": "string"}, "content": {"type": "string"}, "mem_type": {"type": "string"}, "n_results": {"type": "integer"}}, "required": ["action"]}},
    {"name": "hash_file", "description": "计算文件的 MD5/SHA256 哈希值。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}, "algorithm": {"type": "string"}}, "required": ["file_path"]}},
    {"name": "revert", "description": "撤销对文件的最后一次修改。",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}}},
    {"name": "ask_user", "description": "向用户提问（带智能分析和选项）。",
     "input_schema": {"type": "object", "properties": {"question": {"type": "string"}, "options": {"type": "string"}, "analysis": {"type": "string"}, "recommended": {"type": "string"}}, "required": ["question"]}},
]


# ── 向后兼容引用 ──

BUILTIN_HANDLERS: dict = {}
PLUGIN_HANDLERS: dict = {}

# 旧版全局变量（供旧模块引用）
_written_this_session: set = set()
_agent_spawned_pids: set = set()
_file_backups: dict = {}
_session_lessons: list = []
_consecutive_fails: dict = {}
_last_heal_time: float = 0.0


# ── 工具调用调度（v2.0 兼容）──

def handle_tool_call(name: str, params: dict, output_callback: Callable | None = None) -> str:
    """调度工具调用（v2.0 兼容接口）。"""
    allowed, guard_msg = guard_tool_call(name, params)
    if not allowed:
        return f"已阻止: {guard_msg}"

    state = get_state()

    # 自愈检查（非文件操作每 60 秒执行一次）
    if name not in ("read", "glob") and state.should_heal(60):
        try:
            from .tools_shell import _self_heal
            _self_heal()
        except Exception:
            pass

    # 获取处理器
    handler = state.get_handler(name)
    if handler is None:
        return f"未知工具: {name}"

    try:
        if output_callback and name == "bash":
            params = {**params, "output_callback": output_callback}

        is_plugin = name in state.plugin_handlers
        if is_plugin:
            result = handler(params)
        else:
            result = handler(**params)

        result_str = str(result)
        if guard_msg:
            result_str = guard_msg + "\n" + result_str

        return smart_truncate(result_str, _TOOL_RESULT_MAX_LENGTH)

    except Exception as e:
        return f"执行 {name} 出错: {e}"


def guard_tool_call(name: str, params: dict) -> tuple[bool, str]:
    """检查工具调用是否允许执行（安全防护层）。

    当前实现：
      - grep 搜索 node_modules 时发出警告
      - 可在此处添加白名单/黑名单规则
    """
    # grep 保护：避免搜索 node_modules
    if name == "grep":
        p = params.get("path", "")
        if p:
            w = _check_search_scope_warning(p)
            if "node_modules" in w:
                return True, w

    # bash 保护：避免在 node_modules 中搜索
    if name == "bash":
        c = params.get("command", "").lower()
        if "select-string" in c and "node_modules" in c:
            return True, "不应搜索 node_modules。"

    return True, ""


def _check_search_scope_warning(path: str) -> str:
    """检查路径是否包含应避免搜索的目录。"""
    n = path.replace("\\", "/")
    warnings = []
    if "/node_modules/" in n:
        warnings.append("路径包含 node_modules（大量文件，搜索将很慢）")
    if "/bin/" in n or "/obj/" in n:
        warnings.append("路径包含编译输出目录")
    if "/.git/" in n:
        warnings.append("路径包含 .git 目录")
    return "; ".join(warnings)


# ── 结果格式化 ──

def smart_truncate(text: str, max_length: int = 6000) -> str:
    """智能截断文本：保留开头和结尾的重要信息。

    对于构建/编译输出，保留末尾的错误信息。
    """
    if not text or len(text) <= max_length:
        return text

    head_len = int(max_length * 0.6)
    tail_len = max_length - head_len - 50

    head = text[:head_len]
    tail = text[-tail_len:] if tail_len > 0 else ""

    return f"{head}\n... [截断: 共 {len(text):,} 字符，显示 {max_length:,}] ...\n{tail}"


def check_search_scope(path: str) -> str:
    """检查搜索范围是否过大。"""
    if not path or path in (".", "./", os.getcwd()):
        return "."
    return path


def classify_tool_result(result_text: str) -> dict:
    """对工具结果进行分类：自动识别错误类型并给出修复建议。

    Returns:
        {"success": bool, "error_type": str, "suggestion": str}
    """
    if not result_text:
        return {"success": True, "error_type": "ok", "suggestion": ""}

    lower = result_text.lower()

    # 文件不存在
    if any(kw in lower[:300] for kw in ("找不到", "not found", "不存在", "does not exist")):
        return {"success": False, "error_type": "file_not_found",
                "suggestion": "文件不存在，请检查路径是否正确。"}

    # 命令失败
    if any(kw in lower for kw in ("exit code: 1", "exit code: 2", "超时", "timeout")):
        return {"success": False, "error_type": "command_failed",
                "suggestion": "命令执行失败，请检查错误信息。"}

    # 导入错误
    if any(kw in lower[:500] for kw in ("modulenotfound", "importerror", "cannot import")):
        return {"success": False, "error_type": "import_error",
                "suggestion": "缺少依赖模块，自动安装中..."}

    # 工具错误
    if "工具错误" in lower or "工具执行错误" in lower:
        return {"success": False, "error_type": "tool_error",
                "suggestion": "工具执行异常，请重试。"}

    # 通用错误
    if any(kw in lower[:300] for kw in ("错误:", "error:", "failed:", "❌")):
        return {"success": False, "error_type": "error",
                "suggestion": "遇到错误，请检查详情。"}

    # 无结果
    if "无结果" in lower or "no results" in lower:
        return {"success": False, "error_type": "no_results",
                "suggestion": "未找到匹配结果，请调整查询条件。"}

    return {"success": True, "error_type": "ok", "suggestion": ""}


# ── 插件加载 ──

def _load_plugins():
    """加载 agent/plugins 目录下的插件。"""
    state = get_state()
    if state.plugins_loaded:
        return

    import importlib

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
                    handler = result.get("handler")
                    schema = result.get("input_schema", {})
                    if handler:
                        state.register_tool(name, handler, {
                            "name": name,
                            "description": result.get("description", ""),
                            "input_schema": schema,
                        }, is_plugin=True)
        except Exception as e:
            print(f"[插件] 加载 {plugin_name} 失败: {e}")

    state.plugins_loaded = True


def init():
    """初始化工具核心：加载插件并同步旧版全局变量。"""
    _load_plugins()
    state = get_state()
    global BUILTIN_HANDLERS, PLUGIN_HANDLERS
    BUILTIN_HANDLERS.update(state.builtin_handlers)
    PLUGIN_HANDLERS.update(state.plugin_handlers)
