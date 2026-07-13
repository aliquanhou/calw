"""providers — LLM Provider 抽象层。

v2.1 重构：
  - 统一所有 Provider 的接口：complete() 返回 {"content": str, "tool_calls": list}
  - 异常传递清晰（不静默吞掉）
  - 支持 Anthropic、OpenAI、Gemini、Ollama
  - Token 计数可观测
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable


# ── Provider 接口 ──


class LLMProvider:
    """LLM Provider 基类。"""

    def complete(self, system: str, messages: list[dict],
                 tools: list[dict] | None = None,
                 max_tokens: int = 8192,
                 temperature: float = 0.0) -> dict:
        """发送对话请求并返回回复。

        Args:
            system: 系统提示词
            messages: 消息列表
            tools: 工具定义列表
            max_tokens: 最大输出 token 数
            temperature: 温度参数

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

    def __init__(self, config: dict):
        self.api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = config.get("model", "claude-sonnet-4-20250514")
        self.base_url = config.get("base_url", "https://api.anthropic.com/v1")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
            except ImportError:
                raise RuntimeError("anthropic 库未安装: pip install anthropic>=0.49.0")
        return self._client

    def complete(self, system, messages, tools=None, max_tokens=8192, temperature=0.0):
        client = self._get_client()

        try:
            # 转换消息格式（移除 OpenAI 兼容的 name 字段）
            clean_messages = []
            for msg in messages:
                clean = {"role": msg["role"], "content": msg.get("content", "")}
                clean_messages.append(clean)

            # 调用 API
            kwargs = {
                "model": self.model,
                "system": system,
                "messages": clean_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

            if tools:
                # Anthropic 使用 tool_choice
                kwargs["tools"] = tools
                kwargs["tool_choice"] = {"type": "auto"}

            response = client.messages.create(**kwargs)

            # 解析响应
            content = ""
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input),
                        },
                    })

            return {"content": content, "tool_calls": tool_calls}

        except Exception as e:
            raise RuntimeError(f"Anthropic API 调用失败: {e}") from e


# ── OpenAI Provider ──


class OpenAIProvider(LLMProvider):
    """OpenAI / 兼容 API Provider。"""

    def __init__(self, config: dict):
        self.api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        self.model = config.get("model", "gpt-4o")
        self.base_url = config.get("base_url")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
            except ImportError:
                raise RuntimeError("openai 库未安装: pip install openai>=1.0.0")
        return self._client

    def complete(self, system, messages, tools=None, max_tokens=8192, temperature=0.0):
        client = self._get_client()

        try:
            msgs = [{"role": "system", "content": system}]
            for msg in messages:
                role = msg["role"]
                c = msg.get("content", "")

                if role == "tool":
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": msg.get("tool_call_id", ""),
                        "content": str(c),
                    })
                elif role == "assistant" and msg.get("tool_calls"):
                    msgs.append({
                        "role": "assistant",
                        "content": c or None,
                        "tool_calls": msg["tool_calls"],
                    })
                else:
                    msgs.append({"role": role, "content": c or ""})

            kwargs = {
                "model": self.model,
                "messages": msgs,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools

            response = client.chat.completions.create(**kwargs)

            choice = response.choices[0]
            content = choice.message.content or ""

            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })

            return {"content": content, "tool_calls": tool_calls}

        except Exception as e:
            raise RuntimeError(f"OpenAI API 调用失败: {e}") from e


# ── Factory ──


def create_llm_provider(config: dict) -> LLMProvider:
    """根据配置创建 LLM Provider。

    Args:
        config: 配置字典（必须包含 model 字段）

    Returns:
        LLMProvider 实例

    Raises:
        ValueError: 不支持的 Provider
    """
    model = config.get("model", "")

    if model.startswith("anthropic/") or "claude" in model.lower():
        clean_model = model.replace("anthropic/", "")
        return AnthropicProvider({**config, "model": clean_model})

    elif model.startswith("openai/") or model.startswith("gpt-"):
        clean_model = model.replace("openai/", "")
        return OpenAIProvider({**config, "model": clean_model})

    elif model.startswith("gemini/") or "gemini" in model.lower():
        clean_model = model.replace("gemini/", "")
        try:
            from .providers_gemini import GeminiProvider
            return GeminiProvider({**config, "model": clean_model})
        except ImportError:
            raise ValueError("Gemini Provider 未安装")

    elif model.startswith("ollama/"):
        clean_model = model.replace("ollama/", "")
        return OpenAIProvider({
            **config,
            "model": clean_model,
            "base_url": config.get("ollama_url", "http://localhost:11434/v1"),
        })

    else:
        raise ValueError(f"不支持的模型: {model}")
