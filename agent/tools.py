"""Tool definitions and handlers for the agent."""

from __future__ import annotations

import json
import os
import re
import glob as glob_module
import hashlib
import subprocess
import sys
import threading
import time
import uuid
from typing import Any


TOOL_DEFINITIONS = [
    {
        "name": "read",
        "description": "读取指定文件的内容。支持文本文件和常见代码文件。",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要读取的文件的绝对路径"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "write",
        "description": "将内容写入文件（覆盖已有内容）。如果文件不存在则创建，自动创建父目录。",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要写入的文件的绝对路径"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文件内容"
                }
            },
            "required": ["file_path", "content"]
        }
    },
    {
        "name": "edit",
        "description": "对文件执行精确的字符串替换。用于修改现有文件。old_string 必须在文件中唯一匹配。",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要编辑的文件的绝对路径"
                },
                "old_string": {
                    "type": "string",
                    "description": "要被替换的精确字符串（必须唯一匹配一次）"
                },
                "new_string": {
                    "type": "string",
                    "description": "替换后的新字符串"
                }
            },
            "required": ["file_path", "old_string", "new_string"]
        }
    },
    {
        "name": "glob",
        "description": "使用 glob 模式搜索文件和目录。支持 ** 递归匹配多个目录层级。",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "glob 模式，如 **/*.py 或 src/**/*.ts"
                },
                "path": {
                    "type": "string",
                    "description": "搜索根目录（默认当前工作目录）"
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "grep",
        "description": "在文件中搜索正则表达式匹配。支持按文件类型过滤。自动跳过 .git、node_modules、__pycache__ 等目录。",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "要搜索的正则表达式模式"
                },
                "path": {
                    "type": "string",
                    "description": "搜索路径（文件或目录，默认当前目录）"
                },
                "glob_pattern": {
                    "type": "string",
                    "description": "文件过滤 glob 模式，如 *.py 或 *.{ts,tsx}"
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches"],
                    "description": "输出匹配内容或仅输出文件名。默认 content 显示匹配行。"
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "bash",
        "description": "执行任何 PowerShell 命令——完全系统权限。可以运行 .exe、.bat、.ps1、Python、Node.js、npm、pip、git、choco、MSI 安装等。你可以控制任何东西。",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令。使用 PowerShell 语法。可以执行任何程序和系统操作。"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒，默认 120，最大 600）"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "think",
        "description": "使用此工具进行内部推理、规划和思考。不会触发任何外部操作，仅用于你的内部推理。支持 thought 或 content 参数传入思考内容，支持可选的 title 参数。",
        "input_schema": {
            "type": "object",
            "properties": {
                "thought": {
                    "type": "string",
                    "description": "你的推理和思考内容（与 content 二选一）"
                },
                "content": {
                    "type": "string",
                    "description": "你的推理和思考内容（与 thought 二选一）"
                },
                "title": {
                    "type": "string",
                    "description": "可选的思考标题，用于标识思考主题"
                }
            },
            "anyOf": [
                {"required": ["thought"]},
                {"required": ["content"]}
            ]
        }
    },
    {
        "name": "project_memory",
        "description": "读取/写入/追加项目级持久记忆（CLAUDE.md）。用于记录项目约定、编码规范、架构决策、TODO 等跨会话持久化信息。读取操作自动在会话启动时加载到上下文。",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "append"],
                    "description": "操作类型: read=读取, write=覆盖写入, append=追加"
                },
                "content": {
                    "type": "string",
                    "description": "写入或追加的内容（action=read 时忽略）"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "system_info",
        "description": "获取完整的 Windows 系统信息：操作系统版本、CPU、内存、磁盘、网卡、BIOS、安装的软件、环境变量。",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["os", "cpu", "memory", "disk", "network", "software", "environment", "all"],
                    "description": "信息类别（默认 all 返回全部）"
                }
            },
            "required": []
        }
    },
    {
        "name": "process",
        "description": "管理 Windows 进程。可以列出所有进程、按名称搜索、终止进程。",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "kill", "search"],
                    "description": "list=列出所有进程, kill=终止进程, search=搜索进程"
                },
                "name": {
                    "type": "string",
                    "description": "进程名称（用于 search 或 kill 操作），如 notepad.exe"
                },
                "pid": {
                    "type": "integer",
                    "description": "进程 ID（用于 kill 操作）"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "web",
        "description": "发送 HTTP 请求获取网页内容或调用 API。支持 GET 和 POST。",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "请求的 URL"
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST"],
                    "description": "HTTP 方法"
                },
                "data": {
                    "type": "string",
                    "description": "POST 请求体（JSON 字符串）"
                },
                "headers": {
                    "type": "string",
                    "description": "请求头，JSON 格式，如 {\"Authorization\": \"Bearer xxx\"}"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "screencap",
        "description": "截取当前桌面屏幕截图。返回图片 base64 编码数据。",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "browser",
        "description": "使用 Playwright 控制浏览器。支持导航、点击、输入、提取内容、截图、JS注入、页面诊断。浏览器实例在多次调用间保持，自动捕获 console 日志、网络错误、JS错误。",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "click", "type", "read", "screenshot", "html", "close", "get_url", "execute_js", "diagnose", "console", "network"],
                    "description": "操作: navigate=打开URL, click=点击, type=输入, read=提取文本, screenshot=截图, html=获取HTML, close=关闭, get_url=当前URL, execute_js=执行JS, diagnose=全面诊断页面(console+network+JS错误+内容), console=查看console日志, network=查看网络错误"
                },
                "url": {
                    "type": "string",
                    "description": "用于 navigate 操作的 URL"
                },
                "selector": {
                    "type": "string",
                    "description": "CSS 选择器，用于 click/type/read 操作"
                },
                "text": {
                    "type": "string",
                    "description": "用于 type 操作的输入文本"
                },
                "script": {
                    "type": "string",
                    "description": "用于 execute_js 操作的 JavaScript 代码"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "background",
        "description": "在后台运行命令（进程不阻塞 agent 回复）。可启动、查询状态、获取输出、停止、等待完成。适用于长时间运行的任务或需要持续运行的守护进程。",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "list", "output", "stop", "stop_all", "wait"],
                    "description": "操作: start=启动后台任务, list=列出所有任务, output=获取任务输出, stop=停止任务, stop_all=停止所有任务, wait=等待任务完成或匹配特定输出"
                },
                "command": {
                    "type": "string",
                    "description": "用于 start 操作的命令（PowerShell 语法）"
                },
                "task_id": {
                    "type": "string",
                    "description": "任务 ID，用于 output/stop/wait 操作"
                },
                "pattern": {
                    "type": "string",
                    "description": "用于 wait 操作的正则表达式模式，等待输出匹配此模式后返回"
                },
                "timeout": {
                    "type": "integer",
                    "description": "用于 wait 操作的超时时间（秒，默认 300）"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "plan",
        "description": "为复杂任务创建结构化计划并跟踪进度。创建后可用 update 更新步骤状态。",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "update", "list", "show"],
                    "description": "create=创建计划, update=更新步骤, list=列出所有, show=查看详情"
                },
                "title": {
                    "type": "string",
                    "description": "计划标题（用于 create）"
                },
                "plan_id": {
                    "type": "string",
                    "description": "计划 ID（用于 update/show）"
                },
                "steps": {
                    "type": "string",
                    "description": "JSON 数组: [{\"step\":\"描述\",\"status\":\"pending\"}]"
                },
                "step_index": {
                    "type": "integer",
                    "description": "要更新的步骤索引（从0开始）"
                },
                "step_status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed"],
                    "description": "步骤新状态"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "task",
        "description": "快速标记当前任务进度。适用于简单场景，复杂任务请用 plan。",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["start", "progress", "done", "fail"],
                    "description": "任务状态"
                },
                "message": {
                    "type": "string",
                    "description": "状态描述"
                }
            },
            "required": ["status"]
        }
    },
    {
        "name": "ast",
        "description": "AST分析：解析 Python 文件，提取函数、类、导入等结构信息",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要分析的 Python 文件路径"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "dep_graph",
        "description": "依赖图分析：分析项目内文件的导入依赖关系，检测循环依赖和核心模块",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "项目目录或目标文件路径（默认当前目录）"
                }
            }
        }
    },
    {
        "name": "call_chain",
        "description": "调用链分析：正向追踪函数调用了什么，反向追踪谁调用了该函数",
        "input_schema": {
            "type": "object",
            "properties": {
                "function_name": {
                    "type": "string",
                    "description": "要追踪的函数名"
                },
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward"],
                    "description": "forward=谁被调用, backward=谁调用我"
                },
                "path": {
                    "type": "string",
                    "description": "项目目录路径（默认当前目录）"
                },
                "depth": {
                    "type": "integer",
                    "description": "追踪深度（默认3层）"
                }
            },
            "required": ["function_name", "direction"]
        }
    },
    {
        "name": "revert",
        "description": "撤销上一步对文件的修改。自动从备份恢复文件到修改前的状态。可用于 write/edit 操作验证失败后恢复。",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要恢复的文件路径（留空则列出所有可恢复的文件）"
                }
            },
            "required": []
        }
    },
    {
        "name": "web_search",
        "description": "搜索网络获取实时信息。用于查文档、找解决方案、了解最新动态。返回搜索结果列表（标题+摘要+链接）。需要联网。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，清晰描述想查找的内容"
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回结果数量（默认 5，最多 10）"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "ask_user",
        "description": "向用户提出问题以澄清需求、获取决策、请求确认。当指令模糊、有多个可选方案、或需要用户许可执行关键操作时使用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "向用户提出的问题"
                },
                "options": {
                    "type": "string",
                    "description": "可选方案列表（JSON 数组字符串，如 ['方案A','方案B']），用户可选择其一"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "trace_error",
        "description": "自动追溯错误根因。给定错误消息或堆栈跟踪，搜索项目代码分析可能的原因。用于快速定位 ModuleNotFoundError、ImportError、TypeError、AttributeError 及各种运行时异常的根因。",
        "input_schema": {
            "type": "object",
            "properties": {
                "error_message": {
                    "type": "string",
                    "description": "完整的错误消息或堆栈跟踪"
                },
                "file_path": {
                    "type": "string",
                    "description": "怀疑出错的文件路径（可选，留空则自动搜索）"
                },
                "depth": {
                    "type": "integer",
                    "description": "分析深度（默认 2，最大 5），控制递归搜索层级"
                }
            },
            "required": ["error_message"]
        }
    }
]

_TOOL_RESULT_MAX_LENGTH = 120000

# ── Session-level dedup: track written content to prevent repeated identical fixes ──
_written_this_session: set[str] = set()

# ── Session-level PID whitelist: don't self-heal what we started ──
_agent_spawned_pids: set[int] = set()

# ── Pre-write file backups for self-healing rollback ──
_file_backups: dict[str, str | None] = {}

# ── Auto-extracted failure lessons (for injection before tool dispatch) ──
_session_lessons: list[dict] = []

# ── Consecutive failure counter per file/tool ──
_consecutive_fails: dict[str, int] = {}


# ── Smart truncation ──

def smart_truncate(text: str, max_len: int = _TOOL_RESULT_MAX_LENGTH) -> str:
    """Intelligently truncate tool results.

    - If no error keywords: keep first max_len chars (current behavior)
    - If errors present: keep head + tail, omit middle with summary line
    """
    if not text or len(text) <= max_len:
        return text
    has_error = any(kw in text.lower()[:2000] for kw in ("error", "traceback", "异常", "失败"))
    if not has_error:
        # Also check the tail portion in case error keywords are far into the output
        if len(text) > 2000:
            has_error = any(kw in text.lower()[-500:] for kw in ("error", "traceback", "异常", "失败"))
    if not has_error:
        return text[:max_len] + f"\n\n... (截断, 共 {len(text)} 字符)"

    tail_chars = min(800, max_len // 2)
    head_chars = max_len - tail_chars
    return (
        text[:head_chars]
        + f"\n... (智能截断: 共 {len(text)} 字符，保留头 {head_chars} + 尾 {tail_chars} 字符) ...\n"
        + text[-tail_chars:]
    )


# ──────────────────────────────────────────────
# Tool Result Analysis — classify errors, suggest fixes
# ──────────────────────────────────────────────

_NODE_MODULES_WARNED: set[str] = set()  # track warned paths to avoid spam


def check_search_scope(path: str) -> str:
    """Check if a search path is suspicious (node_modules, bin, etc.). Returns warning or empty."""
    normalized = path.replace("\\", "/")
    if "/node_modules/" in normalized:
        if path not in _NODE_MODULES_WARNED:
            _NODE_MODULES_WARNED.add(path)
            return (
                "⚠️ 搜索路径包含 node_modules！这是第三方依赖库的目录，"
                "极少需要在这里搜索。请搜索 src/ app/ lib/ 等源码目录。"
            )
        return "⚠️ 仍在搜索 node_modules，建议检查源码目录。"
    if "/bin/" in normalized or "/obj/" in normalized:
        return "⚠️ 搜索路径包含编译输出目录 (bin/obj)，建议搜索源码目录。"
    if "/.git/" in normalized:
        return "⚠️ 搜索路径包含 .git 目录。"
    return ""


def classify_tool_result(tool_name: str, result: str) -> dict:
    """Analyze a tool result to detect failures, classify error type, and suggest next steps.

    Returns: {
        "success": bool,
        "error_type": str (ok | file_not_found | command_failed | timeout | import_error | ...),
        "suggestion": str,
        "searched_node_modules": bool,
    }
    """
    if not result:
        return {"success": True, "error_type": "ok", "suggestion": "", "searched_node_modules": False}

    text = result.lower()
    searched_nm = "node_modules" in text[:200] or "node_modules" in text[-500:]

    # ── Error detection ──
    error_type = "ok"
    success = True
    suggestion = ""

    # PowerShell Find/Select-String path errors
    if any(kw in text[:300] for kw in ("找不到路径", "cannot find path", "不存在", "not found", "does not exist")):
        error_type = "file_not_found"
        success = False
        suggestion = "文件路径不存在，请先用 glob 搜索正确路径，不要重复修改路径尝试。"
        if searched_nm:
            suggestion += " 路径在 node_modules 中，这是第三方依赖，建议搜索源码目录。"
    # exit code errors
    elif any(kw in text for kw in ("exit code: 1", "exit code: 2", "命令超时", "timeout")):
        error_type = "command_failed"
        success = False
        suggestion = "命令执行失败，请检查命令是否正确或更换方案。"
    # Module/Import errors
    elif any(kw in text[:500] for kw in ("modulenotfounderror", "importerror", "cannot import")):
        error_type = "import_error"
        success = False
        suggestion = "模块导入失败，检查是否已安装或路径是否正确。"
    # Tool execution errors
    elif any(kw in text for kw in ("工具执行错误", "执行命令出错")):
        error_type = "tool_error"
        success = False
        suggestion = "工具执行异常，建议检查参数或换用其他工具。"
    # Stderr with path errors (PowerShell non-terminating)
    elif "select-string" in text and "找不到路径" in text:
        error_type = "file_not_found"
        success = False
        suggestion = "Select-String 路径无效，请先确认文件存在。"
    # Generic error indicators
    elif any(kw in text[:300] for kw in ("错误:", "error:", "failed:", "❌")):
        error_type = "error"
        success = False
        # Only suggest if there isn't already a specific error type
        if not suggestion:
            suggestion = "操作返回了错误，建议检查输入或换一种方式实现。"
    # Empty results from search
    elif "无结果" in text or "no results" in text or "(无输出)" in text:
        error_type = "no_results"
        success = False  # treat as not-success but not critical
        suggestion = "没有找到匹配结果，请尝试更换搜索关键词或路径。"

    return {
        "success": success,
        "error_type": error_type,
        "suggestion": suggestion,
        "searched_node_modules": searched_nm,
    }


def guard_tool_call(name: str, params: dict) -> tuple[bool, str]:
    """Pre-execution validation. Returns (allowed, warning_message)."""
    if name == "grep":
        path = params.get("path", "")
        if path:
            warning = check_search_scope(path)
            if warning and path in _NODE_MODULES_WARNED:
                return False, warning  # Block: already warned once about this node_modules path
            if warning:
                return True, warning  # Allow with warning (first time)

    if name == "bash":
        cmd = params.get("command", "")
        cmd_lower = cmd.lower()
        # Block raw Select-String on node_modules without wildcard
        if "select-string" in cmd_lower and "node_modules" in cmd_lower and "*" not in cmd_lower:
            return True, "⚠️ 在 node_modules 中搜索特定文件路径效率很低。建议用通配符或搜索源码目录。"

    if name == "read":
        path = params.get("file_path", "")
        if path and not os.path.exists(path):
            # Don't block, but warn
            return True, f"⚠️ 文件 '{os.path.basename(path)}' 不存在，请先确认路径。"

    return True, ""


def _check_references(file_path: str, max_refs: int = 10) -> list[str]:
    """Quick scan for files that import/reference the modified file.

    Returns relative paths of files that contain the module name.
    Skips .git, node_modules, __pycache__.
    """
    basename = os.path.basename(file_path)
    name_no_ext = os.path.splitext(basename)[0]
    if not name_no_ext or name_no_ext == "index":
        return []
    refs: list[str] = []
    try:
        cwd = os.getcwd()
        for root, dirs, files in os.walk(cwd):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", ".venv", ".claude")]
            for f in files:
                if not f.endswith((".ts", ".tsx", ".js", ".jsx", ".py")):
                    continue
                fp = os.path.join(root, f)
                try:
                    with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read(16384)  # read first 16KB
                    if name_no_ext in content:
                        rel = os.path.relpath(fp, cwd)
                        if rel != os.path.relpath(file_path, cwd):
                            refs.append(rel)
                            if len(refs) >= max_refs:
                                return refs
                except Exception:
                    continue
    except Exception:
        pass
    return refs
# ── Incremental file validation ──

_VALIDATION_ENABLED = True


def _run_validation(file_path: str, old_content: str | None = None) -> tuple[str, str]:
    """Run file-type-specific validation after write/edit.

    Returns (hard_errors, warnings):
      - hard_errors: syntax errors that require rollback (Python, JSON)
      - warnings: type errors that should be flagged but not rolled back (tsc)
    """
    if not _VALIDATION_ENABLED:
        return "", ""

    ext = os.path.splitext(file_path)[1].lower()
    hard_errors: list[str] = []
    warnings: list[str] = []

    if ext in (".ts", ".tsx", ".js", ".jsx"):
        if ext in (".ts", ".tsx"):
            try:
                result = subprocess.run(
                    ["npx", "tsc", "--noEmit", "--pretty", "false", file_path],
                    capture_output=True, text=True, errors="replace",
                    timeout=30, cwd=os.path.dirname(file_path),
                )
                if result.returncode != 0:
                    out = (result.stdout or "") + (result.stderr or "")
                    out = out.strip()
                    if out:
                        head = "\n".join(out.split("\n")[:10])
                        warnings.append(f"⚠ TypeScript 验证: {len(out.split(chr(10)))} 个问题\n{head}")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

    if ext == ".py":
        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", file_path],
                capture_output=True, text=True, errors="replace",
                timeout=15,
            )
            if result.returncode != 0:
                hard_errors.append(f"⚠ Python 语法错误:\n{result.stderr.strip()}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    if ext == ".json" and "package" in os.path.basename(file_path).lower():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            hard_errors.append(f"⚠ package.json 格式无效: {e}")

    return "\n".join(hard_errors), "\n".join(warnings)


# ── BuildRunner ──

class BuildRunner:
    """Smart build executor with retry, cleanup, and error analysis.

    Detects retryable vs non-retryable build failures and acts accordingly.
    """

    def __init__(self):
        self.attempt = 0
        self.max_retries = 2

    def run(self, command: str, shell_cmd: list[str], timeout: int, output_callback=None) -> str:
        """Execute a build command with retry logic."""
        self.attempt = 0
        last_result: str = ""
        while self.attempt <= self.max_retries:
            self.attempt += 1

            # Self-heal before each retry
            if self.attempt > 1:
                heal_report = _self_heal()
                if heal_report and output_callback:
                    output_callback(f"\n[重试 {self.attempt}/{self.max_retries}] {heal_report}\n")

            result = self._run_once(command, shell_cmd, timeout, output_callback)
            last_result = result

            # Success → done
            if "Exit code: 0" not in result and "exit code 0" not in result.lower():
                # Check exit code from the result
                pass  # we'll check via returncode below

            # Analyze result for retry eligibility
            if self.attempt <= self.max_retries and self._is_retryable(result):
                if output_callback:
                    output_callback(f"\n[重试 {self.attempt}/{self.max_retries}] 检测到可重试错误，清理环境后重试...\n")
                # Clean up common state
                self._cleanup_build_env(command)
                continue

            break  # non-retryable or out of retries

        return last_result

    def _run_once(self, command: str, shell_cmd: list[str], timeout: int, output_callback=None) -> str:
        """Execute a single build attempt."""
        _hb_stop = threading.Event()
        try:
            proc = subprocess.Popen(
                shell_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )

            # ── Heartbeat thread: keep watchdog alive during silent compile phases ──
            if output_callback:
                def _heartbeat():
                    while not _hb_stop.is_set():
                        _hb_stop.wait(30)
                        if not _hb_stop.is_set():
                            try:
                                output_callback("")  # empty = heartbeat
                            except Exception:
                                break
                hb_thread = threading.Thread(target=_heartbeat, daemon=True)
                hb_thread.start()

            stdout_lines: list[str] = []
            deadline = time.time() + timeout
            assert proc.stdout is not None
            for raw_line in iter(proc.stdout.readline, ""):
                if time.time() > deadline:
                    proc.kill()
                    return f"命令超时 ({timeout} 秒)\n" + "".join(stdout_lines)
                line = raw_line.rstrip()
                if line:
                    stdout_lines.append(line + "\n")
                    if output_callback:
                        output_callback(line + "\n")
            proc.stdout.close()
            stderr_remaining = proc.stderr.read() if proc.stderr else ""
            proc.wait()

            result = "".join(stdout_lines)
            if stderr_remaining:
                result += "\nSTDERR:\n" + stderr_remaining.rstrip()
            result += f"\nExit code: {proc.returncode}"

            _hb_stop.set()
            # ── Pattern matching ──
            if proc.returncode != 0 and result.strip():
                try:
                    from .build_patterns import get_engine
                    eng = get_engine()
                    match = eng.match(result)
                    if match and match.get("fix"):
                        result += f"\n\n[模式匹配] 识别到: {match['label']}\n建议: {match['fix']}"
                except Exception:
                    pass

            return result
        except Exception as e:
            return f"执行命令出错: {e}"
        finally:
            _hb_stop.set()

    def _is_retryable(self, result: str) -> bool:
        """Determine if a build failure is worth retrying."""
        retryable_signals = [
            "EADDRINUSE", "port already in use", "address already in use",
            "watchdog", "timed out", "超时",
            "Connection refused", "socket hang up",
            "EPIPE", "ECONNRESET", "ETIMEDOUT",
        ]
        result_lower = result.lower()
        for sig in retryable_signals:
            if sig.lower() in result_lower:
                return True
        return False

    def _cleanup_build_env(self, command: str) -> None:
        """Clean up build environment before retry."""
        try:
            if "expo" in command:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | "
                     "Where-Object { $_.CommandLine -match 'expo' } | "
                     "Select-Object -ExpandProperty ProcessId"],
                    capture_output=True, text=True, timeout=10, errors='replace',
                )
                for line in r.stdout.strip().split('\n'):
                    pid = line.strip()
                    if pid and pid.isdigit():
                        p = int(pid)
                        if p not in _agent_spawned_pids:
                            subprocess.run(
                                ['taskkill', '/F', '/PID', str(p)],
                                capture_output=True, timeout=5,
                            )
        except Exception:
            pass


def _handle_read(file_path: str) -> str:
    file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        return f"错误: 文件不存在: {file_path}"
    if not os.path.isfile(file_path):
        return f"错误: 路径不是文件: {file_path}"
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        content = smart_truncate(content, _TOOL_RESULT_MAX_LENGTH)
        return content
    except Exception as e:
        return f"读取文件出错: {e}"


def _restore_backup(file_path: str) -> str:
    """Restore a file from its pre-write backup. Returns status message."""
    original = _file_backups.get(file_path)
    try:
        if original is not None:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(original)
            return "已恢复原始内容"
        else:
            # File didn't exist before — delete the failed write
            if os.path.exists(file_path):
                os.remove(file_path)
            return "已删除新建的文件（回滚到不存在状态）"
    except Exception as e:
        return f"回滚失败: {e}"



def _handle_write(file_path: str, content: str) -> str:
    file_path = os.path.normpath(os.path.abspath(file_path))
    if os.name == "nt" and len(file_path) >= 2 and file_path[1] == ":":
        file_path = file_path[0].upper() + file_path[1:]
    dir_path = os.path.dirname(file_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    # ── Backup: save original content before overwriting ──
    original_content: str | None = None
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()
        except Exception:
            pass
    _file_backups[file_path] = original_content

    # ── Dedup: detect repeated identical writes ──
    global _written_this_session
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    file_hash_key = f"{file_path}:{content_hash}"
    if file_hash_key in _written_this_session:
        return (f"⚠ 警告: 相同内容已写入过 {file_path}，不建议重复执行。"
                f"如果之前的修复没有效果，需要换一个方案而不是重复写入相同内容。")
    _written_this_session.add(file_hash_key)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        size = len(content.encode("utf-8"))
        result = f"成功写入 {size} 字节到 {file_path}"

        # ── Self-validation loop ──
        hard_errors, warnings = _run_validation(file_path)

        if hard_errors:
            # Hard error → rollback
            _restore_backup(file_path)
            # Record lesson
            fail_key = f"write:{file_path}:{content_hash}"
            _consecutive_fails[fail_key] = _consecutive_fails.get(fail_key, 0) + 1
            _session_lessons.append({
                "type": "write_failed",
                "file": file_path,
                "hash": content_hash,
                "error": hard_errors[:200],
                "attempt": _consecutive_fails[fail_key],
                "timestamp": time.time(),
            })
            return (f"❌ 验证失败: 已自动回滚\n{hard_errors}"
                    + (f"\n[教训 #{_consecutive_fails[fail_key]}] 该方案未通过验证，需要换一个方案" if _consecutive_fails[fail_key] >= 2 else ""))

        if warnings:
            result += f"\n{warnings}"

        # ── Reference scan ──
        refs = _check_references(file_path)
        if refs:
            limit = 6
            result += f"\n📎 检测到 {len(refs)} 个文件可能引用了此模块，可能需要同步更新:"
            for r in refs[:limit]:
                result += f"\n   {r}"
            if len(refs) > limit:
                result += f"\n   ... 及其他 {len(refs) - limit} 个"

        # Clear consecutive fail counter on success
        for k in list(_consecutive_fails.keys()):
            if file_path in k:
                del _consecutive_fails[k]
        return result
    except Exception as e:
        return f"写入文件出错: {e}"


def _handle_edit(file_path: str, old_string: str, new_string: str) -> str:
    file_path = os.path.normpath(os.path.abspath(file_path))
    if os.name == "nt" and len(file_path) >= 2 and file_path[1] == ":":
        file_path = file_path[0].upper() + file_path[1:]
    if not os.path.exists(file_path):
        return f"错误: 文件不存在: {file_path}"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return f"读取文件出错: {e}"

    count = content.count(old_string)
    if count == 0:
        return f"错误: 在文件中未找到要替换的字符串: {file_path}"
    if count > 1:
        return f"错误: 要替换的字符串在文件中出现了 {count} 次，必须唯一匹配。请提供更多上下文。"

    # ── Backup original ──
    _file_backups[file_path] = content

    new_content = content.replace(old_string, new_string)
    content_hash = hashlib.md5(new_content.encode("utf-8")).hexdigest()

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # ── Read-back verification ──
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                verified = f.read()
        except Exception:
            verified = ""

        if old_string in verified:
            # Write failed or was reverted — try full rewrite as fallback
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                with open(file_path, "r", encoding="utf-8") as f:
                    verified2 = f.read()
                if old_string in verified2:
                    return (f"错误: 写入 {file_path} 后验证失败，old_string 仍然存在。"
                            f"已尝试重写但未生效，建议使用 write 工具完整重写此文件。")
            except Exception as e:
                return f"写入文件出错（重试）: {e}"

        result = f"成功在 {file_path} 中替换了 1 处内容"

        # ── Self-validation loop ──
        hard_errors, warnings = _run_validation(file_path, old_content=content)

        if hard_errors:
            _restore_backup(file_path)
            fail_key = f"edit:{file_path}:{content_hash}"
            _consecutive_fails[fail_key] = _consecutive_fails.get(fail_key, 0) + 1
            _session_lessons.append({
                "type": "edit_failed",
                "file": file_path,
                "hash": content_hash,
                "error": hard_errors[:200],
                "attempt": _consecutive_fails[fail_key],
                "timestamp": time.time(),
            })
            return (f"❌ 验证失败: 编辑已自动回滚\n{hard_errors}"
                    + (f"\n[教训 #{_consecutive_fails[fail_key]}] 该方案未通过验证，需要换一个方案" if _consecutive_fails[fail_key] >= 2 else ""))

        if warnings:
            result += f"\n{warnings}"

        # ── Reference scan ──
        refs = _check_references(file_path)
        if refs:
            limit = 6
            result += f"\n📎 检测到 {len(refs)} 个文件可能引用了此模块，可能需要同步更新:"
            for r in refs[:limit]:
                result += f"\n   {r}"
            if len(refs) > limit:
                result += f"\n   ... 及其他 {len(refs) - limit} 个"

        for k in list(_consecutive_fails.keys()):
            if file_path in k:
                del _consecutive_fails[k]
        return result
    except Exception as e:
        return f"写入文件出错: {e}"


def _handle_glob(pattern: str, path: str | None = None) -> str:
    root = os.path.abspath(path) if path else os.getcwd()
    # Normalize separators on Windows to avoid backslash escape issues
    if os.name == "nt":
        root = root.replace("\\", "/")

    # Support {a,b,c} brace expansion (Python glob doesn't support it natively)
    def _expand_braces(pat: str) -> list[str]:
        brace_match = re.search(r'\{([^}]+)\}', pat)
        if not brace_match:
            return [pat]
        alternatives = brace_match.group(1).split(',')
        prefix = pat[:brace_match.start()]
        suffix = pat[brace_match.end():]
        result = []
        for alt in alternatives:
            expanded = prefix + alt + suffix
            result.extend(_expand_braces(expanded))
        return result

    patterns = _expand_braces(pattern)
    all_matches: list[str] = []

    for p in patterns:
        if os.path.isabs(p):
            full_pattern = p.replace("\\", "/") if os.name == "nt" else p
        else:
            full_pattern = root + "/" + p
        try:
            matches = glob_module.glob(full_pattern, recursive=True)
            all_matches.extend(matches)
        except Exception:
            continue

    all_matches = sorted(set(all_matches))

    if not all_matches:
        return "无匹配结果"

    rel_matches = []
    for m in all_matches:
        try:
            rel = os.path.relpath(m, root)
            rel_matches.append(rel)
        except ValueError:
            rel_matches.append(m)

    result = "\n".join(rel_matches)
    return result


def _handle_grep(
    pattern: str,
    path: str | None = None,
    glob_pattern: str | None = None,
    output_mode: str = "content",
) -> str:
    search_path = os.path.abspath(path) if path else os.getcwd()

    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return f"正则表达式无效: {e}"

    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".env", "venv", ".tox", "build", "dist", ".idea", ".vscode"}

    matches: list[str] = []
    files_seen: set[str] = set()

    try:
        if os.path.isfile(search_path):
            files = [search_path]
        else:
            files = []
            for root, dirs, fnames in os.walk(search_path):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for fname in fnames:
                    filepath = os.path.join(root, fname)
                    if glob_pattern:
                        if glob_module.fnmatch.fnmatch(fname, glob_pattern):
                            files.append(filepath)
                    else:
                        try:
                            with open(filepath, "rb") as f:
                                chunk = f.read(8192)
                            if b"\x00" not in chunk:
                                files.append(filepath)
                        except Exception:
                            pass

        for filepath in files:
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    for line_num, line in enumerate(f, 1):
                        if compiled.search(line):
                            relpath = os.path.relpath(filepath, os.getcwd())
                            if output_mode == "files_with_matches":
                                if relpath not in files_seen:
                                    files_seen.add(relpath)
                                    matches.append(relpath)
                            else:
                                matches.append(f"{relpath}:{line_num}:{line.rstrip()}")
            except Exception:
                continue

        if not matches:
            return "无匹配结果"

        result = "\n".join(matches)
        result = smart_truncate(result, _TOOL_RESULT_MAX_LENGTH)
        return result
    except Exception as e:
        return f"grep 搜索出错: {e}"


def _self_heal(heal_type: str = "build") -> str:
    """Pre-flight check: find and kill stale/zombie processes that may interfere.

    Returns a report of actions taken (empty string if nothing was done).
    """
    if sys.platform != "win32":
        return ""
    try:
        actions = []
        current_pid = os.getpid()
        kill_pid = lambda pid: subprocess.run(
            ['taskkill', '/F', '/PID', str(pid)],
            capture_output=True, timeout=5
        ).returncode == 0

        # Pattern 1: Stale expo export/start processes
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             'Get-CimInstance Win32_Process -Filter "Name=\'node.exe\'" | '
             'Where-Object { $_.CommandLine -match \'expo (export|start)\' } | '
             'Select-Object -ExpandProperty ProcessId'],
            capture_output=True, text=True, timeout=10, errors='replace',
        )
        for line in r.stdout.strip().split('\n'):
            pid = line.strip()
            if pid and pid.isdigit():
                p = int(pid)
                if p != current_pid and p not in _agent_spawned_pids and kill_pid(p):
                    actions.append(f"杀僵尸 expo PID {p}")

        # Pattern 2: Stale Claw instances (other python -m agent.app)
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             'Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'" | '
             'Where-Object { $_.ProcessId -ne ' + str(current_pid) + ' -and '
             '$_.CommandLine -match \'agent.app\' } | '
             'Select-Object -ExpandProperty ProcessId'],
            capture_output=True, text=True, timeout=10, errors='replace',
        )
        for line in r.stdout.strip().split('\n'):
            pid = line.strip()
            if pid and pid.isdigit():
                p = int(pid)
                if p not in _agent_spawned_pids and kill_pid(p):
                    actions.append(f"杀旧 Claw PID {p}")

        if actions:
            return f"[自愈] 释放资源: {'; '.join(actions)}"
        return ""
    except Exception:
        return ""


def _handle_bash(command: str, timeout: int = 120, output_callback=None) -> str:
    # Auto-extend timeout for slow operations
    if "pip install" in command or "npm install" in command:
        timeout = max(timeout, 300)
    timeout = min(timeout, 600)

    # ── Self-heal before build commands ──
    heal_report = ""
    is_build = any(kw in command for kw in ['expo', 'npx ', 'npm ', 'pip ', 'npx'])
    if is_build:
        heal_report = _self_heal()
        if heal_report and output_callback:
            output_callback(f"\n{heal_report}\n")

    is_retryable_build = is_build and any(kw in command for kw in ['expo', 'npx ', 'npm install', 'pip install'])

    try:
        if sys.platform == "win32":
            # PowerShell 5.1 does NOT support && (only PS 7+ does)
            # Convert && → ; for chaining commands
            normalized = command
            if " && " in normalized:
                normalized = normalized.replace(" && ", " ; ")
            shell_cmd = ["powershell", "-NoProfile", "-Command", normalized]
        else:
            shell_cmd = ["bash", "-c", command]

        if output_callback and is_retryable_build:
            # ── BuildRunner mode (retry + pattern matching) ──
            runner = BuildRunner()
            result = runner.run(command, shell_cmd, timeout, output_callback)
        elif output_callback:
            # ── Streaming mode: Popen + line-by-line ──
            _hb_stop2 = threading.Event()
            def _heartbeat2():
                while not _hb_stop2.is_set():
                    _hb_stop2.wait(30)
                    if not _hb_stop2.is_set():
                        try:
                            output_callback("")
                        except Exception:
                            break
            hb_thread2 = threading.Thread(target=_heartbeat2, daemon=True)
            hb_thread2.start()

            proc = subprocess.Popen(
                shell_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            stdout_lines: list[str] = []
            deadline = time.time() + timeout
            try:
                assert proc.stdout is not None
                for raw_line in iter(proc.stdout.readline, ""):
                    if time.time() > deadline:
                        proc.kill()
                        return f"命令超时 ({timeout} 秒)\n" + "".join(stdout_lines)
                    line = raw_line.rstrip()
                    if line:
                        stdout_lines.append(line + "\n")
                        output_callback(line + "\n")
                proc.stdout.close()
                stderr_remaining = proc.stderr.read() if proc.stderr else ""
                proc.wait()
                result = "".join(stdout_lines)
                if stderr_remaining and stderr_remaining.strip():
                    result += "\nSTDERR:\n" + stderr_remaining.rstrip()
                if proc.returncode != 0:
                    result += f"\nExit code: {proc.returncode}"

                # ── Pattern matching on streaming non-build results ──
                if proc.returncode != 0 and result.strip():
                    try:
                        from .build_patterns import get_engine
                        eng = get_engine()
                        match = eng.match(result)
                        if match and match.get("fix"):
                            result += f"\n\n[模式匹配] 识别到: {match['label']}\n建议: {match['fix']}"
                    except Exception:
                        pass
            except Exception:
                result = f"执行命令出错"
            finally:
                _hb_stop2.set()
        else:
            # ── Blocking mode (backward compatible) ──
            process = subprocess.run(
                shell_cmd,
                capture_output=True,
                text=True, errors='replace',
                timeout=timeout,
            )
            output_parts = []
            if process.stdout:
                output_parts.append(process.stdout.rstrip())
            if process.stderr:
                output_parts.append(f"STDERR:\n{process.stderr.rstrip()}")
            if process.returncode != 0:
                output_parts.append(f"Exit code: {process.returncode}")
            result = "\n".join(output_parts) if output_parts else "(无输出)"
            if heal_report:
                result = heal_report + "\n" + result

            # ── Pattern matching on blocking results ──
            if process.returncode != 0 and result.strip():
                try:
                    from .build_patterns import get_engine
                    eng = get_engine()
                    match = eng.match(result)
                    if match and match.get("fix"):
                        result += f"\n\n[模式匹配] 识别到: {match['label']}\n建议: {match['fix']}"
                except Exception:
                    pass

        result = smart_truncate(result, _TOOL_RESULT_MAX_LENGTH)
        return result or "(无输出)"
    except subprocess.TimeoutExpired:
        return f"命令超时 ({timeout} 秒)"
    except Exception as e:
        return f"执行命令出错: {e}"


def _handle_think(thought: str = "", content: str = "", title: str = "") -> str:
    return "已记录。"


def _handle_project_memory(action: str = "read", content: str = "") -> str:
    """Read/write/append project-level persistent memory (CLAUDE.md)."""
    from .memory import save_project_memory, load_project_memory

    if action == "read":
        mem = load_project_memory()
        if mem:
            return f"## 项目记忆\n\n{mem}"
        return "项目记忆为空。使用 project_memory 工具写入项目约定和规范。"

    if action == "write":
        if not content:
            return "错误: write 操作需要提供 content 参数"
        return save_project_memory(content)

    if action == "append":
        if not content:
            return "错误: append 操作需要提供 content 参数"
        current = load_project_memory()
        new_content = (current + "\n" + content) if current else content
        return save_project_memory(new_content)

    return f"错误: 未知操作 '{action}'"


def _handle_system_info(category: str = "all") -> str:
    """Get Windows system info via PowerShell."""
    scripts = {
        "os": "Get-CimInstance Win32_OperatingSystem | Format-List Caption, Version, BuildNumber, OSArchitecture, LastBootUpTime, InstallDate",
        "cpu": "Get-CimInstance Win32_Processor | Format-List Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, Manufacturer",
        "memory": "Get-CimInstance Win32_ComputerSystem | Format-List TotalPhysicalMemory; Get-CimInstance Win32_OperatingSystem | Format-List FreePhysicalMemory, TotalVisibleMemorySize, FreeVirtualMemory",
        "disk": "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Format-Table DeviceID, Size, FreeSpace, @{n='Free%';e={[math]::Round($_.FreeSpace/$_.Size*100,1)}} -AutoSize",
        "network": "Get-CimInstance Win32_NetworkAdapter | Where-Object {$_.NetEnabled} | Format-Table Name, MACAddress, Speed, NetConnectionStatus -AutoSize",
        "software": "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | Select-Object DisplayName, DisplayVersion, Publisher | Where-Object {$_.DisplayName} | Format-Table -AutoSize",
        "environment": "Get-ChildItem Env: | Format-Table Name, Value -AutoSize",
    }
    if category == "all":
        results = []
        for cat, script in scripts.items():
            r = _run_powershell(script)
            results.append(f"═══ {cat.upper()} ═══\n{r}")
        return "\n\n".join(results)
    script = scripts.get(category)
    if not script:
        return f"未知类别: {category}"
    return _run_powershell(script)


def _handle_process(action: str, name: str | None = None, pid: int | None = None) -> str:
    """Manage Windows processes."""
    if action == "list":
        return _run_powershell("Get-Process | Sort-Object CPU -Descending | Select-Object -First 50 Id, ProcessName, CPU, WorkingSet64, StartTime | Format-Table -AutoSize")
    elif action == "search":
        if not name:
            return "需要提供进程名称"
        return _run_powershell(f"Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Format-Table Id, ProcessName, CPU, WorkingSet64 -AutoSize")
    elif action == "kill":
        if name:
            return _run_powershell(f"Stop-Process -Name '{name}' -Force -ErrorAction Stop; echo '已终止进程: {name}'")
        elif pid:
            return _run_powershell(f"Stop-Process -Id {pid} -Force -ErrorAction Stop; echo '已终止 PID: {pid}'")
        return "需要提供 name 或 pid"
    return f"未知操作: {action}"


def _handle_web(url: str, method: str = "GET", data: str | None = None, headers: str | None = None) -> str:
    """Send HTTP request using Python requests (available via bash/powershell)."""
    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(url, method=method)
        if headers:
            try:
                hdrs = json.loads(headers)
                for k, v in hdrs.items():
                    req.add_header(k, v)
            except json.JSONDecodeError:
                pass
        if method == "POST" and data:
            req.data = data.encode("utf-8")
            if not headers or "Content-Type" not in str(headers):
                req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            info = f"HTTP {resp.status} {resp.reason} | {len(body)} 字节"
            max_body = 5000
            if len(body) > max_body:
                body = body[:max_body] + f"\n\n... (截断, 共 {len(body)} 字节)"
            return f"{info}\n\n{body}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:1000]
        return f"HTTP 错误 {e.code}: {e.reason}\n{body}"
    except Exception as e:
        return f"请求失败: {e}"


def _handle_web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo. Returns titles + snippets + URLs."""
    max_results = min(max(max_results, 1), 10)
    try:
        import requests as _requests
        params = {"q": query}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        }
        resp = _requests.get(
            "https://html.duckduckgo.com/html/",
            params=params,
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        html = resp.text

        import re
        results = []
        for m in re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>',
            html,
        ):
            href = m.group(1)
            title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            results.append({"title": title, "href": href})

        # Extract snippets
        snippets = re.findall(
            r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>',
            html,
        )

        lines = [f"搜索: {query}", ""]
        for i, r in enumerate(results[:max_results]):
            snippet = snippets[i].strip() if i < len(snippets) else ""
            snippet = re.sub(r'<[^>]+>', '', snippet)
            lines.append(f"{i+1}. {r['title']}")
            if snippet:
                lines.append(f"   {snippet[:200]}")
            lines.append(f"   {r['href']}")
            lines.append("")

        if not lines:
            return f"搜索 '{query}' 无结果"

        return "\n".join(lines).strip()
    except Exception as e:
        return f"搜索失败: {e}"


def _handle_ask_user(question: str, options: str = "") -> str:
    """Ask user a question and return their response."""
    result = f"QUESTION: {question}"
    if options:
        try:
            opts = json.loads(options)
            if isinstance(opts, list) and opts:
                result += "\nOPTIONS:\n" + "\n".join(f"  [{i+1}] {o}" for i, o in enumerate(opts))
        except json.JSONDecodeError:
            pass
    result += "\n\n请等待用户回复后再继续。"
    return result


def _handle_screencap() -> str:
    """Capture desktop screenshot via PowerShell and return base64."""
    ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
try {
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bounds.Size)
    $ms = New-Object System.IO.MemoryStream
    $bitmap.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $bytes = $ms.ToArray()
    [Convert]::ToBase64String($bytes)
} catch {
    "SCREENSHOT_ERROR: $_"
}
'''
    result = _run_powershell(ps_script)
    if result.startswith("SCREENSHOT_ERROR"):
        return f"截图失败: {result.replace('SCREENSHOT_ERROR: ', '')}"
    if len(result) < 100:
        return f"截图失败: {result}"
    b64_len = len(result)
    return f"[SCREENSHOT base64 len={b64_len}]\n{result}"


def _run_powershell(script: str) -> str:
    """Helper: run a PowerShell script and return output."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, errors='replace', timeout=30,
        )
        out = proc.stdout.rstrip() if proc.stdout else ""
        err = proc.stderr.rstrip() if proc.stderr else ""
        if err:
            out += f"\n[stderr]\n{err}"
        if proc.returncode != 0 and not out:
            out += f"\nExit code: {proc.returncode}"
        return out or "(无输出)"
    except subprocess.TimeoutExpired:
        return "命令执行超时"
    except Exception as e:
        return f"执行错误: {e}"


# ──────────────────────────────────────────────
# Browser control (Playwright)
# ──────────────────────────────────────────────

_browser: Any = None
_browser_context: Any = None
_browser_page: Any = None
_browser_console_logs: list[str] = []
_browser_network_errors: list[str] = []
_browser_page_errors: list[str] = []


def _setup_browser_listeners(page) -> None:
    """Attach diagnostic listeners to a Playwright page."""
    global _browser_console_logs, _browser_network_errors, _browser_page_errors
    _browser_console_logs = []
    _browser_network_errors = []
    _browser_page_errors = []

    def _on_console(msg):
        txt = msg.text[:500]
        _browser_console_logs.append(f"[{msg.type}] {txt}")

    def _on_page_error(err):
        _browser_page_errors.append(str(err)[:500])

    def _on_request_failed(req):
        url = req.url[:200]
        fail = str(req.failure) if req.failure else "unknown"
        _browser_network_errors.append(f"{url} -> {fail}")

    page.on("console", _on_console)
    page.on("pageerror", _on_page_error)
    page.on("requestfailed", _on_request_failed)


def _get_browser_page():
    """Lazy-init a persistent Playwright browser page with diagnostic listeners."""
    global _browser, _browser_context, _browser_page
    if _browser_page is not None:
        try:
            _browser_page.title()
            return _browser_page
        except Exception:
            _browser_page = None

    try:
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()
        _browser = p.chromium.launch(headless=False)
        _browser_context = _browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        _browser_page = _browser_context.new_page()
        _setup_browser_listeners(_browser_page)
        return _browser_page
    except Exception as e:
        raise RuntimeError(f"浏览器启动失败: {e}")


def _handle_browser(
    action: str,
    url: str = "",
    selector: str = "",
    text: str = "",
    script: str = "",
) -> str:
    """Control a browser via Playwright (persistent instance across calls)."""
    try:
        page = _get_browser_page()
    except RuntimeError as e:
        return str(e)

    try:
        if action == "navigate":
            if not url:
                return "错误: navigate 操作需要提供 url"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(0.5)
            title = page.title()
            content = page.inner_text("body")[:3000]
            return f"已导航到: {url}\n标题: {title}\n\n页面内容:\n{content}"

        elif action == "click":
            if not selector:
                return "错误: click 操作需要提供 selector"
            page.click(selector, timeout=10000)
            time.sleep(0.3)
            return f"已点击: {selector}"

        elif action == "type":
            if not selector:
                return "错误: type 操作需要提供 selector 和 text"
            page.fill(selector, text)
            return f"已在 {selector} 输入: {text[:100]}"

        elif action == "read":
            if selector:
                elements = page.query_selector_all(selector)
                if not elements:
                    return f"未找到元素: {selector}"
                results = []
                for i, el in enumerate(elements[:20]):
                    t = el.inner_text()
                    if t:
                        results.append(f"[{i}] {t[:200]}")
                return "\n".join(results) if results else "(元素无文本内容)"
            else:
                content = page.inner_text("body")[:5000]
                return content or "(页面无文本内容)"

        elif action == "screenshot":
            b64 = page.screenshot(full_page=False, type="png")
            import base64
            encoded = base64.b64encode(b64).decode("utf-8")
            return f"[BROWSER_SCREENSHOT base64 len={len(encoded)}]\n{encoded}"

        elif action == "html":
            html = page.content()[:8000]
            return html

        elif action == "get_url":
            return f"当前 URL: {page.url}"

        elif action == "console":
            lines = _browser_console_logs
            if not lines:
                return "(无 console 输出)"
            return "\n".join(lines[-50:])

        elif action == "network":
            lines = _browser_network_errors
            if not lines:
                return "(无 network 错误)"
            return "\n".join(lines[-50:])

        elif action == "diagnose":
            if url:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
            title = page.title()
            body_text = page.inner_text("body")[:3000]
            html_scripts = []
            import re
            for m in re.finditer(r'<script[^>]*src="([^"]*)"', page.content()):
                html_scripts.append(m.group(1))

            parts = [
                f"=== 页面诊断 ===",
                f"URL: {page.url}",
                f"标题: {title}",
                f"=== Console 输出 ({len(_browser_console_logs)} 条) ===",
            ]
            for c in _browser_console_logs[-30:]:
                parts.append(f"  {c}")
            if _browser_page_errors:
                parts.append(f"=== 页面 JS 错误 ({len(_browser_page_errors)} 条) ===")
                for e in _browser_page_errors:
                    parts.append(f"  {e}")
            if _browser_network_errors:
                parts.append(f"=== Network 失败 ({len(_browser_network_errors)} 条) ===")
                for n in _browser_network_errors[-20:]:
                    parts.append(f"  {n}")
            parts.append(f"=== Script 标签 ===")
            for s in html_scripts[:10]:
                parts.append(f"  {s}")
            if body_text.strip():
                parts.append(f"=== 页面文本内容 ===")
                parts.append(body_text[:2000])
            else:
                parts.append(f"=== 页面为空（无文本内容）===")

            return "\n".join(parts)

        elif action == "execute_js":
            if not script:
                return "错误: execute_js 需要提供 script"
            result = page.evaluate(script)
            return f"JS 执行结果:\n{result}"

        elif action == "close":
            global _browser, _browser_context, _browser_page
            try:
                _browser_page = None
                _browser_context = None
                if _browser:
                    _browser.close()
                _browser = None
            except Exception:
                pass
            return "浏览器已关闭"

        else:
            return f"错误: 未知操作 '{action}'"

    except Exception as e:
        return f"浏览器操作出错 ({action}): {e}"


# ──────────────────────────────────────────────
# Background task runner
# ──────────────────────────────────────────────

_background_tasks: dict[str, dict] = {}
_background_lock = threading.Lock()


def _handle_background(action: str, command: str = "", task_id: str = "",
                        pattern: str = "", timeout: int = 300) -> str:
    """Run commands in the background (non-blocking)."""
    global _background_tasks

    if action == "start":
        if not command:
            return "错误: start 操作需要提供 command"
        tid = uuid.uuid4().hex[:8]
        try:
            shell_cmd = ["powershell", "-NoProfile", "-Command", command]
            proc = subprocess.Popen(
                shell_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            _agent_spawned_pids.add(proc.pid)
            with _background_lock:
                _background_tasks[tid] = {
                    "proc": proc,
                    "command": command[:100],
                    "started": time.strftime("%H:%M:%S"),
                    "stdout": [],
                    "stderr": [],
                    "done": False,
                }
            # Start collector threads
            def _collect(stream, target):
                for line in iter(stream.readline, ""):
                    with _background_lock:
                        if tid in _background_tasks:
                            _background_tasks[tid][target].append(line.rstrip())
                stream.close()
                with _background_lock:
                    if tid in _background_tasks:
                        _background_tasks[tid]["done"] = True

            threading.Thread(target=_collect, args=(proc.stdout, "stdout"), daemon=True).start()
            threading.Thread(target=_collect, args=(proc.stderr, "stderr"), daemon=True).start()
            return f"后台任务已启动\n任务 ID: {tid}\n命令: {command[:200]}"
        except Exception as e:
            return f"启动后台任务失败: {e}"

    elif action == "list":
        with _background_lock:
            if not _background_tasks:
                return "当前没有运行中的后台任务"
            lines = []
            for tid, task in _background_tasks.items():
                status = "已完成" if task["done"] else "运行中"
                lines.append(f"[{tid}] {status} | {task['started']} | {task['command']}")
            return "\n".join(lines)

    elif action == "output":
        if not task_id:
            return "错误: output 操作需要提供 task_id"
        with _background_lock:
            task = _background_tasks.get(task_id)
        if not task:
            return f"未找到任务: {task_id}"
        return _format_background_output(task_id, task)

    elif action == "stop":
        if not task_id:
            return "错误: stop 操作需要提供 task_id"
        with _background_lock:
            task = _background_tasks.get(task_id)
        if not task:
            return f"未找到任务: {task_id}"
        try:
            _agent_spawned_pids.discard(task["proc"].pid)
            task["proc"].terminate()
            task["done"] = True
            return f"任务 {task_id} 已终止"
        except Exception as e:
            return f"终止任务失败: {e}"

    elif action == "stop_all":
        with _background_lock:
            tids = list(_background_tasks.keys())
        for tid in tids:
            with _background_lock:
                task = _background_tasks.get(tid)
            if task and not task["done"]:
                try:
                    _agent_spawned_pids.discard(task["proc"].pid)
                    task["proc"].terminate()
                    task["done"] = True
                except Exception:
                    pass
        return f"已终止 {len(tids)} 个任务"

    elif action == "wait":
        if not task_id:
            return "错误: wait 操作需要提供 task_id"
        if pattern:
            try:
                re.compile(pattern)
            except re.error:
                return f"错误: 无效的正则表达式模式 '{pattern}'"
        with _background_lock:
            task = _background_tasks.get(task_id)
        if not task:
            return f"未找到任务: {task_id}"
        if task["done"]:
            return f"任务 {task_id} 已结束\n" + _format_background_output(task_id, task)

        deadline = time.time() + timeout
        while time.time() < deadline:
            with _background_lock:
                task = _background_tasks.get(task_id)
            if task is None:
                return f"任务 {task_id} 已消失"
            if task["done"]:
                return f"任务 {task_id} 已完成\n" + _format_background_output(task_id, task)
            if pattern:
                stdout_text = "\n".join(task["stdout"])
                if re.search(pattern, stdout_text, re.IGNORECASE):
                    return (f"任务 {task_id} 输出匹配模式: {pattern}\n"
                            + _format_background_output(task_id, task))
            time.sleep(0.5)
        return (f"等待超时 ({timeout}s)，任务 {task_id} 仍在运行\n"
                + _format_background_output(task_id, task))

def _format_background_output(task_id: str, task: dict) -> str:
    """Format background task output for display."""
    out = "\n".join(task["stdout"][-100:]) if task["stdout"] else ""
    err = "\n".join(task["stderr"][-50:]) if task["stderr"] else ""
    parts = []
    if out:
        parts.append(f"--- STDOUT ---\n{out}")
    if err:
        parts.append(f"--- STDERR ---\n{err}")
    status = "已完成" if task["done"] else "运行中"
    result = f"任务 {task_id} 状态: {status}\n"
    result += f"命令: {task['command']}\n"
    result += f"输出行数: stdout={len(task['stdout'])}, stderr={len(task['stderr'])}\n"
    if parts:
        result += "\n".join(parts)
    else:
        result += "(暂无输出)"
    return result



# ──────────────────────────────────────────────

_plans: dict[str, dict] = {}
_plan_id_counter: int = 0


def _handle_plan(
    action: str,
    title: str = "",
    plan_id: str = "",
    steps: str = "",
    step_index: int = 0,
    step_status: str = "",
) -> str:
    """Create and track structured plans."""
    global _plan_id_counter

    if action == "create":
        if not title or not steps:
            return "错误: create 需要提供 title 和 steps"
        try:
            steps_list = json.loads(steps)
            if not isinstance(steps_list, list):
                return "错误: steps 必须是 JSON 数组"
        except json.JSONDecodeError:
            return "错误: steps 格式无效"
        _plan_id_counter += 1
        pid = f"plan-{_plan_id_counter}"
        _plans[pid] = {
            "title": title,
            "steps": steps_list,
            "created": time.strftime("%H:%M:%S"),
            "current_step": -1,
        }
        done = sum(1 for s in steps_list if s.get("status") == "completed")
        total = len(steps_list)
        lines = [f"计划已创建 | ID: {pid} | {title} | 进度: {done}/{total}"]
        for i, s in enumerate(steps_list):
            mark = "x" if s.get("status") == "completed" else " "
            lines.append(f"  [{i}] [{mark}] {s['step']}")
        return "\n".join(lines)

    elif action == "update":
        if not plan_id:
            return "错误: update 需要提供 plan_id"
        plan = _plans.get(plan_id)
        if not plan:
            return f"未找到计划: {plan_id}"
        steps_list = plan["steps"]
        if step_index < 0 or step_index >= len(steps_list):
            return f"步骤 {step_index} 超出范围 (0-{len(steps_list)-1})"
        if step_status not in ("pending", "in_progress", "completed"):
            return f"无效状态: {step_status}"
        steps_list[step_index]["status"] = step_status
        if step_status == "in_progress":
            plan["current_step"] = step_index
        done = sum(1 for s in steps_list if s.get("status") == "completed")
        total = len(steps_list)
        return f"计划 [{plan_id}] 步骤 {step_index} -> {step_status} ({done}/{total})"

    elif action == "list":
        if not _plans:
            return "暂无计划"
        return "\n".join(
            f"[{pid}] {p['title']} ({sum(1 for s in p['steps'] if s.get('status')=='completed')}/{len(p['steps'])})"
            for pid, p in _plans.items()
        )

    elif action == "show":
        if not plan_id:
            return "错误: show 需要提供 plan_id"
        plan = _plans.get(plan_id)
        if not plan:
            return f"未找到计划: {plan_id}"
        done = sum(1 for s in plan["steps"] if s.get("status") == "completed")
        total = len(plan["steps"])
        marks = {"pending": " ", "in_progress": "~", "completed": "x"}
        lines = [f"计划: {plan['title']} | {done}/{total}"]
        for i, s in enumerate(plan["steps"]):
            m = marks.get(s.get("status", "pending"), " ")
            lines.append(f"  [{i}] [{m}] {s['step']}")
        return "\n".join(lines)

    else:
        return f"错误: 未知操作 '{action}'"


def _handle_task(status: str, message: str = "") -> str:
    """Quick task status update."""
    icons = {"start": ">", "progress": "~", "done": "x", "fail": "!"}
    icon = icons.get(status, "?")
    msg = f"  {message}" if message else ""
    return f"[{icon}] {status}{msg}"


# ──────────────────────────────────────────────
# AST Analysis — parse source, extract structure
# ──────────────────────────────────────────────

def _handle_ast(file_path: str) -> str:
    """Parse a Python file into AST and extract its structure."""
    import ast as ast_module
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
    except FileNotFoundError:
        return f"错误: 文件不存在: {file_path}"
    except Exception as e:
        return f"错误: 读取失败: {e}"

    try:
        tree = ast_module.parse(source)
    except SyntaxError as e:
        return f"语法错误: {e}"

    lines = [f"文件: {file_path}"]
    lines.append(f"总行数: {len(source.splitlines())}")

    # ── Imports ──
    imports = []
    for node in ast_module.walk(tree):
        if isinstance(node, ast_module.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast_module.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append(f"{mod}.{alias.name}")
    if imports:
        lines.append(f"\n--- 导入 ({len(imports)}) ---")
        for i in sorted(set(imports)):
            lines.append(f"  import {i}")

    # ── Top-level: functions, classes, assignments ──
    top_level = []
    classes = []

    for node in ast_module.iter_child_nodes(tree):
        if isinstance(node, ast_module.FunctionDef):
            args = [a.arg for a in node.args.args]
            decos = [d.id if isinstance(d, ast_module.Name) else ast_module.dump(d) for d in node.decorator_list]
            deco_str = f" @{', '.join(decos)}" if decos else ""
            lines.append(f"\n  def {node.name}({', '.join(args)}){deco_str}")
            lines.append(f"    L{node.lineno}-L{node.end_lineno} | body={len(node.body)} stmts")
            # Return type annotation
            if node.returns:
                lines.append(f"    -> {ast_module.dump(node.returns)}")

        elif isinstance(node, ast_module.AsyncFunctionDef):
            args = [a.arg for a in node.args.args]
            lines.append(f"\n  async def {node.name}({', '.join(args)})")
            lines.append(f"    L{node.lineno}-L{node.end_lineno} | body={len(node.body)} stmts")

        elif isinstance(node, ast_module.ClassDef):
            bases = [ast_module.dump(b) for b in node.bases]
            base_str = f"({', '.join(bases)})" if bases else ""
            lines.append(f"\n  class {node.name}{base_str}")
            lines.append(f"    L{node.lineno}-L{node.end_lineno}")

            # Class methods
            for item in ast_module.iter_child_nodes(node):
                if isinstance(item, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)):
                    args = [a.arg for a in item.args.args]
                    kind = "async def" if isinstance(item, ast_module.AsyncFunctionDef) else "def"
                    decos = [d.id if isinstance(d, ast_module.Name) else ast_module.dump(d)
                             for d in item.decorator_list]
                    deco_str = f" @{', '.join(decos)}" if decos else ""
                    func_line = f"    {kind} {item.name}({', '.join(args)}){deco_str}"
                    lines.append(func_line)

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Dependency Graph — import/relationship analysis
# ──────────────────────────────────────────────

def _handle_dep_graph(path: str = "") -> str:
    """Analyze import dependencies between Python files in a project."""
    import ast as ast_module

    target = path or os.getcwd()
    if not os.path.exists(target):
        return f"错误: 路径不存在: {target}"
    if os.path.isfile(target):
        targets = [target]
        root_dir = os.path.dirname(target)
    else:
        root_dir = target
        targets = []
        for root, _, files in os.walk(target):
            for f in files:
                if f.endswith(".py"):
                    targets.append(os.path.join(root, f))
            if len(targets) > 200:  # safety cap
                break

    if not targets:
        return "未找到 Python 文件"

    # Build file → module mapping
    file_modules = {}  # file -> set of modules it imports
    module_file = {}   # module_name -> file (for local modules)

    # First pass: collect local module names
    for fp in targets:
        rel = os.path.relpath(fp, root_dir)
        mod = rel.replace("\\", "/").replace("/", ".").replace(".py", "")
        if mod.endswith(".__init__"):
            mod = mod[:-9]
        module_file[mod] = fp
        module_file[os.path.basename(fp).replace(".py", "")] = fp

    # Second pass: extract imports
    for fp in targets:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                tree = ast_module.parse(f.read())
        except (SyntaxError, Exception):
            continue

        imports = set()
        for node in ast_module.walk(tree):
            if isinstance(node, ast_module.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast_module.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
        file_modules[fp] = imports

    # Analyze
    local_files = set(targets)
    external_imports = {}
    internal_deps = {}  # file -> set of local files it depends on

    for fp in local_files:
        ext = set()
        internal = set()
        for imp in file_modules.get(fp, set()):
            if imp in module_file:
                internal.add(module_file[imp])
            else:
                ext.add(imp)
        external_imports[fp] = ext
        internal_deps[fp] = internal

    # Find circular dependencies
    graph = {fp: internal_deps[fp] for fp in local_files}
    circular = _find_cycles(graph)

    # Output
    lines = [f"依赖分析: {target}", f"文件数: {len(targets)}", ""]

    # Hub modules (most depended-upon)
    dep_counts = {}
    for fp in local_files:
        for dep in internal_deps[fp]:
            dep_counts[dep] = dep_counts.get(dep, 0) + 1

    hub = sorted(dep_counts.items(), key=lambda x: -x[1])[:10]
    if hub:
        lines.append(f"--- 核心模块 (被依赖最多) ---")
        for fp, cnt in hub:
            rel = os.path.relpath(fp, root_dir)
            lines.append(f"  {rel}: {cnt} 处引用")

    # Files with no internal deps (orphans / leaf modules)
    leaves = [fp for fp in local_files if not internal_deps.get(fp)]
    if leaves:
        lines.append(f"\n--- 叶子模块 (无内部依赖) ---")
        for fp in sorted(leaves)[:10]:
            lines.append(f"  {os.path.relpath(fp, root_dir)}")

    # Circular deps
    if circular:
        lines.append(f"\n--- ⚠ 循环依赖 ({len(circular)} 个) ---")
        for cycle in circular[:5]:
            names = [os.path.relpath(n, root_dir) for n in cycle]
            lines.append(f"  {' → '.join(names)}")

    # External dependencies
    all_ext = set()
    for fp in local_files:
        all_ext.update(external_imports[fp])
    if all_ext:
        lines.append(f"\n--- 外部依赖 ({len(all_ext)}) ---")
        for name in sorted(all_ext)[:30]:
            lines.append(f"  {name}")

    return "\n".join(lines)


def _find_cycles(graph: dict) -> list[list]:
    """Detect circular dependencies in a directed graph."""
    visited = set()
    path = []
    cycles = []

    def dfs(node):
        if node in path:
            idx = path.index(node)
            cycle = path[idx:] + [node]
            cycles.append(cycle)
            return
        if node in visited:
            return
        visited.add(node)
        path.append(node)
        for neighbor in graph.get(node, set()):
            if neighbor in graph:  # only follow local nodes
                dfs(neighbor)
        path.pop()

    for node in graph:
        dfs(node)

    # Deduplicate
    seen = set()
    unique = []
    for c in cycles:
        key = tuple(sorted(c[:-1]))  # remove the closing duplicate
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


# ──────────────────────────────────────────────
# Call Chain Analysis — trace function calls
# ──────────────────────────────────────────────

def _handle_call_chain(
    function_name: str,
    direction: str = "forward",
    path: str = "",
    depth: int = 3,
) -> str:
    """Trace function call chains: forward (what does this call) or backward (who calls this)."""
    import ast as ast_module
    from collections import defaultdict

    target = path or os.getcwd()
    if not os.path.exists(target):
        return f"错误: 路径不存在: {target}"

    # Collect Python files
    py_files = []
    if os.path.isfile(target):
        py_files = [target] if target.endswith(".py") else []
    else:
        for root, _, files in os.walk(target):
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))
            if len(py_files) > 500:
                break

    if not py_files:
        return "未找到 Python 文件"

    # Build call graph: caller -> set of callees
    calls: dict[str, dict] = defaultdict(lambda: {"calls": set(), "called_by": set(), "file": "", "line": 0})
    # Map: function_name -> list of (file, line) where it's defined
    defs: dict[str, list[tuple[str, int]]] = defaultdict(list)

    # Also track qualified names
    def _get_func_name(node):
        if isinstance(node, ast_module.Attribute):
            return _get_func_name(node.value) + "." + node.attr
        elif isinstance(node, ast_module.Name):
            return node.id
        return ast_module.dump(node)

    for fp in py_files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                tree = ast_module.parse(f.read())
        except (SyntaxError, Exception):
            continue

        # First: collect definitions
        for node in ast_module.walk(tree):
            if isinstance(node, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)):
                qname = node.name
                defs[qname].append((fp, node.lineno))
                calls[qname]["file"] = os.path.relpath(fp, target if os.path.isdir(target) else os.path.dirname(target))
                calls[qname]["line"] = node.lineno

        # Then: collect calls
        for node in ast_module.walk(tree):
            if isinstance(node, ast_module.Call):
                func = node.func
                callee = _get_func_name(func)
                if callee:
                    # Find enclosing function
                    for ancestor in ast_module.walk(tree):
                        if isinstance(ancestor, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)) and \
                           ancestor.lineno <= node.lineno <= (getattr(ancestor, 'end_lineno', ancestor.lineno)):
                            caller = ancestor.name
                            calls[caller]["calls"].add(callee)
                            calls[callee]["called_by"].add(caller)
                            break

    # Trace
    result_lines = []
    visited = set()

    if direction == "forward":
        result_lines.append(f"正向调用链: {function_name} (深度 ≤ {depth})\n")
        _trace_forward(function_name, calls, defs, 0, depth, result_lines, visited)
    elif direction == "backward":
        result_lines.append(f"反向调用链: 谁调用了 {function_name} (深度 ≤ {depth})\n")
        _trace_backward(function_name, calls, defs, 0, depth, result_lines, visited)
    else:
        return f"错误: direction 必须是 'forward' 或 'backward'"

    if len(result_lines) == 1:
        result_lines.append(f"  (未找到函数 '{function_name}' 的调用信息)")

    return "\n".join(result_lines)


def _trace_forward(name, calls, defs, depth, max_depth, lines, visited):
    if depth > max_depth or name in visited:
        return
    visited.add(name)
    prefix = "  " * depth + ("└─ " if depth > 0 else "")
    loc = calls.get(name, {})
    file_info = f" ({loc.get('file', '?')}:{loc.get('line', '?')})" if loc.get('file') else ""
    lines.append(f"{prefix}{name}{file_info}")

    for callee in sorted(calls.get(name, {}).get("calls", set())):
        _trace_forward(callee, calls, defs, depth + 1, max_depth, lines, visited)


def _trace_backward(name, calls, defs, depth, max_depth, lines, visited):
    if depth > max_depth or name in visited:
        return
    visited.add(name)
    prefix = "  " * depth + ("└─ " if depth > 0 else "")
    loc = calls.get(name, {})
    file_info = f" ({loc.get('file', '?')}:{loc.get('line', '?')})" if loc.get('file') else ""
    if depth > 0:
        lines.append(f"{prefix}{name}{file_info}")
    else:
        lines.append(f"{prefix}{name}{file_info} (目标函数)")

    for caller in sorted(calls.get(name, {}).get("called_by", set())):
        _trace_backward(caller, calls, defs, depth + 1, max_depth, lines, visited)


# ──────────────────────────────────────────────
# Error Trace — automatic root cause analysis
# ──────────────────────────────────────────────


def _handle_trace_error(error_message: str, file_path: str = "", depth: int = 2) -> str:
    """Automatically trace error root cause by searching project code."""
    import ast as ast_module
    max_depth = min(max(depth, 1), 5)
    lines = ["═══ 错误根因分析 ═══", ""]
    lines.append(f"原始错误: {error_message[:500]}")
    lines.append("")

    # ── 1. Extract error type and symbols ──
    err_lower = error_message.lower()
    err_type = ""
    if "modulenotfounderror" in err_lower or "importerror" in err_lower:
        err_type = "import"
    elif "attributeerror" in err_lower:
        err_type = "attribute"
    elif "typeerror" in err_lower:
        err_type = "type"
    elif "keyerror" in err_lower:
        err_type = "key"
    elif "filenotfounderror" in err_lower:
        err_type = "file"
    elif "syntaxerror" in err_lower:
        err_type = "syntax"
    elif "valueerror" in err_lower:
        err_type = "value"
    elif "timeout" in err_lower:
        err_type = "timeout"
    elif "connection" in err_lower:
        err_type = "connection"
    lines.append(f"错误类型: {err_type or '未知'}")
    lines.append("")

    # ── 2. Extract referenced symbols (module names, function names, etc.) ──
    import re
    symbols = set()
    for m in re.finditer(r"'(\\w+(?:\\.\\w+)*)'", error_message):
        symbols.add(m.group(1))
    for m in re.finditer(r'"(\\w+(?:\\.\\w+)*)"', error_message):
        symbols.add(m.group(1))

    # Also extract potential file paths from traceback
    trace_files = []
    for m in re.finditer(r'File "([^"]+)", line (\d+)', error_message):
        trace_files.append((m.group(1), int(m.group(2))))

    if trace_files:
        lines.append(f"堆栈涉及文件:")
        for tf, tln in trace_files[:10]:
            lines.append(f"  {tf}:{tln}")
        lines.append("")

    if symbols:
        lines.append(f"提取的关键符号: {', '.join(list(symbols)[:10])}")
        lines.append("")

    # ── 3. Search project for related definitions ──
    project_root = os.getcwd()
    search_paths = [project_root]
    if file_path and os.path.exists(file_path):
        search_paths.insert(0, os.path.dirname(os.path.abspath(file_path)))

    findings = []
    for sym in list(symbols)[:5]:
        # Search for the symbol's definition
        module_parts = sym.split(".")
        search_name = module_parts[-1]

        try:
            result = _run_powershell(
                f'Select-String -Path "*.py" -Pattern "(class |def |^|\\s+){search_name}\\b" '
                f'-Recurse -SimpleMatch -ErrorAction SilentlyContinue '
                f'| Select-Object -First 5 -ExpandProperty Line'
            )
            if result and "找不到" not in result:
                findings.append(f"符号 '{sym}' 的定义:\n{result[:300]}")
        except Exception:
            pass

    if not findings:
        lines.append("分析: 未在项目中找到相关定义，可能是外部依赖缺失。")
    else:
        for f in findings[:5]:
            lines.append(f)
            lines.append("")

    # ── 4. Import error specific: check package installation ──
    if err_type == "import" and symbols:
        mod_name = list(symbols)[0]
        mod_base = mod_name.split(".")[0]
        lines.append(f"尝试检查模块 '{mod_base}':")
        try:
            # Check if pip knows about it
            check = _run_powershell(
                f"pip list 2>$null | Select-String '{mod_base}'"
            )
            if check and mod_base.lower() in check.lower():
                lines.append(f"  ✓ {mod_base} 已安装: {check.strip()}")
            else:
                lines.append(f"  ✗ '{mod_base}' 未安装或不在 pip list 中")
                # Suggest install
                lines.append(f"  建议: pip install {mod_base}")
        except Exception:
            pass
        lines.append("")

    # ── 5. Check if error references a specific file path ──
    for m in re.finditer(r"(?:No such file|No such file or directory|ENOENT).*'([^']+)'", error_message):
        missing_path = m.group(1)
        lines.append(f"缺失文件: {missing_path}")
        # Check if it exists at an alternative location
        alt = os.path.join(project_root, missing_path.lstrip("./\\"))
        if os.path.exists(alt):
            lines.append(f"  ✓ 在 {alt} 找到")
        elif os.path.exists(missing_path):
            lines.append(f"  ✓ 直接在 {missing_path} 找到")
        lines.append("")

    lines.append("═══ 分析完成 ═══")

    return "\n".join(lines)


# ── Revert tool ──


def _handle_revert(file_path: str = "") -> str:
    """Revert a file modified in this session to its pre-write state.

    Uses _file_backups to restore. If no file_path given, lists recoverable files.
    """
    if not file_path:
        if not _file_backups:
            return "当前没有可恢复的备份"
        lines = ["可恢复的文件（共 %d 个）:" % len(_file_backups)]
        for fp, backup in sorted(_file_backups.items()):
            status = "有备份" if backup is not None else "新文件（可删除）"
            lines.append(f"  {fp}  [{status}]")
        return "\n".join(lines)

    fp = os.path.abspath(file_path)
    if fp not in _file_backups:
        return f"错误: 该文件没有备份，无法恢复。可用 revert （不指定路径）查看可恢复的文件。"
    return _restore_backup(fp)


# ── Built-in handler dispatch ──

BUILTIN_HANDLERS: dict[str, Any] = {
    "read": _handle_read,
    "write": _handle_write,
    "edit": _handle_edit,
    "glob": _handle_glob,
    "grep": _handle_grep,
    "bash": _handle_bash,
    "think": _handle_think,
    "project_memory": _handle_project_memory,
    "system_info": _handle_system_info,
    "process": _handle_process,
    "web": _handle_web,
    "web_search": _handle_web_search,
    "ask_user": _handle_ask_user,
    "screencap": _handle_screencap,
    "browser": _handle_browser,
    "background": _handle_background,
    "plan": _handle_plan,
    "task": _handle_task,
    "ast": _handle_ast,
    "dep_graph": _handle_dep_graph,
    "call_chain": _handle_call_chain,
    "revert": _handle_revert,
    "trace_error": _handle_trace_error,
}

PLUGIN_HANDLERS: dict[str, Any] = {}


# ── Periodic self-heal throttle ──
_last_heal_time: float = 0

def handle_tool_call(name: str, params: dict[str, Any], output_callback=None) -> str:
    """Dispatch a tool call to the appropriate handler."""
    # ── Pre-execution guardrails ──
    allowed, guard_msg = guard_tool_call(name, params)
    if not allowed:
        return f"⛔ 已阻止: {guard_msg}"

    # ── Periodic environment self-heal (every 60s, any tool) ──
    global _last_heal_time
    now = time.time()
    if now - _last_heal_time > 60 and name not in ('think', 'read', 'glob'):
        _last_heal_time = now
        try:
            _self_heal()
        except Exception:
            pass

    # ── Relevant lesson injection (for write/edit on files with prior failures) ──
    lesson_prefix = ""
    if name in ("write", "edit") and "file_path" in params:
        fp = os.path.abspath(params["file_path"])
        related = []
        for les in _session_lessons:
            if les.get("file") == fp and les.get("attempt", 0) >= 2:
                related.append(les)
        if related:
            latest = related[-1]
            lesson_prefix = (
                f"[记忆] 这个文件 ({os.path.basename(fp)}) 之前已连续失败 "
                f"{latest['attempt']} 次。错误: {latest.get('error', '')[:100]}\n"
                f"建议换一个方案，不要重复同样的修复。\n\n"
            )

    handler = PLUGIN_HANDLERS.get(name) or BUILTIN_HANDLERS.get(name)
    if not handler:
        return f"错误: 未知工具 '{name}'"

    try:
        # Inject output_callback for tools that support streaming output
        if output_callback and name == "bash":
            params = {**params, "output_callback": output_callback}

        # Built-in handlers accept **kwargs, plugin handlers accept a single dict
        if name in PLUGIN_HANDLERS:
            result = handler(params)
        else:
            result = handler(**params)
        # Prepend guard warning if present
        if guard_msg:
            result = guard_msg + "\n\n" + result
        if isinstance(result, str):
            return smart_truncate(lesson_prefix + result, _TOOL_RESULT_MAX_LENGTH)
        return smart_truncate(str(result), _TOOL_RESULT_MAX_LENGTH)
    except Exception as e:
        return f"执行 {name} 时出错: {e}"


# ──────────────────────────────────────────────
# Plugin auto-load: merge plugins into tool system
# ──────────────────────────────────────────────

def _load_plugins():
    """Load external plugins and merge into tool definitions and dispatch."""
    try:
        from .plugin import load_plugins
        plugin_defs, plugin_dispatch = load_plugins()
        if plugin_defs:
            TOOL_DEFINITIONS.extend(plugin_defs)
            PLUGIN_HANDLERS.update(plugin_dispatch)
    except ImportError:
        pass  # plugin module not available
    except Exception:
        pass


# Auto-load at import time
_load_plugins()
