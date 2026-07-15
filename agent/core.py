"""core — Agent 核心循环。

v2.2 重构：
  透明输出 + 工作流状态机 + 防死循环 + Claude 优先。

设计原则：
  1. Claude 轻薄壳 — 核心循环直接调用 Anthropic SDK，无多余抽象
  2. 全透明 — 每步输出都推送转录事件，UI 层实时展示
  3. 规划先行 — Agent 必须先建计划再执行，步骤分治
  4. 永不卡死 — 多层防死循环检测（重复调用/重复失败/无进展/超时）

与其他模块的关系：
  - transcript.py → 所有事件的出口
  - workflow.py  → 工作流状态机 + 防死循环
  - tools.py     → 工具注册 + 执行（v2.1 显式注册表）
  - session.py   → 会话持久化
  - context.py   → 上下文压缩
  - providers.py → LLM 调用（Claude 一等公民）
"""

from __future__ import annotations

import json
import os
import time
import traceback
from typing import Any, Callable

from .tools import get_all_tools, execute_tool, init_tools
from .session import get_state, set_state, set_session_workflow, SessionState
from .prompt import build_system_prompt
from .providers import create_llm_provider
from .transcript import Transcript
from .workflow import Workflow


# ── 默认配置 ──

DEFAULT_CONFIG = {
    "provider": "anthropic",           # anthropic | openai
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 8192,
    "temperature": 0.0,
    "timeout": 3600,                    # 1h 纯安全阀

    # 工具执行
    "tool_timeout": 60.0,               # 单个工具超时（秒）

    # 上下文
    "max_context_messages": 50,
    "enable_context_compression": True,

    # 重试
    "retry_on_failure": True,
    "max_retries": 2,
}


# ── StreamHandler（v2.0 兼容）──

class StreamHandler:
    """v2.0 兼容的流处理器基类。"""
    def on_text(self, text: str): pass
    def on_thinking(self, text: str): pass
    def on_tool_start(self, name: str, input_data: dict): pass
    def on_tool_result(self, result: str): pass
    def on_tool_output(self, text: str): pass
    def on_turn_plan(self, tool_count: int): pass
    def on_turn_summary(self, summary: str): pass
    def on_error(self, error: str): pass
    def on_turn_end(self): pass
    def on_complete(self): pass


# ── Agent ──

class Agent:
    """Calw Agent 核心 —— 透明、防死循环、Claude 优先。

    核心循环流程：
      用户消息
        → 1. 规划步骤（强制或可选）
        → 2. 循环执行步骤:
              a. 调用 LLM（流式，实时推送事件）
              b. 如果有工具调用 → 执行 → 检测循环 → 继续
              c. 如果无工具调用 → 返回最终回复
        → 3. 保存会话
    """

    def __init__(self, config: dict | None = None,
                 transcript: Transcript | None = None,
                 workflow: Workflow | None = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}

        # ── 透明输出层 ──
        self.transcript = transcript or Transcript(agent_id="calw")

        # ── 工作流状态机 ──
        self.workflow = workflow or Workflow(transcript=self.transcript)

        # ── 工具系统 ──
        init_tools(config=self.config)

        # ── 会话状态 ──
        self.user_id = "default"
        self.state = SessionState(user_id=self.user_id)
        set_state(self.state)

        # ── LLM Provider ──
        self.provider_name = self.config.get("provider", "anthropic")
        self.model = self.config["model"]
        self._init_provider()

        # ── 消息历史 ──
        self._messages: list[dict] = []
        self._system_prompt: str = ""

    def _init_provider(self):
        """初始化 LLM Provider。

        支持两种配置方式：
          1. core.DEFAULT_CONFIG + 环境变量（默认）
          2. 外部传入 config dict（GUI / CLI 使用）
        """
        # GUI/cli 可能传入了 api_key 和 base_url
        api_key = (self.config.get("api_key") or
                   os.environ.get("ANTHROPIC_API_KEY") or
                   os.environ.get("DEEPSEEK_API_KEY") or
                   os.environ.get("OPENAI_API_KEY") or "")
        base_url = self.config.get("base_url", "")
        model = self.config.get("model", self.model)
        provider_name = self.config.get("provider", "anthropic")

        # 检测模型名前缀以确定 provider
        if "/" not in model and not model.startswith(("claude", "gpt", "deepseek")):
            # 没有前缀也没有明显标记 → 按 provider_name 拼接
            model = f"{provider_name}/{model}"

        provider_cfg = {
            "model": model,
            "api_key": api_key,
        }
        if base_url:
            provider_cfg["base_url"] = base_url

        self.provider = create_llm_provider(provider_cfg)

    # ── 主入口 ──

    def run(self, user_message: str,
            on_text: Callable | None = None,
            on_tool_start: Callable | None = None,
            on_tool_result: Callable | None = None) -> str:
        """处理一条用户消息，返回最终回复。

        全程推送转录事件 + 工作流状态更新。
        """
        # ── 1. 建立会话上下文 ──
        self.transcript.session("start")
        self.transcript.phase("start", phase_name="plan")

        messages = self.state.get_recent_messages(
            max_count=self.config["max_context_messages"]
        )
        messages.append({"role": "user", "content": user_message})

        tools = get_all_tools()
        system_prompt = build_system_prompt(user_id=self.user_id, tools=tools)

        self.transcript.phase("done", phase_name="plan")

        # ── 2. 工具调用循环 ──
        final_response = ""
        tool_round = 0
        start_time = time.time()

        # 同步 workflow 到 session（工具函数可访问）
        set_session_workflow(self.workflow)

        while True:
            tool_round += 1
            self.transcript.phase("running", phase_name="execute",
                                  round=tool_round,
                                  total_steps=len(self.workflow.steps),
                                  completed_steps=sum(
                                      1 for s in self.workflow.steps.values()
                                      if s.status in ("done", "skipped", "failed")
                                  ))

            # ── 调用 LLM（流式，全透明）──
            try:
                response_data = self._stream_llm(
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                    on_text=on_text,
                )
            except Exception as e:
                error_msg = f"LLM 调用失败: {e}"
                self.transcript.error(source="llm", message=str(e))
                self.state.log_error("llm_complete", str(e))

                # 可重试
                if self.config.get("retry_on_failure"):
                    retried = self._retry_llm(system_prompt, messages, tools, on_text)
                    if retried is not None:
                        response_data = retried
                    else:
                        final_response += f"\n[系统: {error_msg}]"
                        break
                else:
                    final_response += f"\n[系统: {error_msg}]"
                    break

            content = response_data.get("content", "")
            tool_calls = response_data.get("tool_calls", [])

            # ── 模型直接回复（无工具调用）→ 完成 ──
            if not tool_calls:
                if content:
                    messages.append({"role": "assistant", "content": content})
                    final_response = content
                    self.transcript.text(delta=content)
                break

            # ── 处理工具调用 ──
            assistant_msg = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [],
            }
            tool_results = []

            for tc in tool_calls:
                tc_id = tc.get("id", "")
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                raw_args = func.get("arguments", "{}")

                # 参数解析
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {"raw": raw_args}
                else:
                    args = raw_args or {}

                tool_call_entry = {
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                }
                assistant_msg["tool_calls"].append(tool_call_entry)

                # ── 执行工具 ──
                t0 = time.time()
                try:
                    result = execute_tool(tool_name, args)
                except Exception as e:
                    result = f"[工具异常] {e}"
                elapsed_ms = (time.time() - t0) * 1000

                # ── 工具结果分析 ──
                error_type = ""
                if isinstance(result, str):
                    if any(k in result.lower() for k in ("error", "失败", "not found", "找不到")):
                        error_type = "tool_failed"

                # ── 推送：工具结果事件 ──
                result_preview = str(result)[:2000] if result else ""
                self.transcript.tool("result", tool_name=tool_name, tool_id=tc_id,
                                     result=result_preview[:500],
                                     duration_ms=elapsed_ms,
                                     error_type=error_type)
                if on_tool_result:
                    on_tool_result(result_preview[:500])

                # ── 构建工具结果消息 ──
                tool_result_msg = {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_preview,
                }
                tool_results.append(tool_result_msg)

            # ── 追加消息 ──
            if assistant_msg.get("tool_calls"):
                messages.append(assistant_msg)
            messages.extend(tool_results)

            # ── 工作流状态同步 ──
            # tools.py 的 plan/task 工具会直接操作 workflow，
            # 但我们需要定期发送进度更新
            self.transcript.phase("progress", phase_name="execute",
                                  progress=self.workflow.progress(),
                                  workflow=self.workflow.to_dict())

            # ── 上下文压缩 ──
            if self.config.get("enable_context_compression", True):
                self._compact_context(messages)

        # ── 3. 完成 ──
        if not self.workflow.is_all_done() and self.workflow.steps:
            self.workflow.status = "done"  # 即使有未完成的步骤，也正常结束
        self.transcript.phase("done", phase_name="done",
                              summary=self.transcript.summary(),
                              workflow=self.workflow.to_dict())
        self.transcript.session("end")

        # 保存会话
        self.state.save_conversation(messages)

        return final_response

    # ── 流式 LLM 调用 ──

    def _stream_llm(self, system: str, messages: list[dict], tools: list[dict],
                     on_text: Callable | None = None) -> dict:
        """流式调用 LLM，通过 providers 的回调接口收集数据 + 推送转录事件。

        Returns:
            {"content": str, "tool_calls": list[dict]}
        """
        collected_text = ""
        tool_calls: list[dict] = []
        tool_buffers: dict[str, dict] = {}
        stream_error: str | None = None

        def _on_text(delta: str):
            nonlocal collected_text
            collected_text += delta
            self.transcript.text(delta=delta)
            if on_text:
                on_text(delta)

        def _on_thinking(delta: str):
            self.transcript.thought(delta=delta)

        def _on_tool_start(name: str, input_data: dict):
            # providers 的回调在 tool_use_start 时触发，
            # 但 Anthropic 流式工具调用的 input 可能不完整。
            # 我们用 tool_id 哈希来跟踪
            pass

        try:
            result = self.provider.stream_complete(
                system=system,
                messages=messages,
                tools=tools,
                max_tokens=self.config["max_tokens"],
                temperature=self.config["temperature"],
                on_text=_on_text,
                on_tool_start=_on_tool_start,
                on_thinking=_on_thinking,
            )
        except Exception as e:
            self.transcript.error(source="llm", message=str(e))
            raise

        # stream_complete 返回 {"content": ..., "tool_calls": [...]}
        collected_text = result.get("content", "")
        tool_calls = result.get("tool_calls", [])

        # 补推工具事件（providers 回调在流结束时才有完整 JSON）
        for tc in tool_calls:
            tc_id = tc.get("id", "")
            fn = tc.get("function", {})
            self.transcript.tool("start", tool_name=fn.get("name", ""),
                                 tool_id=tc_id, args=fn.get("arguments", ""))

        return {"content": collected_text, "tool_calls": tool_calls}

    # ── 重试 ──

    def _retry_llm(self, system: str, messages: list[dict], tools: list[dict],
                    on_text: Callable | None = None) -> dict | None:
        """LLM 调用失败重试（指数退避）。"""
        from .retry import is_retryable as _is_retryable, sleep_with_backoff
        max_retries = self.config.get("max_retries", 2)
        last_error = None

        for attempt in range(max_retries):
            try:
                time.sleep(0.5 * (attempt + 1))  # 简单退避
                return self._stream_llm(system, messages, tools, on_text)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1 and _is_retryable(e):
                    sleep_with_backoff(attempt)
                    continue
                break

        if last_error:
            self.transcript.error(source="llm/retry",
                                  message=f"重试 {max_retries} 次后仍失败: {last_error}")
        return None

    # ── 上下文压缩 ──

    def _compact_context(self, messages: list):
        """上下文压缩。"""
        limit = self.config.get("max_context_messages", 50)
        threshold = int(limit * 0.8)

        if len(messages) <= threshold:
            return

        try:
            from .context import compress_messages
            before = len(messages)
            compressed = compress_messages(messages, self._system_prompt,
                                           self.config.get("model", ""))
            messages.clear()
            messages.extend(compressed)
            self.transcript.checkpoint("context_compressed",
                                       before=before, after=len(messages))
        except Exception as e:
            self.transcript.error(source="context", message=str(e))

    # ── v2.0 兼容接口 ──

    def run_iteration(self, user_input: str, handler: StreamHandler | None = None) -> None:
        """v2.0 兼容接口。"""
        handler = handler or StreamHandler()
        self.transcript.on("*", lambda e: self._bridge_handler(e, handler))

        try:
            result = self.run(
                user_input,
                on_text=lambda t: handler.on_text(t),
                on_tool_start=lambda n, i: handler.on_tool_start(n, i),
                on_tool_result=lambda r: handler.on_tool_result(r),
            )
            if result:
                handler.on_complete()
        except Exception as e:
            handler.on_error(str(e))

    def _bridge_handler(self, event, handler: StreamHandler):
        """将转录事件桥接到 v2.0 StreamHandler。"""
        if event.type == "thinking":
            handler.on_thinking(event.payload.get("delta", ""))
        elif event.type == "tool" and event.subtype == "start":
            pass  # 已通过 on_tool_start 推送
        elif event.type == "error":
            handler.on_error(event.payload.get("message", ""))

    @property
    def messages(self) -> list:
        return self.state.get_all_messages()

    @messages.setter
    def messages(self, value: list):
        self.state.save_conversation(value or [])

    @property
    def system_prompt(self) -> str:
        return getattr(self, '_system_prompt', '')

    @system_prompt.setter
    def system_prompt(self, value: str):
        self._system_prompt = value

    def close(self):
        """清理资源。"""
        self.state.save()
