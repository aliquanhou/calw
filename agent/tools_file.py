"""tools_file — 文件操作工具集。

v2.1 改进：
  - 使用 file_cache 加速文件读取
  - 消除静默异常
  - 明确的路径解析
"""

from __future__ import annotations

import os
import traceback
from typing import Any


def _handle_read(file_path: str = "") -> str:
    """读取文件内容。

    Args:
        file_path: 文件路径

    Returns:
        文件内容字符串
    """
    if not file_path:
        return "[错误] read 需要 file_path 参数"

    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        return f"[错误] 文件不存在: {abs_path}"

    if os.path.isdir(abs_path):
        return f"[错误] 路径是目录: {abs_path}"

    try:
        # 尝试使用 file_cache
        try:
            from .file_cache import get_cache
            cache = get_cache()
            return cache.read(abs_path)
        except ImportError:
            pass

        # 回退到标准文件读取
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    except PermissionError:
        return f"[错误] 权限不足: {abs_path}"
    except Exception as e:
        return f"[错误] 读取失败: {e}"


def _handle_write(file_path: str = "", content: str = "") -> str:
    """写入文件内容。

    Args:
        file_path: 文件路径
        content: 文件内容

    Returns:
        操作结果
    """
    if not file_path:
        return "[错误] write 需要 file_path 参数"

    abs_path = os.path.abspath(file_path)

    try:
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        # 更新缓存（如果存在）
        try:
            from .file_cache import get_cache
            cache = get_cache()
            cache.invalidate(abs_path)
        except ImportError:
            pass

        return f"[写入成功] {os.path.getsize(abs_path)} 字节 → {file_path}"

    except PermissionError:
        return f"[错误] 权限不足: {abs_path}"
    except Exception as e:
        return f"[错误] 写入失败: {e}"


def _handle_edit(file_path: str = "", old_string: str = "", new_string: str = "") -> str:
    """编辑文件内容（替换文本）。

    使用精确字符串替换。注意：任何反斜杠必须经过适当的转义。

    Args:
        file_path: 文件路径
        old_string: 要替换的原文
        new_string: 替换后的文本

    Returns:
        操作结果
    """
    if not file_path or not old_string:
        return "[错误] edit 需要 file_path 和 old_string 参数"

    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        return f"[错误] 文件不存在: {abs_path}"

    try:
        # 读取文件
        try:
            from .file_cache import get_cache
            cache = get_cache()
            content = cache.read(abs_path)
        except ImportError:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()

        # 替换
        if old_string not in content:
            # 模糊匹配：尝试移除首尾空格
            old_stripped = old_string.strip()
            if old_stripped in content:
                old_string = old_stripped
                new_string = new_string.strip()
            else:
                return f"[错误] 未找到匹配的文本"

        new_content = content.replace(old_string, new_string, 1)

        if new_content == content:
            return "[错误] 替换后内容无变化"

        # 写入文件
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # 更新缓存
        try:
            from .file_cache import get_cache
            cache = get_cache()
            cache.invalidate(abs_path)
        except ImportError:
            pass

        return f"[编辑成功] 替换了 {len(old_string)} 个字符 → {file_path}"

    except Exception as e:
        return f"[错误] 编辑失败: {e}"


def _handle_glob(pattern: str = "") -> str:
    """搜索匹配模式的文件路径。

    Args:
        pattern: 通配符模式（如 "**/*.py"）

    Returns:
        匹配到的文件路径列表
    """
    if not pattern:
        return "[错误] glob 需要 pattern 参数"

    import fnmatch

    try:
        results = []

        # 分离目录和模式
        head, tail = os.path.split(pattern)
        root = os.path.abspath(head) if head else os.getcwd()

        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                full = os.path.join(dirpath, f)
                rel = os.path.relpath(full)
                if fnmatch.fnmatch(rel, pattern):
                    results.append(rel)

            # 限制结果数量
            if len(results) > 1000:
                results.append("... (结果过多，仅显示前 1000 条)")
                break

        return "\n".join(results) if results else "(无匹配)"

    except Exception as e:
        return f"[错误] 搜索失败: {e}"


def _handle_grep(pattern: str = "", path: str = "",
                 glob_pattern: str = "", output_mode: str = "content") -> str:
    """在文件中搜索文本内容。

    Args:
        pattern: 要搜索的正则表达式
        path: 搜索目录
        glob_pattern: 文件过滤通配符
        output_mode: 输出模式 (content / files_with_matches)

    Returns:
        匹配结果
    """
    if not pattern:
        return "[错误] grep 需要 pattern 参数"

    import re

    search_dir = os.path.abspath(path) if path else os.getcwd()
    results = []

    try:
        for dirpath, _, filenames in os.walk(search_dir):
            # 跳过隐藏目录
            rel = os.path.relpath(dirpath, search_dir)
            if rel.startswith(".") or rel.startswith("__pycache__"):
                continue

            for f in filenames:
                filepath = os.path.join(dirpath, f)

                # 文件过滤
                if glob_pattern and not fnmatch.fnmatch(f, glob_pattern):
                    continue

                # 跳过大文件
                if os.path.getsize(filepath) > 1024 * 1024:
                    continue

                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                        for line_num, line in enumerate(fh, 1):
                            if re.search(pattern, line):
                                if output_mode == "files_with_matches":
                                    rel_path = os.path.relpath(filepath, search_dir)
                                    results.append(rel_path)
                                    break
                                else:
                                    rel_path = os.path.relpath(filepath, search_dir)
                                    results.append(f"{rel_path}:{line_num}:{line.rstrip()[:500]}")
                except Exception:
                    continue

            if len(results) > 500:
                results.append("... (结果过多，截断)")
                break

        return "\n".join(results) if results else "(无匹配)"

    except Exception as e:
        return f"[错误] 搜索失败: {e}"
