"""Agent loop - provider-agnostic conversation management with streaming and tool execution."""

from __future__ import annotations

import copy
import json
import os
import uuid
import concurrent.futures
from typing import Any

from .tools import TOOL_DEFINITIONS, handle_tool_call
from .prompt import SYSTEM_PROMPT as _DEFAULT_PROMPT
from .providers import LLMProvider
from .retry import is_retryable, sleep_with_backoff
from .context import compress_messages, sanitize_messages, extract_existing_tool_ids


# ── Timeout + Retry helper ──

def _call_with_timeout(func, timeout, *args, **kwargs):
    last_error = None
    for attempt in range(3):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(func, *args, **kwargs)
                return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Function timed out after {timeout}s")
        except Exception as e:
            last_error = e
            if attempt < 2 and is_retryable(e):
                sleep_with_backoff(attempt)
                continue
            raise
    raise last_error


# ── Tool display mappings ──

_TOOL_ICONS = {
    "read": "\U0001f4d6", "write": "✏️", "edit": "\U0001f4dd", "replace": "\U0001f50d",
    "glob": "\U0001f50e", "grep": "\U0001f50d", "bash": "\U0001f4bb", "think": "\U0001f9e0",
    "web": "\U0001f310", "web_search": "\U0001f50d", "ask_user": "\U0001f4ac",
    "browser": "\U0001f30d", "screencap": "\U0001f4f8",
    "plan": "\U0001f4cb", "task": "✅", "project_memory": "\U0001f9e0",
    "ast": "\U0001f52c", "dep_graph": "\U0001f517", "call_chain": "\U0001f517",
    "revert": "⏪", "system_info": "\U0001f5a5", "process": "⚙️",
    "background": "⏳", "trace_error": "\U0001f41b",
    "test": "\U0001f9ea",
    "dep": "\U0001f4e6",
    "service": "⚙️",
    "registry": "\U0001f4c1",
    "move": "\U0001f4c2",
    "copy": "\U0001f4cb",
    "delete": "\U0001f5d1",
    "mkdir": "\U0001f4c1",
    "download": "\U0001f4e5",
}
_TOOL_VERBS = {
    "read": "读取文件", "write": "写入文件", "edit": "编辑文件",
    "replace": "搜索替换", "glob": "搜索路径", "grep": "搜索内容",
    "bash": "执行命令", "think": "推理思考", "ask_user": "询问用户",
    "web": "HTTP 请求", "web_search": "网络搜索",
    "screencap": "屏幕截图", "browser": "浏览器操作",
    "plan": "任务计划", "task": "任务追踪", "project_memory": "项目记忆",
    "ast": "AST 分析", "dep_graph": "依赖分析", "call_chain": "调用链",
    "revert": "撤销更改", "system_info": "系统信息", "process": "进程管理",
    "background": "后台任务", "trace_error": "错误追踪",
    "test": "测试驱动",
    "dep": "依赖管理",
    "service": "服务控制",
    "registry": "注册表",
    "move": "移动文件",
    "copy": "复制文件",
    "delete": "删除文件",
    "mkdir": "创建目录",
    "download": "下载文件",
}


# ──────────────────────────────────────────────
# Stream Handler
# ──────────────────────────────────────────────

class StreamHandler:
    """Callback interface for streaming output from the agent."""

    def on_text(self, text: str) -> None:
        pass

    def on_thinking(self, text: str) -> None:
        pass

    def on_tool_start(self, name: str, input_data: dict) -> None:
        pass

    def on_tool_result(self, result: str) -> None:
        pass

    def on_tool_output(self, text: str) -> None:
        pass

    def on_turn_plan(self, tool_count: int) -> None:
        pass

    def on_turn_summary(self, summary: str) -> None:
        """Called with a structured summary of what happened this turn."""
        pass

    def on_error(self, error: str) -> None:
        pass

    def on_turn_end(self) -> None:
        pass

    def on_complete(self) -> None:
        pass


class ConsoleHandler(StreamHandler):
    """StreamHandler with ANSI colors and structured formatting."""

    def __init__(self):
        self._tool_count = 0
        self._tool_index = 0
        self._tool_start_time = 0.0

    def on_text(self, text: str) -> None:
        print(text, end="", flush=True)

    def on_thinking(self, text: str) -> None:
        print(f"\033[90m{text}\033[0m", end="", flush=True)

    def on_turn_plan(self, tool_count: int) -> None:
        self._tool_count = tool_count
        self._tool_index = 0
        if tool_count > 0:
            print(f"\U0001f4cb \033[1;36m本轮计划 {tool_count} 个工具调用\033[0m")

    def on_tool_start(self, name: str, input_data: dict) -> None:
        self._tool_index += 1
        self._tool_start_time = __import__("time").time()
        icon = _TOOL_ICONS.get(name, "\U0001f527")
        verb = _TOOL_VERBS.get(name, name)
        preview = json.dumps(input_data, ensure_ascii=False)
        preview = preview[:120] + "..." if len(preview) > 120 else preview
        if self._tool_count > 1:
            print(f"\n  {icon} \033[1m[{self._tool_index}/{self._tool_count}] {verb}\033[0m")
        else:
            print(f"\n  {icon} \033[1m{verb}\033[0m")
        if preview and preview != "{}":
            print(f"    \033[90m{preview}\033[0m")

    def on_tool_result(self, result: str) -> None:
        elapsed = __import__("time").time() - self._tool_start_time
        first_line = result.split("\n")[0] if result else ""
        if "错误" in first_line[:50] or "失败" in first_line[:50] or "❌" in first_line:
            status = "❌"
        elif "✅" in first_line:
            status = "✅"
        else:
            status = "✔"
        summary = first_line[:100].replace("\n", " ")
        print(f"    {status} \033[90m({elapsed:.1f}s) {summary}\033[0m")

    def on_tool_output(self, text: str) -> None:
        print(f"\033[90m{text}\033[0m", end="", flush=True)

    def on_turn_summary(self, summary: str) -> None:
        if summary:
            print(f"\033[1;34m{summary}\033[0m")

    def on_error(self, error: str) -> None:
        print(f"\033[31m❌ 错误: {error}\033[0m")

    def on_turn_end(self) -> None:
        print()

    def on_complete(self) -> None:
        print(f"\n\033[1;32m━━━━ 完成 ━━━━\033[0m")


# ──────────────────────────────────────────────
# Git stash snapshot
# ──────────────────────────────────────────────

_TURN_COUNTER: int = 0
MAX_STASH = 20


def _stash_snapshot() -> str:
    import shutil
    import subprocess
    if not shutil.which("git"):
        return ""
    global _TURN_COUNTER
    _TURN_COUNTER += 1
    try:
        cwd = os.getcwd()
        repo_check = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, cwd=cwd, timeout=10)
        if repo_check.returncode != 0:
            return ""
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=cwd, timeout=10)
        if not status.stdout.strip():
            return ""
        subprocess.run(["git", "stash", "push", "--include-untracked",
                        "-m", f"Claw: auto-snapshot turn {_TURN_COUNTER}"],
                       capture_output=True, cwd=cwd, timeout=30)
        count_result = subprocess.run(["git", "stash", "list"], capture_output=True, text=True, cwd=cwd, timeout=10)
        stash_lines = count_result.stdout.strip().split("\n") if count_result.stdout.strip() else []
        while len(stash_lines) > MAX_STASH:
            subprocess.run(["git", "stash", "drop", f"stash@{{{MAX_STASH}}}"], capture_output=True, cwd=cwd, timeout=10)
            stash_lines.pop()
        return f"[git] 已保存工作区快照 (turn {_TURN_COUNTER})"
    except Exception:
        return ""


# ──────────────────────────────────────────────
# Agent
# ──────────────────────────────────────────────

class Agent:
    def __init__(self, provider: LLMProvider, system_prompt: str | None = None):
        self.provider = provider
        self.system_prompt = system_prompt or _DEFAULT_PROMPT
        self.messages: list[dict[str, Any]] = []
        self._last_user_msg: str = ""
        self._fail_streak: int = 0
        self._fail_history: list[dict] = []
        self._pending_todos: list[str] = []
        self._strategy_history: list[dict] = []
        self._same_error_count: int = 0
        self._last_error_type: str = ""
        self._blocked_strategies: list[str] = []
        self._used_tool_ids: set[str] = set()
        self._turn_start_time: float = 0.0
        self._turn_executed_tools: list[tuple[str, bool]] = []

        try:
            from .memory import build_context
            mem = build_context()
            if mem:
                self.system_prompt = (self.system_prompt or _DEFAULT_PROMPT) + "\n\n" + mem
        except Exception:
            pass

        try:
            from .project_map import ProjectMap
            pm = ProjectMap().to_prompt_block()
            if pm:
                self.system_prompt = self.system_prompt + "\n\n" + pm
        except Exception:
            pass

    def run_iteration(self, user_input: str, handler: StreamHandler | None = None) -> None:
        handler = handler or ConsoleHandler()
        self._last_user_msg = user_input
        self.messages.append({"role": "user", "content": user_input})
        overall_start = __import__("time").time()

        turn_count = 0
        while turn_count < 50:
            turn_count += 1
            content_blocks: dict[int, dict] = {}
            tool_use_ids: list[int] = []
            tool_input_buffers: dict[str, str] = {}
            tool_id_to_block_idx: dict[str, int] = {}
            tool_calls_for_history: list[dict] = []
            collected_text = ""
            stop_reason: str | None = None

            handler.on_turn_end()
            self._turn_start_time = __import__("time").time()
            self._turn_executed_tools = []

            self.messages = compress_messages(self.messages, self.system_prompt, self.provider.model)
            self.messages = sanitize_messages(self.messages)
            self._used_tool_ids.update(extract_existing_tool_ids(self.messages))
            _msg_checkpoint = copy.deepcopy(self.messages)

            for event in self.provider.stream_chat(
                system_prompt=self.system_prompt,
                messages=self.messages,
                tools=TOOL_DEFINITIONS,
            ):
                if event.type == "error":
                    self.messages = _msg_checkpoint
                    handler.on_error(f"API 错误: {event.error_msg}")
                    handler.on_complete()
                    return
                elif event.type == "text_delta":
                    handler.on_text(event.delta)
                    collected_text += event.delta
                elif event.type == "thinking_delta":
                    handler.on_thinking(event.delta)
                elif event.type == "tool_use_start":
                    idx = len(content_blocks)
                    content_blocks[idx] = {"type": "tool_use", "id": event.tool_id, "name": event.tool_name, "input": {}}
                    tool_use_ids.append(idx)
                    tool_input_buffers[event.tool_id] = ""
                    tool_id_to_block_idx[event.tool_id] = idx
                    tool_calls_for_history.append({"id": event.tool_id, "type": "function",
                                                    "function": {"name": event.tool_name, "arguments": ""}})
                elif event.type == "tool_use_delta":
                    tid = event.tool_id
                    if tid and tid in tool_input_buffers:
                        tool_input_buffers[tid] += event.partial_json
                elif event.type == "done":
                    stop_reason = event.stop_reason

            handler.on_turn_end()

            if tool_calls_for_history:
                id_map = {}
                for tch in tool_calls_for_history:
                    tid = tch["id"]
                    if tid in self._used_tool_ids:
                        new_id = f"call_{uuid.uuid4().hex[:12]}"
                        id_map[tid] = new_id
                        tch["id"] = new_id
                        self._used_tool_ids.add(new_id)
                    else:
                        self._used_tool_ids.add(tid)
                    raw = tool_input_buffers.get(tid, "")
                    if raw:
                        try:
                            parsed = json.loads(raw)
                            tch["function"]["arguments"] = json.dumps(parsed, ensure_ascii=False)
                        except json.JSONDecodeError:
                            tch["function"]["arguments"] = raw
                if id_map:
                    for idx, cb in list(content_blocks.items()):
                        if isinstance(idx, int) and cb.get("type") == "tool_use":
                            old_id = cb.get("id", "")
                            if old_id in id_map:
                                cb["id"] = id_map[old_id]

            final_text = collected_text or None
            assistant_msg = {"role": "assistant"}
            if tool_calls_for_history:
                assistant_msg["content"] = None
                assistant_msg["tool_calls"] = tool_calls_for_history
            elif final_text:
                assistant_msg["content"] = final_text
            else:
                assistant_msg["content"] = ""
            self.messages.append(assistant_msg)

            stash_report = _stash_snapshot()
            if stash_report:
                handler.on_text(f"\n{stash_report}\n")

            _READONLY = {'read', 'glob', 'grep', 'think', 'web', 'web_search',
                         'ast', 'dep_graph', 'call_chain', 'system_info', 'process'}
            if tool_calls_for_history:
                handler.on_turn_plan(len(tool_calls_for_history))
                tool_results = []
                parallel = [tch for tch in tool_calls_for_history if tch["function"]["name"] in _READONLY]
                sequential = [tch for tch in tool_calls_for_history if tch["function"]["name"] not in _READONLY]
                if parallel:
                    def _exec(tch):
                        fn = tch["function"]; name = fn["name"]
                        try: inp = json.loads(fn["arguments"]) if fn["arguments"] else {}
                        except: inp = {}
                        handler.on_tool_start(name, inp); oc = getattr(handler, 'on_tool_output', None)
                        try: r = _call_with_timeout(lambda: handle_tool_call(name, inp, output_callback=oc), 300)
                        except TimeoutError: r = f"错误:工具'{name}'超时(300s)"
                        except Exception as e: r = f"工具执行错误:{e}"
                        handler.on_tool_result(r); return {"tool_call_id": tch["id"], "_tool_name": name, "content": r}
                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(parallel), 8)) as pool:
                        for fut in concurrent.futures.as_completed({pool.submit(_exec, tch): tch for tch in parallel}):
                            tool_results.append(fut.result())
                for tch in sequential:
                    fn = tch["function"]; name = fn["name"]
                    try: inp = json.loads(fn["arguments"]) if fn["arguments"] else {}
                    except: inp = {}
                    handler.on_tool_start(name, inp); oc = getattr(handler, 'on_tool_output', None)
                    try: r = _call_with_timeout(lambda: handle_tool_call(name, inp, output_callback=oc), 300)
                    except TimeoutError: r = f"错误:工具'{name}'超时(300s)"
                    except Exception as e: r = f"工具执行错误:{e}"
                    handler.on_tool_result(r)
                    tool_results.append({"tool_call_id": tch["id"], "_tool_name": name, "content": r})
                for tr in tool_results:
                    content = tr.get("content") or ""
                    from .tools import classify_tool_result
                    a = classify_tool_result(tr.get("_tool_name", ""), content)
                    # 自动安装缺失依赖
                    if a["error_type"] == "import_error":
                        try:
                            from .tools_deps import extract_missing_modules, install_package
                            missing = extract_missing_modules(content)
                            for mod in missing[:2]:
                                result = install_package(mod)
                                content += f"\n[自动安装] {result}"
                        except Exception:
                            pass
                    tool_succeeded = a["success"]
                    self._turn_executed_tools.append((tr.get("_tool_name", ""), tool_succeeded))
                    if not tool_succeeded:
                        self._fail_streak += 1
                        self._fail_history.append({"tool": tr.get("_tool_name", ""), "error_type": a["error_type"],
                                                    "detail": content[:150], "suggestion": a["suggestion"]})
                        if a["error_type"] == self._last_error_type and a["error_type"] != "ok":
                            self._same_error_count += 1
                        else:
                            self._same_error_count = 1; self._last_error_type = a["error_type"]
                        if self._same_error_count >= 2 and a["error_type"]:
                            bk = f"{tr.get('_tool_name','')}:{a['error_type']}"
                            if bk not in self._blocked_strategies:
                                self._blocked_strategies.append(bk)
                        if self._fail_streak >= 2:
                            self._pending_todos.append(f"[TODO]连续失败{self._fail_streak}次,换方案。")
                    else:
                        self._fail_streak = 0; self._same_error_count = 0; self._last_error_type = ""

                provider_results = self.provider.make_tool_result_messages(tool_results)
                self.messages.extend(provider_results)

                # Turn summary
                elapsed = __import__("time").time() - self._turn_start_time
                total_tools = len(self._turn_executed_tools)
                ok = sum(1 for _, s in self._turn_executed_tools if s)
                fail = total_tools - ok
                summary_parts = []
                if total_tools > 0:
                    summary_parts.append(f"\U0001f4cb 轮次结束: {total_tools} 个工具 | ✅ {ok} 成功")
                    if fail:
                        summary_parts.append(f"❌ {fail} 失败")
                    summary_parts.append(f"⏱ {elapsed:.1f}s")
                if self._pending_todos:
                    summary_parts.append(f"\n  \U0001f4dd {len(self._pending_todos)} 条待办")
                if summary_parts:
                    handler.on_turn_summary(" | ".join(summary_parts))

                reflection_lines = []
                if self._pending_todos:
                    reflection_lines.extend(self._pending_todos[-5:])
                    self._pending_todos.clear()
                if self._blocked_strategies:
                    reflection_lines.append(f"[策略] 以下方案已反复失败，不要再次使用: {', '.join(self._blocked_strategies[-3:])}")
                if self._same_error_count >= 2:
                    reflection_lines.append(f"[反思] 连续 {self._same_error_count} 次都是同一类错误 ({self._last_error_type})，请换一个完全不同的思路。")
                if reflection_lines:
                    self.messages.append({"role": "user", "content": "## 任务状态\n" + "\n".join(f"  {l}" for l in reflection_lines)})

            if tool_calls_for_history and stop_reason in ("tool_use", None):
                continue
            else:
                break

        handler.on_complete()

        total_elapsed = __import__("time").time() - overall_start
        handler.on_text(f"  ⏱ 总耗时 {total_elapsed:.1f}s\n")

        try:
            from .memory import save_turn
            last_assistant = None
            last_tools = None
            for msg in reversed(self.messages):
                if msg.get("role") == "assistant":
                    last_assistant = msg.get("content") or ""
                    last_tools = msg.get("tool_calls")
                    break
            save_turn(user_msg=self._last_user_msg, assistant_text=last_assistant,
                      tool_calls=last_tools, tool_results=None)
        except Exception:
            pass
        self._last_user_msg = ""

    def run_repl(self) -> None:
        handler = ConsoleHandler()
        handler.on_text("\033[1;34m" + "=" * 60 + "\n  Agent CLI - Claude Powered Agent"
                        + "\n  命令: /exit 退出  /clear 清空历史  /help 帮助"
                        + "\n" + "=" * 60 + "\033[0m\n\n")
        while True:
            try:
                user_input = input("\033[1;32m>>> \033[0m").strip()
            except (EOFError, KeyboardInterrupt):
                handler.on_text("\nBye!\n")
                break
            if not user_input:
                continue
            if user_input == "/exit":
                handler.on_text("Bye!\n")
                break
            elif user_input == "/clear":
                self.messages = []
                handler.on_text("\033[33m对话历史已清空\033[0m\n")
                continue
            elif user_input == "/help":
                handler.on_text("命令:\n  /exit   退出\n  /clear  清空对话历史\n  /help   显示帮助\n  /tokens 显示当前对话消息数\n")
                continue
            elif user_input == "/tokens":
                handler.on_text(f"\033[33m当前对话: {len(self.messages)} 条消息\033[0m\n")
                continue
            try:
                self.run_iteration(user_input, handler)
            except KeyboardInterrupt:
                handler.on_text("\n\033[33m⏹ 已中断\033[0m\n")
            except Exception as e:
                handler.on_error(str(e))
