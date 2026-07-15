"""tools_extra — 实用增强：定时任务、文件监控、WebSocket。

v2.1 重写：
  - 统一返回格式 + 类型注解
  - 更清晰的 action 分发逻辑
  - 完善的异常处理
"""

from __future__ import annotations

import json
import os
import re
import time
import threading


# ═══════════════════════════════════════════
# 定时任务
# ═══════════════════════════════════════════

def _handle_schedule(action: str = "list", name: str = "", cron: str = "",
                     command: str = "", task_id: str = "") -> str:
    """定时任务管理：list/add/remove/events。

    Args:
        action: list | add | remove | events
        name: 任务名（add 时必填）
        cron: cron 表达式（add 时必填）
        command: 要执行的命令（add 时必填）
        task_id: 任务 ID（remove/events 时必填）

    Returns:
        操作结果
    """
    try:
        from .scheduler import get_scheduler, CronParser
        sched = get_scheduler()
        if not sched.is_running:
            sched.start()

        if action == "list":
            tasks = sched.list_tasks()
            if not tasks:
                return "[定时] 无任务。使用 schedule add 创建"
            lines = ["[定时] 任务列表:"]
            for t in tasks:
                desc = CronParser.describe(t.cron_expr)
                status = "🟢" if t.enabled else "⚪"
                last = f"上次: {time.strftime('%H:%M', time.localtime(t.last_run))}" if t.last_run else "未触发"
                lines.append(f"  [{t.id}] {t.name} {status}")
                lines.append(f"    {desc} | {last} | {t.run_count}次")
            return "\n".join(lines)

        elif action == "add":
            if not name or not cron or not command:
                return "[错误] add 需要 name, cron, command 参数"
            t = sched.add_task(name, cron, command)
            desc = CronParser.describe(cron)
            return f"[定时] ✅ 已创建 [{t.id}] {name}\n  触发: {desc}\n  命令: {command[:100]}"

        elif action == "remove":
            if not task_id:
                return "[错误] remove 需要 task_id 参数"
            ok = sched.remove_task(task_id)
            return f"[定时] 已删除: {task_id}" if ok else f"[错误] 未找到: {task_id}"

        elif action == "events":
            events = sched.get_recent_events(20)
            if not events:
                return "[定时] 暂无事件"
            lines = ["[定时] 最近事件:"]
            for e in events[-10:]:
                ts = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
                lines.append(f"  [{ts}] {e.task_name}: {e.result[:80]}")
            return "\n".join(lines)

        return f"[错误] 未知操作: {action}（可用: list/add/remove/events）"

    except Exception as e:
        return f"[错误] 调度器: {e}"


# ═══════════════════════════════════════════
# 文件监控
# ═══════════════════════════════════════════

def _handle_watch(action: str = "list", name: str = "", kind: str = "file",
                  path: str = "", pattern: str = "", watch_id: str = "") -> str:
    """文件/进程监控管理：list/add/remove/events。

    Args:
        action: list | add | remove | events
        name: 监控名（add 时必填）
        kind: 类型 file|directory|log|process
        path: 路径（add 时必填）
        pattern: 匹配模式
        watch_id: 监控 ID（remove/events 时必填）

    Returns:
        操作结果
    """
    try:
        from .watcher import get_watcher
        w = get_watcher()

        if action == "list":
            watches = w.list_watches()
            if not watches:
                return "[监控] 无监控项。使用 watch add 创建"
            lines = ["[监控] 列表:"]
            for wt in watches:
                ev_count = len(wt.events)
                lines.append(f"  [{wt.id}] {wt.name} ({wt.kind}) 路径:{wt.path} 事件:{ev_count}")
            return "\n".join(lines)

        elif action == "add":
            if not name or not path:
                return "[错误] add 需要 name, path 参数"
            if kind not in ("file", "directory", "log", "process"):
                return "[错误] kind 须为 file/directory/log/process"
            wid = w.add_watch(name, kind, os.path.abspath(path), pattern)
            return f"[监控] ✅ 已添加 [{wid}] {name}（{kind}: {path}）"

        elif action == "remove":
            if not watch_id:
                return "[错误] remove 需要 watch_id 参数"
            ok = w.remove_watch(watch_id)
            return f"[监控] 已移除: {watch_id}" if ok else f"[错误] 未找到: {watch_id}"

        elif action == "events":
            if not watch_id:
                return "[错误] events 需要 watch_id 参数"
            evs = w.get_events(watch_id, 20)
            if not evs:
                return f"[监控] 暂无事件（{watch_id}）"
            lines = [f"[监控] 事件（{watch_id}）:"]
            for e in evs[-15:]:
                ts = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
                lines.append(f"  [{ts}] {e.event_type}: {e.detail[:100]}")
            return "\n".join(lines)

        return f"[错误] 未知操作: {action}（可用: list/add/remove/events）"

    except Exception as e:
        return f"[错误] 监控器: {e}"


# ═══════════════════════════════════════════
# WebSocket 客户端
# ═══════════════════════════════════════════

def _handle_websocket(action: str = "connect", url: str = "",
                      message: str = "", timeout: int = 10) -> str:
    """WebSocket 客户端：connect/send/ping。

    Args:
        action: connect（连接+接收）| send（发送+接收回复）| ping（测试延迟）
        url: ws:// 或 wss:// URL
        message: 要发送的消息
        timeout: 超时秒数

    Returns:
        操作结果
    """
    try:
        import websocket as ws
    except ImportError:
        return "[错误] 需安装 websocket-client: pip install websocket-client"

    try:
        if action == "connect":
            if not url:
                return "[错误] connect 需要 url 参数（ws:// 或 wss://）"
            wsa = ws.create_connection(url, timeout=timeout)
            wsa.settimeout(3)
            lines = [f"[WS] ✅ 已连接 {url}"]
            try:
                msg = wsa.recv()
                display = msg[:500] + ("..." if len(msg) > 500 else "")
                lines.append(f"  收到: {display}")
            except ws.WebSocketTimeoutException:
                lines.append("  (3s内无消息)")
            except Exception as e:
                lines.append(f"  (接收错误: {e})")
            wsa.close()
            lines.append("  🔒 已断开")
            return "\n".join(lines)

        elif action == "send":
            if not url or not message:
                return "[错误] send 需要 url 和 message 参数"
            wsa = ws.create_connection(url, timeout=timeout)
            wsa.send(message)
            wsa.settimeout(5)
            result = f"[WS] ✅ 已发送（{len(message)} 字节）"
            try:
                reply = wsa.recv()
                display = reply[:500] + ("..." if len(reply) > 500 else "")
                result += f"\n  回复: {display}"
            except ws.WebSocketTimeoutException:
                result += "\n  (5s内无回复)"
            except Exception as e:
                result += f"\n  (接收错误: {e})"
            wsa.close()
            result += "\n  🔒 已断开"
            return result

        elif action == "ping":
            if not url:
                return "[错误] ping 需要 url 参数"
            wsa = ws.create_connection(url, timeout=timeout)
            t0 = time.time()
            wsa.ping("ping")
            wsa.settimeout(timeout)
            try:
                op_code, data = wsa.recv_data_frame()
                elapsed = (time.time() - t0) * 1000
                wsa.close()
                return f"[WS] 🏓 Pong! ({elapsed:.0f}ms)"
            except Exception as e:
                wsa.close()
                return f"[WS] Ping 失败: {e}"

        return f"[错误] 未知操作: {action}（可用: connect/send/ping）"

    except Exception as e:
        return f"[错误] WebSocket: {e}"
