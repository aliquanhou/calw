"""tools_memory — 语义记忆工具。

v2.1 重写：
  - 统一返回格式 [状态] 描述
  - 类型注解 + 显式参数
  - 完整的异常处理
"""

from __future__ import annotations

import time

from .memory_v2 import get_memory, build_semantic_context


def _handle_remember(
    action: str = "search",
    query: str = "",
    content: str = "",
    mem_type: str = "note",
    n_results: int = 5,
) -> str:
    """语义记忆：搜索/存储/统计/上下文。

    Args:
        action: search | store | stats | context
        query: 搜索关键词
        content: 要存储的内容
        mem_type: 记忆类型 (note/tool_result/file_change/error/user_decision/task_complete)
        n_results: 返回结果数

    Returns:
        操作结果
    """
    try:
        mem = get_memory()

        if action == "search":
            if not query:
                return "[错误] remember search 需要 query 参数"
            results = mem.search(query, n_results=n_results)
            if not results:
                return f"[搜索] 未找到与「{query}」相关的记忆"
            lines = [f"[搜索] 「{query}」找到 {len(results)} 条:"]
            for i, r in enumerate(results):
                meta = r.get("metadata", {})
                ts = meta.get("timestamp", 0)
                time_str = time.strftime("%m/%d %H:%M", time.localtime(ts)) if ts else "?"
                score = 1 - r.get("distance", 0)
                text = r.get("content", "")[:200]
                lines.append(f"  #{i+1} ({score:.0%}) [{time_str}] {text}")
            return "\n".join(lines)

        elif action == "store":
            if not content:
                return "[错误] remember store 需要 content 参数"
            ok = mem.store(content, {"type": mem_type, "timestamp": time.time()})
            if ok:
                return f"[记忆] 已存储（共 {mem.count()} 条）"
            return "[错误] 存储失败"

        elif action == "stats":
            c = mem.count()
            return f"[记忆] 共 {c} 条" if c else "[记忆] 空"

        elif action == "context":
            ctx = build_semantic_context()
            return ctx if ctx else "[记忆] 暂无"

        return f"[错误] 未知操作: {action}（可用: search/store/stats/context）"

    except Exception as e:
        return f"[错误] 记忆操作失败: {e}"
