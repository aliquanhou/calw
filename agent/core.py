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
    """Call a function with a timeout + retry. Raises TimeoutError if it exceeds the limit."""
    last_error = None
    for attempt in range(3):  # 3 attempts including first
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
    raise last_error  # type: ignore[misc]


# ──────────────────────────────────────────────
# Stream Handler (output callback interface)
# ──────────────────────────────────────────────

class StreamHandler:
    """Callback interface for streaming output from the agent.

    Override methods to route output to CLI, GUI, or other destinations.
    """

    def on_text(self, text: str) -> None:
        pass

    def on_thinking(self, text: str) -> None:
        pass

    def on_tool_start(self, name: str, input_data: dict) -> None:
        pass

    def on_tool_result(self, result: str) -> None:
        pass

    def on_tool_output(self, text: str) -> None:
        """Called with partial output during long-running tool execution (e.g., bash)."""
        pass

    def on_turn_plan(self, tool_count: int) -> None:
        """Called at the start of agent turn with the expected number of tool calls."""
        pass

    def on_error(self, error: str) -> None:
        pass

    def on_turn_end(self) -> None:
        pass

    def on_complete(self) -> None:
        pass


class ConsoleHandler(StreamHandler):
    """StreamHandler that prints to console with ANSI colors."""

    def on_text(self, text: str) -> None:
        print(text, end="", flush=True)

    def on_thinking(self, text: str) -> None:
        print(f"\033[90m{text}\033[0m", end="", flush=True)

    def on_tool_start(self, name: str, input_data: dict) -> None:
        preview = json.dumps(input_data, ensure_ascii=False)
        preview = preview[:200] + "..." if len(preview) > 200 else preview
        print(f"\033[33m⚡ {name}({preview})\033[0m")

    def on_tool_result(self, result: str) -> None:
        display = result[:300].replace("\n", "\\n")
        if len(result) > 300:
            display += "..."
        print(f"\033[33m  → {display}\033[0m")

    def on_tool_output(self, text: str) -> None:
        print(f"\033[90m{text}\033[0m", end="", flush=True)

    def on_error(self, error: str) -> None:
        print(f"\033[31m错误: {error}\033[0m")

    def on_turn_end(self) -> None:
        print()

    def on_complete(self) -> None:
        pass


# ──────────────────────────────────────────────
# Git stash snapshot (per-agent-turn)
# ──────────────────────────────────────────────

_TURN_COUNTER: int = 0


MAX_STASH = 20


def _stash_snapshot() -> str:
    """Create a single git stash checkpoint per agent turn.

    Uses `git stash push --include-untracked` to snapshot the working tree
    without polluting the commit history. Stashes are listed via `git stash list`.
    Only creates a stash if there are uncommitted changes.
    Auto-cleans old stashes beyond MAX_STASH (20) to prevent unbounded growth.
    """
    import shutil
    import subprocess

    if not shutil.which("git"):
        return ""

    global _TURN_COUNTER
    _TURN_COUNTER += 1

    try:
        cwd = os.getcwd()
        # Check git repo
        repo_check = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, cwd=cwd, timeout=10,
        )
        if repo_check.returncode != 0:
            return ""

        # Only stash if there are changes
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        if not status.stdout.strip():
            return ""

        subprocess.run(
            ["git", "stash", "push", "--include-untracked",
             "-m", f"Claw: auto-snapshot turn {_TURN_COUNTER}"],
            capture_output=True, cwd=cwd, timeout=30,
        )

        # Auto-clean old stashes beyond limit
        count_result = subprocess.run(
            ["git", "stash", "list"],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        stash_lines = count_result.stdout.strip().split("\n") if count_result.stdout.strip() else []
        while len(stash_lines) > MAX_STASH:
            subprocess.run(
                ["git", "stash", "drop", f"stash@{{{MAX_STASH}}}"],
                capture_output=True, cwd=cwd, timeout=10,
            )
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
        # ── Task state machine ──
        self._fail_streak: int = 0           # consecutive tool failures this turn
        self._fail_history: list[dict] = []  # what failed (for reflection)
        self._pending_todos: list[str] = []  # open action items
        # ── Strategy tracking ──
        self._strategy_history: list[dict] = []  # {tool, params_sig, error_type, turn}
        self._same_error_count: int = 0          # same error type consecutive
        self._last_error_type: str = ""           # last error type seen
        self._blocked_strategies: list[str] = []  # strategies to avoid
        # ── Session-level tool_call_id tracking (survives compression) ──
        self._used_tool_ids: set[str] = set()

        # Load memory context
        try:
            from .memory import build_context
            mem = build_context()
            if mem:
                self.system_prompt = (self.system_prompt or _DEFAULT_PROMPT) + "\n\n" + mem
        except Exception:
            pass  # memory not available, continue without

        # Load project map
        try:
            from .project_map import ProjectMap
            pm = ProjectMap().to_prompt_block()
            if pm:
                self.system_prompt = self.system_prompt + "\n\n" + pm
        except Exception:
            pass

    def run_iteration(self, user_input: str, handler: StreamHandler | None = None) -> None:
        """Process a single user input through the agent loop.

        Args:
            user_input: The user's message text.
            handler: Optional StreamHandler for output. Defaults to ConsoleHandler.
        """
        handler = handler or ConsoleHandler()
        self._last_user_msg = user_input
        self.messages.append({"role": "user", "content": user_input})

        turn_count = 0
        while turn_count < 50:  # safety limit
            turn_count += 1
            content_blocks: dict[int, dict] = {}
            tool_use_ids: list[int] = []
            tool_input_buffers: dict[str, str] = {}
            tool_id_to_block_idx: dict[str, int] = {}
            tool_calls_for_history: list[dict] = []
            collected_text = ""
            stop_reason: str | None = None

            handler.on_turn_end()

            # ── Compress context to fit model window ──
            self.messages = compress_messages(self.messages, self.system_prompt, self.provider.model)
            self.messages = sanitize_messages(self.messages)

            # ── Sync _used_tool_ids from actual messages ──
            self._used_tool_ids.update(extract_existing_tool_ids(self.messages))

            # ── Checkpoint: save pre-API-call state for rollback on error ──
            _msg_checkpoint = copy.deepcopy(self.messages)

            # ── Stream from provider ──
            for event in self.provider.stream_chat(
                system_prompt=self.system_prompt,
                messages=self.messages,
                tools=TOOL_DEFINITIONS,
            ):
                if event.type == "error":
                    # Rollback to pre-API-call state to avoid corrupted history
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
                    content_blocks[idx] = {
                        "type": "tool_use",
                        "id": event.tool_id,
                        "name": event.tool_name,
                        "input": {},
                    }
                    tool_use_ids.append(idx)
                    tool_input_buffers[event.tool_id] = ""
                    tool_id_to_block_idx[event.tool_id] = idx

                    tool_calls_for_history.append({
                        "id": event.tool_id,
                        "type": "function",
                        "function": {"name": event.tool_name, "arguments": ""},
                    })

                elif event.type == "tool_use_delta":
                    tid = event.tool_id
                    if tid and tid in tool_input_buffers:
                        tool_input_buffers[tid] += event.partial_json

                elif event.type == "done":
                    stop_reason = event.stop_reason

            handler.on_turn_end()

            # ── Finalize tool call inputs ──
            if tool_calls_for_history:
                # Remap duplicate tool_call_ids (DeepSeek may reuse IDs across turns).
                # Uses session-level set to survive message compression/sanitization.
                id_map: dict[str, str] = {}
                for tch in tool_calls_for_history:
                    tid = tch["id"]
                    if tid in self._used_tool_ids:
                        new_id = f"call_{uuid.uuid4().hex[:12]}"
                        id_map[tid] = new_id
                        tch["id"] = new_id
                        self._used_tool_ids.add(new_id)
                    else:
                        self._used_tool_ids.add(tid)
                    # Parse arguments from stream buffer (uses original tid before remap)
                    raw = tool_input_buffers.get(tid, "")
                    if raw:
                        try:
                            parsed = json.loads(raw)
                            tch["function"]["arguments"] = json.dumps(parsed, ensure_ascii=False)
                        except json.JSONDecodeError:
                            tch["function"]["arguments"] = raw

                # Update content_blocks with remapped IDs
                if id_map:
                    for idx, cb in list(content_blocks.items()):
                        if isinstance(idx, int) and cb.get("type") == "tool_use":
                            old_id = cb.get("id", "")
                            if old_id in id_map:
                                cb["id"] = id_map[old_id]

            # ── Build assistant message ──
            # Note: When tool_calls is present, content MUST be null
            # (OpenAI/DeepSeek requirement — non-null content + tool_calls causes 400)
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

            # ── Git stash snapshot before executing tool calls ──
            stash_report = _stash_snapshot()
            if stash_report:
                handler.on_text(f"\n{stash_report}\n")

            # ── Execute tools ──
            # Execute tool calls regardless of stop_reason
            # (some APIs may not set finish_reason="tool_calls" in streaming)
            # ── Execute tools (parallel for read-only tools) ──
            _READONLY = {'read','glob','grep','think','web','web_search','ast','dep_graph','call_chain','system_info','process'}
            if tool_calls_for_history:
                handler.on_turn_plan(len(tool_calls_for_history))
                tool_results: list[dict] = []
                parallel = [tch for tch in tool_calls_for_history if tch["function"]["name"] in _READONLY]
                sequential = [tch for tch in tool_calls_for_history if tch["function"]["name"] not in _READONLY]
                if parallel:
                    def _exec(tch: dict) -> dict:
                        fn=tch["function"];name=fn["name"]
                        try:inp=json.loads(fn["arguments"])if fn["arguments"]else{}
                        except:inp={}
                        handler.on_tool_start(name,inp);oc=getattr(handler,'on_tool_output',None)
                        try:r=_call_with_timeout(lambda:handle_tool_call(name,inp,output_callback=oc),300)
                        except TimeoutError:r=f"错误:工具'{name}'超时(300s)"
                        except Exception as e:r=f"工具执行错误:{e}"
                        handler.on_tool_result(r);return{"tool_call_id":tch["id"],"_tool_name":name,"content":r}
                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(parallel),8))as pool:
                        for fut in concurrent.futures.as_completed({pool.submit(_exec,tch):tch for tch in parallel}):
                            tool_results.append(fut.result())
                for tch in sequential:
                    fn=tch["function"];name=fn["name"]
                    try:inp=json.loads(fn["arguments"])if fn["arguments"]else{}
                    except:inp={}
                    handler.on_tool_start(name,inp);oc=getattr(handler,'on_tool_output',None)
                    try:r=_call_with_timeout(lambda:handle_tool_call(name,inp,output_callback=oc),300)
                    except TimeoutError:r=f"错误:工具'{name}'超时(300s)"
                    except Exception as e:r=f"工具执行错误:{e}"
                    handler.on_tool_result(r);tool_results.append({"tool_call_id":tch["id"],"_tool_name":name,"content":r})
                for tr in tool_results:
                    content=tr.get("content")or""
                    from.tools import classify_tool_result
                    a=classify_tool_result(tr.get("_tool_name",""),content)
                    if not a["success"]:
                        self._fail_streak+=1;self._fail_history.append({"tool":tr.get("_tool_name",""),"error_type":a["error_type"],"detail":content[:150],"suggestion":a["suggestion"]})
                        if a["error_type"]==self._last_error_type and a["error_type"]!="ok":self._same_error_count+=1
                        else:self._same_error_count=1;self._last_error_type=a["error_type"]
                        if self._same_error_count>=2 and a["error_type"]:
                            bk=f"{tr.get('_tool_name','')}:{a['error_type']}"
                            if bk not in self._blocked_strategies:self._blocked_strategies.append(bk)
                        if self._fail_streak>=2:self._pending_todos.append(f"[TODO]连续失败{self._fail_streak}次,换方案。")
                    else:self._fail_streak=0;self._same_error_count=0;self._last_error_type=""
                # ── All tools executed: append results ONCE, outside for-tch loop ──
                provider_results = self.provider.make_tool_result_messages(tool_results)
                self.messages.extend(provider_results)

                # ── Inject strategy reflection when stuck ──
                reflection_lines = []
                if self._pending_todos:
                    reflection_lines.extend(self._pending_todos[-5:])
                    self._pending_todos.clear()

                if self._blocked_strategies:
                    reflection_lines.append(
                        f"[策略] 以下方案已反复失败，不要再次使用: {', '.join(self._blocked_strategies[-3:])}"
                    )

                if self._same_error_count >= 2:
                    reflection_lines.append(
                        f"[反思] 连续 {self._same_error_count} 次都是同一类错误 ({self._last_error_type})，"
                        f"请换一个完全不同的思路。"
                    )

                if reflection_lines:
                    self.messages.append({
                        "role": "user",
                        "content": "## 任务状态\n" + "\n".join(f"  {l}" for l in reflection_lines),
                    })

            # ── Decide whether to continue or return ──
            if tool_calls_for_history and stop_reason in ("tool_use", None):
                continue  # let model process tool results and continue
            else:
                break  # model finished - return to user

        handler.on_complete()

        # ── Persist to memory ──
        try:
            from .memory import save_turn
            last_assistant = None
            last_tools = None
            for msg in reversed(self.messages):
                if msg.get("role") == "assistant":
                    last_assistant = msg.get("content") or ""
                    last_tools = msg.get("tool_calls")
                    break
            save_turn(
                user_msg=self._last_user_msg,
                assistant_text=last_assistant,
                tool_calls=last_tools,
                tool_results=None,
            )
        except Exception:
            pass  # memory save is best-effort

        self._last_user_msg = ""

    # ── REPL (legacy) ──

    def run_repl(self) -> None:
        """Run the REPL (Read-Eval-Print Loop)."""
        handler = ConsoleHandler()
        handler.on_text(
            "\033[1;34m" + "=" * 60
            + "\n  Agent CLI - Claude Powered Agent"
            + "\n  命令: /exit 退出  /clear 清空历史  /help 帮助"
            + "\n" + "=" * 60 + "\033[0m\n\n"
        )
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
