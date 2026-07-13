"""__init__ — agent 包初始化。

v2.1 改进：
  - 无模块级副作用
  - init() 函数做一次性的全部导入和注册
  - 从 v2.0 移植：retry/router/researcher/reviewer/mcpserver/project_map
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

# 从 v2.0 移植的模块（惰性导入，不增加启动开销）
from .retry import (
    retryable, with_retry, retry_generator,
    is_retryable, sleep_with_backoff,
)
from .router import classify_task, recommend_model, compare_models
from .project_map import ProjectMap

# 可选模块（需要时才导入）
# from .researcher import deep_research, format_report
# from .reviewer import review_diff, review_file, format_report
# from .mcpserver import get_mcp


def create_agent(user_id: str = "default", config: dict | None = None) -> Agent:
    """便捷工厂函数：创建 Agent 实例。

    Args:
        user_id: 用户 ID
        config: 配置字典

    Returns:
        配置好的 Agent 实例
    """
    return Agent(user_id=user_id, config=config)
