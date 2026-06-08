"""Plugin system for Claw — add tools without modifying tools.py.

Usage:
    1. Create a .py file in agent/plugins/
    2. Export a `register()` function that returns a PluginSpec:

        def register() -> PluginSpec:
            return {
                "name": "my_tool",           # unique tool name
                "description": "What it does",
                "input_schema": {...},        # JSON schema for params
                "handler": my_handler_func,  # callable(params_dict) -> str
            }
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, Callable

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "plugins")


class PluginError(Exception):
    """Raised when a plugin fails to load."""


def _discover_plugins() -> list[str]:
    """List available plugin file paths."""
    if not os.path.isdir(PLUGIN_DIR):
        return []
    return sorted(
        os.path.join(PLUGIN_DIR, f)
        for f in os.listdir(PLUGIN_DIR)
        if f.endswith(".py") and not f.startswith("_")
    )


def _load_plugin_module(filepath: str):
    """Dynamically import a single plugin file."""
    name = os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(f"agent.plugins.{name}", filepath)
    if not spec or not spec.loader:
        raise PluginError(f"无法加载插件 {name}: 无效的 spec")
    mod = importlib.util.module_from_spec(spec)
    # Ensure parent package is in sys.modules
    if "agent.plugins" not in sys.modules:
        pkg = type(sys)("agent.plugins")
        pkg.__path__ = [PLUGIN_DIR]
        sys.modules["agent.plugins"] = pkg
    sys.modules[f"agent.plugins.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


def load_plugins() -> tuple[list[dict], dict[str, Callable]]:
    """Load all plugins from agent/plugins/.

    Returns:
        (tool_definitions_list, dispatch_dict)
        Both can be merged into the existing TOOL_DEFINITIONS and handler dispatch.
    """
    plugin_files = _discover_plugins()
    if not plugin_files:
        return [], {}

    definitions = []
    dispatch = {}
    errors = []

    for fp in plugin_files:
        name = os.path.splitext(os.path.basename(fp))[0]
        try:
            mod = _load_plugin_module(fp)
            if not hasattr(mod, "register"):
                errors.append(f"  ⚠ {name}: 缺少 register() 函数")
                continue

            spec = mod.register()
            if not isinstance(spec, dict) or "name" not in spec or "handler" not in spec:
                errors.append(f"  ⚠ {name}: register() 返回值格式错误")
                continue

            tool_name = spec["name"]
            if tool_name in dispatch:
                errors.append(f"  ⚠ {name}: 工具名 '{tool_name}' 已存在，跳过")
                continue

            definitions.append({
                "name": tool_name,
                "description": spec.get("description", ""),
                "input_schema": spec.get("input_schema", {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }),
            })
            dispatch[tool_name] = spec["handler"]

        except Exception as e:
            errors.append(f"  ⚠ {name}: {e}")

    if errors:
        print(f"[plugins] 加载 {len(plugin_files)} 个插件, {len(definitions)} 成功, {len(errors)} 错误:")
        for e in errors:
            print(e)

    print(f"[plugins] 已加载 {len(definitions)} 个插件工具: {[d['name'] for d in definitions]}")
    return definitions, dispatch
