"""Entry point: python -m agent

Launches the GUI application by default.
Use --cli for the command-line REPL mode.
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> None:
    # Fix Windows console encoding for Unicode (emoji, CJK)
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(description="AI Agent - 多 LLM 支持")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="使用命令行模式而非 GUI",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="单次执行模式：直接输入指令（仅 CLI 模式）",
    )
    args = parser.parse_args()

    if args.cli:
        # ── CLI mode ──
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("错误: 未设置 API Key 环境变量 (ANTHROPIC_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY)")
            sys.exit(1)

        from .core import Agent
        from .providers import OpenAIProvider
        provider = OpenAIProvider(api_key=api_key, model=os.environ.get("LLM_MODEL", "deepseek-chat"))
        agent = Agent(provider)

        if args.prompt:
            from .core import ConsoleHandler
            prompt_text = " ".join(args.prompt)
            try:
                agent.run_iteration(prompt_text, ConsoleHandler())
            except Exception as e:
                print(f"\033[31m错误: {e}\033[0m")
                sys.exit(1)
        else:
            agent.run_repl()
    else:
        # ── GUI mode (default) ──
        from .app import run as run_gui
        run_gui()


if __name__ == "__main__":
    main()
