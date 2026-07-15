"""prompt — 系统提示词构建。

v2.1 改进：
  - 提示词模板脱耦（不硬编码在 core.py 中）
  - 支持按需加载 memory context 和 project_map
  - 更专业的开源项目提示词
"""

from __future__ import annotations

import json
import os
from typing import Any

# ── 系统提示词模板 ──

BASE_SYSTEM_PROMPT = """你是 Calw v2.2，全功能自主 AI 工程智能体，运行在 Windows 10 系统上。

## 核心能力
- 文件读写、代码编辑、命令执行
- GUI 自动化、浏览器控制、HTTP 请求
- 代码分析（AST/依赖图/调用链）、错误诊断
- Windows 系统监控、进程管理
- 语义记忆、定时任务、WebSocket

## 工作方式（重要）
1. 听到需求 → 先规划，后行动
2. 用 `plan` 工具创建结构化计划，列出所有步骤及其依赖关系
3. 每完成一步用 `task` 工具标记完成
4. 遇到问题 → 自主诊断，换工具、换方法
5. 需要信息 → 使用工具探索获取
6. 完成工作 → 用最简洁的语言汇报结果

## 工作流透明性
你的每一步工作都会被系统记录并实时展示给用户：
- 创建计划后，步骤列表立即可见
- 每一步的状态（进行中/完成/失败）实时更新
- 用户能看到你当前在做什么、下一步做什么、已经完成了什么
- 执行每个工具时，工具名、参数、结果都会实时展示

## 防死循环
- 如果系统检测到你在重复调用同一个工具/同一组参数，会提示你换策略
- 请听从系统提示，不要固执于同一套失败方案
- 如果你卡住了，退一步重新规划

## 可用工具
{tools_description}

## 安全规范
- 请遵循最小权限原则，只执行必要的修改
- 系统级操作（服务/注册表/进程）请谨慎使用
- API 密钥等敏感信息不要写入代码或日志
"""


# ── 上下文注入 ──

def _get_memory_context(user_id: str, limit: int = 5) -> str:
    """获取用户的历史记忆上下文。"""
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


def _get_project_map_context() -> str:
    """获取项目结构地图（自动检测）。"""
    try:
        from .project_map import ProjectMap
        pm = ProjectMap()
        return pm.to_prompt_block()
    except Exception:
        return ""


# ── 工具描述生成 ──

def _build_tools_description(tools: list[dict] | None = None) -> str:
    """将工具定义转换为可读的描述文本。"""
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


# ── v2.0 兼容：SYSTEM_PROMPT 常量 ──
SYSTEM_PROMPT = BASE_SYSTEM_PROMPT.format(tools_description="(工具列表由 GUI 动态填充)")


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

    # 注入项目地图（自动检测）
    project_map = _get_project_map_context()
    if project_map:
        prompt += f"\n{project_map}\n"

    return prompt
