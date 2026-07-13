"""tools_plan — 计划 & 后台任务管理。

v2.1 重写：
  - 统一返回格式 + 类型注解
  - 更清晰的 action 分发
  - 使用文件持久化替代全局变量
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import uuid

_BACKGROUND_TASKS: dict[str, dict] = {}
_BT_LOCK = threading.Lock()
_PLAN_COUNTER: int = 0


# ═══════════════════════════════════════════
# 后台任务
# ═══════════════════════════════════════════

def _handle_background(action: str = "list", command: str = "", task_id: str = "",
                       pattern: str = "", timeout: int = 300) -> str:
    """后台任务：start/list/output/stop/stop_all/wait。"""
    global _BACKGROUND_TASKS
    try:
        if action == "start":
            if not command:
                return "[错误] start 需要 command 参数"
            tid = uuid.uuid4().hex[:8]
            p = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", command],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            with _BT_LOCK:
                _BACKGROUND_TASKS[tid] = {
                    "proc": p, "command": command[:100],
                    "started": time.strftime("%H:%M:%S"),
                    "stdout": [], "stderr": [], "done": False,
                }

            def _collect(stream, target, tid_inner):
                for line in iter(stream.readline, ""):
                    with _BT_LOCK:
                        if tid_inner in _BACKGROUND_TASKS:
                            _BACKGROUND_TASKS[tid_inner][target].append(line.rstrip())
                stream.close()
                with _BT_LOCK:
                    if tid_inner in _BACKGROUND_TASKS:
                        _BACKGROUND_TASKS[tid_inner]["done"] = True

            threading.Thread(target=_collect, args=(p.stdout, "stdout", tid), daemon=True).start()
            threading.Thread(target=_collect, args=(p.stderr, "stderr", tid), daemon=True).start()
            return f"[后台] ✅ 已启动\n  ID: {tid}\n  命令: {command[:200]}"

        elif action == "list":
            with _BT_LOCK:
                if not _BACKGROUND_TASKS:
                    return "[后台] 无任务"
                return "[后台] 任务列表:\n" + "\n".join(
                    f"  [{tid}] {'✅' if t['done'] else '▶'} {t['started']} | {t['command']}"
                    for tid, t in _BACKGROUND_TASKS.items()
                )

        elif action == "output":
            with _BT_LOCK:
                t = _BACKGROUND_TASKS.get(task_id)
            if not t:
                return f"[错误] 未找到任务: {task_id}"
            lines = [f"[后台] {task_id}（{'完成' if t['done'] else '运行'}）"]
            if t["stdout"]:
                lines.append("  stdout:\n" + "\n".join(t["stdout"][-50:]))
            if t["stderr"]:
                lines.append("  stderr:\n" + "\n".join(t["stderr"][-20:]))
            return "\n".join(lines)

        elif action == "stop":
            with _BT_LOCK:
                t = _BACKGROUND_TASKS.get(task_id)
            if not t:
                return f"[错误] 未找到任务: {task_id}"
            t["proc"].terminate()
            t["done"] = True
            return f"[后台] 已终止: {task_id}"

        elif action == "stop_all":
            with _BT_LOCK:
                tids = list(_BACKGROUND_TASKS.keys())
            for tid in tids:
                with _BT_LOCK:
                    t = _BACKGROUND_TASKS.get(tid)
                if t and not t["done"]:
                    t["proc"].terminate()
                    t["done"] = True
            return f"[后台] 已终止 {len(tids)} 个任务"

        elif action == "wait":
            with _BT_LOCK:
                t = _BACKGROUND_TASKS.get(task_id)
            if not t:
                return f"[错误] 未找到任务: {task_id}"
            if t["done"]:
                return "[后台] 已完成"
            dl = time.time() + timeout
            while time.time() < dl:
                with _BT_LOCK:
                    t = _BACKGROUND_TASKS.get(task_id)
                if t and t["done"]:
                    return "[后台] 已完成"
                if pattern and t and re.search(pattern, "\n".join(t["stdout"]), re.I):
                    return "[后台] 匹配成功"
                time.sleep(0.5)
            return "[后台] 超时"

        return f"[错误] 未知操作: {action}（可用: start/list/output/stop/stop_all/wait）"
    except Exception as e:
        return f"[错误] 后台任务失败: {e}"


# ═══════════════════════════════════════════
# 计划管理
# ═══════════════════════════════════════════

def _handle_plan(action: str = "list", title: str = "", plan_id: str = "",
                 steps: str = "", step_index: int = 0, step_status: str = "") -> str:
    """计划管理：create/update/list/show。"""
    global _PLAN_COUNTER
    PLANS_DIR = os.path.join(os.path.dirname(__file__), "..", ".claude", "plans")
    os.makedirs(PLANS_DIR, exist_ok=True)

    try:
        # 动作别名映射（LLM 常说的词 vs 工具实际接受的词）
        action_aliases = {
            "update_step": "update",
            "update_status": "update",
            "show_plan": "show",
            "list_plans": "list",
            "create_plan": "create",
            "new_plan": "create",
        }
        action = action_aliases.get(action, action)

        if action == "create":
            if not title or not steps:
                return "[错误] create 需要 title 和 steps 参数"
            try:
                step_list = json.loads(steps)
            except json.JSONDecodeError:
                return "[错误] steps 须为 JSON 数组"
            if not isinstance(step_list, list):
                return "[错误] steps 须为数组"

            for i, s in enumerate(step_list):
                if isinstance(s, str):
                    step_list[i] = {"id": i, "step": s, "status": "pending", "depends_on": []}
                elif isinstance(s, dict):
                    s.setdefault("id", i)
                    s.setdefault("status", "pending")
                    s.setdefault("depends_on", [])

            _PLAN_COUNTER += 1
            pid = f"plan-{_PLAN_COUNTER}"
            plan_data = {
                "id": pid, "title": title, "steps": step_list,
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(os.path.join(PLANS_DIR, f"{pid}.json"), "w", encoding="utf-8") as f:
                json.dump(plan_data, f, ensure_ascii=False, indent=2)

            done = sum(1 for s in step_list if s.get("status") == "completed")
            lines = [f"[计划] ✅ [{pid}] {title}（{done}/{len(step_list)}）"]
            for i, s in enumerate(step_list):
                dep = ""
                if s.get("depends_on"):
                    dep = f" [依赖: {','.join(str(x) for x in s['depends_on'])}]"
                ic = "x" if s.get("status") == "completed" else "~" if s.get("status") == "in_progress" else " "
                lines.append(f"  [{i}] [{ic}] {s['step']}{dep}")
            return "\n".join(lines)

        elif action == "update":
            plan_file = os.path.join(PLANS_DIR, f"{plan_id}.json")
            if os.path.exists(plan_file):
                with open(plan_file, "r", encoding="utf-8") as f:
                    pl = json.load(f)
            else:
                return f"[错误] 未找到计划: {plan_id}"
            sl = pl["steps"]
            if step_index < 0 or step_index >= len(sl):
                return f"[错误] step {step_index} 超出（0-{len(sl)-1}）"
            if step_status not in ("pending", "in_progress", "completed"):
                return f"[错误] 无效状态: {step_status}"
            if step_status == "in_progress":
                for dep in sl[step_index].get("depends_on", []):
                    if dep < len(sl) and sl[dep].get("status") != "completed":
                        return f"[错误] step {step_index} 依赖 step {dep} 未完成"
            sl[step_index]["status"] = step_status
            pl["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(plan_file, "w", encoding="utf-8") as f:
                json.dump(pl, f, ensure_ascii=False, indent=2)
            done = sum(1 for s in sl if s.get("status") == "completed")
            r = f"[计划] [{plan_id}] step {step_index} → {step_status}（{done}/{len(sl)}）"
            if step_status == "completed":
                for i, s in enumerate(sl):
                    if s.get("status") == "pending" and all(
                        d < len(sl) and sl[d].get("status") == "completed" for d in s.get("depends_on", [])
                    ):
                        r += f"\n  下一步: step {i}「{s['step']}」"
                        break
            return r

        elif action == "list":
            plans = []
            if os.path.exists(PLANS_DIR):
                for fn in sorted(os.listdir(PLANS_DIR)):
                    if fn.endswith(".json"):
                        try:
                            with open(os.path.join(PLANS_DIR, fn), "r", encoding="utf-8") as f:
                                p = json.load(f)
                            d = sum(1 for s in p.get("steps", []) if s.get("status") == "completed")
                            plans.append(f"  [{p['id']}] {p['title']}（{d}/{len(p['steps'])}）")
                        except Exception:
                            pass
            return "[计划]\n" + "\n".join(plans) if plans else "[计划] 无计划"

        elif action == "show":
            plan_file = os.path.join(PLANS_DIR, f"{plan_id}.json")
            if os.path.exists(plan_file):
                with open(plan_file, "r", encoding="utf-8") as f:
                    pl = json.load(f)
            else:
                return f"[错误] 未找到计划: {plan_id}"
            sl = pl["steps"]
            m = {"pending": " ", "in_progress": "~", "completed": "x"}
            d = sum(1 for s in sl if s.get("status") == "completed")
            lines = [f"[计划] {pl['title']}（{d}/{len(sl)}）", f"  创建: {pl.get('created', '?')}"]
            for i, s in enumerate(sl):
                dep = ""
                if s.get("depends_on"):
                    dep = f" [依赖: {','.join(str(x) for x in s['depends_on'])}]"
                lines.append(f"  [{i}] [{m.get(s.get('status', 'pending'), ' ')}] {s['step']}{dep}")
            return "\n".join(lines)

        return f"[错误] 未知操作: {action}（可用: create/update/list/show）"
    except Exception as e:
        return f"[错误] 计划操作失败: {e}"


# ═══════════════════════════════════════════
# 任务状态 + 项目记忆
# ═══════════════════════════════════════════

def _handle_task(status: str = "", message: str = "") -> str:
    """标记步骤状态。status: start/progress/done/fail"""
    icons = {"start": "▶", "progress": "~", "done": "✅", "fail": "❌"}
    msg = f"  {message}" if message else ""
    return f"{icons.get(status, '·')} {status}{msg}"


def _handle_project_memory(action: str = "read", content: str = "") -> str:
    """项目记忆读写（CLAUDE.md）。action: read/write/append"""
    try:
        from .memory import save_project_memory, load_project_memory
        if action == "read":
            m = load_project_memory()
            return f"## 项目记忆\n\n{m}" if m else "[记忆] 项目记忆为空"
        if action == "write":
            return save_project_memory(content) if content else "[错误] write 需要 content"
        if action == "append":
            c = load_project_memory()
            return save_project_memory((c + "\n" + content) if c else content)
        return f"[错误] 未知: {action}（read/write/append）"
    except Exception as e:
        return f"[错误] 项目记忆: {e}"
