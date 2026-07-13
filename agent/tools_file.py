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


# ═══════════════════════════════════════════
# 文件操作：移动 / 复制 / 删除 / 创建目录
# ═══════════════════════════════════════════

def _handle_move(source: str = "", destination: str = "") -> str:
    """移动/重命名文件或目录。"""
    if not source or not destination:
        return "[错误] move 需要 source 和 destination 参数"
    try:
        src = os.path.abspath(source)
        dst = os.path.abspath(destination)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)
        return f"[移动] {source} → {destination}"
    except FileNotFoundError:
        return f"[错误] 源文件不存在: {source}"
    except Exception as e:
        return f"[错误] 移动失败: {e}"


def _handle_copy(source: str = "", destination: str = "", recursive: bool = False) -> str:
    """复制文件或目录。"""
    if not source or not destination:
        return "[错误] copy 需要 source 和 destination 参数"
    try:
        src = os.path.abspath(source)
        dst = os.path.abspath(destination)
        if os.path.isdir(src):
            if not recursive:
                return "[错误] 复制目录需要 recursive=True"
            import shutil
            shutil.copytree(src, dst, dirs_exist_ok=True)
            return f"[复制] 目录 {source} → {destination}"
        else:
            import shutil
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            return f"[复制] {source} → {destination}"
    except FileNotFoundError:
        return f"[错误] 源路径不存在: {source}"
    except Exception as e:
        return f"[错误] 复制失败: {e}"


def _handle_delete(path: str = "", recursive: bool = False) -> str:
    """删除文件或目录。"""
    if not path:
        return "[错误] delete 需要 path 参数"
    try:
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return f"[错误] 路径不存在: {path}"
        if os.path.isdir(abs_path):
            if not recursive:
                return "[错误] 删除目录需要 recursive=True"
            import shutil
            shutil.rmtree(abs_path)
            return f"[删除] 目录: {path}"
        else:
            os.remove(abs_path)
            return f"[删除] 文件: {path}"
    except Exception as e:
        return f"[错误] 删除失败: {e}"


def _handle_mkdir(path: str = "", parents: bool = False) -> str:
    """创建目录。"""
    if not path:
        return "[错误] mkdir 需要 path 参数"
    try:
        abs_path = os.path.abspath(path)
        if parents:
            os.makedirs(abs_path, exist_ok=True)
        else:
            os.mkdir(abs_path)
        return f"[创建目录] {path}"
    except FileNotFoundError:
        return f"[错误] 父目录不存在（需要 parents=True）: {path}"
    except FileExistsError:
        return f"[错误] 目录已存在: {path}"
    except Exception as e:
        return f"[错误] 创建目录失败: {e}"


def _handle_download(url: str = "", destination: str = "") -> str:
    """从 URL 下载文件到本地路径。"""
    if not url or not destination:
        return "[错误] download 需要 url 和 destination 参数"
    try:
        import urllib.request
        abs_path = os.path.abspath(destination)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        urllib.request.urlretrieve(url, abs_path)
        size = os.path.getsize(abs_path)
        return f"[下载] {url} → {destination}（{size} 字节）"
    except Exception as e:
        return f"[错误] 下载失败: {e}"


def _handle_replace(file_path: str = "", search: str = "", replace_text: str = "", partial: bool = False) -> str:
    """SEARCH/REPLACE 替换（支持模糊匹配）。"""
    if not file_path or not search:
        return "[错误] replace 需要 file_path 和 search 参数"
    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        return f"[错误] 文件不存在: {abs_path}"

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 精确匹配
        count = content.count(search)
        if count == 1:
            new_content = content.replace(search, replace_text)
        elif count == 0 and partial:
            # 模糊匹配：逐行尝试
            import re
            lines = content.split("\n")
            search_lines = search.split("\n")
            matched = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                search_stripped = search_lines[0].strip()
                if stripped == search_stripped or (len(stripped) > 20 and stripped[:20] == search_stripped[:20]):
                    # 尝试多行匹配
                    match_len = 1
                    while match_len < len(search_lines) and i + match_len < len(lines):
                        if lines[i + match_len].strip() == search_lines[match_len].strip():
                            match_len += 1
                        else:
                            break
                    if match_len >= max(2, len(search_lines) // 2):
                        lines[i:i + match_len] = replace_text.split("\n")
                        matched = True
                        break
            if not matched:
                return f"[错误] 未找到匹配文本（已尝试模糊匹配）"
            new_content = "\n".join(lines)
        elif count > 1:
            return f"[错误] 文本出现 {count} 次，无法确定替换位置"
        else:
            return f"[错误] 未找到匹配文本"

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"[替换成功] {file_path}"

    except Exception as e:
        return f"[错误] 替换失败: {e}"


def _handle_revert(file_path: str = "") -> str:
    """撤销对文件的修改（TODO: 需接入备份系统）。"""
    return "[revert] 该功能需要接入备份系统（v2.2 支持）"

