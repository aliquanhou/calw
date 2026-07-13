"""__init__ — agent 包初始化。

v2.1 改进：
  - 无模块级副作用
  - init() 函数做一次性的全部导入和注册
"""

from __future__ import annotations

import os

# ── 版本 ──

__version__ = "2.1.0"
__codename__ = "Calw"


# ── 公开 API ──

from .core import Agent
from .session import get_state, set_state, SessionState
from .tools import get_all_tools, execute_tool, init_tools, register_tool


def create_agent(user_id: str = "default", config: dict | None = None) -> Agent:
    """便捷工厂函数：创建 Agent 实例。

    Args:
        user_id: 用户 ID
        config: 配置字典

    Returns:
        配置好的 Agent 实例
    """
    return Agent(user_id=user_id, config=config)
