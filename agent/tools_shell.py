"""tools_shell — Shell 命令执行。

v2.1 重写：
  - 统一返回格式
  - 类型注解
  - BuildRunner 优化（重试、超时、心跳）
  - 自愈机制（清理孤儿进程）
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time

from .tools_core import smart_truncate, _TOOL_RESULT_MAX_LENGTH
from ._encoding import enc


# ── 自愈（清理孤儿进程）──

def _self_heal() -> str:
    """清理孤儿进程（Windows 专用）。"""
    if sys.platform != "win32":
        return ""
    try:
        actions = []
        cp = os.getpid()

        def kill_proc(pid: int) -> bool:
            return subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=5,
            ).returncode == 0

        # 清理孤儿 node.exe（expo）
        r = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                'Get-CimInstance Win32_Process -Filter "Name=\'node.exe\'" '
                "| Where-Object {$_.CommandLine -match 'expo'} "
                "| Select-Object -ExpandProperty ProcessId",
            ],
            capture_output=True, text=True, timeout=10, errors="replace",
        )
        for line in r.stdout.strip().split("\n"):
            p = line.strip()
            if p and p.isdigit():
                pi = int(p)
                if pi != cp and kill_proc(pi):
                    actions.append(f"杀expo PID{pi}")

        # 清理孤儿 Python agent 进程
        r = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f'Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'" '
                f"| Where-Object {{$_.ProcessId -ne {cp} -and $_.CommandLine -match 'agent.app'}} "
                "| Select-Object -ExpandProperty ProcessId",
            ],
            capture_output=True, text=True, timeout=10, errors="replace",
        )
        for line in r.stdout.strip().split("\n"):
            p = line.strip()
            if p and p.isdigit():
                pi = int(p)
                if kill_proc(pi):
                    actions.append(f"杀旧agent PID{pi}")

        return f"[自愈] {'; '.join(actions)}" if actions else ""
    except Exception:
        return ""


# ── BuildRunner ──

class BuildRunner:
    """长时间运行命令的执行器，支持重试和实时回调。"""

    def __init__(self):
        self.attempt = 0
        self.max_retries = 2

    def run(self, cmd: str, scmd: list[str], timeout: int, output_callback=None) -> str:
        self.attempt = 0
        last_result = ""
        while self.attempt <= self.max_retries:
            self.attempt += 1
            if self.attempt > 1:
                hr = _self_heal()
                if hr and output_callback:
                    output_callback(f"[重试 {self.attempt}/{self.max_retries}] {hr}")
            r = self._run_once(cmd, scmd, timeout, output_callback)
            last_result = r
            if self.attempt <= self.max_retries and self._is_retryable(r):
                if output_callback:
                    output_callback(f"[重试 {self.attempt}/{self.max_retries}] 清理...")
                self._cleanup(cmd)
                continue
            break
        return last_result

    def _run_once(self, cmd: str, scmd: list[str], timeout: int, output_callback=None) -> str:
        hs = threading.Event()
        try:
            p = subprocess.Popen(
                scmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding=_enc, errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if output_callback:
                def heartbeat():
                    while not hs.is_set():
                        hs.wait(30)
                        if not hs.is_set():
                            try:
                                output_callback("")
                            except Exception:
                                pass
                threading.Thread(target=heartbeat, daemon=True).start()

            lines = []
            dl = time.time() + timeout
            assert p.stdout is not None
            for rl in iter(p.stdout.readline, ""):
                if time.time() > dl:
                    p.kill()
                    return f"[超时] 命令超过 {timeout}s\n" + "".join(lines)
                l = rl.rstrip()
                if l:
                    lines.append(l + "\n")
                if output_callback:
                    output_callback(l + "\n")
            p.stdout.close()
            se = p.stderr.read() if p.stderr else ""
            p.wait()
            r = "".join(lines)
            if se:
                r += "\nSTDERR:\n" + se.rstrip()
            r += f"\nExit code: {p.returncode}"
            hs.set()

            if p.returncode and r.strip():
                try:
                    from .build_patterns import get_engine
                    m = get_engine().match(r)
                    if m and m.get("fix"):
                        r += f"\n[模式] {m['label']}\n建议: {m['fix']}"
                except Exception:
                    pass
            return r
        except Exception as e:
            return f"[错误] 执行出错: {e}"
        finally:
            hs.set()

    def _is_retryable(self, result: str) -> bool:
        patterns = [
            "EADDRINUSE", "port already in use", "address already in use",
            "watchdog", "timed out", "超时", "Connection refused",
            "socket hang up", "EPIPE", "ECONNRESET", "ETIMEDOUT",
        ]
        return any(p.lower() in result.lower() for p in patterns)

    def _cleanup(self, cmd: str):
        try:
            if "expo" in cmd:
                r = subprocess.run(
                    [
                        "powershell", "-NoProfile", "-Command",
                        'Get-CimInstance Win32_Process -Filter "Name=\'node.exe\'" '
                        "| Where-Object {$_.CommandLine -match 'expo'} "
                        "| Select-Object -ExpandProperty ProcessId",
                    ],
                    capture_output=True, text=True, timeout=10, errors="replace",
                )
                for line in r.stdout.strip().split("\n"):
                    p = line.strip()
                    if p and p.isdigit():
                        pi = int(p)
                        subprocess.run(["taskkill", "/F", "/PID", str(pi)], capture_output=True, timeout=5)
        except Exception:
            pass


# ── PowerShell 执行 ──

def _run_powershell(script: str) -> str:
    """执行 PowerShell 脚本。

    Args:
        script: PowerShell 命令

    Returns:
        命令输出
    """
    try:
        from ._encoding import run as _ps_run
        p = _ps_run(
            ["powershell", "-NoProfile", "-Command", script],
            timeout=30,
        )
        o = p.stdout.rstrip() if p.stdout else ""
        e = p.stderr.rstrip() if p.stderr else ""
        if e:
            o += f"\n[stderr]\n{e}"
        if p.returncode and not o:
            o += f"\nExit code: {p.returncode}"
        return o or "(无输出)"
    except subprocess.TimeoutExpired:
        return "[超时] PowerShell 命令超过 30s"
    except Exception as ex:
        return f"[错误] PowerShell 执行失败: {ex}"


# ── bash 工具主入口 ──

def _handle_bash(command: str = "", timeout: int = 120, output_callback=None) -> str:
    """执行命令。运行 shell 命令并返回输出。

    长时间运行命令（构建、安装）自动延长超时。
    支持输出回调实现流式推送。

    Args:
        command: 要执行的命令
        timeout: 超时秒数（默认 120，安装类命令自动延长到 300）
        output_callback: 输出回调函数（用于 GUI 流式显示）

    Returns:
        命令输出
    """
    if not command:
        return "[错误] bash 需要 command 参数"

    # 强制 timeout 为 int（LLM 有时传字符串）
    if not isinstance(timeout, int):
        try:
            timeout = int(timeout)
        except (ValueError, TypeError):
            timeout = 120

    # 超时调整 — 长时间构建命令自动延长
    _build_keywords = ["pip install", "npm install", "build", "apk", "gradle",
                        "mvn ", "make ", "cmake", "python setup", "bundle",
                        "expo", "npx "]
    if any(k in command for k in _build_keywords):
        timeout = max(timeout, 600)
    timeout = min(timeout, 3600)  # 最大 60 分钟

    # 自愈检查（构建类命令）
    heal_result = ""
    is_build = any(k in command for k in ["expo", "npx ", "npm ", "pip ", "npx", "build", "apk", "gradle", "make"])
    if is_build:
        heal_result = _self_heal()
        if heal_result and output_callback:
            output_callback(f"{heal_result}")

    # 每次命令执行前释放 MMAP 文件锁（防止文件被锁导致无法复制/写入/删除）
    try:
        from .file_cache import release_cache
        release_cache()
    except Exception:
        pass

    is_interactive = is_build  # 所有构建命令都用 BuildRunner（流式 + 心跳 + 超时终止）

    # 系统编码（统一来自 _encoding.py）
    _enc = __import__('agent._encoding', fromlist=['enc']).enc

    try:
        # 选择 shell
        if sys.platform == "win32":
            n = command.replace(" && ", " ; ") if " && " in command else command
            shell_cmd = ["powershell", "-NoProfile", "-Command", n]
        else:
            shell_cmd = ["bash", "-c", command]

        if output_callback and is_interactive:
            # 交互模式：BuildRunner + 实时回调
            result = BuildRunner().run(command, shell_cmd, timeout, output_callback)
            return smart_truncate(result, _TOOL_RESULT_MAX_LENGTH) or "(无输出)"

        elif output_callback:
            # 流式输出模式
            hs = threading.Event()

            def heartbeat():
                while not hs.is_set():
                    hs.wait(30)
                    if not hs.is_set():
                        try:
                            output_callback("")
                        except Exception:
                            pass
            threading.Thread(target=heartbeat, daemon=True).start()

            p = subprocess.Popen(
                shell_cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding=_enc, errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            lines = []
            dl = time.time() + timeout
            try:
                assert p.stdout is not None
                for rl in iter(p.stdout.readline, ""):
                    if time.time() > dl:
                        p.kill()
                        return f"[超时] 命令超过 {timeout}s\n" + "".join(lines)
                    l = rl.rstrip()
                    if l:
                        lines.append(l + "\n")
                        output_callback(l + "\n")
                p.stdout.close()
                se = p.stderr.read() if p.stderr else ""
                p.wait()
                r = "".join(lines)
                if se and se.strip():
                    r += "\nSTDERR:\n" + se.rstrip()
                if p.returncode:
                    r += f"\nExit code: {p.returncode}"
                if p.returncode and r.strip():
                    try:
                        from .build_patterns import get_engine
                        m = get_engine().match(r)
                        if m and m.get("fix"):
                            r += f"\n[模式] {m['label']}\n建议: {m['fix']}"
                    except Exception:
                        pass
            except Exception:
                r = "[错误] 执行出错"
            finally:
                hs.set()
        else:
            # 简单模式：直接执行
            proc = subprocess.run(
                shell_cmd, capture_output=True, text=True, errors="replace", timeout=timeout,
            )
            parts = []
            if proc.stdout:
                parts.append(proc.stdout.rstrip())
            if proc.stderr:
                parts.append(f"STDERR:\n{proc.stderr.rstrip()}")
            if proc.returncode:
                parts.append(f"Exit code: {proc.returncode}")
            r = "\n".join(parts) if parts else "(无输出)"
            if heal_result:
                r = heal_result + "\n" + r
            if proc.returncode and r.strip():
                try:
                    from .build_patterns import get_engine
                    m = get_engine().match(r)
                    if m and m.get("fix"):
                        r += f"\n[模式] {m['label']}\n建议: {m['fix']}"
                except Exception:
                    pass

        return smart_truncate(r, _TOOL_RESULT_MAX_LENGTH) or "(无输出)"

    except subprocess.TimeoutExpired:
        return f"[超时] 命令超过 {timeout} 秒"
    except Exception as e:
        return f"[错误] 执行出错: {e}"
