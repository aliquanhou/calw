"""_encoding — 编码统一模块。

原理：Claude Code 不乱码是因为运行时环境处理了 subprocess 编码。
Calw 学同样的策略——捕获原始字节，检测真实编码后解码。

解码策略：
  1. 先尝试 UTF-8 解码（最通用）
  2. 如果失败，用系统 locale 编码（Windows 中文 = GBK）
  3. 如果还失败，用 errors='replace' 保底

用法:
    from ._encoding import enc, run, popen
    r = run([...])          # 返回正确解码的字符串
    p = popen([...])        # 同上
"""

from __future__ import annotations

import os
import subprocess
import sys

# ── 备选编码（系统 locale 决定的编码）──

_locale_enc: str = "utf-8"

if sys.platform == "win32":
    try:
        import locale
        e = locale.getpreferredencoding(do_setlocale=False)
        if e.lower() not in ("utf-8", "utf8"):
            _locale_enc = e  # Windows 中文 = 'gbk'
    except Exception:
        pass

enc = _locale_enc if _locale_enc != "utf-8" else "utf-8"


def _decode(data: bytes) -> str:
    """智能解码：优先 UTF-8 strict，失败时回退到 locale 编码。

    关键：用 strict 模式检测编码。errors='replace' 会安静地吃掉错误
    字节变成 U+FFFD，导致 fallback 逻辑永远不会触发。
    """
    if not data:
        return ""
    # 优先 UTF-8 strict（成功就是纯 UTF-8 输出）
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        pass
    # 回退到 locale 编码（Windows 中文 = gbk/cp936）
    try:
        return data.decode(_locale_enc, errors="replace")
    except (LookupError, UnicodeDecodeError):
        pass
    # 终极保底
    return data.decode("utf-8", errors="replace")


def _decode_first(data: bytes) -> str:
    """只解码前 64KB 用于判断编码，用检测到的编码解码完整数据。"""
    if not data:
        return ""

    # 小数据：直接试 UTF-8
    if len(data) < 65536:
        return _decode(data)

    # 大数据：用前 64KB 检测编码
    head = data[:65536]
    detected_enc = "utf-8"
    try:
        head.decode("utf-8")
        detected_enc = "utf-8"
    except UnicodeDecodeError:
        detected_enc = _locale_enc

    try:
        return data.decode(detected_enc, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def run(args, **kwargs):
    """subprocess.run 包装——捕获字节流，智能解码。"""
    # 移除可能存在的 text/encoding 参数，我们自己处理
    kwargs.pop("text", None)
    kwargs.pop("encoding", None)
    kwargs["capture_output"] = True

    try:
        result = subprocess.run(args, **kwargs)
        decoded_stdout = _decode(result.stdout)
        decoded_stderr = _decode(result.stderr)

        # 构造类 subprocess.CompletedProcess 对象
        class Result:
            def __init__(self, returncode, stdout, stderr):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

            def check_returncode(self):
                if self.returncode != 0:
                    raise subprocess.CalledProcessError(self.returncode, args)

        return Result(result.returncode, decoded_stdout, decoded_stderr)
    except FileNotFoundError:
        return Result(-1, "", f"命令未找到: {args}")


def popen(args, **kwargs):
    """subprocess.Popen 包装——默认用 UTF-8 编码读管道。"""
    kwargs.pop("text", None)
    kwargs.pop("encoding", None)
    return subprocess.Popen(args, **kwargs)


def check_output(args, **kwargs):
    """subprocess.check_output 包装——智能解码。"""
    kwargs.pop("text", None)
    kwargs.pop("encoding", None)
    try:
        raw = subprocess.check_output(args, **kwargs)
        return _decode(raw)
    except subprocess.CalledProcessError as e:
        return _decode(e.output)
