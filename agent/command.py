"""command — 命令执行工具。"""

from __future__ import annotations

import os
import subprocess
import sys
import traceback


def _handle_bash(command: str = "", timeout: int = 30) -> str:
    """在系统 shell 中执行命令。

    Args:
        command: 要执行的命令
        timeout: 超时秒数（默认 30）

    Returns:
        命令输出（stdout + stderr）
    """
    if not command:
        return "[错误] bash 需要 command 参数"

    try:
        # 选择 shell
        if sys.platform == "win32":
            shell_cmd = ["cmd.exe", "/c", command]
        else:
            shell_cmd = ["bash", "-c", command]

        result = subprocess.run(
            shell_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n"
            output += result.stderr

        if result.returncode != 0:
            return f"[退出码 {result.returncode}]\n{output}" if output else f"[退出码 {result.returncode}]"

        return output if output else "(命令执行成功，无输出)"

    except subprocess.TimeoutExpired:
        return f"[超时] 命令超过 {timeout} 秒"
    except FileNotFoundError:
        return f"[错误] 命令未找到或路径不存在"
    except Exception as e:
        return f"[错误] 命令执行失败: {e}"
