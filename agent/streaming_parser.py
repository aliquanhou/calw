"""streaming_parser — 流式渐进工具调用解析器。

在 LLM 输出流中实时检测并解析工具调用。
不等完整 JSON 生成完毕，检测到关键参数即开始执行。

核心改进：
  传统方式：等待 LLM 生成完整 JSON → 解析 → 执行（串行）
  流式方式：检测到工具名就预分配 → 检测到关键参数就执行（并行）

使用方式（在 Agent 主循环中）：
    parser = StreamingToolParser()
    parser.on_tool_ready = lambda name, params, result: cache.set(name, params, result)

    for token in llm_stream:
        signals = parser.feed(token)
        for signal in signals:
            if signal["type"] == "early_exec":
                # 工具已经在后台执行了
                pass
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Callable

# ── 工具的关键参数定义 ──

ESSENTIAL_PARAMS: dict[str, set[str]] = {
    "read": {"file_path"},
    "write": {"file_path", "content"},
    "edit": {"file_path", "old_string", "new_string"},
    "replace": {"file_path", "search", "replace_text"},
    "glob": {"pattern"},
    "grep": {"pattern"},
    "bash": {"command"},
    "web": {"url"},
    "browser": {"action"},
    "web_search": {"query"},
    "ast": {"file_path"},
    "dep_graph": {"path"},
    "call_chain": {"function_name", "direction"},
    "trace_error": {"error_message"},
    "test": {"action"},
    "dep": {"action"},
    "process": {"action"},
    "service": {"action"},
    "registry": {"action", "key"},
    "monitor": {"action"},
    "remember": {"action"},
    "move": {"source", "destination"},
    "copy": {"source", "destination"},
    "delete": {"path"},
    "mkdir": {"path"},
    "download": {"url", "destination"},
    "gui": {"action"},
}

# ── JSON 片段正则 ──

# 匹配工具名
TOOL_NAME_PATTERN = re.compile(
    r'(?:"(?:name|function|tool)"\s*:\s*)"(\w+)"',
    re.IGNORECASE,
)

# 匹配字符串参数
STRING_PARAM_PATTERN = re.compile(
    r'"(file_path|path|content|command|url|query|pattern|search|old_string|new_string|replace_text|error_message|source|destination|action|key)"\s*:\s*"((?:[^"\\]|\\.)*)"',
)

# 匹配整数参数
INT_PARAM_PATTERN = re.compile(
    r'"(timeout|max_results|depth|pid|n_results)"\s*:\s*(\d+)',
)

# 匹配布尔参数
BOOL_PARAM_PATTERN = re.compile(
    r'"(parents|recursive|partial)"\s*:\s*(true|false)',
)


class StreamingToolParser:
    """流式渐进工具调用解析器。

    在 LLM 输出的 token 流中实时解析工具调用，
    检测到关键参数即触发回调进行预执行。
    """

    def __init__(self):
        self._buffer = ""
        """累积的文本缓冲区。"""

        self._current_tool: str | None = None
        """当前正在解析的工具名。"""

        self._current_params: dict[str, Any] = {}
        """已解析出的部分参数。"""

        self._tool_start_pos = 0
        """当前工具调用在缓冲区中的起始位置。"""

        self._early_executed = False
        """是否已触发提前执行。"""

        self._lock = threading.Lock()

        # ── 回调 ──
        self.on_tool_ready: Callable[[str, dict, Any], None] | None = None
        """当工具提前执行完成时触发。参数：(tool_name, params, result)"""

        self.on_signal: Callable[[str], None] | None = None
        """当解析器产生状态信号时触发。"""

    def feed(self, token: str) -> list[dict]:
        """输入一个 token 进行解析。

        每次调用都在当前缓冲区尾部追加 token，
        然后尝试识别工具调用模式。

        Args:
            token: LLM 输出的一个 token（字符或文本块）

        Returns:
            Signal 列表，每个 signal 格式：
            {
                "type": str,  # tool_detected | param_detected | early_exec | tool_complete | error
                "tool": str,  # 工具名
                "params": dict,  # 当前已解析的参数
                "message": str,  # 描述信息
            }
        """
        signals: list[dict] = []
        self._buffer += token

        # 检测工具调用开始
        if self._current_tool is None:
            tool_match = TOOL_NAME_PATTERN.search(self._buffer)
            if tool_match:
                tool_name = tool_match.group(1)
                with self._lock:
                    self._current_tool = tool_name
                    self._current_params = {}
                    self._early_executed = False

                signals.append({
                    "type": "tool_detected",
                    "tool": tool_name,
                    "params": {},
                    "message": f"检测到工具: {tool_name}",
                })
                self._signal(f"检测到工具: {tool_name}")
                return signals

        # 解析参数（在当前工具上下文中）
        if self._current_tool and not self._early_executed:
            params_before = len(self._current_params)

            # 搜索字符串参数
            for match in STRING_PARAM_PATTERN.finditer(self._buffer[self._tool_start_pos:]):
                key, value = match.group(1), match.group(2)
                if key not in self._current_params:
                    self._current_params[key] = value

            # 搜索整数参数
            for match in INT_PARAM_PATTERN.finditer(self._buffer[self._tool_start_pos:]):
                key, value = match.group(1), int(match.group(2))
                if key not in self._current_params:
                    self._current_params[key] = value

            # 搜索布尔参数
            for match in BOOL_PARAM_PATTERN.finditer(self._buffer[self._tool_start_pos:]):
                key, value = match.group(1), match.group(2).lower() == "true"
                if key not in self._current_params:
                    self._current_params[key] = value

            # 如果解析到了新参数，发出 signal
            if len(self._current_params) > params_before:
                signals.append({
                    "type": "param_detected",
                    "tool": self._current_tool,
                    "params": dict(self._current_params),
                    "message": f"解析到参数: {list(self._current_params.keys())}",
                })

            # 检查是否已获得关键参数
            essential = ESSENTIAL_PARAMS.get(self._current_tool, set())
            if essential and essential.issubset(self._current_params.keys()):
                # 在后台线程提前执行
                tool_name = self._current_tool
                params = dict(self._current_params)
                self._early_executed = True

                signals.append({
                    "type": "early_exec",
                    "tool": tool_name,
                    "params": params,
                    "message": f"提前执行: {tool_name}",
                })
                self._signal(f"提前执行: {tool_name}")

                # 启动后台线程执行
                if self.on_tool_ready:
                    threading.Thread(
                        target=self._execute_early,
                        args=(tool_name, params),
                        daemon=True,
                    ).start()

                return signals

        # 检测工具调用结束（完整 JSON 解析）
        if self._current_tool and "}" in self._buffer[self._tool_start_pos:]:
            # 尝试解析完整 JSON
            try:
                # 从 buffer 中提取 JSON 对象
                json_start = self._buffer.find("{", self._tool_start_pos)
                if json_start >= 0:
                    for end in range(len(self._buffer), json_start, -1):
                        candidate = self._buffer[json_start:end].strip()
                        if candidate.endswith("}"):
                            parsed = json.loads(candidate)
                            # 检查是否是工具调用格式
                            if "function" in parsed or "name" in parsed:
                                signals.append({
                                    "type": "tool_complete",
                                    "tool": self._current_tool,
                                    "params": dict(self._current_params),
                                    "message": f"工具调用完整: {self._current_tool}",
                                })
                                self._reset()
                                break
            except (json.JSONDecodeError, ValueError):
                pass

        return signals

    def _execute_early(self, tool_name: str, params: dict):
        """在后台执行工具并回调。

        Args:
            tool_name: 工具名称
            params: 提前解析出的参数
        """
        # 查找处理器
        from .session import get_state
        state = get_state()
        handler = state.get_handler(tool_name)

        if handler is None:
            return

        try:
            result = handler(**params)
            if self.on_tool_ready:
                self.on_tool_ready(tool_name, params, result)
        except Exception:
            pass  # 提前执行失败没关系，正常路径会重新执行

    def _signal(self, message: str):
        """触发状态信号回调。"""
        if self.on_signal:
            self.on_signal(message)

    def _reset(self):
        """重置当前解析状态。"""
        self._current_tool = None
        self._current_params = {}
        self._tool_start_pos = len(self._buffer)
        self._early_executed = False

    def reset(self):
        """完全重置解析器状态。"""
        with self._lock:
            self._buffer = ""
            self._current_tool = None
            self._current_params = {}
            self._tool_start_pos = 0
            self._early_executed = False

    @property
    def current_tool(self) -> str | None:
        """当前正在解析的工具名。"""
        return self._current_tool

    @property
    def current_params(self) -> dict:
        """当前已解析的参数。"""
        return dict(self._current_params)

    @property
    def buffer_length(self) -> int:
        """缓冲区字符数。"""
        return len(self._buffer)
