"""command — 命令执行工具。"""
from __future__ import annotations
import os,subprocess,sys
from ._encoding import run as _run, popen as _popen


def _handle_bash(command: str = "", timeout: int = 30) -> str:
    """在系统 shell 中执行命令。"""
    if not command:
        return "[错误] bash 需要 command 参数"
    try:
        sc = ["cmd.exe", "/c", command] if sys.platform == "win32" else ["bash", "-c", command]
        r = _run(sc, capture_output=True, text=True, timeout=timeout, cwd=os.getcwd())
        o = ""
        if r.stdout: o += r.stdout
        if r.stderr: o += ("\n" + r.stderr) if o else r.stderr
        if r.returncode != 0: return f"[退出码 {r.returncode}]\n{o}" if o else f"[退出码 {r.returncode}]"
        return o if o else "(命令执行成功，无输出)"
    except subprocess.TimeoutExpired: return f"[超时] 命令超过 {timeout} 秒"
    except FileNotFoundError: return "[错误] 命令未找到"
    except Exception as e: return f"[错误] 命令执行失败: {e}"
