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


# ═══════════════════════════════════════════
# GUI 自动化 (pyautogui)
# ═══════════════════════════════════════════

def _handle_gui(action: str = "info", x: int = 0, y: int = 0,
                 text: str = "", button: str = "left",
                 key: str = "", query: str = "") -> str:
    """GUI 自动化：鼠标/键盘/屏幕/窗口控制。"""
    try:
        import pyautogui as pag
        pag.FAILSAFE = True
        pag.PAUSE = 0.3
    except ImportError:
        return "需安装 pyautogui: pip install pyautogui"

    try:
        if action == "info":
            w, h = pag.size()
            xm, ym = pag.position()
            return f"🖥 屏幕: {w}x{h}\n🖱 鼠标: ({xm}, {ym})"

        elif action == "click":
            if x or y:
                pag.click(x, y, button=button)
            else:
                pag.click(button=button)
            return f"🖱 点击: ({x}, {y}) {button}"

        elif action == "double_click":
            if x or y:
                pag.doubleClick(x, y)
            else:
                pag.doubleClick()
            return f"🖱 双击: ({x}, {y})"

        elif action == "right_click":
            if x or y:
                pag.rightClick(x, y)
            else:
                pag.rightClick()
            return f"🖱 右键: ({x}, {y})"

        elif action == "move":
            dur = 0.5
            pag.moveTo(x, y, duration=dur)
            return f"🖱 移动到: ({x}, {y})"

        elif action == "drag":
            if not text:
                return "需指定目标坐标 (text='x,y')"
            parts = text.split(",")
            if len(parts) == 2:
                dx, dy = int(parts[0]), int(parts[1])
                pag.drag(dx, dy, duration=0.5)
                return f"🖱 拖动: ({dx}, {dy})"
            return "格式: text='dx,dy'"

        elif action == "type":
            pag.write(text, interval=0.05)
            display = text[:50] + ("..." if len(text) > 50 else "")
            return f"⌨ 输入: {display}"

        elif action == "keypress":
            if not key:
                return "需指定 key (如 enter, esc, tab, ctrl+c)"
            pag.hotkey(*key.split("+")) if "+" in key else pag.press(key)
            return f"⌨ 按键: {key}"

        elif action == "scroll":
            pag.scroll(-y if y else -3)  # 负=向下
            return f"📜 滚动: {y or 3} 单位"

        elif action == "screenshot":
            import base64
            region = None
            if text:
                parts = text.split(",")
                if len(parts) == 4:
                    region = tuple(int(p) for p in parts)
            img = pag.screenshot(region=region)
            b64 = base64.b64encode(img.tobytes()).decode("utf-8")
            return f"[GUI_SCREENSHOT {img.width}x{img.height} base64={len(b64)}]"

        elif action == "locate":
            if not query:
                return "需指定要查找的图像路径 (query)"
            try:
                pos = pag.locateOnScreen(query, confidence=0.8)
                if pos:
                    cx, cy = pag.center(pos)
                    return f"🔍 找到 '{query}' 在 ({int(cx)}, {int(cy)}) 区域 {pos}"
                return f"🔍 未找到 '{query}'"
            except pag.ImageNotFoundException:
                return f"🔍 未找到 '{query}'"
            except Exception as e:
                return f"查找失败:{e}"

        elif action == "get_window":
            # 获取活动窗口信息
            results = []
            try:
                import pygetwindow as gw
                active = gw.getActiveWindow()
                if active:
                    results.append(f"活动窗口: {active.title}")
                for w in gw.getAllWindows()[:10]:
                    if w.visible:
                        results.append(f"  {w.title} ({w.width}x{w.height} @{w.left},{w.top})")
            except ImportError:
                # Fallback to PowerShell
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
                return f"🪟 窗口信息:\n{r}"
            return "\n".join(results) if results else "未获取到窗口信息"

        return f"未知操作: {action} (可用: info/click/double_click/right_click/move/drag/type/keypress/scroll/screenshot/locate/get_window)"

    except Exception as e:
        return f"GUI 操作错误: {e}"
