"""_encoding — 系统编码检测（全局统一来源）。

Windows 命令输出编码由控制台代码页 (chcp) 决定，而非 locale。
使用 GetConsoleOutputCP() 获取真实编码，彻底解决中文乱码。

用法:
    from ._encoding import enc, run, popen
    r = run([...])          # subprocess.run 自动用正确编码
    p = popen([...])        # subprocess.Popen 自动用正确编码
    print(enc)              # 当前编码名，如 'gbk'
"""

from __future__ import annotations

import sys

# ── 检测一次，全局共享 ──

_enc: str | None = None


def _detect() -> str:
    """检测 Windows 控制台代码页（命令实际输出编码）。

    优先级:
      1. Windows: GetConsoleOutputCP() — 真实 cmd 输出编码
      2. locale.getpreferredencoding() — 备选
      3. utf-8 — 保底
    """
    global _enc
    if _enc is not None:
        return _enc

    # Windows: 用控制台代码页（最准确）
    if sys.platform == "win32":
        try:
            import ctypes
            cp = ctypes.windll.kernel32.GetConsoleOutputCP()
            # 代码页 → 编码名映射
            cp_map = {
                936: "gbk",
                950: "big5",
                932: "shift_jis",
                949: "euc-kr",
                65001: "utf-8",
                437: "cp437",
                850: "cp850",
                1250: "cp1250",
                1251: "cp1251",
                1252: "cp1252",
                1253: "cp1253",
                1254: "cp1254",
                1255: "cp1255",
                1256: "cp1256",
                1257: "cp1257",
                1258: "cp1258",
            }
            name = cp_map.get(cp)
            if name:
                _enc = name
                return _enc
            # 未知代码页，但数字本身就是有效编码名
            _enc = f"cp{cp}"
            return _enc
        except Exception:
            pass

    # 备选: locale
    try:
        import locale
        e = locale.getpreferredencoding(do_setlocale=False)
        if e.lower() in ("utf-8", "utf8"):
            _enc = "utf-8"
        else:
            _enc = e
    except Exception:
        _enc = "utf-8"
    return _enc


enc = _detect()
"""系统命令输出编码，例如 'gbk' (中文 Windows) 或 'utf-8'。"""


def run(args, **kwargs):
    """subprocess.run 包装（自动注入正确 encoding）。"""
    import subprocess
    kwargs.setdefault("encoding", enc)
    kwargs.setdefault("errors", "replace")
    return subprocess.run(args, **kwargs)


def popen(args, **kwargs):
    """subprocess.Popen 包装（自动注入正确 encoding）。"""
    import subprocess
    kwargs.setdefault("encoding", enc)
    kwargs.setdefault("errors", "replace")
    return subprocess.Popen(args, **kwargs)


def check_output(args, **kwargs):
    """subprocess.check_output 包装（自动注入正确 encoding）。"""
    import subprocess
    kwargs.setdefault("encoding", enc)
    kwargs.setdefault("errors", "replace")
    return subprocess.check_output(args, **kwargs)
