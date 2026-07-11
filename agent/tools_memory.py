"""tools_memory — 语义记忆工具。"""
from __future__ import annotations
import time
from .memory_v2 import get_memory, build_semantic_context


def _handle_remember(action: str = "search", query: str = "",
                      content: str = "", mem_type: str = "note",
                      n_results: int = 5) -> str:
    mem = get_memory()
    if action == "search":
        if not query:
            return "需指定 query"
        results = mem.search(query, n_results=n_results)
        if not results:
            return f"未找到与「{query}」相关的记忆。"
        lines = [f"语义搜索: {query}", f"找到 {len(results)} 条:", ""]
        for i, r in enumerate(results):
            meta = r.get("metadata", {})
            ts = meta.get("timestamp", 0)
            time_str = time.strftime("%m/%d %H:%M", time.localtime(ts)) if ts else "?"
            score = 1 - r.get("distance", 0)
            content_str = r.get("content", "")[:200]
            lines.append(f"#{i+1} ({score:.0%}) [{time_str}] {content_str}")
            lines.append("")
        return "\n".join(lines)
    elif action == "store":
        if not content:
            return "需指定 content"
        ok = mem.store(content, {"type": mem_type, "timestamp": time.time()})
        return f"已记住 ({mem.count()} 条总)" if ok else "存储失败"
    elif action == "stats":
        c = mem.count()
        return f"记忆统计: 共 {c} 条" if c else "记忆为空"
    elif action == "context":
        ctx = build_semantic_context()
        return ctx if ctx else "暂无语义记忆"
    return f"未知操作: {action}"
