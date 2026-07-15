"""Entry point: python -m agent

默认启动 GUI。
使用 --cli 进入命令行 REPL。
使用 --run 执行单条指令。
增加 --transcript 输出 JSON 事件流供 UI 层消费。
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Calw AI Agent - 透明自主编程")
    parser.add_argument("--cli", action="store_true", help="命令行 REPL 模式")
    parser.add_argument("--run", type=str, help="非交互模式：执行一条指令后退出")
    parser.add_argument("--model", type=str, default="", help="模型名（默认 claude-sonnet-4-20250514）")
    parser.add_argument("--provider", type=str, default="anthropic", help="LLM 提供商")
    parser.add_argument("--transcript", action="store_true", help="输出 JSON 事件流（供 UI 消费）")
    parser.add_argument("--json", action="store_true", help="最终结果以 JSON 格式输出")
    parser.add_argument("prompt", nargs="*", help="单次执行指令（仅 --cli 模式）")
    args = parser.parse_args()

    api_key = (os.environ.get("ANTHROPIC_API_KEY") or
               os.environ.get("DEEPSEEK_API_KEY") or
               os.environ.get("OPENAI_API_KEY"))

    # ── GUI 模式（默认） ──
    if not args.cli and not args.run:
        from .app import run as run_gui
        run_gui()
        return

    # ── CLI / --run 模式 ──
    if not api_key:
        print("错误: 未设置 API Key (ANTHROPIC_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY)")
        sys.exit(1)

    from .core import Agent
    from .transcript import Transcript

    config = {
        "api_key": api_key,
        "provider": args.provider if args.provider else "anthropic",
        "model": args.model or os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514"),
    }

    transcript = Transcript(agent_id="calw")

    if args.transcript:
        def _json_printer(event):
            line = json.dumps(event.dict(), ensure_ascii=False)
            print(f"@EVENT {line}", flush=True)
        transcript.on("*", _json_printer)

    agent = Agent(config=config, transcript=transcript)

    if args.run:
        result = agent.run(args.run,
                           on_text=lambda t: print(t, end="", flush=True))
        if args.json:
            print("\n" + json.dumps({
                "result": result,
                "summary": transcript.summary(),
                "workflow": agent.workflow.to_dict(),
            }, ensure_ascii=False, indent=2))
        agent.close()
        return

    # ── CLI REPL ──
    from .core import StreamHandler

    class ConsoleHandler(StreamHandler):
        def on_text(self, text): print(text, end="", flush=True)
        def on_thinking(self, text): print(f"\033[90m{text}\033[0m", end="", flush=True)
        def on_tool_start(self, name, input_data):
            preview = json.dumps(input_data, ensure_ascii=False)[:200]
            print(f"\n\033[33m⚡ {name}({preview})\033[0m")
        def on_tool_result(self, result):
            display = result[:300].replace("\n", "\\n")
            print(f"\033[33m  → {display}\033[0m")
        def on_error(self, error): print(f"\033[31m错误: {error}\033[0m")
        def on_complete(self): print()

    print("\033[1;34m" + "=" * 60 + "\n  Calw v2.2 - 透明自主编程\n  命令: /exit 退出  /status 查看工作流\n" + "=" * 60 + "\033[0m")
    while True:
        try:
            user_input = input("\033[1;32m>>> \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not user_input:
            continue
        if user_input == "/exit":
            print("Bye!")
            break
        elif user_input == "/clear":
            agent = Agent(config=config, transcript=transcript)
            print("\033[33m对话已重置\033[0m")
            continue
        elif user_input == "/status":
            wf = agent.workflow.to_dict()
            print(f"\033[33m工作流状态: {json.dumps(wf, ensure_ascii=False, indent=2)}\033[0m")
            continue
        try:
            agent.run_iteration(user_input, ConsoleHandler())
        except KeyboardInterrupt:
            print("\n\033[33m⏹ 已中断\033[0m")
        except Exception as e:
            print(f"\033[31m错误: {e}\033[0m")


if __name__ == "__main__":
    main()
