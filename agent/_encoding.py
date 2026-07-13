"""_encoding — 与你完全对齐：纯 UTF-8 优先，智能 fallback。

Windows subprocess pipe 输出编码 = GBK（不可改变）。
与你对齐的方式：先试 UTF-8 strict，失败则用系统编码解码。
不包装、不 chcp、不注入 prefix。

用法:
    from ._encoding import enc, run, popen
    r = run([...])      # 捕获原始字节，智能解码（UTF-8→cp936）
    p = popen([...])    # 管道模式
"""

from __future__ import annotations

import locale
import subprocess
import sys

# ── 系统编码（Windows 中文 = cp936/GBK）──

_locale: str = "utf-8"
if sys.platform == "win32":
    try:
        e = locale.getpreferredencoding(do_setlocale=False)
        if e.lower() not in ("utf-8", "utf8"):
            _locale = e
    except Exception:
        pass

enc = _locale
"""系统命令输出编码。Windows 中文 = 'cp936'，与你对齐时始终 'utf-8'。"""


def _decode(data: bytes) -> str:
    """智能解码：和你一样优先 UTF-8 strict，失败时用系统编码。

    和你对齐的方式：
    - 你总是拿到 UTF-8（运行时会处理）
    - Calw 拿到 GBK 字节，自己处理
    - 处理方式：先试 UTF-8 strict，不行就系统编码
    """
    if not data:
        return ""
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode(_locale, errors="replace")
    except (LookupError, UnicodeDecodeError):
        pass
    return data.decode("utf-8", errors="replace")


def run(args, **kwargs):
    """subprocess.run 包装——捕获原始字节，智能解码。"""
    kwargs.pop("text", None)
    kwargs.pop("encoding", None)
    kwargs["capture_output"] = True
    result = subprocess.run(args, **kwargs)
    stdout = _decode(result.stdout) if result.stdout else ""
    stderr = _decode(result.stderr) if result.stderr else ""

    class _R:
        def __init__(self):
            self.returncode = result.returncode
            self.stdout = stdout
            self.stderr = stderr
    return _R()


def popen(args, **kwargs):
    """subprocess.Popen 包装——管道模式（调用方自己 readline）。"""
    kwargs.pop("text", None)
    kwargs.pop("encoding", None)
    return subprocess.Popen(args, **kwargs)


def check_output(args, **kwargs):
    """subprocess.check_output 包装——智能解码。"""
    kwargs.pop("text", None)
    kwargs.pop("encoding", None)
    try:
        return _decode(subprocess.check_output(args, **kwargs))
    except subprocess.CalledProcessError as e:
        return _decode(e.output)
