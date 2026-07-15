"""tools_agent — 子Agent系统。

提供 subagent 工具：在隔离上下文中执行子 Agent，支持同步/后台模式。
支持通过 agent_loader 注册的 Agent 类型。

使用方式（LLM 视角）：
  subagent(action="run", agent="code-architect", prompt="分析这个项目的架构")
  subagent(action="run", prompt="搜索文件并返回结果", model="claude-haiku-4-5")
  subagent(action="run", agent="code-reviewer", prompt="审查这段代码", mode="background")
  subagent(action="agent")  — 列出可用 Agent 类型
  subagent(action="list")   — 列出后台子 Agent
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from typing import Any

from .core import Agent
from .session import get_state, set_state, SessionState
from .agent_loader import get_agent, list_agents, ensure_loaded


# ── 后台任务注册表 ──

_SUB_AGENTS: dict[str, dict] = {}
"""活跃的子 Agent 列表。"""
_SUB_LOCK = threading.Lock()


def _handle_subagent(action: str = "run",
                  agent: str = "",
                  prompt: str = "",
                  model: str = "",
                  mode: str = "sync",
                  task_id: str = "") -> str:
    """子Agent管理：run/agent/list/output/stop/wait。

    Args:
        action: run | agent | list | output | stop | wait
        agent: Agent 类型名（来自 agents/*.md），空=通用
        prompt: 子 Agent 的执行指令
        model: 模型名（覆盖默认）
        mode: sync | background | plan
        task_id: 任务 ID（list/output/stop/wait 时使用）

    Returns:
        操作结果
    """
    if action == "agent":
        return _list_agent_defs()

    if action == "list":
        return _list_sub_agents()

    if action == "output":
        return _get_output(task_id)

    if action == "stop":
        return _stop_agent(task_id)

    if action == "wait":
        return _wait_agent(task_id, timeout=300)

    # action == "run"
    if not prompt:
        return "[错误] run 需要 prompt 参数"

    # ── 解析 Agent 定义 ──
    system_prompt_extra = ""
    tools_whitelist = None
    if agent:
        adef = get_agent(agent)
        if adef:
            system_prompt_extra = adef.system_prompt
            tools_whitelist = adef.tools
            if not model and adef.model:
                model = adef.model
        else:
            return f"[错误] 未知 Agent 类型: {agent}（可用: {', '.join(a['name'] for a in list_agents())}）"

    # ── 拼装最终提示词 ──
    full_prompt = prompt
    if system_prompt_extra:
        full_prompt = f"{system_prompt_extra}\n\n---\n\n任务：{prompt}"
        if tools_whitelist:
            full_prompt += f"\n\n注意：你只能使用以下工具：{', '.join(tools_whitelist)}"

    # ── 后台模式 ──
    if mode == "background":
        tid = f"sub-{int(time.time()*1000) % 100000:05d}"
        with _SUB_LOCK:
            _SUB_AGENTS[tid] = {
                "agent": agent or "通用",
                "prompt": prompt[:100],
                "status": "running",
                "started": time.strftime("%H:%M:%S"),
                "result": "",
                "done": False,
            }

        def _run_bg(tid_inner: str, p: str, m: str, a: str):
            try:
                result = _run_sub_agent(p, model=m)
                with _SUB_LOCK:
                    if tid_inner in _SUB_AGENTS:
                        _SUB_AGENTS[tid_inner]["result"] = str(result)[:2000]
                        _SUB_AGENTS[tid_inner]["status"] = "done"
                        _SUB_AGENTS[tid_inner]["done"] = True
            except Exception as e:
                with _SUB_LOCK:
                    if tid_inner in _SUB_AGENTS:
                        _SUB_AGENTS[tid_inner]["result"] = f"错误: {e}"
                        _SUB_AGENTS[tid_inner]["status"] = "failed"
                        _SUB_AGENTS[tid_inner]["done"] = True

        threading.Thread(target=_run_bg, args=(tid, full_prompt, model, agent), daemon=True).start()
        return f"[子Agent] ✅ 已启动\n  ID: {tid}\n  Agent: {agent or '通用'}\n  指令: {prompt[:200]}"

    # ── 同步模式 ──
    return _run_sub_agent(full_prompt, model=model)


def _run_sub_agent(prompt: str, model: str = "") -> str:
    """在隔离上下文中执行子 Agent。

    创建一个新的 Agent 实例，使用独立的会话状态。
    子 Agent 可通过 transcript 获取自己的工作流状态。
    """
    from .transcript import Transcript

    # 获取父 Agent 的配置
    parent_state = get_state()
    parent_config = getattr(parent_state, '_config', None) or {}

    # 构建子 Agent 配置（继承父配置，可覆盖模型）
    config = dict(parent_config)
    if model:
        config["model"] = model

    # 创建独立转录（可被子 Agent 的 plan/task 同步触发）
    transcript = Transcript(agent_id=f"sub-{time.time():.0f}")

    try:
        sub_agent = Agent(config=config, transcript=transcript)
        result = sub_agent.run(prompt)
        sub_agent.close()
        return result
    except Exception as e:
        tb = traceback.format_exc()
        return f"[子Agent错误] {e}\n{tb[:500]}"


def _list_agent_defs() -> str:
    """列出所有可用的 Agent 类型。"""
    agents = list_agents()
    if not agents:
        return "[子Agent] 无注册的 Agent 类型"
    lines = ["[子Agent] 可用 Agent 类型:"]
    for a in agents:
        lines.append(f"  {a['name']}")
        lines.append(f"    描述: {a['description']}")
        lines.append(f"    模型: {a['model']}")
        if a['tools']:
            lines.append(f"    工具: {', '.join(a['tools'])}")
    return "\n".join(lines)


def _list_sub_agents() -> str:
    """列出所有后台子 Agent。"""
    with _SUB_LOCK:
        if not _SUB_AGENTS:
            return "[子Agent] 无活跃任务"
        lines = ["[子Agent] 任务列表:"]
        for tid, info in _SUB_AGENTS.items():
            status_icon = "✅" if info["done"] else "▶"
            lines.append(f"  [{tid}] {status_icon} {info['agent']} | {info['prompt'][:50]}")
        return "\n".join(lines)


def _get_output(task_id: str) -> str:
    with _SUB_LOCK:
        info = _SUB_AGENTS.get(task_id)
    if not info:
        return f"[错误] 未找到任务: {task_id}"
    status = "完成" if info["done"] else "运行中"
    result = info.get("result", "")
    return f"[子Agent] {task_id}（{status}）\n{result[:2000]}"


def _stop_agent(task_id: str) -> str:
    with _SUB_LOCK:
        if task_id in _SUB_AGENTS:
            _SUB_AGENTS[task_id]["done"] = True
            _SUB_AGENTS[task_id]["status"] = "stopped"
            return f"[子Agent] 已终止: {task_id}"
    return f"[错误] 未找到任务: {task_id}"


def _wait_agent(task_id: str, timeout: int = 300) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _SUB_LOCK:
            info = _SUB_AGENTS.get(task_id)
        if info and info.get("done"):
            return f"[子Agent] 已完成\n{info.get('result', '')[:2000]}"
        time.sleep(0.5)
    return "[子Agent] 超时"
