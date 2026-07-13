"""main — Calw v2.1 CLI 入口（流式输出）。"""

from __future__ import annotations

import os
import sys

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)


def main():
    from agent import create_agent
    from agent.core import StreamHandler

    config = {
        "model": os.environ.get("CALW_MODEL", "anthropic/claude-sonnet-4-20250514"),
        "max_tokens": int(os.environ.get("CALW_MAX_TOKENS", "8192")),
        "max_tool_rounds": int(os.environ.get("CALW_MAX_ROUNDS", "50")),
    }

    agent = create_agent(user_id="cli", config=config)

    class CliHandler(StreamHandler):
        def on_text(self, text):
            print(text, end="", flush=True)
        def on_thinking(self, text):
            print(f"\033[2m{text}\033[0m", end="", flush=True)
        def on_tool_start(self, name, inp):
            preview = list(inp.values())[0][:80] if inp else ""
            print(f"\n  \033[33m⚡ {name}\033[0m", end="", flush=True)
            if preview:
                print(f" \033[90m{preview}\033[0m", end="", flush=True)
            print(flush=True)
        def on_tool_result(self, result):
            preview = result[:120].replace("\n", " ")
            print(f"  \033[32m← {preview}\033[0m", flush=True)
        def on_complete(self):
            print()
        def on_error(self, error):
            print(f"\n\033[31m错误: {error}\033[0m")

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

        handler = CliHandler()
        agent.run_iteration(user_input, handler)

    agent.close()


if __name__ == "__main__":
    main()
