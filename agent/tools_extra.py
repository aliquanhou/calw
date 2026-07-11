"""tools_extra — 实用增强：定时任务、文件监控、WebSocket。"""

from __future__ import annotations

import json
import os
import re
import time
import threading


# ═══════════════════════════════════════════
# 定时任务 (接入 scheduler.py)
# ═══════════════════════════════════════════

def _handle_schedule(action: str = "list", name: str = "", cron: str = "",
                      command: str = "", task_id: str = "") -> str:
    """定时任务管理。"""
    try:
        from .scheduler import get_scheduler, CronParser
        sched = get_scheduler()
        if not sched.is_running:
            sched.start()

        if action == "list":
            tasks = sched.list_tasks()
            if not tasks:
                return "无定时任务。使用 schedule add 创建。"
            lines = ["定时任务列表:"]
            for t in tasks:
                desc = CronParser.describe(t.cron_expr)
                status = "ON" if t.enabled else "OFF"
                last = f"上次: {time.strftime('%H:%M', time.localtime(t.last_run))}" if t.last_run else "未触发"
                lines.append(f"  [{t.id}] {t.name} ({status})")
                lines.append(f"    {desc} | {last} | {t.run_count}次")
            return "\n".join(lines)

        elif action == "add":
            if not name or not cron or not command:
                return "需指定 name, cron, command"
            t = sched.add_task(name, cron, command)
            desc = CronParser.describe(cron)
            return f"定时任务已创建: [{t.id}] {name}\n  触发: {desc}\n  命令: {command[:100]}"

        elif action == "remove":
            if not task_id:
                return "需指定 task_id"
            ok = sched.remove_task(task_id)
            return f"已删除: {task_id}" if ok else f"未找到: {task_id}"

        elif action == "events":
            events = sched.get_recent_events(20)
            if not events:
                return "暂无事件"
            lines = ["最近事件:"]
            for e in events[-10:]:
                ts = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
                lines.append(f"  [{ts}] {e.task_name}: {e.result[:80]}")
            return "\n".join(lines)

        return f"未知操作: {action} (可用: list/add/remove/events)"

    except Exception as e:
        return f"调度器错误: {e}"


# ═══════════════════════════════════════════
# 文件监控 (接入 watcher.py)
# ═══════════════════════════════════════════

def _handle_watch(action: str = "list", name: str = "", kind: str = "file",
                   path: str = "", pattern: str = "", watch_id: str = "") -> str:
    """文件/进程监控管理。"""
    try:
        from .watcher import get_watcher
        w = get_watcher()
        if action == "list":
            watches = w.list_watches()
            if not watches:
                return "无监控项。使用 watch add 创建。"
            lines = ["监控列表:"]
            for wt in watches:
                ev_count = len(wt.events)
                lines.append(f"  [{wt.id}] {wt.name} ({wt.kind}) 路径:{wt.path} 事件:{ev_count}")
            return "\n".join(lines)

        elif action == "add":
            if not name or not path:
                return "需指定 name, path"
            if kind not in ("file", "directory", "log", "process"):
                return "kind 需为 file/directory/log/process"
            wid = w.add_watch(name, kind, os.path.abspath(path), pattern)
            return f"监控已添加: [{wid}] {name} ({kind}: {path})"

        elif action == "remove":
            if not watch_id:
                return "需指定 watch_id"
            ok = w.remove_watch(watch_id)
            return f"已移除: {watch_id}" if ok else f"未找到: {watch_id}"

        elif action == "events":
            if not watch_id:
                return "需指定 watch_id"
            evs = w.get_events(watch_id, 20)
            if not evs:
                return f"暂无事件 ({watch_id})"
            lines = [f"事件 ({watch_id}):"]
            for e in evs[-15:]:
                ts = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
                lines.append(f"  [{ts}] {e.event_type}: {e.detail[:100]}")
            return "\n".join(lines)

        return f"未知操作: {action} (可用: list/add/remove/events)"

    except Exception as e:
        return f"监控器错误: {e}"


# ═══════════════════════════════════════════
# WebSocket 客户端
# ═══════════════════════════════════════════

def _handle_websocket(action: str = "connect", url: str = "",
                       message: str = "", timeout: int = 10) -> str:
    """WebSocket 客户端。"""
    try:
        import websocket as ws
    except ImportError:
        return "需安装 websocket-client: pip install websocket-client"

    try:
        if action == "connect":
            if not url:
                return "需指定 ws:// 或 wss:// URL"
            result = [f"连接: {url}"]
            wsa = ws.create_connection(url, timeout=timeout)
            result.append(f"已连接 (timeout={timeout}s)")
            wsa.settimeout(3)
            try:
                msg = wsa.recv()
                display = msg[:500] + ("..." if len(msg) > 500 else "")
                result.append(f"收到: {display}")
            except ws.WebSocketTimeoutException:
                result.append("(3s内无消息)")
            except Exception as e:
                result.append(f"(接收: {e})")
            wsa.close()
            result.append("已断开")
            return "\n".join(result)

        elif action == "send":
            if not url or not message:
                return "需指定 url 和 message"
            wsa = ws.create_connection(url, timeout=timeout)
            wsa.send(message)
            result = f"已发送 ({len(message)} 字节)"
            wsa.settimeout(5)
            try:
                reply = wsa.recv()
                display = reply[:500] + ("..." if len(reply) > 500 else "")
                result += f"\n回复: {display}"
            except ws.WebSocketTimeoutException:
                result += "\n(5s内无回复)"
            except Exception as e:
                result += f"\n(接收: {e})"
            wsa.close()
            return result

        elif action == "ping":
            if not url:
                return "需指定 URL"
            wsa = ws.create_connection(url, timeout=timeout)
            t0 = time.time()
            wsa.ping("ping")
            wsa.settimeout(timeout)
            try:
                op_code, data = wsa.recv_data_frame()
                elapsed = (time.time() - t0) * 1000
                wsa.close()
                return f"Pong! ({elapsed:.0f}ms)"
            except Exception as e:
                wsa.close()
                return f"Ping 失败: {e}"

        return f"未知操作: {action} (可用: connect/send/ping)"

    except Exception as e:
        return f"WebSocket 错误: {e}"
