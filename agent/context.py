"""Context window manager — keeps messages within model limits.

Provides:
  - Token estimation (character-based, no external deps)
  - Model-aware context limits
  - Tool result truncation
  - Message compaction for older turns
  - Aggressive compression with summary preservation
"""

from __future__ import annotations

import json
import os

MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "claude": 200000,
    "deepseek": 65536,
    "gpt-4": 128000,
    "gpt-4o": 128000,
}

RESERVED_OUTPUT_TOKENS = 4096
MAX_TOOL_RESULT_CHARS = 6000
KEEP_RECENT_COMPACT = 8


# ── Token estimation ──

def estimate_tokens(text: str) -> int:
    """Estimate token count: ~4 chars/token for mixed CJK/English text."""
    if not text:
        return 0
    return max(1, len(text) // 4 + 1)


def count_message_tokens(msg: dict) -> int:
    """Count tokens in a user or assistant message."""
    total = 0
    content = msg.get("content")
    if content and isinstance(content, str):
        total += estimate_tokens(content)
    elif content and isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                total += estimate_tokens(str(item.get("text", "")))
    # Tool calls within assistant messages
    for tc in msg.get("tool_calls", []):
        fn = tc.get("function", {})
        total += estimate_tokens(fn.get("name", ""))
        total += estimate_tokens(fn.get("arguments", ""))
    return total


def count_tool_result_tokens(msg: dict) -> int:
    """Count tokens in a tool result message."""
    content = msg.get("content")
    if isinstance(content, str):
        return estimate_tokens(content)
    if isinstance(content, list):
        total = 0
        for item in content:
            if isinstance(item, dict):
                total += estimate_tokens(str(item.get("content", "") or item.get("text", "")))
        return total
    return 0


def count_total_tokens(messages: list[dict], system_prompt: str) -> int:
    """Total token count across system prompt + all messages."""
    total = estimate_tokens(system_prompt)
    for msg in messages:
        if msg["role"] in ("user", "assistant"):
            total += count_message_tokens(msg)
        elif msg["role"] == "tool":
            total += count_tool_result_tokens(msg)
        total += 4  # per-message overhead
    return total


# ── Context limits ──

def get_context_limit(model_name: str) -> int:
    """Get max context tokens for a model. Defaults to 65536 (DeepSeek)."""
    if not model_name:
        return 65536
    model_lower = model_name.lower()
    for prefix, limit in MODEL_CONTEXT_LIMITS.items():
        if prefix in model_lower:
            return limit
    return 65536


# ── Compression strategies ──

def truncate_tool_results(messages: list[dict]) -> list[dict]:
    """Truncate oversized tool result content to save context.

    Uses smart truncation (head + tail preservation) for error output,
    which preserves the error context at the end of build/compile output.
    """
    from .tools import smart_truncate

    result = []
    for msg in messages:
        if msg.get("role") == "tool":
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > MAX_TOOL_RESULT_CHARS:
                msg = dict(msg)
                msg["content"] = smart_truncate(content, MAX_TOOL_RESULT_CHARS)
        result.append(msg)
    return result


def compact_messages(messages: list[dict]) -> list[dict]:
    """Compact content of older messages beyond the recent window."""
    if len(messages) <= KEEP_RECENT_COMPACT * 2:
        return messages

    # Identify which messages belong to the last KEEP_RECENT_COMPACT turns
    turn_count = 0
    keep_indices: set[int] = set()
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] in ("user", "assistant"):
            turn_count += 1
        if turn_count <= KEEP_RECENT_COMPACT:
            keep_indices.add(i)

    if len(keep_indices) == len(messages):
        return messages

    result = []
    for i, msg in enumerate(messages):
        if i in keep_indices:
            result.append(msg)
            continue
        # Compact this message
        compacted = dict(msg)
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 300:
            compacted["content"] = content[:300] + "... [压缩]"
        # Tool results in older turns: drastically reduce
        if msg.get("role") == "tool":
            compacted["content"] = "[工具结果已压缩]"
        # Tool calls in older assistant messages: keep only names
        if msg.get("tool_calls"):
            names = [tc.get("function", {}).get("name", "?") for tc in msg.get("tool_calls", [])]
            compacted["tool_calls"] = []
            compacted["content"] = compacted.get("content") or "" + f"[调用工具: {', '.join(names)}]"
        result.append(compacted)

    return result


# ── Level 3: Project state snapshot (before dropping turns) ──

def summarize_project_state(messages: list[dict], dropped_end: int) -> str:
    """Extract a structured project state summary from the messages being dropped.

    Scans the portion of messages being compressed and produces a compact
    snapshot covering: project goal, key files touched, errors encountered,
    completed operations, pending issues.
    """
    if not messages or dropped_end <= 0:
        return ""

    lines: list[str] = []
    files_touched: set[str] = set()
    errors: list[str] = []
    tool_names: set[str] = set()
    goals: list[str] = []

    for msg in messages[:dropped_end]:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user" and isinstance(content, str):
            text = content[:300]
            # Capture first user message as project goal
            if not goals:
                goals.append(text[:200])

        if role == "assistant":
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls if isinstance(tool_calls, list) else []:
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                name = fn.get("name", "")
                if name:
                    tool_names.add(name)
                # Track file paths from read/write/edit params
                try:
                    args_str = fn.get("arguments", "{}")
                    if isinstance(args_str, str):
                        args = json.loads(args_str) if args_str else {}
                    else:
                        args = args_str or {}
                    fp = args.get("file_path", "")
                    if fp:
                        files_touched.add(os.path.basename(fp))
                except Exception:
                    pass

        if role == "tool" and isinstance(content, str) and len(content) < 300:
            text_lower = content.lower()
            if any(kw in text_lower for kw in ("error", "fail", "exit code", "stderr")):
                err_line = content.strip()[:200]
                if err_line:
                    errors.append(err_line)

    if goals:
        lines.append(f"项目目标: {goals[0]}")
    if files_touched:
        lines.append(f"涉及文件: {', '.join(sorted(files_touched)[:20])}")
    if tool_names:
        lines.append(f"使用工具: {', '.join(sorted(tool_names))}")
    if errors:
        lines.append(f"已遇错误 ({len(errors)}):")
        for e in errors[:5]:
            lines.append(f"  - {e}")

    snapshot = "\n".join(lines)
    if snapshot:
        snapshot = "## 项目状态快照（先前对话摘要）\n" + snapshot
    return snapshot


def compress_messages(messages: list[dict], system_prompt: str, model_name: str = "") -> list[dict]:
    """Compress messages to fit within the model's context window.

    Applies progressive compression:
      1. Truncate oversized tool results
      2. Compact old message content
      3. Drop oldest turns with a summary marker
      4. Project state snapshot (before dropping)
    """
    if not messages:
        return messages

    max_context = get_context_limit(model_name)
    max_safe = max_context - RESERVED_OUTPUT_TOKENS

    # ── Round 1: Truncate tool results ──
    messages = truncate_tool_results(messages)

    total = count_total_tokens(messages, system_prompt)
    if total <= max_safe:
        return messages

    # ── Round 2: Compact old messages ──
    messages = compact_messages(messages)

    total = count_total_tokens(messages, system_prompt)
    if total <= max_safe:
        return messages

    # ── Round 3: Aggressive — drop oldest turns ──
    # Walk backwards, keep as many recent messages as fit in 70% of budget
    target = int(max_safe * 0.7)
    budget = target - estimate_tokens(system_prompt)
    if budget <= 0:
        # System prompt alone is too large; keep last 4 messages as bare minimum
        return messages[-4:] if len(messages) > 4 else messages[-2:]

    keep_count = 0
    cum = 0
    for i in range(len(messages) - 1, -1, -1):
        t = count_message_tokens(messages[i]) if messages[i]["role"] in ("user", "assistant") else count_tool_result_tokens(messages[i])
        if cum + t <= budget:
            cum += t
            keep_count += 1
        else:
            break

    if keep_count >= len(messages):
        return messages

    kept = messages[-keep_count:] if keep_count > 0 else messages[-5:]
    dropped_end = len(messages) - keep_count if keep_count > 0 else len(messages) - 5

    # ── Round 4: Generate project state snapshot ──
    # Before dropping, extract a structured summary from the dropped messages
    snapshot = summarize_project_state(messages, max(0, dropped_end))

    # Count dropped user/assistant turns for the summary note
    dropped_turns = 0
    for msg in messages[: max(0, dropped_end)]:
        if msg["role"] in ("user", "assistant"):
            dropped_turns += 1

    if dropped_turns > 0:
        note = (
            f"[上下文管理] 为节省 token，已自动压缩之前的 {dropped_turns} 轮对话。"
            f"关键信息已通过记忆系统持久化。"
        )
        if snapshot:
            kept.insert(0, {"role": "user", "content": note + "\n\n" + snapshot})
        else:
            kept.insert(0, {"role": "user", "content": note})

    # ── Final integrity pass ──
    kept = sanitize_messages(kept)

    return kept


# ── Integrity sanitization ──



def extract_existing_tool_ids(messages: list[dict], include_assistant: bool = True) -> set[str]:
    """Scan messages for existing tool_call_ids in the conversation."""
    ids: set[str] = set()
    for msg in messages:
        role = msg.get("role", "")
        if role == "tool":
            tid = msg.get("tool_call_id", "")
            if tid: ids.add(tid)
        elif role == "user":
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tid = block.get("tool_use_id", "")
                        if tid: ids.add(tid)
        if include_assistant and role == "assistant":
            for tc in (msg.get("tool_calls") or []):
                if isinstance(tc, dict):
                    tid = tc.get("id", "")
                    if tid: ids.add(tid)
    return ids





def sanitize_messages(messages: list[dict]) -> list[dict]:
    """Ensure tool_call/tool_result pairing integrity after compression.
    
    Uses two separate sets: assistant IDs (what was requested) vs result IDs (what was received).
    This prevents orphan self-validation where a tool result validates itself.
    """
    if not messages:
        return messages

    # Set A: IDs from assistant tool_calls (what was requested by the model)
    requested_ids: set[str] = set()
    # Set B: IDs from actual tool results (what was received)
    received_ids: set[str] = set()

    for msg in messages:
        role = msg.get("role", "")
        if role == "tool":
            tid = msg.get("tool_call_id", "")
            if tid: received_ids.add(tid)
        elif role == "user":
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tid = block.get("tool_use_id", "")
                        if tid: received_ids.add(tid)
        elif role == "assistant":
            for tc in (msg.get("tool_calls") or []):
                if isinstance(tc, dict):
                    tid = tc.get("id", "")
                    if tid: requested_ids.add(tid)

    sanitized: list[dict] = []
    for msg in messages:
        # Drop orphan tool results (no matching assistant tool_call requested it)
        if msg.get("role") == "tool":
            tid = msg.get("tool_call_id", "")
            if tid and tid not in requested_ids:
                continue

        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            valid_calls = [
                tc for tc in msg["tool_calls"]
                if isinstance(tc, dict) and tc.get("id") in received_ids
            ]
            if valid_calls:
                msg = dict(msg)
                msg["tool_calls"] = valid_calls
            elif msg.get("content"):
                msg = dict(msg)
                msg.pop("tool_calls", None)
            else:
                continue

        sanitized.append(msg)

    return sanitized