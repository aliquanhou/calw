"""main — Calw v2.1 入口。

所有模块依赖都已消除副作用：
  - 启动时不自动加载工具
  - 工具在 Agent.run() 首次调用时按需注册
  - 全局状态收敛到 SessionState
"""

from __future__ import annotations

import os
import sys

# 确保当前目录在 sys.path 中
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)


def main():
    """CLI 交互入口。"""
    from agent import create_agent

    config = {
        "model": os.environ.get("CALW_MODEL", "anthropic/claude-sonnet-4-20250514"),
        "max_tokens": int(os.environ.get("CALW_MAX_TOKENS", "8192")),
        "max_tool_rounds": int(os.environ.get("CALW_MAX_ROUNDS", "50")),
    }

    agent = create_agent(user_id="cli", config=config)

    print(f"Calw v2.1 — 输入 'exit' 退出\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            break

        response = agent.run(user_input)
        print(f"\n{response}\n")

    agent.close()


if __name__ == "__main__":
    main()
