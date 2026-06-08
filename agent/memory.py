"""Persistent memory system for Claw.

Stores conversation history and code analysis results for cross-session recall.
Uses file-based JSON storage at D:\\Claude\\claw_memory\\
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "claw_memory")
CONVERSATIONS_DIR = os.path.join(MEMORY_DIR, "conversations")
CODEBASE_DIR = os.path.join(MEMORY_DIR, "codebase")
INDEX_FILE = os.path.join(MEMORY_DIR, "index.json")

# Project-level memory (CLAUDE.md)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT_MEMORY_FILE = os.path.join(PROJECT_ROOT, "CLAUDE.md")

MAX_CONVERSATION_TURNS = 100  # max stored turns per day
MAX_CONTEXT_TURNS = 20        # loaded back into context on init
TAG_CACHE_TTL = 3600 * 24     # 24 hours before re-analysis needed


# ── Init ──

def _ensure_dirs():
    for d in [MEMORY_DIR, CONVERSATIONS_DIR, CODEBASE_DIR]:
        os.makedirs(d, exist_ok=True)


def _load_index() -> dict:
    if os.path.exists(INDEX_FILE):
        try:
            return json.load(open(INDEX_FILE, "r", encoding="utf-8"))
        except Exception:
            pass
    return {"conversations": {}, "codebase": {}}


def _save_index(idx: dict):
    _ensure_dirs()
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Conversation Memory ──

def save_turn(user_msg: str, assistant_text: str | None, tool_calls: list | None,
              tool_results: list | None):
    """Save a conversation turn to persistent memory."""
    _ensure_dirs()
    idx = _load_index()
    today = _today()
    filepath = os.path.join(CONVERSATIONS_DIR, f"{today}.jsonl")

    turn = {
        "ts": time.time(),
        "user": user_msg[:500],
        "assistant": (assistant_text or "")[:2000] if assistant_text else "",
        "tools": [t.get("function", {}).get("name", "") for t in (tool_calls or [])],
        "tool_count": len(tool_calls or []),
    }

    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(turn, ensure_ascii=False) + "\n")

    # Update index
    conv_idx = idx.setdefault("conversations", {})
    today_entry = conv_idx.setdefault(today, {"turns": 0, "tools_used": {}})
    today_entry["turns"] += 1
    for t in turn["tools"]:
        today_entry["tools_used"][t] = today_entry["tools_used"].get(t, 0) + 1
    _save_index(idx)


def load_recent_context(max_turns: int = MAX_CONTEXT_TURNS) -> str:
    """Load recent conversation history as context text."""
    _ensure_dirs()
    today = _today()

    # Load today's conversations first, then yesterday's
    turns = []
    for day in [today]:
        filepath = os.path.join(CONVERSATIONS_DIR, f"{day}.jsonl")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            turns.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

    if not turns:
        return ""

    # Take last N turns
    recent = turns[-max_turns:]
    lines = ["## 历史记忆（上次会话记录）", ""]
    for t in recent:
        ts_str = datetime.fromtimestamp(t["ts"]).strftime("%H:%M")
        user = t.get("user", "")[:120]
        tools = t.get("tools", [])
        tool_str = f" [工具: {', '.join(tools)}]" if tools else ""
        lines.append(f"[{ts_str}] 用户: {user}{tool_str}")

    return "\n".join(lines)


def get_conversation_stats() -> dict:
    """Get conversation statistics for display."""
    idx = _load_index()
    conv = idx.get("conversations", {})
    total_turns = sum(d.get("turns", 0) for d in conv.values())
    all_tools = {}
    for d in conv.values():
        for t, c in d.get("tools_used", {}).items():
            all_tools[t] = all_tools.get(t, 0) + c
    return {"total_turns": total_turns, "days": len(conv), "tools_used": all_tools}


# ── Codebase Memory ──

def save_code_analysis(file_path: str, analysis_type: str, summary: str):
    """Cache a code analysis result for later recall."""
    _ensure_dirs()
    idx = _load_index()

    # Normalize path to module name
    rel = file_path.replace("\\", "/")
    if "/agent/" in rel:
        key = rel.split("/agent/")[-1].replace("/", ".").replace(".py", "")
    else:
        key = os.path.basename(file_path).replace(".py", "")

    filepath = os.path.join(CODEBASE_DIR, f"{key}.json")
    existing = {}
    if os.path.exists(filepath):
        try:
            existing = json.load(open(filepath, "r", encoding="utf-8"))
        except Exception:
            pass

    existing[analysis_type] = {
        "ts": time.time(),
        "summary": summary[:2000],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    codebase_idx = idx.setdefault("codebase", {})
    codebase_idx[key] = {
        "file": file_path,
        "analyses": list(existing.keys()),
        "updated": time.time(),
    }
    _save_index(idx)


def load_code_context(file_path: str) -> str:
    """Load cached code analysis for a file."""
    rel = file_path.replace("\\", "/")
    if "/agent/" in rel:
        key = rel.split("/agent/")[-1].replace("/", ".").replace(".py", "")
    else:
        key = os.path.basename(file_path).replace(".py", "")

    filepath = os.path.join(CODEBASE_DIR, f"{key}.json")
    if not os.path.exists(filepath):
        return ""

    try:
        data = json.load(open(filepath, "r", encoding="utf-8"))
    except Exception:
        return ""

    lines = [f"## 缓存分析: {key}"]
    for atype, info in data.items():
        age_seconds = time.time() - info.get("ts", 0)
        if age_seconds > TAG_CACHE_TTL:
            continue  # Expired
        lines.append(f"[{atype}] {info.get('summary', '')[:500]}")
    return "\n".join(lines)


def get_codebase_stats() -> dict[str, Any]:
    """Get cached codebase analysis stats."""
    idx = _load_index()
    cb = idx.get("codebase", {})
    return {"cached_modules": len(cb), "modules": list(cb.keys())}


# ── Project-level memory (CLAUDE.md) ──

def save_project_memory(content: str) -> str:
    """Write project-level memory to CLAUDE.md. Overwrites existing content."""
    try:
        with open(PROJECT_MEMORY_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        return f"项目记忆已保存到 {PROJECT_MEMORY_FILE}"
    except Exception as e:
        return f"保存项目记忆失败: {e}"


def load_project_memory() -> str:
    """Read project-level memory from CLAUDE.md. Returns empty string if absent."""
    try:
        if os.path.exists(PROJECT_MEMORY_FILE):
            with open(PROJECT_MEMORY_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


# ── Full context load ──

def build_context() -> str:
    """Build memory context string for the system prompt."""
    parts = []

    # Recent conversations
    conv = load_recent_context()
    if conv:
        parts.append(conv)

    # Project-level memory (CLAUDE.md)
    proj = load_project_memory()
    if proj:
        parts.append("## 项目记忆\n" + proj)

    # Cached codebase analyses
    cached = []
    idx = _load_index()
    for key, info in idx.get("codebase", {}).items():
        age_hours = (time.time() - info.get("updated", 0)) / 3600
        if age_hours < 24:
            cached.append(f"  - {key}: {', '.join(info.get('analyses', []))}")
    if cached:
        parts.append("## 已缓存代码分析\n" + "\n".join(cached))

    return "\n\n".join(parts)
