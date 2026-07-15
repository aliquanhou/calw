"""tools_deps — 包依赖自动修复。

v2.1 重写：
  - 统一返回格式
  - 类型注解
  - 改进的错误信息
  - 修复 scan_requirements 死代码
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from ._encoding import run as _run, popen as _popen


# 已知的 PyPI 包名映射（import名 → pip包名）
KNOWN_PACKAGE_MAP: dict[str, str] = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "lxml": "lxml",
    "dotenv": "python-dotenv",
    "crypto": "pycryptodome",
    "dateutil": "python-dateutil",
    "requests": "requests",
    "flask": "Flask",
    "django": "Django",
    "numpy": "numpy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "selenium": "selenium",
    "playwright": "playwright",
    "fastapi": "fastapi",
    "pydantic": "pydantic",
    "sqlalchemy": "sqlalchemy",
    "alembic": "alembic",
    "pytest": "pytest",
    "rich": "rich",
    "click": "click",
    "typer": "typer",
    "httpx": "httpx",
    "aiohttp": "aiohttp",
    "websockets": "websockets",
    "jinja2": "Jinja2",
    "markdown": "Markdown",
    "openai": "openai",
    "anthropic": "anthropic",
    "customtkinter": "customtkinter",
    "chromadb": "chromadb",
}


def extract_missing_modules(text: str) -> list[str]:
    """从错误输出中提取缺失的模块名。"""
    modules = []
    m = re.findall(r"ModuleNotFoundError[^:]*:\s*(?:No module named\s+)?['\"]?(\w+)['\"]?", text, re.I)
    modules.extend(m)
    m = re.findall(r"ImportError[^:]*:\s*(?:No module named\s+)?['\"]?(\w+)['\"]?", text, re.I)
    modules.extend(m)
    # Node.js module not found
    m = re.findall(r"Cannot find module\s+['\"](\w+)['\"]", text, re.I)
    modules.extend(m)
    seen: set[str] = set()
    result = []
    for mod in modules:
        mod = mod.strip()
        if mod and mod not in seen:
            seen.add(mod)
            result.append(mod)
    return result


def resolve_package_name(module_name: str) -> str:
    """将 import 模块名转为 pip 包名。"""
    return KNOWN_PACKAGE_MAP.get(module_name, module_name)


def is_stdlib(module_name: str) -> bool:
    """判断是否为 Python 标准库模块。"""
    return module_name in {
        "os", "sys", "json", "re", "time", "datetime", "math", "random",
        "collections", "itertools", "functools", "pathlib", "shutil",
        "subprocess", "threading", "multiprocessing", "io", "base64",
        "hashlib", "uuid", "typing", "enum", "dataclasses", "abc",
        "copy", "pprint", "logging", "warnings", "traceback",
        "unittest", "argparse", "configparser", "tempfile",
        "textwrap", "string", "urllib", "http", "socket", "ssl",
        "html", "xml", "csv", "sqlite3",
    }


def install_package(module_name: str, timeout: int = 120) -> str:
    """安装缺失的 Python 包。"""
    if is_stdlib(module_name):
        return f"[跳过] '{module_name}' 是标准库模块"

    pkg = resolve_package_name(module_name)

    try:
        r = _run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode == 0:
            return f"[安装] ✅ {pkg}"
        return f"[失败] ❌ 安装 {pkg}: {r.stderr.strip()[:200]}"
    except subprocess.TimeoutExpired:
        return f"[超时] ⏱ 安装 {pkg}（{timeout}s）"
    except Exception as e:
        return f"[错误] 安装异常: {e}"


def _handle_deps(action: str = "check", module_name: str = "", text: str = "") -> str:
    """包依赖管理：检查/安装/自动修复。

    Args:
        action: check（就绪检查）| install（安装指定包）| auto（从错误文本自动安装）
        module_name: 要安装的模块名
        text: 包含错误信息的文本（auto 模式使用）

    Returns:
        操作结果
    """
    try:
        if action == "install":
            if not module_name:
                return "[错误] install 需要 module_name 参数"
            return install_package(module_name)

        if action == "auto":
            if not text:
                return "[错误] auto 需要 text 参数（包含错误信息）"
            modules = extract_missing_modules(text)
            if not modules:
                return "[检测] 未检测到缺失模块"
            results = []
            for mod in modules[:3]:
                results.append(install_package(mod))
            return "\n".join(results)

        if action == "check":
            return "[就绪] dep 工具可用。使用 auto 自动检测安装，或 install 指定模块名。"

        return f"[错误] 未知操作: {action}（可用: check/install/auto）"

    except Exception as e:
        return f"[错误] dep 操作失败: {e}"
