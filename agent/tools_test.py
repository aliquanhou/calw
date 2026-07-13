"""tools_test — 测试驱动：发现、运行、分析。

v2.1 重写：
  - 统一返回格式 + 类型注解
  - 改进的 pytest 输出解析
  - 更清晰的错误报告
"""

from __future__ import annotations
from ._encoding import enc as _ENC

import os
import re
import subprocess
import sys
import time


def discover_tests(path: str | None = None) -> dict:
    """自动发现项目中的测试文件和测试用例。"""
    root = path or os.getcwd()
    test_files = []
    framework = "unknown"

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            ".env", ".tox", "build", "dist", ".idea", ".vscode",
        )]
        for f in filenames:
            if f.startswith("test_") and f.endswith(".py"):
                test_files.append(os.path.relpath(os.path.join(dirpath, f), root))
            elif f.endswith("_test.py"):
                test_files.append(os.path.relpath(os.path.join(dirpath, f), root))

    if os.path.exists(os.path.join(root, "conftest.py")):
        framework = "pytest"
    elif any(os.path.basename(f).startswith("test_") or f.endswith("_test.py") for f in test_files):
        framework = "pytest"
    else:
        for tf in test_files[:5]:
            fp = os.path.join(root, tf)
            try:
                content = open(fp, "r", encoding="utf-8", errors="replace").read()
                if "unittest" in content and "TestCase" in content:
                    framework = "unittest"
                    break
            except Exception:
                pass

    return {"framework": framework, "files": sorted(test_files), "total": len(test_files)}


def run_tests(path: str | None = None, test_name: str = "", timeout: int = 300) -> dict:
    """运行测试并解析结果。"""
    root = path or os.getcwd()
    result = {
        "passed": 0, "failed": 0, "errors": 0, "total": 0,
        "duration": 0.0, "failures": [], "framework": "pytest", "raw_output": "",
    }
    start = time.time()

    cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short", "--no-header"]
    if test_name:
        if "::" in test_name:
            cmd.append(test_name)
        elif test_name.endswith(".py"):
            cmd.append(os.path.join(root, test_name))
        else:
            cmd.extend(["-k", test_name])
    else:
        cmd.append(root)
    cmd.extend(["-p", "no:cacheprovider"])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding=_ENC,
                              errors="replace", timeout=timeout)
        raw = proc.stdout + "\n" + proc.stderr
    except subprocess.TimeoutExpired:
        return {**result, "errors": 1, "duration": time.time() - start, "raw_output": "TIMEOUT"}
    except FileNotFoundError:
        return {**result, "errors": 1, "duration": time.time() - start, "raw_output": "pytest not installed"}

    result["duration"] = round(time.time() - start, 2)
    result["raw_output"] = raw[-5000:]

    # 解析 pytest 逐用例结果
    for m in re.finditer(r"^(.+?)::(.+?) (PASSED|FAILED|ERROR)", raw, re.MULTILINE):
        filepath, test_func, status = m.group(1), m.group(2), m.group(3)
        result["total"] += 1
        if status == "PASSED":
            result["passed"] += 1
        elif status in ("FAILED", "ERROR"):
            result[{"FAILED": "failed", "ERROR": "errors"}[status]] += 1
            result["failures"].append({"file": filepath, "test": test_func, "detail": _extract_failure(raw, test_func)})

    # 如果逐用例解析失败，尝试概要行
    if result["total"] == 0:
        sm = re.search(r"(\d+) passed.*?(\d+) failed.*?(\d+) error", raw, re.DOTALL)
        if sm:
            result["passed"] = int(sm.group(1))
            result["failed"] = int(sm.group(2))
            result["errors"] = int(sm.group(3))
            result["total"] = result["passed"] + result["failed"] + result["errors"]
        else:
            pm = re.search(r"(\d+) passed", raw)
            fm = re.search(r"(\d+) failed", raw)
            if pm: result["passed"] = int(pm.group(1))
            if fm: result["failed"] = int(fm.group(1))
            result["total"] = result["passed"] + result["failed"] + result["errors"]

    return result


def _extract_failure(raw_output: str, test_name: str) -> str:
    """从 pytest 输出中提取指定测试的失败详情。"""
    lines = raw_output.split("\n")
    detail_lines = []
    target_pattern = re.compile(rf"FAILED.*{re.escape(test_name)}")
    failures_header = False
    capture = False

    for i, line in enumerate(lines):
        if "= FAILURES =" in line:
            failures_header = True
            continue
        if failures_header:
            if line.startswith("_" * 10):
                if capture:
                    break
                capture = True
                continue
            if capture:
                detail_lines.append(line.rstrip())
                if len(detail_lines) > 50:
                    detail_lines.append("... (截断)")
                    break
        if target_pattern.search(line):
            for j in range(i + 1, min(i + 15, len(lines))):
                l = lines[j].rstrip()
                if not l or l.startswith("="):
                    break
                detail_lines.append(l)

    result = "\n".join(detail_lines).strip()
    return result[:2000] if result else "(无详细错误信息)"


def _handle_test(action: str = "run", path: str = "", test_name: str = "", timeout: int = 300) -> str:
    """测试驱动：发现/运行测试并解析结果。

    Args:
        action: discover（发现测试）| run（运行测试）
        path: 测试文件或目录路径
        test_name: 特定测试名或过滤表达式
        timeout: 超时秒数

    Returns:
        测试结果
    """
    try:
        if action == "discover":
            info = discover_tests(path or None)
            if info["total"] == 0:
                return "[测试] 未发现测试文件"
            lines = [
                f"[测试] 框架: {info['framework']}",
                f"[测试] 文件数: {info['total']}",
            ]
            for f in info["files"][:30]:
                lines.append(f"  🧪 {f}")
            if len(info["files"]) > 30:
                lines.append(f"  ... 还有 {len(info['files']) - 30} 个")
            return "\n".join(lines)

        elif action == "run":
            r = run_tests(path or None, test_name, timeout)
            lines = [
                f"[测试] 📊 结果 ({r['framework']})",
                f"  总计: {r['total']} | ✅ 通过: {r['passed']} | ❌ 失败: {r['failed']} | ⚠️ 错误: {r['errors']}",
                f"  耗时: {r['duration']}s",
            ]
            if r["failures"]:
                lines.append("")
                lines.append(f"--- 失败详情 ({len(r['failures'])} 个) ---")
                for i, f in enumerate(r["failures"][:5]):
                    lines.append(f"#{i+1} {f['file']}::{f['test']}")
                    detail = f["detail"]
                    if detail:
                        for d_line in detail.split("\n")[:8]:
                            lines.append(f"  {d_line}")
                    if len(r["failures"]) > 5 and i == 4:
                        lines.append(f"  ... 还有 {len(r['failures']) - 5} 个失败")
            return "\n".join(lines)

        return f"[错误] 未知操作: {action}（可用: discover/run）"

    except Exception as e:
        return f"[错误] test 操作失败: {e}"
