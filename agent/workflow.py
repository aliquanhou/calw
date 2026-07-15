"""workflow — 工作流状态机。

管理 Agent 执行计划的完整生命周期：
  计划创建 → 步骤分解 → 逐步执行 → 完成/失败

透明输出：每一步状态变化都推送到 transcript。
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


# ── 步骤状态 ──

STEP_PENDING  = "pending"
STEP_RUNNING  = "running"
STEP_DONE     = "done"
STEP_FAILED   = "failed"
STEP_SKIPPED  = "skipped"


@dataclass
class Step:
    """一个工作流步骤。"""
    id: str
    name: str
    status: str = STEP_PENDING
    depends_on: list[str] = field(default_factory=list)
    tool_calls: int = 0
    errors: int = 0
    started_at: float = 0.0
    completed_at: float = 0.0
    result: str = ""
    error_info: str = ""


class Workflow:
    """工作流状态机 — 透明追踪执行计划。"""

    def __init__(self, transcript=None, config: dict | None = None):
        self.transcript = transcript
        self.config = config or {}
        self.plan_id: str = ""
        self.plan_title: str = ""
        self.steps: dict[str, Step] = {}
        self.step_order: list[str] = []
        self.current_step_id: str = ""
        self.status: str = "idle"
        self.started_at: float = 0.0
        self._on_step_change: list[callable] = []

    def create_plan(self, title: str, steps: list[dict]) -> str:
        """创建新计划。steps = [{"id": "...", "name": "...", "depends_on": [...]}, ...]"""
        self.plan_id = hashlib.md5(f"{title}{time.time()}".encode()).hexdigest()[:12]
        self.plan_title = title
        self.step_order = []
        for s in steps:
            step = Step(
                id=s.get("id", str(len(self.steps))),
                name=s.get("name", ""),
                depends_on=s.get("depends_on", []),
            )
            self.steps[step.id] = step
            self.step_order.append(step.id)
        self.status = "idle"
        if self.transcript:
            self.transcript.plan_created(
                plan_id=self.plan_id, title=title,
                steps=[{"id": s.id, "name": s.name, "status": s.status} for s in self.steps.values()],
            )
        return self.plan_id

    def get_ready_steps(self) -> list[Step]:
        """获取当前可执行的步骤。"""
        ready = []
        for sid in self.step_order:
            s = self.steps[sid]
            if s.status != STEP_PENDING:
                continue
            deps_met = all(self.steps.get(d, Step("","")).status == STEP_DONE for d in s.depends_on)
            if deps_met:
                ready.append(s)
        return ready

    def is_all_done(self) -> bool:
        return all(s.status in (STEP_DONE, STEP_SKIPPED) for s in self.steps.values())

    def start_step(self, step_id: str) -> bool:
        step = self.steps.get(step_id)
        if not step:
            return False
        step.status = STEP_RUNNING
        step.started_at = time.time()
        self.current_step_id = step_id
        if self.started_at == 0:
            self.started_at = time.time()
            self.status = "running"
        if self.transcript:
            self.transcript.step("start", step_id=step_id, step_name=step.name, status="running")
        return True

    def complete_step(self, step_id: str, result: str = "") -> bool:
        step = self.steps.get(step_id)
        if not step:
            return False
        step.status = STEP_DONE
        step.completed_at = time.time()
        step.result = result
        if step_id == self.current_step_id:
            self.current_step_id = ""
        if self.transcript:
            self.transcript.step("done", step_id=step_id, step_name=step.name, status="done", result=result[:500])
        return True

    def fail_step(self, step_id: str, error: str = "") -> bool:
        step = self.steps.get(step_id)
        if not step:
            return False
        step.status = STEP_FAILED
        step.completed_at = time.time()
        step.error_info = error
        if step_id == self.current_step_id:
            self.current_step_id = ""
        if self.transcript:
            self.transcript.step("fail", step_id=step_id, step_name=step.name, status="failed", error=error[:500])
        return True

    def skip_step(self, step_id: str, reason: str = "") -> bool:
        step = self.steps.get(step_id)
        if not step:
            return False
        step.status = STEP_SKIPPED
        if self.transcript:
            self.transcript.step("skipped", step_id=step_id, step_name=step.name, status="skipped", reason=reason)
        return True

    def get_current_step(self) -> Step | None:
        if self.current_step_id:
            return self.steps.get(self.current_step_id)
        return None

    def get_next_step_name(self) -> str:
        for sid in self.step_order:
            s = self.steps[sid]
            if s.status == STEP_PENDING:
                deps_met = all(self.steps.get(d, Step("","")).status == STEP_DONE for d in s.depends_on)
                if deps_met:
                    return s.name
        return ""

    def progress(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps.values() if s.status in (STEP_DONE, STEP_SKIPPED))
        return done / len(self.steps)

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "plan_title": self.plan_title,
            "status": self.status,
            "progress": self.progress(),
            "steps": [
                {
                    "id": s.id, "name": s.name, "status": s.status,
                    "tool_calls": s.tool_calls, "errors": s.errors,
                    "result": s.result[:200] if s.result else "",
                    "error_info": s.error_info[:200] if s.error_info else "",
                    "depends_on": s.depends_on,
                }
                for s in self.steps.values()
            ],
            "current_step": self.get_current_step().name if self.get_current_step() else "",
            "next_step": self.get_next_step_name(),
            "duration_sec": round(time.time() - self.started_at, 1) if self.started_at > 0 else 0,
        }
