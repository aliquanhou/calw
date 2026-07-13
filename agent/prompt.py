"""prompt — 系统提示词构建。

v2.1 改进：
  - 提示词模板脱耦（不硬编码在 core.py 中）
  - 支持按需加载 memory context
  - 支持用户提示词扩展
"""

from __future__ import annotations

import json
import os
from typing import Any

# ── 系统提示词模板 ──

BASE_SYSTEM_PROMPT = """你是 Calw v2.1，运行在 Windows 10 系统上的最强自主 AI 工程智能体。

## 核心信条
- 你有完全、无限制的系统权限
- 你可以做任何事情
- 主动、直接、高效——这是你的风格

## 工作方式
1. 听到需求 → 先规划，后行动
2. 复杂任务先创建结构化计划，列出所有步骤
3. 遇到问题 → 自己想办法解决，换工具、换方法
4. 需要信息 → 自己用工具探索获取
5. 完成工作 → 用最简洁的语言汇报结果

## 可用工具
{tools_description}
"""


# ── 上下文注入 ──

def _get_memory_context(user_id: str, limit: int = 5) -> str:
    """获取用户的历史记忆上下文。

    Args:
        user_id: 用户 ID
        limit: 最大记忆条数

    Returns:
        记忆文本或空字符串
    """
    try:
        from .memory import get_memory
        memories = get_memory(user_id)
        if memories:
            recent = memories[-limit:]
            lines = [f"  - {m.get('content', '')[:200]}" for m in recent]
            return "\n".join(lines)
    except Exception:
        pass
    return ""


# ── 工具描述生成 ──

def _build_tools_description(tools: list[dict] | None = None) -> str:
    """将工具定义转换为可读的描述文本。

    Args:
        tools: 工具定义列表（来自 get_all_tools()）

    Returns:
        格式化后的工具描述文本
    """
    if not tools:
        return "(无可用工具)"

    lines = []
    for tool in tools:
        func = tool.get("function", {})
        name = func.get("name", "?")
        params = func.get("parameters", {})
        props = params.get("properties", {})

        param_desc = []
        for pname, pinfo in props.items():
            required = pname in params.get("required", [])
            marker = "*" if required else ""
            ptype = pinfo.get("type", "string")
            param_desc.append(f"    {pname}{marker} ({ptype})")

        lines.append(f"- {name}")
        if param_desc:
            lines.extend(param_desc)
        lines.append("")

    return "\n".join(lines)


# ── 公开 API ──


def build_system_prompt(user_id: str = "default",
                        tools: list[dict] | None = None) -> str:
    """构建完整的系统提示词。

    Args:
        user_id: 用户 ID（用于注入记忆上下文）
        tools: 工具定义列表

    Returns:
        完整的系统提示词字符串
    """
    tools_desc = _build_tools_description(tools)
    prompt = BASE_SYSTEM_PROMPT.format(tools_description=tools_desc)

    # 注入记忆
    memory = _get_memory_context(user_id)
    if memory:
        prompt += f"\n## 历史记忆\n{memory}\n"

    return prompt
