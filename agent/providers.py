"""LLM Provider abstraction - supports Anthropic and OpenAI-compatible APIs (DeepSeek, OpenAI, etc.)."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generator

from .retry import retry_generator, is_retryable

import anthropic
import openai


# ──────────────────────────────────────────────
# Normalized streaming event
# ──────────────────────────────────────────────

@dataclass
class StreamEvent:
    """Unified streaming event from any LLM provider."""

    type: str  # text_delta | thinking_delta | tool_use_start | tool_use_delta | tool_use_stop | done | error

    # text_delta / thinking_delta
    delta: str = ""

    # tool_use_start
    tool_id: str = ""
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)

    # tool_use_delta
    partial_json: str = ""

    # done
    stop_reason: str | None = None  # end_turn | tool_use | max_tokens

    # error
    error_msg: str = ""


# ──────────────────────────────────────────────
# Normalized message utilities
# ──────────────────────────────────────────────

def make_assistant_msg(text: str | None, tool_calls: list[dict] | None = None) -> dict:
    """Build a normalized assistant message."""
    msg: dict = {"role": "assistant"}
    if text:
        msg["content"] = text
    else:
        msg["content"] = None
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def make_tool_result_msg(tool_call_id: str, content: str) -> dict:
    """Build a normalized tool result message (OpenAI/DeepSeek format)."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }


def make_anthropic_tool_results(tool_results: list[dict]) -> list[dict]:
    """Wrap tool results in Anthropic's user-role format."""
    return [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": r["tool_call_id"], "content": r["content"]}
                for r in tool_results
            ],
        }
    ]


# ──────────────────────────────────────────────
# Provider Base
# ──────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract base for LLM API providers."""

    name: str = ""
    default_model: str = ""
    models: list[str] = []

    def __init__(self, api_key: str, model: str | None = None):
        self.api_key = api_key
        self.model = model or self.default_model

    @abstractmethod
    def stream_chat(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
    ) -> Generator[StreamEvent, None, None]:
        """Yield StreamEvent objects from a streaming chat completion."""
        ...

    @abstractmethod
    def messages_to_provider(self, messages: list[dict], system_prompt: str) -> dict:
        """Convert normalized messages + system prompt to provider-specific API params."""
        ...

    def make_tool_result_messages(self, tool_results: list[dict]) -> list[dict]:
        """Convert tool execution results back to provider-specific message format."""
        return [make_tool_result_msg(r["tool_call_id"], r["content"]) for r in tool_results]


# ──────────────────────────────────────────────
# Anthropic Provider
# ──────────────────────────────────────────────

class AnthropicProvider(LLMProvider):
    name = "Anthropic"
    default_model = "claude-opus-4-7"
    models = ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"]

    def __init__(self, api_key: str, model: str | None = None):
        super().__init__(api_key, model)
        self.client = anthropic.Anthropic(api_key=api_key)

    def messages_to_provider(self, messages: list[dict], system_prompt: str) -> dict:
        """Convert to Anthropic's content-block format."""
        provider_msgs = []
        for msg in messages:
            role = msg.get("role", "user")

            if role == "tool":
                # Find the tool call in the last assistant message
                provider_msgs.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": msg.get("tool_call_id", ""), "content": msg.get("content", "")}],
                })
            elif role == "assistant":
                content: list[dict] = []
                text = msg.get("content")
                if text:
                    content.append({"type": "text", "text": text})
                for tc in (msg.get("tool_calls") or []):
                    content.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", ""),
                        "input": json.loads(tc.get("function", {}).get("arguments", "{}")),
                    })
                if not content:
                    content = [{"type": "text", "text": ""}]
                provider_msgs.append({"role": "assistant", "content": content})
            else:
                provider_msgs.append(msg)  # user role, plain format

        return {
            "system": system_prompt,
            "messages": provider_msgs,
        }

    def stream_chat(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
    ) -> Generator[StreamEvent, None, None]:
        params = self.messages_to_provider(messages, system_prompt)
        extra = {}
        if self.model in ("claude-opus-4-7", "claude-sonnet-4-6"):
            extra["thinking"] = {"type": "adaptive"}

        try:
            stream = retry_generator(
                lambda: self.client.messages.create(
                    model=self.model,
                    max_tokens=8192,
                    system=params["system"],
                    messages=params["messages"],
                    tools=tools,
                    **extra,
                    stream=True,
                ),
                max_retries=2,
                retry_on=is_retryable,
            )
        except Exception as e:
            yield StreamEvent(type="error", error_msg=str(e))
            return

        current_tool_id = None
        done_sent = False
        last_data_time = time.time()
        STREAM_TIMEOUT = 120

        for event in stream:
            # ── Streaming watchdog: no data for 120s → abort ──
            if time.time() - last_data_time > STREAM_TIMEOUT:
                yield StreamEvent(type="error", error_msg=f"流式响应超时 ({STREAM_TIMEOUT}s 无数据)")
                return
            last_data_time = time.time()
            try:
                if event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield StreamEvent(type="text_delta", delta=delta.text)
                    elif delta.type == "thinking_delta":
                        yield StreamEvent(type="thinking_delta", delta=delta.text)
                    elif delta.type == "input_json_delta":
                        yield StreamEvent(
                            type="tool_use_delta",
                            partial_json=delta.partial_json,
                            tool_id=current_tool_id or "",
                        )

                elif event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool_id = block.id
                        yield StreamEvent(
                            type="tool_use_start",
                            tool_id=block.id,
                            tool_name=block.name,
                            tool_input=block.input or {},
                        )

                elif event.type == "content_block_stop":
                    current_tool_id = None

                elif event.type == "message_delta":
                    done_sent = True
                    yield StreamEvent(type="done", stop_reason=event.delta.stop_reason)

            except Exception as e:
                yield StreamEvent(type="error", error_msg=f"事件处理: {e}")

        if not done_sent:
            yield StreamEvent(type="done", stop_reason="end_turn")

    def make_tool_result_messages(self, tool_results: list[dict]) -> list[dict]:
        return make_anthropic_tool_results(tool_results)


# ──────────────────────────────────────────────
# OpenAI-Compatible Provider (DeepSeek, OpenAI, etc.)
# ──────────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    name = "DeepSeek"
    default_model = "deepseek-chat"
    models = ["deepseek-chat", "deepseek-reasoner", "gpt-4o", "gpt-4o-mini"]

    def __init__(self, api_key: str, model: str | None = None, base_url: str | None = None):
        super().__init__(api_key, model)
        self.base_url = base_url or "https://api.deepseek.com"
        self.client = openai.OpenAI(api_key=api_key, base_url=self.base_url)

    def messages_to_provider(self, messages: list[dict], system_prompt: str) -> dict:
        """Convert to OpenAI-compatible format (system + messages)."""
        msgs = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            if role == "tool":
                msgs.append(msg)
            elif role == "assistant":
                entry: dict = {"role": "assistant"}
                tc = msg.get("tool_calls")
                if msg.get("content"):
                    entry["content"] = msg["content"]
                elif tc:
                    entry["content"] = None
                else:
                    entry["content"] = ""
                if tc:
                    entry["tool_calls"] = tc
                msgs.append(entry)
            else:
                msgs.append(msg)
        return {"messages": msgs}

    def stream_chat(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
    ) -> Generator[StreamEvent, None, None]:
        params = self.messages_to_provider(messages, system_prompt)

        # Convert tools to OpenAI format
        openai_tools = None
        if tools:
            openai_tools = []
            for t in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    },
                })

        api_params = {
            "model": self.model,
            "messages": params["messages"],
            "stream": True,
        }
        if openai_tools:
            api_params["tools"] = openai_tools

        # DeepSeek Reasoner does NOT support tools (beta limitation)
        if self.model == "deepseek-reasoner":
            api_params.pop("tools", None)

        try:
            stream = retry_generator(
                lambda: self.client.chat.completions.create(**api_params),
                max_retries=2,
                retry_on=is_retryable,
            )
        except Exception as e:
            yield StreamEvent(type="error", error_msg=str(e))
            return

        tool_buffers: dict[str, dict] = {}  # index -> {"id": ..., "name": ..., "args": ""}

        done_sent = False
        last_data_time = time.time()
        STREAM_TIMEOUT = 120  # 120s without data = timeout

        for chunk in stream:
            # ── Streaming watchdog: no data for 120s → abort ──
            now = time.time()
            if now - last_data_time > STREAM_TIMEOUT:
                yield StreamEvent(type="error", error_msg=f"流式响应超时 ({STREAM_TIMEOUT}s 无数据)")
                return
            if chunk.choices:
                last_data_time = now

            try:
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                # ── Thinking (DeepSeek Reasoner) ──
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    yield StreamEvent(type="thinking_delta", delta=delta.reasoning_content)

                # ── Text ──
                if delta.content:
                    yield StreamEvent(type="text_delta", delta=delta.content)

                # ── Tool calls ──
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if tc.id:
                            # Start of a new tool call
                            args = tc.function.arguments or ""
                            tool_buffers[idx] = {
                                "id": tc.id,
                                "name": tc.function.name or "",
                                "args": args,
                            }
                            yield StreamEvent(
                                type="tool_use_start",
                                tool_id=tc.id,
                                tool_name=tc.function.name or "",
                            )
                            # Yield first-chunk arguments as delta so core can buffer them
                            if args:
                                yield StreamEvent(
                                    type="tool_use_delta",
                                    partial_json=args,
                                    tool_id=tc.id,
                                )
                        elif idx in tool_buffers:
                            # Continuation
                            if tc.function and tc.function.arguments:
                                tool_buffers[idx]["args"] += tc.function.arguments
                                yield StreamEvent(
                                    type="tool_use_delta",
                                    partial_json=tc.function.arguments,
                                    tool_id=tool_buffers[idx]["id"],
                                )

                # ── Finish reason ──
                if choice.finish_reason:
                    done_sent = True
                    sr = choice.finish_reason
                    mapped = {
                        "stop": "end_turn",
                        "tool_calls": "tool_use",
                        "length": "max_tokens",
                    }
                    yield StreamEvent(type="done", stop_reason=mapped.get(sr, sr))

            except Exception as e:
                yield StreamEvent(type="error", error_msg=f"流处理: {e}")

        if not done_sent:
            yield StreamEvent(type="done", stop_reason="end_turn")


# ── Token/Cost Tracking ──
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-7":{"input":15.00,"output":75.00},"claude-sonnet-4-6":{"input":3.00,"output":15.00},
    "claude-haiku-4-5":{"input":0.80,"output":4.00},"deepseek-chat":{"input":0.27,"output":1.10},
    "deepseek-reasoner":{"input":0.55,"output":2.19},"gpt-4o":{"input":2.50,"output":10.00},"gpt-4o-mini":{"input":0.15,"output":0.60},
}
_usage: dict[str,int]={"input_tokens":0,"output_tokens":0,"calls":0}
def reset_usage():_usage["input_tokens"]=0;_usage["output_tokens"]=0;_usage["calls"]=0
def track_usage(it:int,ot:int):_usage["input_tokens"]+=it;_usage["output_tokens"]+=ot;_usage["calls"]+=1
def get_usage_summary()->str:
    c=_usage["calls"]
    if c==0:return"暂无API调用"
    i=_usage["input_tokens"];o=_usage["output_tokens"]
    return f"API调用:{c}次\nToken:{i:,}入+{o:,}出={(i+o):,}\n费用:${i/1e6*3.00+o/1e6*15.00:.4f}"
def estimate_cost(m:str,i:int,o:int)->float:
    p=MODEL_PRICING.get(m,{"input":3.00,"output":15.00});return(i/1e6*p["input"])+(o/1e6*p["output"])

# ──────────────────────────────────────────────
# Provider Registry
# ──────────────────────────────────────────────

PROVIDERS: dict[str, type[LLMProvider]] = {
    "Anthropic Claude": AnthropicProvider,
    "DeepSeek": OpenAIProvider,
}


def get_provider(provider_name: str, api_key: str, model: str, base_url: str | None = None) -> LLMProvider:
    """Factory: create a provider instance by name."""
    cls = PROVIDERS.get(provider_name)
    if not cls:
        raise ValueError(f"未知的 LLM 提供商: {provider_name}")

    if cls is OpenAIProvider:
        return cls(api_key=api_key, model=model, base_url=base_url)
    return cls(api_key=api_key, model=model)


def get_default_provider() -> str:
    """Return the name of the default provider."""
    return "DeepSeek"


def get_models_for(provider_name: str) -> list[str]:
    cls = PROVIDERS.get(provider_name)
    if cls:
        return cls.models
    return []
