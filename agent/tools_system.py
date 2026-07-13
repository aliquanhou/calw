"""tools_system — 系统工具：服务、注册表、进程、GUI 自动化、监控。

v2.1 增强：
  - 统一返回格式 [前缀]
  - 所有错误返回使用统一格式
  - 更清晰的 action 分发
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from ._encoding import run as _run, popen as _popen


def _run_ps(script: str, timeout: int = 30) -> str:
    """运行 PowerShell 脚本并返回输出。"""
    try:
        r = _run(
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
        return "[超时]"
    except Exception as e:
        return f"[错误] {e}"


# ═══════════════════════════════════════════
# 服务控制
# ═══════════════════════════════════════════

def _handle_service(action: str = "list", name: str = "", start_type: str = "") -> str:
    """Windows 服务控制：list/search/status/start/stop/restart/set_startup。"""
    try:
        if action == "list":
            output = _run_ps(
                "Get-Service | Where-Object {$_.Status -eq 'Running' -or $_.Status -eq 'Stopped'} "
                "| Select-Object -First 50 Name, DisplayName, Status, StartType | Format-Table -AutoSize"
            )
            return f"[服务] 📋 列表 (前50):\n{output}"

        if action == "search":
            if not name:
                return "[错误] search 需要 name 参数"
            output = _run_ps(
                f"Get-Service -Name '*{name}*' -ErrorAction SilentlyContinue "
                f"| Select-Object Name, DisplayName, Status, StartType | Format-Table -AutoSize"
            )
            return f"[服务] 🔍 搜索: {name}\n{output}"

        if action == "status":
            if not name:
                return "[错误] status 需要 name 参数"
            output = _run_ps(
                f"Get-Service -Name '{name}' -ErrorAction SilentlyContinue "
                f"| Format-List Name, DisplayName, Status, StartType, ServiceType"
            )
            return f"[服务] 📊 状态: {name}\n{output}"

        if action == "start":
            if not name:
                return "[错误] start 需要 name 参数"
            output = _run_ps(f"Start-Service -Name '{name}' -ErrorAction Stop; echo '已启动'")
            return f"[服务] ▶️ 启动: {name}\n{output}"

        if action == "stop":
            if not name:
                return "[错误] stop 需要 name 参数"
            output = _run_ps(f"Stop-Service -Name '{name}' -Force -ErrorAction Stop; echo '已停止'")
            return f"[服务] ⏹ 停止: {name}\n{output}"

        if action == "restart":
            if not name:
                return "[错误] restart 需要 name 参数"
            output = _run_ps(f"Restart-Service -Name '{name}' -Force -ErrorAction Stop; echo '已重启'")
            return f"[服务] 🔄 重启: {name}\n{output}"

        if action == "set_startup":
            if not name:
                return "[错误] set_startup 需要 name 参数"
            valid = {"auto": "Automatic", "manual": "Manual", "disabled": "Disabled", "delayed": "AutomaticDelayedStart"}
            st = valid.get(start_type.lower(), start_type) if start_type else "Manual"
            output = _run_ps(
                f"Set-Service -Name '{name}' -StartupType '{st}' -ErrorAction Stop; echo '已设置'"
            )
            return f"[服务] ⚙️ 启动类型: {name} → {st}\n{output}"

        return f"[错误] 未知操作: {action}（可用: list/search/status/start/stop/restart/set_startup）"
    except Exception as e:
        return f"[错误] 服务操作失败: {e}"


# ═══════════════════════════════════════════
# 注册表操作
# ═══════════════════════════════════════════

def _handle_registry(action: str = "read", key: str = "", name: str = "", value: str = "") -> str:
    """注册表操作：read/write/delete/list_keys。"""
    try:
        _esc = lambda s: s.replace("'", "''")

        if action == "read":
            if not key:
                return "[错误] read 需要 key 参数（如 HKLM:\\Software\\...）"
            if name:
                output = _run_ps(
                    f"Get-ItemProperty -Path '{_esc(key)}' -Name '{_esc(name)}' -ErrorAction SilentlyContinue | Format-List"
                )
                if "无输出" in output or not output.strip():
                    output = _run_ps(
                        f"(Get-ItemProperty -Path '{_esc(key)}').'{_esc(name)}' -ErrorAction SilentlyContinue"
                    )
            else:
                output = _run_ps(
                    f"Get-ItemProperty -Path '{_esc(key)}' -ErrorAction SilentlyContinue | Format-List *"
                )
            return f"[注册表] 📖 读取: {key}\\{name}\n{output}"

        if action == "write":
            if not key or not name:
                return "[错误] write 需要 key 和 name 参数"
            output = _run_ps(
                f"Set-ItemProperty -Path '{_esc(key)}' -Name '{_esc(name)}' -Value '{_esc(value or '')}' -ErrorAction Stop; echo '已写入'"
            )
            return f"[注册表] ✏️ 写入: {key}\\{name}\n{output}"

        if action == "delete":
            if not key or not name:
                return "[错误] delete 需要 key 和 name 参数"
            output = _run_ps(
                f"Remove-ItemProperty -Path '{_esc(key)}' -Name '{_esc(name)}' -ErrorAction Stop; echo '已删除'"
            )
            return f"[注册表] 🗑 删除: {key}\\{name}\n{output}"

        if action == "list_keys":
            if not key:
                return "[错误] list_keys 需要 key 参数"
            output = _run_ps(
                f"Get-ChildItem -Path '{_esc(key)}' -ErrorAction SilentlyContinue | Select-Object Name, Property | Format-Table -AutoSize"
            )
            return f"[注册表] 📂 子键: {key}\n{output}"

        return f"[错误] 未知操作: {action}（可用: read/write/delete/list_keys）"
    except Exception as e:
        return f"[错误] 注册表操作失败: {e}"


# ═══════════════════════════════════════════
# 进程管理
# ═══════════════════════════════════════════

def _handle_process(action: str = "list", name: str = "", pid: int = 0, sort_by: str = "cpu") -> str:
    """进程管理：list/top/tree/wait_exit/launch/kill。"""
    try:
        if action == "list":
            output = _run_ps(
                "Get-Process | Sort-Object CPU -Descending | Select-Object -First 30 "
                "Id, ProcessName, CPU, @{N='MEM(MB)';E={[math]::Round($_.WorkingSet64/1MB,1)}} | Format-Table -AutoSize"
            )
            return f"[进程] 📋 Top 30:\n{output}"

        if action == "top":
            count = 20
            sort_field = sort_by if sort_by in ("cpu", "mem", "id") else "cpu"
            sort_prop = {"cpu": "CPU", "mem": "WorkingSet64", "id": "Id"}
            prop = sort_prop[sort_field]
            output = _run_ps(
                f"Get-Process | Sort-Object {prop} -Descending | Select-Object -First {count} "
                f"Id, ProcessName, CPU, @{{N='MEM(MB)';E={{[math]::Round($_.WorkingSet64/1MB,1)}}}} | Format-Table -AutoSize"
            )
            label = {"cpu": "CPU", "mem": "内存", "id": "PID"}.get(sort_field, "CPU")
            return f"[进程] 📊 Top {count}（按{label}）:\n{output}"

        if action == "tree":
            output = _run_ps(
                "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 | "
                "ForEach-Object { Write-Output \\\"$($_.Id) $($_.ProcessName) CPU:$($_.CPU) MEM:$([math]::Round($_.WorkingSet64/1MB,1))MB\\\" }"
            )
            return f"[进程] 🌳 Top 5 by CPU:\n{output}"

        if action == "tree_full":
            output = _run_ps(
                "Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -ne 0 } | "
                "Select-Object ProcessId, Name, ParentProcessId, @{N='CPU';E={$_.KernelModeTime}} | Format-Table -AutoSize"
            )
            return f"[进程] 🌳 父子关系:\n{output[:3000]}"

        if action == "wait_exit":
            if not name and not pid:
                return "[错误] wait_exit 需要 name 或 pid"
            if pid:
                output = _run_ps(
                    f"Wait-Process -Id {pid} -Timeout 300 -ErrorAction SilentlyContinue; echo '进程已退出'"
                )
            else:
                output = _run_ps(
                    f"Wait-Process -Name '{name}' -Timeout 300 -ErrorAction SilentlyContinue; echo '进程已退出'"
                )
            return f"[进程] ⏳ 等待: {name or pid}\n{output}"

        if action == "launch":
            if not name:
                return "[错误] launch 需要程序路径或命令"
            output = _run_ps(f"Start-Process -NoNewWindow -FilePath '{name}'; echo '已启动'")
            return f"[进程] 🚀 启动: {name}\n{output}"

        if action == "kill":
            if pid:
                output = _run_ps(f"Stop-Process -Id {pid} -Force -ErrorAction Stop; echo '已终止'")
            elif name:
                output = _run_ps(f"Stop-Process -Name '{name}' -Force -ErrorAction Stop; echo '已终止'")
            else:
                return "[错误] kill 需要 name 或 pid"
            return f"[进程] 🔪 终止: {name or pid}\n{output}"

        return f"[错误] 未知操作: {action}（可用: list/top/tree/tree_full/wait_exit/launch/kill）"
    except Exception as e:
        return f"[错误] 进程操作失败: {e}"


# v2.0 兼容别名
_handle_process_v2 = _handle_process


# ═══════════════════════════════════════════
# GUI 自动化
# ═══════════════════════════════════════════

def _handle_gui(action: str = "info", x: int = 0, y: int = 0,
                text: str = "", button: str = "left", key: str = "", query: str = "") -> str:
    """GUI 自动化：鼠标/键盘/截图/窗口控制。"""
    try:
        import pyautogui as pag
        pag.FAILSAFE = True
        pag.PAUSE = 0.3
    except ImportError:
        return "[错误] 需安装 pyautogui: pip install pyautogui"

    try:
        if action == "info":
            w, h = pag.size()
            xm, ym = pag.position()
            return f"[GUI] 🖥 {w}x{h} | 🖱 ({xm}, {ym})"

        if action == "click":
            if x or y:
                pag.click(x, y, button=button)
            else:
                pag.click(button=button)
            return f"[GUI] 🖱 点击 ({x}, {y}) {button}"

        if action == "double_click":
            pag.doubleClick(x, y) if (x or y) else pag.doubleClick()
            return f"[GUI] 🖱 双击 ({x}, {y})"

        if action == "right_click":
            pag.rightClick(x, y) if (x or y) else pag.rightClick()
            return f"[GUI] 🖱 右键 ({x}, {y})"

        if action == "move":
            pag.moveTo(x, y, duration=0.5)
            return f"[GUI] 🖱 移动到 ({x}, {y})"

        if action == "drag":
            if not text:
                return "[错误] drag 需要 text='dx,dy'"
            parts = text.split(",")
            if len(parts) == 2:
                dx, dy = int(parts[0]), int(parts[1])
                pag.drag(dx, dy, duration=0.5)
                return f"[GUI] 🖱 拖动 ({dx}, {dy})"
            return "[错误] 格式: text='dx,dy'"

        if action == "type":
            pag.write(text, interval=0.05)
            display = text[:50] + ("..." if len(text) > 50 else "")
            return f"[GUI] ⌨ 输入: {display}"

        if action == "keypress":
            if not key:
                return "[错误] keypress 需要 key（如 enter, esc, ctrl+c）"
            if "+" in key:
                pag.hotkey(*key.split("+"))
            else:
                pag.press(key)
            return f"[GUI] ⌨ 按键: {key}"

        if action == "scroll":
            pag.scroll(-y if y else -3)
            return f"[GUI] 📜 滚动 {y or 3} 单位"

        if action == "screenshot":
            import base64
            region = None
            if text:
                parts = text.split(",")
                if len(parts) == 4:
                    region = tuple(int(p) for p in parts)
            img = pag.screenshot(region=region)
            b64 = base64.b64encode(img.tobytes()).decode("utf-8")
            return f"[GUI_SCREENSHOT {img.width}x{img.height} base64={len(b64)}]"

        if action == "locate":
            if not query:
                return "[错误] locate 需要图像路径"
            try:
                pos = pag.locateOnScreen(query, confidence=0.8)
                if pos:
                    cx, cy = pag.center(pos)
                    return f"[GUI] 🔍 找到 '{query}' 在 ({int(cx)}, {int(cy)}) {pos}"
                return f"[GUI] 🔍 未找到 '{query}'"
            except pag.ImageNotFoundException:
                return f"[GUI] 🔍 未找到 '{query}'"
            except Exception as e:
                return f"[GUI] 查找失败: {e}"

        if action == "get_window":
            try:
                import pygetwindow as gw
                active = gw.getActiveWindow()
                results = []
                if active:
                    results.append(f"[GUI] 🪟 活动: {active.title}")
                for w in gw.getAllWindows()[:10]:
                    if w.visible:
                        results.append(f"  {w.title} ({w.width}x{w.height} @{w.left},{w.top})")
                return "\n".join(results) if results else "[GUI] 未获取到窗口信息"
            except ImportError:
                r = _run_ps(
                    "Add-Type @'\\n[System.Runtime.InteropServices.DllImport(\\\"user32.dll\\\")]\\n"
                    "public static extern IntPtr GetForegroundWindow();\\n"
                    "public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);\\n"
                    "'@ | Out-Null; "
                    "$hwnd = [Win32]::GetForegroundWindow(); "
                    "$sb = New-Object System.Text.StringBuilder 256; "
                    "[Win32]::GetWindowText($hwnd, $sb, 256) | Out-Null; "
                    "echo \"活动窗口: $($sb.ToString())\""
                )
                return f"[GUI] 🪟\n{r}"

        return f"[错误] 未知操作: {action}（可用: info/click/double_click/right_click/move/drag/type/keypress/scroll/screenshot/locate/get_window）"
    except Exception as e:
        return f"[GUI] 错误: {e}"


# ═══════════════════════════════════════════
# 系统监控
# ═══════════════════════════════════════════

def _handle_monitor(action: str = "resources", path: str = "",
                    interval: int = 1, name: str = "") -> str:
    """系统监控：resources/cpu/memory/disk/process_count/watch_file/network/uptime/process_events。"""
    try:
        if action == "resources":
            output = _run_ps(
                "Get-CimInstance Win32_Processor | Select-Object @{N='CPU%';E={$_.LoadPercentage}}; "
                "$os=Get-CimInstance Win32_OperatingSystem; "
                "$t=[math]::Round($os.TotalVisibleMemorySize/1MB,1); $f=[math]::Round($os.FreePhysicalMemory/1MB,1); "
                "Write-Output \"内存: $($t-$f)GB / ${t}GB ($([math]::Round(($t-$f)/$t*100,1))%)\"; "
                "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | "
                "Select-Object DeviceID, @{N='Free%';E={[math]::Round($_.FreeSpace/$_.Size*100,1)}}"
            )
            return f"[监控] 📊 系统资源:\n{output}"

        if action == "cpu":
            output = _run_ps(
                "Get-CimInstance Win32_Processor | Select-Object @{N='CPU%';E={$_.LoadPercentage}}, Name"
            )
            return f"[监控] 💻 CPU:\n{output}"

        if action == "memory":
            output = _run_ps(
                "$os=Get-CimInstance Win32_OperatingSystem; "
                "$t=[math]::Round($os.TotalVisibleMemorySize/1MB,1); $f=[math]::Round($os.FreePhysicalMemory/1MB,1); "
                "Write-Output \"总: ${t}GB  已用: $($t-$f)GB  可用: ${f}GB  使用率: $([math]::Round(($t-$f)/$t*100,1))%\""
            )
            return f"[监控] 🧠 内存:\n{output}"

        if action == "disk":
            output = _run_ps(
                "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | "
                "Select-Object DeviceID, @{N='Size(GB)';E={[math]::Round($_.Size/1GB,1)}}, "
                "@{N='Free(GB)';E={[math]::Round($_.FreeSpace/1GB,1)}}, "
                "@{N='Free%';E={[math]::Round($_.FreeSpace/$_.Size*100,1)}} | Format-Table -AutoSize"
            )
            return f"[监控] 💾 磁盘:\n{output}"

        if action == "process_count":
            output = _run_ps(
                "$p=Get-Process; Write-Output \"总数: $($p.Count)\"; "
                "$p | Group-Object ProcessName | Sort-Object Count -Descending | Select-Object -First 15 Name, Count | Format-Table -AutoSize"
            )
            return f"[监控] 📋 进程统计:\n{output}"

        if action == "watch_file":
            if not path:
                return "[错误] watch_file 需要 path 参数"
            output = _run_ps(
                f"$w=New-Object System.IO.FileSystemWatcher; $w.Path='{path.replace(chr(39), chr(39)*2)}'; "
                f"$w.IncludeSubdirectories=$true; $w.EnableRaisingEvents=$true; "
                f"$r=$w.WaitForChanged('All', 5000); "
                f"if ($r.TimedOut) {{ echo '(5s内无变更)' }} else {{ echo \"变更: $($r.ChangeType) $($r.Name)\" }}"
            )
            return f"[监控] 👁 文件: {path}\n{output}"

        if action == "network":
            output = _run_ps(
                "Get-CimInstance Win32_NetworkAdapter | Where-Object {$_.NetEnabled} | "
                "Select-Object Name, MACAddress, Speed, "
                "@{N='IP';E={(Get-CimInstance Win32_NetworkAdapterConfiguration -Filter \"Index=$($_.Index)\").IPAddress -join ','}} | Format-Table -AutoSize"
            )
            return f"[监控] 🌐 网络:\n{output}"

        if action == "uptime":
            output = _run_ps(
                "$os=Get-CimInstance Win32_OperatingSystem; $boot=$os.LastBootUpTime; "
                "$up=(Get-Date)-$boot; Write-Output \"启动: $boot\"; "
                "Write-Output \"运行: $($up.Days)天 $($up.Hours)小时 $($up.Minutes)分钟\""
            )
            return f"[监控] ⏱ 运行时间:\n{output}"

        if action == "process_events":
            output = _run_ps(
                "Get-Process | Sort-Object StartTime -Descending | Select-Object -First 15 "
                "Id, ProcessName, @{N='Start';E={$_.StartTime.ToString('HH:mm:ss')}} | Format-Table -AutoSize"
            )
            return f"[监控] 🆕 最近进程:\n{output}"

        return f"[错误] 未知操作: {action}（可用: resources/cpu/memory/disk/process_count/watch_file/network/uptime/process_events）"
    except Exception as e:
        return f"[监控] 错误: {e}"
