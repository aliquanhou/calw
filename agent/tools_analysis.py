"""tools_analysis — 代码分析工具。

v2.1 重写：
  - 统一返回格式 + 类型注解
  - 更清晰的逻辑结构
  - 完善的异常处理
"""

from __future__ import annotations

import ast
import os
import re
from collections import defaultdict


# ── 工具函数 ──

def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """在依赖图中检测循环依赖。"""
    visited: set[str] = set()
    path: list[str] = []
    cycles: list[list[str]] = []

    def dfs(node: str):
        if node in path:
            idx = path.index(node)
            cycles.append(path[idx:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        path.append(node)
        for nb in graph.get(node, set()):
            if nb in graph:
                dfs(nb)
        path.pop()

    for n in graph:
        dfs(n)

    # 去重
    seen: set = set()
    unique = []
    for c in cycles:
        k = tuple(sorted(c[:-1]))
        if k not in seen:
            seen.add(k)
            unique.append(c)
    return unique


# ═══════════════════════════════════════════
# AST 分析
# ═══════════════════════════════════════════

def _handle_ast(file_path: str = "") -> str:
    """解析 Python 文件的 AST 结构。

    Args:
        file_path: Python 文件路径

    Returns:
        AST 分析结果
    """
    if not file_path:
        return "[错误] ast 需要 file_path 参数"

    try:
        with open(file_path, encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        return f"[错误] 文件不存在: {file_path}"
    except Exception as e:
        return f"[错误] 读取失败: {e}"

    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return f"[语法错误] {e}"

    lines = [f"[AST] 文件: {file_path}", f"  行数: {len(src.splitlines())}"]

    # 导入分析
    imports = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                imports.append(a.name)
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                imports.append(f"{n.module or ''}.{a.name}")
    if imports:
        lines.append(f"  导入 ({len(imports)}):")
        for i in sorted(set(imports)):
            lines.append(f"    import {i}")

    # 函数/类定义
    for n in ast.iter_child_nodes(tree):
        if isinstance(n, ast.FunctionDef):
            args = [a.arg for a in n.args.args]
            decos = [d.id if isinstance(d, ast.Name) else ast.dump(d) for d in n.decorator_list]
            ds = f" @{', '.join(decos)}" if decos else ""
            lines.append(f"  def {n.name}({', '.join(args)}){ds}")
            lines.append(f"    L{n.lineno}-L{n.end_lineno} | body={len(n.body)}")
        elif isinstance(n, ast.AsyncFunctionDef):
            args = [a.arg for a in n.args.args]
            lines.append(f"  async def {n.name}({', '.join(args)})")
            lines.append(f"    L{n.lineno}-L{n.end_lineno}")
        elif isinstance(n, ast.ClassDef):
            bases = [ast.dump(b) for b in n.bases]
            bs = f"({', '.join(bases)})" if bases else ""
            lines.append(f"  class {n.name}{bs}")
            lines.append(f"    L{n.lineno}-L{n.end_lineno}")
            for item in ast.iter_child_nodes(n):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [a.arg for a in item.args.args]
                    kd = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                    decos = [d.id if isinstance(d, ast.Name) else ast.dump(d) for d in item.decorator_list]
                    ds = f" @{', '.join(decos)}" if decos else ""
                    lines.append(f"    {kd} {item.name}({', '.join(args)}){ds}")

    return "\n".join(lines)


# ═══════════════════════════════════════════
# 依赖图
# ═══════════════════════════════════════════

def _handle_dep_graph(path: str = "") -> str:
    """分析项目的模块依赖关系。

    Args:
        path: 项目根目录或文件路径

    Returns:
        依赖分析结果
    """
    target = path or os.getcwd()
    if not os.path.exists(target):
        return f"[错误] 路径不存在: {target}"

    # 收集 Python 文件
    py_files: list[str] = []
    if os.path.isfile(target):
        py_files = [target]
        root_dir = os.path.dirname(target)
    else:
        root_dir = target
        for rt, _, fs in os.walk(target):
            for f in fs:
                if f.endswith(".py"):
                    py_files.append(os.path.join(rt, f))
                    if len(py_files) > 200:
                        break

    if not py_files:
        return "[依赖图] 无 Python 文件"

    # 模块路径映射
    module_map: dict[str, str] = {}
    for fp in py_files:
        rel = os.path.relpath(fp, root_dir)
        mod = rel.replace("\\", "/").replace("/", ".").replace(".py", "")
        if mod.endswith(".__init__"):
            mod = mod[:-9]
        module_map[mod] = fp
        module_map[os.path.basename(fp).replace(".py", "")] = fp

    # 解析每个文件的导入
    file_imports: dict[str, set[str]] = {}
    for fp in py_files:
        try:
            with open(fp, encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception:
            continue
        imps: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    imps.add(a.name.split(".")[0])
            elif isinstance(n, ast.ImportFrom):
                if n.module:
                    imps.add(n.module.split(".")[0])
        file_imports[fp] = imps

    # 内部依赖图
    internal_deps: dict[str, set[str]] = {}
    for fp in py_files:
        internal: set[str] = set()
        for imp in file_imports.get(fp, set()):
            if imp in module_map:
                internal.add(module_map[imp])
        internal_deps[fp] = internal

    # 检测循环依赖
    cycles = _find_cycles({fp: internal_deps[fp] for fp in py_files})

    lines = [f"[依赖图] {target}", f"  文件: {len(py_files)}", ""]

    # 核心模块（被依赖最多）
    dep_counts: dict[str, int] = {}
    for fp in py_files:
        for d in internal_deps[fp]:
            dep_counts[d] = dep_counts.get(d, 0) + 1
    hubs = sorted(dep_counts.items(), key=lambda x: -x[1])[:10]
    if hubs:
        lines.append("--- 核心模块 ---")
        for fp, c in hubs:
            lines.append(f"  {os.path.relpath(fp, root_dir)}: 被引 {c} 次")

    # 叶子模块（无内部依赖）
    leaves = [fp for fp in py_files if not internal_deps.get(fp)]
    if leaves:
        lines.append(f"\n--- 叶子模块 ({len(leaves)}) ---")
        for fp in sorted(leaves)[:10]:
            lines.append(f"  {os.path.relpath(fp, root_dir)}")

    # 循环依赖
    if cycles:
        lines.append(f"\n--- 循环依赖 ({len(cycles)} 个) ---")
        for c in cycles[:5]:
            lines.append(f"  {' -> '.join(os.path.relpath(n, root_dir) for n in c)}")

    # 外部依赖
    all_ext: set[str] = set()
    for fp in py_files:
        all_ext.update(file_imports.get(fp, set()) - set(module_map.keys()))
    if all_ext:
        lines.append(f"\n--- 外部依赖 ({len(all_ext)}) ---")
        for n in sorted(all_ext)[:30]:
            lines.append(f"  {n}")

    return "\n".join(lines)


# ═══════════════════════════════════════════
# 调用链追踪
# ═══════════════════════════════════════════

def _handle_call_chain(function_name: str = "", direction: str = "forward",
                       path: str = "", depth: int = 3) -> str:
    """追踪函数调用链。

    Args:
        function_name: 函数名
        direction: forward（谁调了谁）| backward（谁调了我）
        path: 搜索路径
        depth: 追踪深度

    Returns:
        调用链结果
    """
    if not function_name:
        return "[错误] call_chain 需要 function_name 参数"

    target = path or os.getcwd()
    if not os.path.exists(target):
        return f"[错误] 路径不存在: {target}"

    # 收集 Python 文件
    py_files: list[str] = []
    if os.path.isfile(target):
        py_files = [target] if target.endswith(".py") else []
    else:
        for rt, _, fs in os.walk(target):
            for f in fs:
                if f.endswith(".py"):
                    py_files.append(os.path.join(rt, f))
                    if len(py_files) > 500:
                        break

    if not py_files:
        return "[调用链] 无 Python 文件"

    # 构建调用图
    calls: dict[str, dict] = defaultdict(lambda: {"calls": set(), "called_by": set(), "file": "", "line": 0})

    def get_func_name(n):
        if isinstance(n, ast.Attribute):
            return get_func_name(n.value) + "." + n.attr
        elif isinstance(n, ast.Name):
            return n.id
        return ast.dump(n)

    for fp in py_files:
        try:
            with open(fp, encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception:
            continue

        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                calls[n.name]["file"] = os.path.relpath(fp, target if os.path.isdir(target) else os.path.dirname(target))
                calls[n.name]["line"] = n.lineno

        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                callee = get_func_name(n.func)
                if callee:
                    for a in ast.walk(tree):
                        if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef)) and a.lineno <= n.lineno <= (getattr(a, 'end_lineno', a.lineno)):
                            calls[a.name]["calls"].add(callee)
                            calls[callee]["called_by"].add(a.name)
                            break

    result_lines = [f"[调用链] {function_name} ({direction}, depth≤{depth})"]
    visited: set[str] = set()

    def trace_forward(name: str, current_depth: int):
        if current_depth > depth or name in visited:
            return
        visited.add(name)
        indent = "  " * current_depth
        loc = calls.get(name, {})
        loc_str = f"({loc.get('file', '?'):{loc.get('line', '?')}})" if loc.get('file') else ""
        prefix = "└ " if current_depth else ""
        result_lines.append(f"{indent}{prefix}{name} {loc_str}")
        for callee in sorted(calls.get(name, {}).get("calls", set())):
            trace_forward(callee, current_depth + 1)

    def trace_backward(name: str, current_depth: int):
        if current_depth > depth or name in visited:
            return
        visited.add(name)
        indent = "  " * current_depth
        loc = calls.get(name, {})
        loc_str = f"({loc.get('file', '?'):{loc.get('line', '?')}})" if loc.get('file') else ""
        prefix = "└ " if current_depth else ""
        marker = " (目标)" if current_depth == 0 else ""
        result_lines.append(f"{indent}{prefix}{name}{loc_str}{marker}")
        for caller in sorted(calls.get(name, {}).get("called_by", set())):
            trace_backward(caller, current_depth + 1)

    if direction == "forward":
        trace_forward(function_name, 0)
    elif direction == "backward":
        trace_backward(function_name, 0)
    else:
        return "[错误] direction 须为 forward 或 backward"

    if len(result_lines) == 1:
        result_lines.append(f"  (未找到 '{function_name}' 的定义)")

    return "\n".join(result_lines)


# ═══════════════════════════════════════════
# 错误根因分析
# ═══════════════════════════════════════════

def _handle_trace_error(error_message: str = "", file_path: str = "", depth: int = 2) -> str:
    """分析错误信息并定位根因。

    Args:
        error_message: 错误信息文本
        file_path: 相关文件路径
        depth: 分析深度

    Returns:
        分析结果
    """
    if not error_message:
        return "[错误] trace_error 需要 error_message 参数"

    lines = [f"[错误分析] {error_message[:500]}", ""]

    # 分类错误类型
    error_type = "未知"
    for kw, tp in [
        ("modulenotfound", "import"), ("importerror", "import"),
        ("attributeerror", "attr"), ("typeerror", "type"),
        ("keyerror", "key"), ("filenotfound", "file"),
        ("syntaxerror", "syntax"), ("valueerror", "value"),
    ]:
        if kw in error_message.lower():
            error_type = tp
            break

    lines.append(f"类型: {error_type}")

    # 提取符号名
    symbols: set[str] = set()
    for m in re.finditer(r"'(\w+(?:\.\w+)*)'", error_message):
        symbols.add(m.group(1))
    for m in re.finditer(r'"(\w+(?:\.\w+)*)"', error_message):
        symbols.add(m.group(1))

    # 提取堆栈
    trace = re.findall(r'File "([^"]+)", line (\d+)', error_message)
    if trace:
        lines.append("")
        lines.append("堆栈:")
        for f, l in trace[:10]:
            lines.append(f"  {f}:{l}")

    if symbols:
        lines.append("")
        lines.append(f"符号: {', '.join(list(symbols)[:10])}")

    # 搜索符号定义
    from .tools_shell import _run_powershell
    for s in list(symbols)[:5]:
        sym = s.split(".")[-1]
        try:
            r = _run_powershell(
                f"Select-String -Path '*.py' -Pattern '(class |def |^|\\s+){sym}\\b' -Recurse -SimpleMatch -ErrorAction SilentlyContinue | Select-Object -First 5 -ExpandProperty Line"
            )
            if r and "找不到" not in r:
                lines.append(f"")
                lines.append(f"定义 '{s}': {r[:300]}")
        except Exception:
            pass

    # Import 错误：检查 pip 安装
    if error_type == "import" and symbols:
        mod = list(symbols)[0].split(".")[0]
        try:
            ck = _run_powershell(f"pip list 2>$null | Select-String '{mod}'")
            if ck and mod.lower() in ck.lower():
                lines.append(f"\n✅ {mod} 已安装")
            else:
                lines.append(f"\n❌ {mod} 未安装\n建议: pip install {mod}")
        except Exception:
            pass

    # 检查缺失文件
    for m in re.finditer(r"(?:No such file|ENOENT).*'([^']+)'", error_message):
        mp = m.group(1)
        lines.append(f"\n缺文件: {mp}")
        alt = os.path.join(os.getcwd(), mp.lstrip("./\\"))
        if os.path.exists(alt):
            lines.append(f"  在 {alt} 找到")

    return "\n".join(lines)
