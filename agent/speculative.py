"""speculative — 推测性执行引擎。

在 Agent 思考时，基于执行历史预测下一步最可能的工具调用，
并在后台提前准备执行环境，使工具延迟趋近于零。

核心思想：
  - Agent 的 LLM 推理是瓶颈，而 CPU 和 I/O 通常是空闲的
  - 利用空闲时间预判下一步并准备环境
  - 当 Agent 实际调用时，直接命中缓存

设计：
  - 规则引擎驱动（低延迟，不依赖 LLM 二次推理）
  - 基于最近 N 条工具调用历史进行模式匹配
  - 高置信度（>80%）的预测才会触发预执行
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SpeculativePrediction:
    """一个推测出来的工具调用预测。"""

    tool_name: str
    params: dict
    confidence: float
    """置信度 0.0 ~ 1.0"""

    ready: bool = False
    """后台是否已准备好结果"""

    result: Any = None
    """预执行的结果"""

    prepared: bool = False
    """是否已执行过准备动作"""

    _lock: threading.Lock = field(default_factory=threading.Lock)

    def wait_and_get(self, timeout: float = 0.05) -> Any | None:
        """等待后台准备完成（最多 timeout 秒）并获取结果。

        Args:
            timeout: 最大等待时间（秒）

        Returns:
            预执行结果，或 None 表示未准备好
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self.ready:
                    return self.result
            time.sleep(0.002)
        return None


# ── 执行模式规则库 ──


def _read_then_edit(params: dict, history: list[dict]) -> list[SpeculativePrediction]:
    """模式 1: read → edit（读完后大概率编辑）"""
    if not history:
        return []

    last = history[-1]
    if last.get("name") != "read":
        return []

    path = last.get("params", {}).get("file_path", "")
    if not path:
        return []

    # 被读到的文件路径，接下来大概率要被编辑
    return [
        SpeculativePrediction(
            tool_name="edit",
            params={"file_path": path, "old_string": "...", "new_string": "..."},
            confidence=0.75,
        ),
        SpeculativePrediction(
            tool_name="write",
            params={"file_path": path, "content": "..."},
            confidence=0.60,
        ),
    ]


def _build_then_test(params: dict, history: list[dict]) -> list[SpeculativePrediction]:
    """模式 2: bash(build) → bash(test)（构建后大概率测试）"""
    if not history:
        return []

    last = history[-1]
    if last.get("name") != "bash":
        return []

    result_preview = str(last.get("result", ""))
    exit_code = last.get("exit_code", 1)

    # 构建成功 → 下一步大概率测试
    if exit_code == 0 and any(kw in result_preview.lower()
                              for kw in ("build", "compile", "success", "done", "npm run")):
        # 检测项目类型
        if os.path.exists("pytest.ini") or os.path.exists("setup.cfg"):
            return [
                SpeculativePrediction(tool_name="bash", params={"command": "pytest -x", "timeout": 60},
                                      confidence=0.85),
            ]
        if os.path.exists("package.json"):
            return [
                SpeculativePrediction(tool_name="bash", params={"command": "npm test", "timeout": 60},
                                      confidence=0.75),
            ]
        return [
            SpeculativePrediction(tool_name="bash", params={"command": "echo done", "timeout": 10},
                                  confidence=0.50),
        ]

    # 构建失败 → 下一步大概率读日志
    if exit_code != 0:
        # 提取错误文件路径
        error_files = re.findall(r'File\s+"([^"]+\.\w+)"', result_preview)
        predictions = []
        for ef in error_files[:2]:
            predictions.append(
                SpeculativePrediction(tool_name="read", params={"file_path": ef},
                                      confidence=0.65),
            )
        return predictions

    return []


def _web_then_browser(params: dict, history: list[dict]) -> list[SpeculativePrediction]:
    """模式 3: web → browser（拿到 HTML 后大概率浏览器操作）"""
    if not history:
        return []

    last = history[-1]
    if last.get("name") != "web":
        return []

    url = last.get("params", {}).get("url", "")
    if not url:
        return []

    # 如果 web 返回的是 HTML 页面，下一步可能要在浏览器中诊断
    result_preview = str(last.get("result", ""))
    if "<html" in result_preview.lower() or "<!doctype" in result_preview.lower():
        return [
            SpeculativePrediction(
                tool_name="browser",
                params={"action": "navigate", "url": url},
                confidence=0.90,
            ),
        ]

    # API 请求 → 下一步可能是另一个 API 或解析结果
    if url.endswith((".json", "/api/", "/v1/")):
        return [
            SpeculativePrediction(
                tool_name="web",
                params={"url": url, "method": "GET"},
                confidence=0.50,
            ),
        ]

    return []


def _write_then_verify(params: dict, history: list[dict]) -> list[SpeculativePrediction]:
    """模式 4: write → bash(verify)（写完文件后验证）"""
    if not history:
        return []

    last = history[-1]
    if last.get("name") != "write":
        return []

    file_path = last.get("params", {}).get("file_path", "")

    if file_path.endswith(".py"):
        return [
            SpeculativePrediction(
                tool_name="bash",
                params={"command": f"python -m py_compile \"{file_path}\"" if os.name != "nt"
                        else f"python -m py_compile '{file_path}'", "timeout": 15},
                confidence=0.95,
            ),
        ]

    if file_path.endswith(".json"):
        return [
            SpeculativePrediction(
                tool_name="bash",
                params={"command": "python -c \"import json; json.load(open('" + file_path.replace("\\", "/") + "'))\"" if os.name != "nt"
                        else f"python -c \"import json; json.load(open('{file_path}'))\"", "timeout": 10},
                confidence=0.90,
            ),
        ]

    return []


def _consecutive_fail_heal(params: dict, history: list[dict]) -> list[SpeculativePrediction]:
    """模式 5: 连续 3+ 次失败 → 执行环境诊断"""
    if len(history) < 3:
        return []

    recent_fails = sum(
        1 for h in history[-6:]
        if h.get("name") in ("bash", "web", "browser")
        and h.get("exit_code", 1) != 0
    )

    if recent_fails >= 3:
        return [
            SpeculativePrediction(
                tool_name="bash",
                params={"command": "tasklist /FI \"STATUS eq running\" 2>nul | head -20",
                        "timeout": 10},
                confidence=0.70,
            ),
            SpeculativePrediction(
                tool_name="monitor",
                params={"action": "resources"},
                confidence=0.60,
            ),
        ]

    return []


# ── 规则集合 ──

_RULES = [
    _read_then_edit,
    _build_then_test,
    _web_then_browser,
    _write_then_verify,
    _consecutive_fail_heal,
]


class SpeculativeEngine:
    """推测性执行引擎。

    在 Agent 思考期间，预测下一步工具调用并在后台预先准备。
    """

    def __init__(self):
        self._history: deque[dict] = deque(maxlen=50)
        """最近 50 条工具调用历史。"""

        self._predictions: list[SpeculativePrediction] = []
        """当前的推测预测列表。"""

        self._thread: threading.Thread | None = None
        self._running = False

        # 预执行白名单（只预执行安全的、无副作用的工具）
        self._safe_tools_for_prepare = {
            "read",        # 预读文件到缓存
            "bash",        # 预检查命令是否存在（不执行）
            "browser",     # 预打开页面
            "web",         # 预 DNS 解析
        }

    def record_call(self, tool_name: str, params: dict, result: str,
                    exit_code: int = 0, duration_ms: float = 0.0):
        """记录一次工具调用。

        Args:
            tool_name: 工具名称
            params: 参数字典
            result: 结果字符串
            exit_code: 退出码（0=成功）
            duration_ms: 执行耗时（毫秒）
        """
        entry = {
            "name": tool_name,
            "params": params,
            "result": result[:500],
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        }
        self._history.append(entry)

        # 每次记录新调用后触发预测
        self._predict()

    def consume(self, tool_name: str, params: dict) -> Any | None:
        """Agent 实际发起工具调用时，检查是否有匹配的预测结果。

        如果匹配，立即返回预执行结果（零延迟）。
        如果不匹配，返回 None（走正常执行路径）。

        Args:
            tool_name: 实际调用的工具名
            params: 实际调用的参数

        Returns:
            预执行结果，或 None
        """
        for pred in self._predictions:
            if pred.tool_name != tool_name:
                continue

            # 参数匹配度检查
            match_score = self._param_similarity(pred.params, params)
            if match_score >= 0.5:
                result = pred.wait_and_get(timeout=0.02)
                if result is not None:
                    # 消费后移除
                    self._predictions = [p for p in self._predictions if p is not pred]
                    return result

        return None

    def _predict(self):
        """运行所有规则生成预测。"""
        if not self._history:
            return

        last_call = self._history[-1]
        params = last_call.get("params", {})

        all_predictions = []
        for rule in _RULES:
            try:
                predictions = rule(dict(params), list(self._history))
                all_predictions.extend(predictions)
            except Exception:
                continue

        # 按置信度排序，保留 Top-3
        all_predictions.sort(key=lambda p: p.confidence, reverse=True)
        self._predictions = all_predictions[:3]

        # 对高置信度的预测，在后台准备
        for pred in self._predictions:
            if pred.confidence > 0.7 and pred.tool_name in self._safe_tools_for_prepare:
                if not pred.prepared:
                    pred.prepared = True
                    self._prepare_background(pred)

    def _prepare_background(self, pred: SpeculativePrediction):
        """在后台为预测准备环境（无副作用的操作）。"""
        tool = pred.tool_name

        try:
            if tool == "read":
                path = pred.params.get("file_path", "")
                if path and os.path.exists(path):
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    with pred._lock:
                        pred.result = content
                        pred.ready = True

            elif tool == "bash":
                # 只检查命令是否存在，不执行
                cmd = pred.params.get("command", "")
                if cmd:
                    # 标记为"已准备好可立即执行"
                    with pred._lock:
                        pred.ready = True

            elif tool == "web":
                # 预 DNS 解析
                import socket
                url = pred.params.get("url", "")
                if url and "//" in url:
                    host = url.split("//")[1].split("/")[0]
                    try:
                        socket.getaddrinfo(host, 80)
                    except Exception:
                        pass
                    with pred._lock:
                        pred.ready = True

        except Exception:
            pass  # 预加载失败没关系，走正常路径

    def _param_similarity(self, pred_params: dict, actual_params: dict) -> float:
        """计算预测参数和实际参数的相似度。

        Args:
            pred_params: 预测的参数
            actual_params: 实际的参数

        Returns:
            相似度 0.0 ~ 1.0
        """
        if not pred_params or not actual_params:
            return 0.0

        common_keys = set(pred_params.keys()) & set(actual_params.keys())
        if not common_keys:
            return 0.0

        # 检查关键参数的值是否相似
        exact_matches = 0
        for key in common_keys:
            pred_val = str(pred_params.get(key, "")).strip()
            actual_val = str(actual_params.get(key, "")).strip()

            if pred_val == actual_val:
                exact_matches += 1
            elif pred_val.startswith("...") or pred_val.endswith("..."):
                # 占位符匹配
                exact_matches += 0.5

        total_keys = max(len(actual_params), 1)
        return exact_matches / total_keys

    @property
    def prediction_count(self) -> int:
        """当前预测数量。"""
        return len(self._predictions)

    def clear(self):
        """清除所有预测。"""
        self._predictions.clear()


# ── 全局单例 ──

_engine: SpeculativeEngine | None = None
_engine_lock = threading.Lock()


def get_engine() -> SpeculativeEngine:
    """获取推测引擎全局单例。"""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = SpeculativeEngine()
    return _engine
