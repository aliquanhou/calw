"""
文件操作工具模块

提供安全的文件读写、路径处理、格式转换等工具函数。
所有函数均包含类型注解、完整的错误处理和中文文档。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional


def read_file(file_path: str, encoding: str = "utf-8") -> str:
    """读取文本文件内容

    Args:
        file_path: 文件路径（绝对或相对路径）
        encoding: 文件编码，默认 utf-8

    Returns:
        文件内容的字符串

    Raises:
        FileNotFoundError: 文件不存在时抛出
        PermissionError: 权限不足时抛出
        UnicodeDecodeError: 编码不匹配时抛出
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    try:
        with open(file_path, "r", encoding=encoding) as f:
            return f.read()
    except PermissionError:
        raise PermissionError(f"没有读取权限: {file_path}")
    except UnicodeDecodeError as e:
        raise UnicodeDecodeError(
            e.encoding, e.object, e.start, e.end, f"文件编码不是 {encoding}: {file_path}"
        )


def write_file(file_path: str, content: str, encoding: str = "utf-8") -> int:
    """写入文本内容到文件（自动创建父目录）

    Args:
        file_path: 目标文件路径
        content: 要写入的文本内容
        encoding: 文件编码，默认 utf-8

    Returns:
        写入的字节数

    Raises:
        PermissionError: 权限不足时抛出
        OSError: 其他系统错误
    """
    file_path_obj = Path(file_path)
    file_path_obj.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(file_path, "w", encoding=encoding) as f:
            return f.write(content)
    except PermissionError:
        raise PermissionError(f"没有写入权限: {file_path}")


def append_file(file_path: str, content: str, encoding: str = "utf-8") -> int:
    """追加文本内容到文件末尾

    Args:
        file_path: 目标文件路径
        content: 要追加的文本内容
        encoding: 文件编码，默认 utf-8

    Returns:
        写入的字节数
    """
    file_path_obj = Path(file_path)
    file_path_obj.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "a", encoding=encoding) as f:
        return f.write(content)


def file_size(file_path: str) -> int:
    """获取文件大小（字节）

    Args:
        file_path: 文件路径

    Returns:
        文件字节数

    Raises:
        FileNotFoundError: 文件不存在
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    return os.path.getsize(file_path)


def file_hash(file_path: str, algorithm: str = "md5") -> str:
    """计算文件哈希值

    Args:
        file_path: 文件路径
        algorithm: 哈希算法，支持 md5、sha256、sha1，默认 md5

    Returns:
        十六进制哈希字符串

    Raises:
        ValueError: 不支持的算法
        FileNotFoundError: 文件不存在
    """
    if algorithm not in ("md5", "sha256", "sha1"):
        raise ValueError(f"不支持的哈希算法: {algorithm}，支持: md5, sha256, sha1")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    h = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def list_files(directory: str, pattern: str = "*", recursive: bool = False) -> list[str]:
    """列出目录中的文件

    Args:
        directory: 目录路径
        pattern: 文件名匹配模式，如 "*.py"
        recursive: 是否递归子目录

    Returns:
        符合条件的文件路径列表

    Raises:
        NotADirectoryError: 路径不是目录
        FileNotFoundError: 目录不存在
    """
    if not os.path.exists(directory):
        raise FileNotFoundError(f"目录不存在: {directory}")
    if not os.path.isdir(directory):
        raise NotADirectoryError(f"路径不是目录: {directory}")

    path = Path(directory)
    if recursive:
        return [str(p) for p in path.rglob(pattern) if p.is_file()]
    return [str(p) for p in path.glob(pattern) if p.is_file()]


def read_json(file_path: str, encoding: str = "utf-8") -> Any:
    """读取 JSON 文件

    Args:
        file_path: JSON 文件路径
        encoding: 文件编码

    Returns:
        解析后的 Python 对象

    Raises:
        json.JSONDecodeError: JSON 格式错误
    """
    content = read_file(file_path, encoding)
    return json.loads(content)


def write_json(file_path: str, data: Any, indent: int = 2, encoding: str = "utf-8") -> int:
    """写入 JSON 文件

    Args:
        file_path: 目标文件路径
        data: 要写入的数据
        indent: 缩进空格数，默认 2
        encoding: 文件编码

    Returns:
        写入的字节数
    """
    content = json.dumps(data, ensure_ascii=False, indent=indent)
    return write_file(file_path, content, encoding)


def list_directory_tree(directory: str, max_depth: int = 3) -> str:
    """以树形结构列出目录

    Args:
        directory: 目录路径
        max_depth: 最大递归深度，默认 3

    Returns:
        树形结构的字符串表示
    """
    path = Path(directory)
    if not path.exists():
        return f"[目录不存在] {directory}"

    result: list[str] = []

    def _walk(current: Path, prefix: str = "", depth: int = 0) -> None:
        if depth > max_depth:
            return
        entries = sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            result.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)

    result.append(f"{path.name}/")
    _walk(path)
    return "\n".join(result)


def safe_filename(filename: str, replacement: str = "_") -> str:
    """将字符串转换为安全的文件名（替换非法字符）

    Args:
        filename: 原始文件名
        replacement: 非法字符的替换字符，默认下划线

    Returns:
        安全的文件名
    """
    illegal_chars = '<>:"/\\|?*'
    for c in illegal_chars:
        filename = filename.replace(c, replacement)
    # 去除控制字符
    filename = "".join(c if c.isprintable() else replacement for c in filename)
    return filename.strip()


def retry_on_error(
    func: Callable,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """重试装饰器：函数执行失败时自动重试

    Args:
        func: 要执行的函数
        max_retries: 最大重试次数，默认 3
        retry_delay: 重试间隔秒数，默认 1
        exceptions: 捕获的异常类型元组

    Returns:
        被包装的函数

    Example:
        @retry_on_error
        def unstable_network_call():
            ...
    """
    import time
    from functools import wraps

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                last_exception = e
                if attempt < max_retries:
                    time.sleep(retry_delay)
                else:
                    raise
        # 不应该执行到这里
        raise RuntimeError("重试异常状态") from last_exception

    return wrapper
