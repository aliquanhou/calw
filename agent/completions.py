"""completions — 内联代码补全服务。GUI 中输入时自动触发轻量补全。"""
from __future__ import annotations
import re, threading, time
from typing import Any, Callable
_COMPLETION_PROMPT = "你是一个代码补全引擎。只输出补全的代码本身，不要解释。补全 1-3 行。"
class CompletionEngine:
    def __init__(self, stream_fn: Callable | None = None):
        self._stream_fn = stream_fn; self._last_time: float = 0
        self._debounce_ms: int = 400; self._active = False
    def request(self, text_before: str, text_after: str = "", file_ext: str = ".py", callback: Callable[[str],None]|None=None):
        now = time.time()*1000
        if now - self._last_time < self._debounce_ms: return
        self._last_time = now
        result = self._rule_complete(text_before, file_ext)
        if result and callback: callback(result)
    def _rule_complete(self, text: str, file_ext: str = ".py") -> str:
        if not text: return ""
        lines = text.split('\n'); stripped = lines[-1].strip() if lines else ""
        if file_ext == ".py":
            if re.match(r'def\s+\w+\(.*\):\s*$', stripped): return "    pass"
            if re.match(r'class\s+\w+.*:\s*$', stripped): return "    pass"
            if re.match(r'(for|while)\s+.*:\s*$', stripped): return "    pass"
            if stripped in ("else:","elif:") or stripped == "try:": return "    pass"
            if stripped == "if __name__ == '__main__':": return "    pass"
        return ""
    @property
    def is_active(self) -> bool: return self._active
_engine: CompletionEngine | None = None
def get_engine(stream_fn=None) -> CompletionEngine:
    global _engine
    if _engine is None: _engine = CompletionEngine(stream_fn)
    return _engine
