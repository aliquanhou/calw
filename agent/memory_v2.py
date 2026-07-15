"""memory_v2 — 语义记忆系统（ChromaDB 向量数据库 + 语义搜索）。"""
from __future__ import annotations
import json, os, time, uuid
from typing import Any

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "..", ".claude", "memory_v2")
MAX_RESULTS = 10


class SemanticMemory:
    def __init__(self, collection_name: str = "calw_memory", memory_dir: str = ""):
        self.collection_name = collection_name
        self._memory_dir = memory_dir or MEMORY_DIR
        self._collection = None
        self._client = None
        self._ready = False

    def _ensure(self):
        if self._ready:
            return True
        try:
            import chromadb
            os.makedirs(self._memory_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self._memory_dir)
            try:
                self._collection = self._client.get_collection(self.collection_name)
            except ValueError:
                self._collection = self._client.create_collection(self.collection_name)
            except Exception as _gce:
                if "NotFound" in type(_gce).__name__:
                    self._collection = self._client.create_collection(self.collection_name)
                else:
                    raise
            self._ready = True
            return True
        except Exception:
            self._ready = False
            return False

    def close(self):
        self._client = None
        self._collection = None
        self._ready = False

    def store(self, content: str, metadata: dict | None = None) -> bool:
        if not self._ensure():
            return False
        try:
            mem_id = str(uuid.uuid4())
            if metadata is None:
                metadata = {}
            metadata.setdefault("timestamp", time.time())
            metadata.setdefault("type", "general")
            self._collection.add(documents=[content], metadatas=[metadata], ids=[mem_id])
            return True
        except Exception:
            return False

    def search(self, query: str, n_results: int = MAX_RESULTS, filter_metadata: dict | None = None) -> list[dict]:
        if not self._ensure():
            return []
        try:
            where = None
            if filter_metadata:
                where = {k: v for k, v in filter_metadata.items() if isinstance(v, str)}
            results = self._collection.query(query_texts=[query], n_results=n_results, where=where)
            items = []
            if results and results["ids"] and results["ids"][0]:
                for i in range(len(results["ids"][0])):
                    items.append({
                        "id": results["ids"][0][i],
                        "content": results["documents"][0][i] if results["documents"] else "",
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results.get("distances") else 0,
                    })
            return items
        except Exception:
            return []

    def count(self) -> int:
        if not self._ensure():
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0

    def get_recent(self, n: int = 10, mem_type: str = "") -> list[dict]:
        if not self._ensure():
            return []
        try:
            where = {"type": mem_type} if mem_type else None
            results = self._collection.get(where=where, limit=n)
            items = []
            if results and results["ids"]:
                metadatas = results["metadatas"] or []
                sorted_indices = sorted(
                    range(len(results["ids"])),
                    key=lambda i: metadatas[i].get("timestamp", 0) if metadatas[i] else 0,
                    reverse=True,
                )
                for idx in sorted_indices[:n]:
                    items.append({
                        "id": results["ids"][idx],
                        "content": results["documents"][idx] if results["documents"] else "",
                        "metadata": metadatas[idx] if metadatas else {},
                    })
            return items
        except Exception:
            return []


_memory: SemanticMemory | None = None


def get_memory() -> SemanticMemory:
    global _memory
    if _memory is None:
        _memory = SemanticMemory()
    return _memory


def auto_store_tool_result(tool_name: str, params: dict, result: str) -> None:
    if not result or len(result) < 10:
        return
    mem = get_memory()
    summary = result[:200].replace("\n", " ").strip()
    mem_type = "tool_result"
    if tool_name in ("write", "edit", "replace", "move", "copy", "delete", "mkdir"):
        mem_type = "file_change"
    elif tool_name in ("bash", "test") and any(k in result[:100] for k in ("error", "fail", "❌", "Exit code")):
        mem_type = "error"
    metadata = {"type": mem_type, "tool": tool_name, "timestamp": time.time()}
    mem.store(summary, metadata)


def auto_store_file_change(file_path: str, action: str, diff_summary: str) -> None:
    if not diff_summary:
        return
    get_memory().store(f"[{action}] {file_path}: {diff_summary[:300]}",
                       {"type": "file_change", "file": file_path, "action": action, "timestamp": time.time()})


def build_semantic_context(mem: SemanticMemory | None = None) -> str:
    mem = mem or get_memory()
    count = mem.count()
    if count == 0:
        return ""
    recent = mem.get_recent(8)
    if not recent:
        return ""
    lines = ["## 语义记忆（跨会话知识）", ""]
    for item in recent:
        meta = item.get("metadata", {})
        mem_type = meta.get("type", "general")
        tool = meta.get("tool", "")
        ts = meta.get("timestamp", 0)
        time_str = time.strftime("%H:%M", time.localtime(ts)) if ts else "?"
        icon = {"tool_result": "\U0001f527", "file_change": "\U0001f4dd", "error": "❌",
                "user_decision": "\U0001f4ac", "task_complete": "✅", "note": "\U0001f4cc"}.get(mem_type, "\U0001f4c4")
        tag = f"[{tool}]" if tool else ""
        content = item.get("content", "")[:150]
        if content:
            lines.append(f"  {icon} [{time_str}] {tag} {content}")
    lines.append("")
    lines.append(f"  \U0001f4ca 共 {count} 条记忆 | 使用 remember search 查询更多")
    lines.append("")
    return "\n".join(lines)
