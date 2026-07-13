"""providers — LLM Provider 抽象层。

v2.1 重构：
  - 统一所有 Provider 的接口：complete() 返回 {"content": str, "tool_calls": list}
  - stream_complete() 流式接口：逐 token 回调 on_text/on_tool_start
  - 支持 Anthropic、OpenAI、Gemini、Ollama
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable


# ── 流式事件类型 ──

STREAM_TEXT = "text"
STREAM_TOOL_START = "tool_start"
STREAM_TOOL_DELTA = "tool_delta"
STREAM_DONE = "done"
STREAM_ERROR = "error"


# ── Provider 接口 ──


class LLMProvider:
    """LLM Provider 基类。"""

    def complete(self, system: str, messages: list[dict],
                 tools: list[dict] | None = None,
                 max_tokens: int = 8192,
                 temperature: float = 0.0) -> dict:
        raise NotImplementedError

    def stream_complete(self, system: str, messages: list[dict],
                        tools: list[dict] | None = None,
                        max_tokens: int = 8192,
                        temperature: float = 0.0,
                        on_text: Callable[[str], None] | None = None,
                        on_tool_start: Callable[[str, dict], None] | None = None,
                        on_thinking: Callable[[str], None] | None = None) -> dict:
        """流式生成，逐 token 回调。

        Args:
            on_text: 实时文本回调（每次收到一段文本就调用）
            on_tool_start: 工具调用开始时回调 (name, input_data)
            on_thinking: 思考过程回调（Anthropic thinking block）

        Returns:
            {"content": str, "tool_calls": list[dict]}
        """
        raise NotImplementedError

    @property
    def name(self) -> str:
        return self.__class__.__name__


# ── Anthropic Provider ──


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API Provider。"""
    models = ["claude-opus-4-7", "claude-sonnet-4-20250514", "claude-sonnet-4-6", "claude-haiku-4-5"]
    default_model = "claude-sonnet-4-20250514"

    def __init__(self, config: dict):
        self.api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = config.get("model", "claude-sonnet-4-20250514")
        self.base_url = config.get("base_url", "https://api.anthropic.com/v1")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key, base_url=self.base_url)
            except ImportError:
                raise RuntimeError("anthropic 库未安装: pip install anthropic>=0.49.0")
        return self._client

    def _to_anthropic_messages(self, messages: list[dict]) -> list[dict]:
        """将通用消息格式转为 Anthropic content-block 格式。

        确保 tool_result 与 tool_use 正确配对，
        跳过没有对应 tool_use 的孤立 tool_result。
        """
        # 第一遍：收集所有 tool_use ID
        tool_use_ids: set[str] = set()
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tid = tc.get("id", "")
                    if tid:
                        tool_use_ids.add(tid)

        result = []
        for msg in messages:
            role = msg["role"]
            raw_content = msg.get("content")
            tool_calls = msg.get("tool_calls")

            if role == "assistant" and tool_calls:
                # Assistant: 文本 + tool_use blocks 合并
                blocks = []
                if raw_content and isinstance(raw_content, str) and raw_content.strip():
                    blocks.append({"type": "text", "text": raw_content})
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    try:
                        inp = json.loads(fn.get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        inp = {}
                    tid = tc.get("id", "")
                    blocks.append({
                        "type": "tool_use",
                        "id": tid,
                        "name": fn.get("name", ""),
                        "input": inp,
                    })
                if blocks:
                    result.append({"role": "assistant", "content": blocks})

            elif role == "tool":
                # Tool result: 只有有关联 tool_use 时才保留
                tool_call_id = msg.get("tool_call_id", "")
                if tool_call_id and tool_call_id in tool_use_ids:
                    result.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": str(raw_content or ""),
                        }],
                    })

            elif role == "user":
                result.append({"role": "user", "content": raw_content or ""})

            elif role == "assistant" and raw_content:
                result.append({"role": "assistant", "content": raw_content})

        return result

    def complete(self, system, messages, tools=None, max_tokens=8192, temperature=0.0):
        client = self._get_client()
        try:
            kwargs = {"model": self.model, "system": system,
                      "messages": self._to_anthropic_messages(messages),
                      "max_tokens": max_tokens, "temperature": temperature}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = {"type": "auto"}
            response = client.messages.create(**kwargs)
            content = ""
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({"id": block.id, "type": "function",
                                       "function": {"name": block.name, "arguments": json.dumps(block.input)}})
            return {"content": content, "tool_calls": tool_calls}
        except Exception as e:
            raise RuntimeError(f"Anthropic API 调用失败: {e}") from e

    def stream_complete(self, system, messages, tools=None, max_tokens=8192, temperature=0.0,
                        on_text=None, on_tool_start=None, on_thinking=None):
        """流式生成：逐 token 回调 on_text，逐工具回调 on_tool_start。"""
        client = self._get_client()
        try:
            kwargs = {"model": self.model, "system": system,
                      "messages": self._to_anthropic_messages(messages),
                      "max_tokens": max_tokens, "temperature": temperature}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = {"type": "auto"}

            content = ""
            tool_calls = []
            current_tool_id = None
            current_tool_name = None
            current_tool_input_parts = []

            with client.messages.create(**kwargs, stream=True) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            content += delta.text
                            if on_text:
                                on_text(delta.text)
                        elif delta.type == "thinking_delta":
                            if on_thinking:
                                on_thinking(delta.thinking)
                        elif delta.type == "input_json_delta":
                            if current_tool_id:
                                current_tool_input_parts.append(delta.partial_json)

                    elif event.type == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            current_tool_id = block.id
                            current_tool_name = block.name
                            current_tool_input_parts = []
                            if on_tool_start:
                                on_tool_start(block.name, {})

                    elif event.type == "content_block_stop":
                        if current_tool_id:
                            raw = "".join(current_tool_input_parts)
                            try:
                                parsed = json.loads(raw) if raw else {}
                            except json.JSONDecodeError:
                                parsed = {}
                            tool_calls.append({
                                "id": current_tool_id,
                                "type": "function",
                                "function": {"name": current_tool_name, "arguments": json.dumps(parsed)},
                            })
                            current_tool_id = None
                            current_tool_name = None
                            current_tool_input_parts = []

            return {"content": content, "tool_calls": tool_calls}

        except Exception as e:
            if on_text:
                on_text(f"\n[错误: {e}]")
            raise RuntimeError(f"Anthropic API 流式调用失败: {e}") from e


# ── OpenAI Provider ──


class OpenAIProvider(LLMProvider):
    """OpenAI / 兼容 API Provider。"""
    models = ["gpt-4o", "gpt-4o-mini", "deepseek-chat", "deepseek-reasoner"]
    default_model = "gpt-4o"

    def __init__(self, config: dict):
        self.api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        self.model = config.get("model", "gpt-4o")
        self.base_url = config.get("base_url")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except ImportError:
                raise RuntimeError("openai 库未安装: pip install openai>=1.0.0")
        return self._client

    def _build_messages(self, system, messages):
        msgs = [{"role": "system", "content": system}]
        # 检查工具调用 ID 一致性：收集所有 assistant tool_call IDs
        tool_call_ids: set[str] = set()
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tid = tc.get("id", "")
                    if tid:
                        tool_call_ids.add(tid)

        for msg in messages:
            role = msg["role"]
            c = msg.get("content")
            if role == "tool":
                tid = msg.get("tool_call_id", "")
                if tid and tid not in tool_call_ids:
                    continue  # 跳过孤立 tool_result
                msgs.append({"role": "tool", "tool_call_id": tid, "content": str(c or "")})
            elif role == "assistant" and msg.get("tool_calls"):
                msgs.append({"role": "assistant", "content": c if c else None, "tool_calls": msg["tool_calls"]})
            else:
                msgs.append({"role": role, "content": c if c else ""})
        return msgs

    def complete(self, system, messages, tools=None, max_tokens=8192, temperature=0.0):
        client = self._get_client()
        try:
            msgs = self._build_messages(system, messages)
            kwargs = {"model": self.model, "messages": msgs, "max_tokens": max_tokens, "temperature": temperature}
            if tools:
                kwargs["tools"] = tools
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            content = choice.message.content or ""
            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls.append({"id": tc.id, "type": "function",
                                       "function": {"name": tc.function.name, "arguments": tc.function.arguments}})
            return {"content": content, "tool_calls": tool_calls}
        except Exception as e:
            raise RuntimeError(f"OpenAI API 调用失败: {e}") from e

    def stream_complete(self, system, messages, tools=None, max_tokens=8192, temperature=0.0,
                        on_text=None, on_tool_start=None, on_thinking=None):
        """流式生成：逐 chunk 回调 on_text，逐工具回调 on_tool_start。"""
        client = self._get_client()
        try:
            msgs = self._build_messages(system, messages)
            kwargs = {"model": self.model, "messages": msgs, "max_tokens": max_tokens,
                      "temperature": temperature, "stream": True}
            if tools:
                kwargs["tools"] = tools

            content = ""
            tool_calls = []
            tool_call_buffers: dict[int, dict] = {}

            for chunk in client.chat.completions.create(**kwargs):
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # 文本增量
                if delta.content:
                    content += delta.content
                    if on_text:
                        on_text(delta.content)

                # 工具调用增量
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_buffers:
                            tool_call_buffers[idx] = {
                                "id": tc_delta.id or "",
                                "name": tc_delta.function.name if tc_delta.function else "",
                                "arguments": "",
                            }
                            if on_tool_start and tc_delta.function and tc_delta.function.name:
                                on_tool_start(tc_delta.function.name, {})
                        if tc_delta.function and tc_delta.function.arguments:
                            tool_call_buffers[idx]["arguments"] += tc_delta.function.arguments

            # 收集完整的工具调用
            for idx in sorted(tool_call_buffers.keys()):
                buf = tool_call_buffers[idx]
                raw_args = buf["arguments"]
                try:
                    parsed = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    parsed = {}
                tool_calls.append({
                    "id": buf["id"],
                    "type": "function",
                    "function": {"name": buf["name"], "arguments": json.dumps(parsed)},
                })

            return {"content": content, "tool_calls": tool_calls}

        except Exception as e:
            if on_text:
                on_text(f"\n[错误: {e}]")
            raise RuntimeError(f"OpenAI API 流式调用失败: {e}") from e


# ── Factory ──


def create_llm_provider(config: dict) -> LLMProvider:
    """根据配置创建 LLM Provider。"""
    model = config.get("model", "")
    if model.startswith("anthropic/") or "claude" in model.lower():
        clean_model = model.replace("anthropic/", "")
        return AnthropicProvider({**config, "model": clean_model})
    elif model.startswith("openai/") or model.startswith("gpt-"):
        clean_model = model.replace("openai/", "")
        return OpenAIProvider({**config, "model": clean_model})
    elif model.startswith("gemini/") or "gemini" in model.lower():
        from .providers_gemini import GeminiProvider
        return GeminiProvider({**config, "model": clean_model})
    elif model.startswith("ollama/"):
        clean_model = model.replace("ollama/", "")
        return OpenAIProvider({**config, "model": clean_model,
                               "base_url": config.get("ollama_url", "http://localhost:11434/v1")})
    elif "deepseek" in model.lower():
        return OpenAIProvider({**config, "model": model,
                               "base_url": config.get("base_url", "https://api.deepseek.com/v1")})
    else:
        raise ValueError(f"不支持的模型: {model}")
