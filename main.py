"""main — Calw v2.1 CLI 入口（Claude Code 风格输出）。"""

from __future__ import annotations

import json
import os
import sys
import time
import shutil

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)


def _term_width() -> int:
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def _format_path(inp: dict) -> str:
    """从工具参数中提取文件路径或命令。"""
    if "file_path" in inp:
        return inp["file_path"]
    if "command" in inp:
        cmd = inp["command"]
        return cmd[:80] + ("..." if len(cmd) > 80 else "")
    if "url" in inp:
        return inp["url"]
    if "pattern" in inp:
        return inp["pattern"]
    if "query" in inp:
        return inp["query"]
    return ""


def _format_result_summary(result: str, tool_name: str = "") -> str:
    """生成简洁的结果摘要（Claude Code 风格）。"""
    if not result or result == "(无输出)":
        return "✔ done"
    # 提取第一行有意义的摘要
    if tool_name in ("read",):
        lines = result.split("\n")
        return f"{len(lines)} 行"
    if tool_name in ("write", "edit", "replace"):
        if "成功" in result:
            return "✔ " + result.split("]")[-1].strip() if "]" in result else "✔ success"
        return result[:100]
    if tool_name in ("bash",):
        lines = [l for l in result.split("\n") if l.strip()]
        for kw in ("error", "Error", "Traceback", "Exit code"):
            if kw in result:
                err_lines = [l for l in lines if kw in l]
                if err_lines:
                    return f"⚠ {err_lines[0][:120]}"
        return f"✔ {len(lines)} 行输出"
    if len(result) > 150:
        return result[:150] + "..."
    return result.replace("\n", " ")


def main():
    from agent import create_agent
    from agent.core import StreamHandler

    config = {
        "model": os.environ.get("CALW_MODEL", "anthropic/claude-sonnet-4-20250514"),
        "max_tokens": int(os.environ.get("CALW_MAX_TOKENS", "8192")),
        "max_tool_rounds": int(os.environ.get("CALW_MAX_ROUNDS", "50")),
    }

    agent = create_agent(user_id="cli", config=config)

    # ── ANSI 颜色 ──
    C = {
        "reset": "\033[0m",
        "dim": "\033[2m",
        "bold": "\033[1m",
        "user": "\033[32m",       # 绿色 — 用户
        "asst": "\033[37m",       # 白色 — Assistant
        "think": "\033[90m",      # 灰色 — 思考
        "tool": "\033[33m",       # 橙色 — 工具名
        "tool_param": "\033[36m", # 青色 — 参数（路径/命令）
        "result": "\033[32m",     # 绿色 — 成功结果
        "result_err": "\033[31m", # 红色 — 错误结果
        "separator": "\033[90m",  # 灰色 — 分隔线
        "code": "\033[94m",       # 蓝色 — 代码/文件内容
        "info": "\033[35m",       # 紫色 — 额外信息
        "arrow": "\033[2m",       # 灰色箭头
    }

    tool_icons = {
        "read": "📖", "write": "✏️", "edit": "🔧", "replace": "🔍",
        "glob": "🔎", "grep": "🔎", "bash": "💻", "web": "🌐",
        "web_search": "🔍", "browser": "🌍", "process": "⚙️",
        "service": "⚙️", "registry": "📋", "gui": "🖱️",
        "plan": "📋", "task": "✅", "background": "⏳",
        "remember": "🧠", "test": "🧪", "dep": "📦",
        "ast": "🌳", "dep_graph": "🕸️", "call_chain": "🔗",
        "monitor": "📊", "schedule": "⏰", "watch": "👁️",
        "websocket": "🔌", "download": "📥", "move": "📂",
        "copy": "📄", "delete": "🗑️", "mkdir": "📁",
        "ask_user": "💬", "trace_error": "🐛",
    }

    class CliHandler(StreamHandler):
        def __init__(self):
            self._tool_start_time = 0.0
            self._current_tool = ""
            self._current_tool_path = ""
            self._turn_tool_count = 0

        def on_text(self, text):
            print(f"{C['asst']}{text}{C['reset']}", end="", flush=True)

        def on_thinking(self, text):
            print(f"{C['think']}{text}{C['reset']}", end="", flush=True)

        def on_turn_plan(self, tool_count: int):
            self._turn_tool_count = tool_count
            if tool_count > 1:
                print(f"{C['info']}📋 计划 {tool_count} 个步骤{C['reset']}")

        def on_tool_start(self, name, inp):
            self._tool_start_time = time.time()
            self._current_tool = name
            self._current_tool_path = _format_path(inp)
            icon = tool_icons.get(name, "⚡")
            path = self._current_tool_path

            # 工具名 + 目标（Claude Code 风格）
            label = f"{icon} {name}"
            width = _term_width()
            if path:
                # 截断路径以适配终端宽度
                max_path = max(width - len(label) - 10, 30)
                if len(path) > max_path:
                    path = "..." + path[-(max_path-3):]
                print(f"\n  {C['tool']}{label}{C['reset']} {C['tool_param']}{path}{C['reset']}")
            else:
                print(f"\n  {C['tool']}{label}{C['reset']}")

            # 如果有额外参数，灰色显示
            extra_params = {k: v for k, v in inp.items()
                          if k not in ("file_path", "command", "url", "pattern", "query") and v}
            if extra_params:
                preview = " ".join(f"{k}={v}" for k, v in extra_params.items())
                if len(preview) > 100:
                    preview = preview[:100] + "..."
                print(f"    {C['dim']}{preview}{C['reset']}")

        def on_tool_result(self, result):
            elapsed = time.time() - self._tool_start_time
            elapsed_str = f" ({elapsed:.1f}s)" if elapsed > 0.3 else ""
            summary = _format_result_summary(result, self._current_tool)
            is_err = any(kw in result[:100].lower() for kw in ("错误", "error", "失败", "❌"))

            if is_err:
                print(f"  {C['result_err']}✗ {summary}{elapsed_str}{C['reset']}")
                # 错误详情用灰色展开
                if len(result) > len(summary):
                    detail = result[:500]
                    print(f"    {C['dim']}{detail}{C['reset']}")
            else:
                print(f"  {C['result']}✔ {summary}{elapsed_str}{C['reset']}")

            # 读文件：展示内容摘要
            if self._current_tool == "read" and result:
                lines = result.split("\n")
                # 显示前 5 行和后 3 行
                preview_lines = lines[:5]
                if len(lines) > 8:
                    preview_lines.append(C['dim'] + f"    ... 共 {len(lines)} 行" + C['reset'])
                    preview_lines.extend(lines[-3:])
                for line in preview_lines:
                    print(f"    {C['code']}{line}{C['reset']}")

            # bash 输出：展示最后几行
            if self._current_tool == "bash" and result:
                lines = [l for l in result.split("\n") if l.strip()]
                if len(lines) > 6:
                    for l in lines[-4:]:
                        print(f"    {C['dim']}{l[:150]}{C['reset']}")

            self._current_tool = ""

        def on_error(self, error):
            print(f"\n{C['result_err']}❌ 错误: {error}{C['reset']}")

        def on_complete(self):
            print(f"\n{C['separator']}{'─' * 40}{C['reset']}\n")

    print(f"\n{C['bold']}{C['info']}Calw v2.1 — 输入 exit 退出{C['reset']}\n")

    while True:
        try:
            user_input = input(f"{C['user']}▶ {C['reset']}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C['dim']}再见。{C['reset']}")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            break

        # 显示用户输入
        print(f"{C['user']}>>> {user_input}{C['reset']}\n")

        handler = CliHandler()
        agent.run_iteration(user_input, handler)

    agent.close()


if __name__ == "__main__":
    main()
