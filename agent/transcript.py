"""transcript — 透明输出事件系统。

Agent 内部每一个步骤都产出结构化事件，通过回调总线向外广播。
UI 层订阅这些事件，实现"用户时刻看到 Agent 在做什么"。

事件层级：
  SESSION   → 一次对话的开始/结束
  PHASE     → 阶段切换（plan / execute / verify / done）
  STEP      → 工作流步骤（step_created / step_start / step_done / step_fail）
  THOUGHT   → Agent 思考过程（thinking_delta）
  TOOL      → 工具调用全过程（tool_start / tool_param / tool_result）
  TEXT      → 流式文本输出
  LOOP      → 循环检测/防死循环事件（loop_warning / loop_break）
  ERROR     → 错误
  CHECKPOINT→ 上下文压缩/状态快照

使用方式：
    transcript = Transcript()
    transcript.on("*", lambda e: print(json.dumps(e)))
    transcript.emit("phase", phase="plan", status="start")
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Callable


# ── 事件类型常量 ──

SESSION     = "session"
PHASE       = "phase"
STEP        = "step"
THOUGHT     = "thought"
TOOL        = "tool"
TEXT        = "text"
LOOP        = "loop"
ERROR       = "error"
CHECKPOINT  = "checkpoint"
PLAN        = "plan"


# ── 事件结构 ──

@dataclass
class Event:
    """一条结构化事件记录。"""
    type: str                 # 事件类型（SESSION / PHASE / STEP / ...）
    subtype: str              # 子类型（start / done / delta / warning / ...）
    ts: float = 0.0           # 时间戳（自动填充）
    seq: int = 0              # 序号（自动递增）
    agent_id: str = ""        # Agent 标识
    payload: dict = field(default_factory=dict)  # 事件负载

    def dict(self) -> dict:
        return asdict(self)


# ── 回调总线 ──

class Transcript:
    """透明输出总线 —— Agent 每步动作都通过这里广播。

    特性：
      - 通配符订阅 "*" 接收所有事件
      - 按 type 过滤订阅（如 "tool" 只收工具事件）
      - 自动填充时间戳和序号
      - 可序列化为 JSON（供 WebSocket/文件/UI 消费）
    """

    def __init__(self, agent_id: str = "calw"):
        self.agent_id = agent_id
        self._seq = 0
        self._subs: dict[str, list[Callable]] = {}
        self._history: list[Event] = []       # 事件历史（可回溯）
        self._max_history = 10000             # 最多保留 10000 条

    # ── 订阅 ──

    def on(self, event_type: str, callback: Callable[[Event], None]):
        """订阅事件。 event_type="*" 表示所有事件。"""
        self._subs.setdefault(event_type, []).append(callback)

    def off(self, event_type: str, callback: Callable | None = None):
        """取消订阅。不传 callback 则取消该类型所有订阅。"""
        if callback:
            self._subs.get(event_type, []).remove(callback)
        else:
            self._subs.pop(event_type, None)

    # ── 发射 ──

    def emit(self, event_type: str, subtype: str = "", **payload) -> Event:
        """发射一条事件。"""
        self._seq += 1
        ev = Event(
            type=event_type,
            subtype=subtype,
            ts=time.time(),
            seq=self._seq,
            agent_id=self.agent_id,
            payload=payload,
        )
        # 存历史
        self._history.append(ev)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        # 广播
        for cb in self._subs.get(event_type, []):
            try:
                cb(ev)
            except Exception:
                pass
        for cb in self._subs.get("*", []):
            try:
                cb(ev)
            except Exception:
                pass
        return ev

    # ── 便捷发射器 ──

    def session(self, subtype: str, **kw):
        return self.emit(SESSION, subtype, **kw)

    def phase(self, subtype: str, phase_name: str = "", progress: float = 0.0, **kw):
        return self.emit(PHASE, subtype, phase_name=phase_name, progress=progress, **kw)

    def step(self, subtype: str, step_id: str = "", step_name: str = "", status: str = "", **kw):
        return self.emit(STEP, subtype, step_id=step_id, step_name=step_name, status=status, **kw)

    def thought(self, delta: str, **kw):
        return self.emit(THOUGHT, "delta", delta=delta, **kw)

    def tool(self, subtype: str, tool_name: str = "", tool_id: str = "", **kw):
        return self.emit(TOOL, subtype, tool_name=tool_name, tool_id=tool_id, **kw)

    def text(self, delta: str, **kw):
        return self.emit(TEXT, "delta", delta=delta, **kw)

    def loop(self, subtype: str, reason: str = "", **kw):
        return self.emit(LOOP, subtype, reason=reason, **kw)

    def error(self, source: str = "", message: str = "", **kw):
        return self.emit(ERROR, "raised", source=source, message=message, **kw)

    def checkpoint(self, action: str = "", detail: str = "", **kw):
        return self.emit(CHECKPOINT, action, detail=detail, **kw)

    def plan_created(self, plan_id: str, title: str, steps: list[dict], **kw):
        return self.emit(PLAN, "created", plan_id=plan_id, title=title, steps=steps, **kw)

    def step_plan(self, step_id: str, step_name: str, **kw):
        return self.emit(PLAN, "step_planned", step_id=step_id, step_name=step_name, **kw)

    # ── 查询 ──

    def recent(self, n: int = 20, event_type: str | None = None) -> list[Event]:
        """获取最近的 N 条事件。"""
        if event_type:
            filtered = [e for e in self._history if e.type == event_type]
            return filtered[-n:]
        return self._history[-n:]

    def latest(self, event_type: str | None = None) -> Event | None:
        """获取最新一条事件。"""
        if event_type:
            for e in reversed(self._history):
                if e.type == event_type:
                    return e
            return None
        return self._history[-1] if self._history else None

    def summary(self) -> dict:
        """生成当前会话摘要（供 UI 展示）。"""
        phases = [e for e in self._history if e.type == PHASE]
        steps = [e for e in self._history if e.type == STEP]
        tool_calls = [e for e in self._history if e.type == TOOL and e.subtype == "start"]
        return {
            "total_events": self._seq,
            "current_phase": phases[-1].payload.get("phase_name", "") if phases else "",
            "steps_completed": len([s for s in steps if s.subtype == "done"]),
            "steps_total": len(steps),
            "tool_calls": len(tool_calls),
            "errors": len([e for e in self._history if e.type == ERROR]),
            "duration_sec": round(time.time() - (self._history[0].ts if self._history else time.time()), 1),
        }
