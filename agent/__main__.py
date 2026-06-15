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
    parser.add_argument("--cli", action="store_true", help="CLI REPL 模式")
    parser.add_argument("--run", type=str, help="非交互模式：执行一条指令后退出")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出（配合 --run）")
    parser.add_argument("--model", type=str, default="", help="指定模型名")
    parser.add_argument("--router", action="store_true", help="启用智能模型路由")
    parser.add_argument("prompt", nargs="*", help="单次执行指令（仅 --cli 模式）")
    args = parser.parse_args()

    if args.run:
        from .providers import OpenAIProvider, AnthropicProvider, get_provider, reset_usage, get_usage_summary
        from .core import Agent, ConsoleHandler, StreamHandler
        from .router import recommend_model, classify_task
        model = args.model or os.environ.get("LLM_MODEL", "deepseek-chat")
        if args.router:
            task_type = classify_task(args.run)
            available = OpenAIProvider.models + AnthropicProvider.models
            recommended = recommend_model(args.run, available)
            if recommended and recommended != model:
                model = recommended
        provider = get_provider("DeepSeek" if "deepseek" in model or "gpt" in model else "Anthropic Claude", api_key, model)
        agent = Agent(provider)
        if args.json:
            class JH(StreamHandler):
                def __init__(s): s.text="";s.tools=[]
                def on_text(s,t):s.text+=t
                def on_tool_start(s,n,i):s.tools.append({"name":n,"input":i})
                def on_error(s,e):s.text+=f"\n[错误]{e}"
            h=JH(); agent.run_iteration(args.run, h)
            import json; print(json.dumps({"text":h.text,"tools":h.tools,"usage":get_usage_summary()}, ensure_ascii=False, indent=2))
        else:
            agent.run_iteration(args.run, ConsoleHandler())
        return

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
