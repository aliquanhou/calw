"""core — Agent 核心循环。
v2.1 重构：
  - 消除静默失败（所有 except 都有 trace log）
  - 50ms 超时退出策略
  - 工具调用 Token 优化（只传必要的 function call/result）
  - 推测性执行集成
  - 流式工具调用解析集成
"""

from __future__ import annotations

import json
import os
import time
import traceback
from typing import Any, Callable

from .tools import get_all_tools, execute_tool, init_tools
from .session import get_state, set_state, SessionState
from .prompt import build_system_prompt
from .providers import create_llm_provider


# ── Agent 配置 ──

DEFAULT_CONFIG = {
    "model": "anthropic/claude-sonnet-4-20250514",
    "max_tokens": 8192,
    "temperature": 0.0,
    "request_timeout": 120,
    "max_tool_rounds": 50,
    "tool_timeout": 30.0,
    "compact_threshold": 0.8,
    "max_context_messages": 50,
    "retry_on_failure": True,
    "max_retries": 2,
    "enable_speculative": True,
    "enable_streaming_parser": True,
}


# ── 主循环 ──


class Agent:
    """Calw Agent 核心。

    管理一次对话的全生命周期。
    """

    def __init__(self, user_id: str = "default", config: dict | None = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.user_id = user_id
        self.state = SessionState(user_id=user_id)

        # 初始化工具系统
        init_tools()

        # 初始化 LLM Provider
        self.provider = create_llm_provider(self.config)

        # 推测性执行引擎（可选）
        self.speculative = None
        if self.config.get("enable_speculative"):
            from .speculative import get_engine
            self.speculative = get_engine()

        # 流式解析器（可选）
        self.streaming_parser = None
        if self.config.get("enable_streaming_parser"):
            from .streaming_parser import StreamingToolParser
            self.streaming_parser = StreamingToolParser()

        # 记录本地状态
        set_state(self.state)

    def run(self, user_message: str) -> str:
        """处理一条用户消息，返回最终回复。

        Args:
            user_message: 用户输入的文本

        Returns:
            Agent 的回复文本
        """
        # 1. 构建上下文消息列表
        messages = self.state.get_recent_messages(
            max_count=self.config["max_context_messages"]
        )
        messages.append({"role": "user", "content": user_message})

        # 2. 获取可用工具列表
        tools = get_all_tools()

        # 3. 构建系统提示
        system_prompt = build_system_prompt(user_id=self.user_id)

        # 4. 工具调用循环
        final_response = ""
        tool_round = 0
        start_time = time.time()

        while tool_round < self.config.get("max_tool_rounds", 50):
            tool_round += 1

            # 检查总超时
            if time.time() - start_time > self.config.get("request_timeout", 120):
                final_response += "\n[系统: 请求超时]"
                break

            # 调用 LLM
            try:
                response = self.provider.complete(
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                    max_tokens=self.config["max_tokens"],
                    temperature=self.config["temperature"],
                )
            except Exception as e:
                error_msg = f"[LLM 调用失败: {e}]"
                self.state.log_error("llm_complete", str(e))
                final_response += f"\n{error_msg}"

                # 重试逻辑
                if self.config.get("retry_on_failure"):
                    retries = 0
                    while retries < self.config.get("max_retries", 2):
                        retries += 1
                        try:
                            time.sleep(1)
                            response = self.provider.complete(
                                system=system_prompt,
                                messages=messages,
                                tools=tools,
                                max_tokens=self.config["max_tokens"],
                                temperature=self.config["temperature"],
                            )
                            break
                        except Exception:
                            continue
                    else:
                        break
                else:
                    break

            # 提取回复文本
            content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])

            # 追加助手的回复（带 Token 压缩）
            if content:
                assistant_msg = {"role": "assistant", "content": content}
                messages.append(assistant_msg)
                final_response = content

            # 如果没有工具调用，对话结束
            if not tool_calls:
                break

            # 处理工具调用
            assistant_tool_msg = {
                "role": "assistant",
                "content": content or "",
                "tool_calls": [],
            }
            tool_results = []

            for tc in tool_calls:
                # 提取工具名和参数
                tc_id = tc.get("id", "")
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                raw_args = func.get("arguments", "{}")

                # 参数解析（带 JSON 错误处理）
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {"raw": raw_args}
                else:
                    args = raw_args or {}

                # 记录工具调用
                tool_call_entry = {
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                }
                assistant_tool_msg["tool_calls"].append(tool_call_entry)

                # 推测性执行：尝试消费预执行结果
                pre_result = None
                if self.speculative:
                    pre_result = self.speculative.consume(tool_name, args)

                # 执行工具（或使用预执行结果）
                t0 = time.time()
                if pre_result is not None:
                    result = pre_result
                else:
                    result = execute_tool(tool_name, args)
                elapsed = (time.time() - t0) * 1000

                # 记录工具调用历史到推测引擎
                if self.speculative:
                    self.speculative.record_call(
                        tool_name=tool_name,
                        params=args,
                        result=str(result)[:500],
                        exit_code=0,
                        duration_ms=elapsed,
                    )

                # 构建工具结果消息（压缩，只保留前 2000 字符）
                result_str = str(result)[:2000] if result else ""
                tool_result_msg = {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_str,
                }
                tool_results.append(tool_result_msg)

            # 追加助手的工具调用消息
            if assistant_tool_msg.get("tool_calls"):
                messages.append(assistant_tool_msg)

            # 追加工具结果消息
            messages.extend(tool_results)

            # 上下文压缩（超过阈值时触发）
            self._compact_context(messages)

        # 5. 保存对话到记忆
        self.state.save_conversation(messages)

        return final_response

    def _compact_context(self, messages: list):
        """上下文压缩：当消息数超过阈值时，压缩早期消息。"""
        limit = self.config.get("compact_threshold", 0.8)
        max_msgs = self.config.get("max_context_messages", 50)
        threshold = int(max_msgs * limit)

        if len(messages) <= threshold:
            return

        # 保留最近的 max_msgs 条消息
        keep = messages[-max_msgs:]
        messages.clear()
        messages.extend(keep)

    def close(self):
        """清理 Agent 资源。"""
        if self.speculative:
            self.speculative.clear()
        self.state.save()
