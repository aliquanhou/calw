"""tools — 工具注册与管理。
v2.1 重构：
  - 消除模块级副作用的隐式注册
  - 改用显式注册表模式（注册表就是一个普通 dict）
  - 注册在函数调用时显式发生，而非模块导入时隐式发生
  - 所有函数纯引用，不包含任何实例化和异步启动代码
  - 适配工具处理器签名统一：接受 **(**kwargs) 变参
"""

from __future__ import annotations

import inspect
import os
import sys
import time
import traceback
from typing import Any, Callable

# ── 工具注册表（纯数据结构，0 副作用）──

_TOOL_REGISTRY: dict[str, dict[str, Any]] = {}
"""工具注册表，结构：
{
    "tool_name": {
        "name": str,
        "handler": Callable,
        "description": str,
        "parameters": dict,  # JSON Schema 格式
    }
}
"""


# ── 注册表操作 ──


def register_tool(
    name: str,
    handler: Callable,
    description: str = "",
    parameters: dict | None = None,
):
    """注册一个工具到注册表。

    Args:
        name: 工具名称（唯一标识）
        handler: 处理函数（接受 **kwargs 变参）
        description: 工具描述
        parameters: JSON Schema 格式的参数定义
    """
    _TOOL_REGISTRY[name] = {
        "name": name,
        "handler": handler,
        "description": description,
        "parameters": parameters or {"type": "object", "properties": {}},
    }


def unregister_tool(name: str) -> bool:
    """注销一个工具。

    Args:
        name: 工具名称

    Returns:
        True 表示注销成功，False 表示工具不存在
    """
    return _TOOL_REGISTRY.pop(name, None) is not None


def get_tool(name: str) -> dict | None:
    """获取工具定义。

    Args:
        name: 工具名称

    Returns:
        工具定义 dict，或 None
    """
    return _TOOL_REGISTRY.get(name)


def get_all_tools() -> list[dict]:
    """获取所有已注册的工具定义列表。"""
    return [{"type": "function", "function": t} for t in _TOOL_REGISTRY.values()]


def execute_tool(name: str, params: dict) -> str:
    """执行一个工具（带统一异常处理）。

    Args:
        name: 工具名称
        params: 参数字典

    Returns:
        工具执行结果字符串（失败时返回错误描述）
    """
    tool_def = _TOOL_REGISTRY.get(name)
    if not tool_def:
        return f"[错误] 未知工具: {name}"

    handler = tool_def["handler"]
    try:
        result = handler(**params)
        # 统一转字符串
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        try:
            return str(result)
        except Exception:
            return f"<{type(result).__name__}>"
    except Exception as e:
        tb = traceback.format_exc()
        return f"[工具错误: {name}] {e}\n{tb}"


# ── 从模块导入并注册工具 ──


def load_tools_from_module(module_path: str) -> list[str]:
    """从指定模块导入并注册所有工具处理函数。

    约定：模块中名字以 _handle_ 开头的函数自动注册为工具。
    函数名 _handle_X → 注册为工具名 X。

    Args:
        module_path: 模块路径，例如 "agent.tools_browser"

    Returns:
        注册成功的工具名列表
    """
    import importlib

    try:
        mod = importlib.import_module(module_path)
    except Exception as e:
        return [f"导入失败 {module_path}: {e}"]

    registered = []
    for attr_name in dir(mod):
        if not attr_name.startswith("_handle_"):
            continue

        tool_name = attr_name[len("_handle_"):]
        handler = getattr(mod, attr_name)

        if not callable(handler):
            continue

        # 从函数签名生成参数 schema
        sig = inspect.signature(handler)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name == "kwargs":
                continue
            param_type = param.annotation if param.annotation is not inspect.Parameter.empty else "string"
            properties[param_name] = {
                "type": _py_type_to_json_type(param_type),
                "description": param_name,
            }
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        parameters_schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            parameters_schema["required"] = required

        register_tool(
            name=tool_name,
            handler=handler,
            description=f"自动注册: {module_path}.{attr_name}",
            parameters=parameters_schema,
        )
        registered.append(tool_name)

    return registered


def _py_type_to_json_type(py_type):
    """Python 类型 → JSON Schema 类型。"""
    type_map = {
        str: "string",
        int: "number",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    if py_type in type_map:
        return type_map[py_type]
    return "string"


# ── 内置工具注册 ──


def _register_builtins():
    """注册 Calw 内置工具。

    显式调用，取代之前的模块级副作用模式。
    """
    # 加载各模块中的 _handle_* 函数
    tool_modules = [
        "agent.file_ops",
        "agent.command",
        "agent.tools_browser",
    ]

    for module in tool_modules:
        try:
            load_tools_from_module(module)
        except Exception as e:
            print(f"[tools] 加载模块失败 {module}: {e}")


def init_tools():
    """初始化工具系统（显式调用，无模块级副作用）。

    必须在 Agent 启动时显式调用一次。
    """
    _register_builtins()
