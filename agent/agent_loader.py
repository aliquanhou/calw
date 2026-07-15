"""agent_loader — Agent 定义加载器。

从 agents/*.md 读取 YAML frontmatter + Markdown 正文，
注册为可被 Task 工具调用的 Agent 类型。

格式：
  ---
  name: code-architect
  description: 设计功能架构
  model: claude-sonnet-4-20250514
  tools: read, glob, grep, web_search, web_fetch
  color: green
  ---
  You are a senior software architect...
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

# ── Agent 注册表 ──

_AGENT_REGISTRY: dict[str, "AgentDef"] = {}
"""全局 Agent 类型注册表。key = agent name, value = AgentDef"""


@dataclass
class AgentDef:
    """一个 Agent 类型的定义。"""
    name: str
    description: str
    system_prompt: str
    model: str = ""
    tools: list[str] | None = None
    color: str = "cyan"


# ── Frontmatter 解析 ──

_FM_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)', re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 YAML frontmatter + Markdown 正文。

    Args:
        text: 完整的 .md 文件内容

    Returns:
        (frontmatter_dict, body_text)
    """
    m = _FM_PATTERN.match(text)
    if not m:
        return {}, text.strip()

    yaml_text = m.group(1)
    body = m.group(2).strip()

    # 轻量 YAML 解析（不依赖 pyyaml）
    fm: dict = {}
    for line in yaml_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            fm[key] = val

    return fm, body


def _parse_list_field(value: str) -> list[str]:
    """解析逗号分隔的列表字段。"""
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


# ── 加载 ──

def load_agents(agents_dir: str | None = None) -> dict[str, AgentDef]:
    """扫描 agents/ 目录加载所有 Agent 定义。

    Args:
        agents_dir: agents 目录路径，默认 __file__ 同级 agents/

    Returns:
        {name: AgentDef, ...}
    """
    if agents_dir is None:
        agents_dir = os.path.join(os.path.dirname(__file__), "agents")

    if not os.path.isdir(agents_dir):
        return {}

    loaded: dict[str, AgentDef] = {}
    for fname in sorted(os.listdir(agents_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(agents_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue

        fm, body = _parse_frontmatter(text)
        if not fm.get("name"):
            continue

        adef = AgentDef(
            name=fm["name"],
            description=fm.get("description", ""),
            system_prompt=body,
            model=fm.get("model", ""),
            tools=_parse_list_field(fm.get("tools", "")),
            color=fm.get("color", "cyan"),
        )
        loaded[adef.name] = adef

    return loaded


def get_agent(name: str) -> AgentDef | None:
    """按名称获取 Agent 定义。"""
    if not _AGENT_REGISTRY:
        # 惰性加载
        _AGENT_REGISTRY.update(load_agents())
    return _AGENT_REGISTRY.get(name)


def list_agents() -> list[dict]:
    """列出所有可用 Agent 类型。"""
    if not _AGENT_REGISTRY:
        _AGENT_REGISTRY.update(load_agents())
    return [
        {
            "name": a.name,
            "description": a.description,
            "model": a.model or "(继承主Agent)",
            "tools": a.tools or "(全部)",
        }
        for a in _AGENT_REGISTRY.values()
    ]


def ensure_loaded():
    """确保注册表已加载。"""
    if not _AGENT_REGISTRY:
        _AGENT_REGISTRY.update(load_agents())
