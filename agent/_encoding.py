"""_encoding — 系统编码自动检测（全局统一来源）。

Windows 中文系统默认 GBK，但 Calw 的 stream 输出用 UTF-8。
所有 subprocess 调用统一使用此模块，彻底解决中文乱码。

用法:
    from ._encoding import enc, run, popen
    r = run([...], capture_output=True)
    p = popen([...], stdout=subprocess.PIPE)
"""

from __future__ import annotations

import locale
import sys

# ── 只检测一次，全局共享 ──

_enc: str | None = None


def _detect() -> str:
    """检测系统默认编码。"""
    global _enc
    if _enc is not None:
        return _enc
    try:
        e = locale.getpreferredencoding(do_setlocale=False)
        if e and e.lower() not in ("utf-8", "utf8"):
            _enc = e
        else:
            _enc = "utf-8"
    except Exception:
        _enc = "utf-8"
    return _enc


enc = _detect()
"""系统编码，例如 'gbk' (中文 Windows) 或 'utf-8'。"""


def run(args, **kwargs):
    """subprocess.run 包装（自动注入 encoding）。"""
    import subprocess
    kwargs.setdefault("encoding", enc)
    kwargs.setdefault("errors", "replace")
    return subprocess.run(args, **kwargs)


def popen(args, **kwargs):
    """subprocess.Popen 包装（自动注入 encoding）。"""
    import subprocess
    kwargs.setdefault("encoding", enc)
    kwargs.setdefault("errors", "replace")
    return subprocess.Popen(args, **kwargs)


def check_output(args, **kwargs):
    """subprocess.check_output 包装（自动注入 encoding）。"""
    import subprocess
    kwargs.setdefault("encoding", enc)
    kwargs.setdefault("errors", "replace")
    return subprocess.check_output(args, **kwargs)
