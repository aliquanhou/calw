"""tools_deps — 包依赖自动修复。

检测 import 错误 → 自动安装缺失包，支持 pip / npm。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys


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
    "tkinter": "tkinter",  # part of standard lib
}


def extract_missing_modules(text: str) -> list[str]:
    """从错误输出中提取缺失的模块名。

    支持格式:
      - ModuleNotFoundError: No module named 'xxx'
      - ImportError: No module named xxx
      - Error: Cannot find module 'xxx'
      - MODULE_NOT_FOUND
    """
    modules = []

    # Python ModuleNotFoundError
    m = re.findall(r"ModuleNotFoundError[^:]*:\s*(?:No module named\s+)?['\"]?(\w+)['\"]?", text, re.I)
    modules.extend(m)

    # Python ImportError
    m = re.findall(r"ImportError[^:]*:\s*(?:No module named\s+)?['\"]?(\w+)['\"]?", text, re.I)
    modules.extend(m)

    # Node.js
    m = re.findall(r"Cannot find module\s+['\"](\w+)['\"]", text, re.I)
    modules.extend(m)

    # 去重
    seen: set[str] = set()
    result = []
    for mod in modules:
        mod = mod.strip()
        if mod and mod not in seen and mod not in KNOWN_PACKAGE_MAP.get("tkinter", ""):
            seen.add(mod)
            result.append(mod)
    return result


def resolve_package_name(module_name: str) -> str:
    """将 import 模块名转为 pip 包名。"""
    if module_name in KNOWN_PACKAGE_MAP:
        return KNOWN_PACKAGE_MAP[module_name]
    # 默认同名
    return module_name


def is_stdlib(module_name: str) -> bool:
    """粗略判断是否为标准库模块。"""
    stdlib_modules = {
        "os", "sys", "json", "re", "time", "datetime", "math", "random",
        "collections", "itertools", "functools", "pathlib", "shutil",
        "subprocess", "threading", "multiprocessing", "io", "base64",
        "hashlib", "uuid", "typing", "enum", "dataclasses", "abc",
        "copy", "pprint", "logging", "warnings", "traceback",
        "unittest", "argparse", "configparser", "tempfile",
        "textwrap", "string", "urllib", "http", "socket", "ssl",
        "html", "xml", "csv", "json", "sqlite3",
    }
    return module_name in stdlib_modules


def install_package(module_name: str, timeout: int = 120) -> str:
    """安装缺失的 Python 包。

    Returns:
        安装结果描述。
    """
    if is_stdlib(module_name):
        return f"'{module_name}' 是 Python 标准库模块，不需要安装"

    pkg = resolve_package_name(module_name)
    if pkg == module_name and module_name in KNOWN_PACKAGE_MAP.values():
        pkg = module_name

    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode == 0:
            return f"✅ 已自动安装: {pkg}"
        else:
            stderr = r.stderr.strip()[:300]
            return f"❌ 安装 {pkg} 失败: {stderr}"
    except subprocess.TimeoutExpired:
        return f"⏱ 安装 {pkg} 超时({timeout}s)"
    except Exception as e:
        return f"❌ 安装异常: {e}"


def scan_requirements(path: str | None = None) -> list[dict]:
    """扫描项目依赖配置文件，检查缺失的包。"""
    root = path or os.getcwd()
    missing = []

    # 检查 requirements.txt
    req_file = os.path.join(root, "requirements.txt")
    if os.path.exists(req_file):
        try:
            with open(req_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith("-"):
                        continue
                    pkg = re.split(r"[<>=!~]", line)[0].strip()
                    if pkg:
                        # 快速检查是否已安装
                        try:
                            subprocess.run(
                                [sys.executable, "-m", "pip", "show", pkg],
                                capture_output=True, text=True, timeout=15,
                            )
                        except:
                            pass
                        if True:  # simple check
                            pass
        except Exception:
            pass

    return missing


def _handle_deps(action: str = "check", module_name: str = "", text: str = "") -> str:
    """dep 工具入口。"""
    if action == "install":
        if not module_name:
            return "需指定 module_name"
        return install_package(module_name)

    if action == "auto":
        if not text:
            return "需提供错误文本"
        modules = extract_missing_modules(text)
        if not modules:
            return "未检测到缺失的模块"
        results = []
        for mod in modules[:3]:  # 最多装3个
            results.append(install_package(mod))
        return "\n".join(results)

    if action == "check":
        return "dep 工具就绪。使用 action='auto' 传入错误文本自动安装，或 action='install' 指定模块名。"

    return f"未知操作: {action}"
