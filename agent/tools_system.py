"""tools_system — 系统完全接管：服务、注册表、进程树、GUI自动化。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time


# ═══════════════════════════════════════════
# 服务控制
# ═══════════════════════════════════════════

def _run_ps(script: str, timeout: int = 30) -> str:
    """运行 PowerShell 脚本并返回输出。"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, errors="replace", timeout=timeout,
        )
        out = r.stdout.rstrip() if r.stdout else ""
        err = r.stderr.rstrip() if r.stderr else ""
        if err:
            out += f"\n[stderr]\n{err}"
        if r.returncode and not out:
            out += f"\nExit code: {r.returncode}"
        return out or "(无输出)"
    except subprocess.TimeoutExpired:
        return "超时"
    except Exception as e:
        return f"错误:{e}"


def _handle_service(action: str = "list", name: str = "", start_type: str = "") -> str:
    """服务控制：查询/启动/停止/重启 Windows 服务。"""
    if action == "list":
        output = _run_ps(
            "Get-Service | Where-Object {$_.Status -eq 'Running' -or $_.Status -eq 'Stopped'} "
            "| Select-Object -First 50 Name, DisplayName, Status, StartType "
            "| Format-Table -AutoSize"
        )
        return f"📋 服务列表 (前50):\n{output}"

    elif action == "search":
        if not name:
            return "需指定服务名"
        output = _run_ps(
            f"Get-Service -Name '*{name}*' -ErrorAction SilentlyContinue "
            f"| Select-Object Name, DisplayName, Status, StartType "
            f"| Format-Table -AutoSize"
        )
        return f"🔍 搜索服务: {name}\n{output}"

    elif action == "status":
        if not name:
            return "需指定服务名"
        output = _run_ps(
            f"Get-Service -Name '{name}' -ErrorAction SilentlyContinue "
            f"| Format-List Name, DisplayName, Status, StartType, ServiceType"
        )
        return f"📊 服务状态: {name}\n{output}"

    elif action == "start":
        if not name:
            return "需指定服务名"
        output = _run_ps(f"Start-Service -Name '{name}' -ErrorAction Stop; echo '已启动: {name}'")
        return f"▶️ 启动服务: {name}\n{output}"

    elif action == "stop":
        if not name:
            return "需指定服务名"
        output = _run_ps(f"Stop-Service -Name '{name}' -Force -ErrorAction Stop; echo '已停止: {name}'")
        return f"⏹ 停止服务: {name}\n{output}"

    elif action == "restart":
        if not name:
            return "需指定服务名"
        output = _run_ps(f"Restart-Service -Name '{name}' -Force -ErrorAction Stop; echo '已重启: {name}'")
        return f"🔄 重启服务: {name}\n{output}"

    elif action == "set_startup":
        if not name:
            return "需指定服务名"
        valid = {"auto": "Automatic", "manual": "Manual", "disabled": "Disabled", "delayed": "AutomaticDelayedStart"}
        st = valid.get(start_type.lower(), start_type) if start_type else "Manual"
        output = _run_ps(
            f"Set-Service -Name '{name}' -StartupType '{st}' -ErrorAction Stop; "
            f"echo '已设置 {name} 启动类型为: {st}'"
        )
        return f"⚙️ 设置服务启动类型: {name} → {st}\n{output}"

    return f"未知操作: {action} (可用: list/search/status/start/stop/restart/set_startup)"


# ═══════════════════════════════════════════
# 注册表操作
# ═══════════════════════════════════════════

def _handle_registry(action: str = "read", key: str = "", name: str = "", value: str = "") -> str:
    """注册表操作：读/写/删除键值。"""
    PS_ESCAPE = lambda s: s.replace("'", "''")  # noqa: E731

    if action == "read":
        if not key:
            return "需指定注册表路径 (如 HKLM:\\Software\\...)"
        if name:
            output = _run_ps(
                f"Get-ItemProperty -Path '{PS_ESCAPE(key)}' -Name '{PS_ESCAPE(name)}' -ErrorAction SilentlyContinue "
                f"| Format-List"
            )
            if "无输出" in output or not output.strip():
                output = _run_ps(
                    f"(Get-ItemProperty -Path '{PS_ESCAPE(key)}').'{PS_ESCAPE(name)}' -ErrorAction SilentlyContinue"
                )
        else:
            output = _run_ps(
                f"Get-ItemProperty -Path '{PS_ESCAPE(key)}' -ErrorAction SilentlyContinue "
                f"| Format-List *"
            )
        return f"📖 注册表读取: {key}\\{name}\n{output}"

    elif action == "write":
        if not key or not name:
            return "需指定 key, name"
        if value is None:
            value = ""
        # 判断值类型
        val_escaped = PS_ESCAPE(value)
        output = _run_ps(
            f"Set-ItemProperty -Path '{PS_ESCAPE(key)}' -Name '{PS_ESCAPE(name)}' -Value '{val_escaped}' -ErrorAction Stop; "
            f"echo '已写入: {key}\\{name} = {value}'"
        )
        return f"✏️ 注册表写入: {key}\\{name}\n{output}"

    elif action == "delete":
        if not key or not name:
            return "需指定 key, name"
        output = _run_ps(
            f"Remove-ItemProperty -Path '{PS_ESCAPE(key)}' -Name '{PS_ESCAPE(name)}' -ErrorAction Stop; "
            f"echo '已删除: {key}\\{name}'"
        )
        return f"🗑 注册表删除: {key}\\{name}\n{output}"

    elif action == "list_keys":
        if not key:
            return "需指定注册表路径"
        output = _run_ps(
            f"Get-ChildItem -Path '{PS_ESCAPE(key)}' -ErrorAction SilentlyContinue "
            f"| Select-Object Name, Property "
            f"| Format-Table -AutoSize"
        )
        return f"📂 注册表子键: {key}\n{output}"

    return f"未知操作: {action} (可用: read/write/delete/list_keys)"


# ═══════════════════════════════════════════
# 进程深度管理
# ═══════════════════════════════════════════

def _handle_process_v2(action: str = "list", name: str = "", pid: int = 0, sort_by: str = "cpu") -> str:
    """进程深度管理：树、排序、守护、等待。"""
    if action == "tree":
        _run_ps("chcp 65001 >$null")  # UTF-8
        output = _run_ps(
            "$p = Get-Process | Sort-Object CPU -Descending | Select-Object -First 5; "
            "$p | ForEach-Object { Write-Output \\\"$($_.Id) $($_.ProcessName) CPU:$($_.CPU) MEM:$([math]::Round($_.WorkingSet64/1MB,1))MB\\\" }"
        )
        return f"🌳 进程树 (Top 5 by CPU):\n{output}"

    if action == "tree_full":
        output = _run_ps(
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.ParentProcessId -ne 0 } | "
            "Select-Object ProcessId, Name, ParentProcessId, @{N='CPU';E={$_.KernelModeTime}} | "
            "Format-Table -AutoSize"
        )
        return f"🌳 进程父子关系:\n{output[:3000]}"

    if action == "top":
        count = 20
        sort_field = sort_by if sort_by in ("cpu", "mem", "id") else "cpu"
        sort_prop = {"cpu": "CPU", "mem": "WorkingSet64", "id": "Id"}
        prop = sort_prop.get(sort_field, "CPU")
        if sort_field == "mem":
            fmt = f"@{'{'}$_.WorkingSet64/1MB;f='0.0'{'}'}MB"
            output = _run_ps(
                f"Get-Process | Sort-Object {prop} -Descending | "
                f"Select-Object -First {count} Id, ProcessName, "
                f"@{'{'}N='CPU';E={'{'}($_.TotalProcessorTime.TotalSeconds){'}'}{'}'}, "
                f"@{'{'}N='MEM(MB)';E={'{'}[math]::Round($_.WorkingSet64/1MB,1){'}'}{'}'} "
                f"| Format-Table -AutoSize"
            )
        else:
            fmt = "$_.ProcessName"
            output = _run_ps(
                f"Get-Process | Sort-Object {prop} -Descending | "
                f"Select-Object -First {count} Id, ProcessName, CPU, "
                f"@{'{'}N='MEM(MB)';E={'{'}[math]::Round($_.WorkingSet64/1MB,1){'}'}{'}'} "
                f"| Format-Table -AutoSize"
            )
        return f"📊 进程 Top {count} (按{ {'cpu':'CPU','mem':'内存','id':'PID'} .get(sort_field, 'CPU')}排序):\n{output}"

    if action == "wait_exit":
        if not name and not pid:
            return "需指定 name 或 pid"
        if pid:
            output = _run_ps(
                f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
                f"if (-not $p) {{ echo '进程不存在' }} "
                f"else {{ echo '等待进程退出...'; Wait-Process -Id {pid} -Timeout 300; echo '进程已退出' }}"
            )
        else:
            output = _run_ps(
                f"$p = Get-Process -Name '{name}' -ErrorAction SilentlyContinue; "
                f"if (-not $p) {{ echo '进程不存在' }} "
                f"else {{ echo '等待进程退出...'; Wait-Process -Name '{name}' -Timeout 300; echo '进程已退出' }}"
            )
        return f"⏳ 等待进程: {name or pid}\n{output}"

    if action == "launch":
        if not name:
            return "需指定程序路径或命令"
        output = _run_ps(
            f"Start-Process -NoNewWindow -FilePath '{name}'; echo '已启动: {name}'"
        )
        return f"🚀 启动进程: {name}\n{output}"

    if action == "kill":
        if pid:
            output = _run_ps(
                f"Stop-Process -Id {pid} -Force -ErrorAction Stop; echo '已终止 PID: {pid}'"
            )
        elif name:
            output = _run_ps(
                f"Stop-Process -Name '{name}' -Force -ErrorAction Stop; echo '已终止: {name}'"
            )
        else:
            return "需指定 name 或 pid"
        return f"🔪 终止进程: {name or pid}\n{output}"

    if action == "list":
        output = _run_ps(
            "Get-Process | Sort-Object CPU -Descending | "
            "Select-Object -First 30 Id, ProcessName, CPU, "
            "@{N='MEM(MB)';E={[math]::Round($_.WorkingSet64/1MB,1)}} "
            "| Format-Table -AutoSize"
        )
        return f"📋 进程列表 (Top 30):\n{output}"

    return f"未知操作: {action} (可用: list/top/tree/wait_exit/launch/kill)"
