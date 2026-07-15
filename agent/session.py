"""session — 会话状态管理。
v2.1 新增模块。

统一管理 Agent 会话的生命周期状态：
  - 对话历史存储与检索
  - 配置持久化
  - 错误日志记录
  - 会话 ID 管理

消除原代码中散布在各模块间的全局变量和隐式状态。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Any


_SESSION_STATE: dict[str, "SessionState"] = {}
"""全局会话状态注册表。"""

_CURRENT_USER_ID: str | None = None
"""当前活跃的用户 ID。"""


def set_state(state: "SessionState"):
    """设置当前会话状态。"""
    global _CURRENT_USER_ID
    _SESSION_STATE[state.user_id] = state
    _CURRENT_USER_ID = state.user_id


def get_state(user_id: str | None = None) -> "SessionState | None":
    """获取当前或指定用户的会话状态。

    Args:
        user_id: 用户 ID，None 表示返回当前活跃状态

    Returns:
        SessionState 实例，或 None
    """
    if user_id:
        return _SESSION_STATE.get(user_id)
    if _CURRENT_USER_ID:
        return _SESSION_STATE.get(_CURRENT_USER_ID)
    return None


def get_handler(tool_name: str) -> Any | None:
    """获取工具处理函数（用于 streaming_parser 调用）。

    Args:
        tool_name: 工具名称

    Returns:
        工具处理函数，或 None
    """
    from .tools import get_tool
    tool_def = get_tool(tool_name)
    if tool_def:
        return tool_def.get("handler")
    return None


def set_session_workflow(workflow: Any):
    """设置当前会话的工作流引用（供工具函数同步状态）。"""
    state = get_state()
    if state:
        state.workflow = workflow


class SessionState:
    """会话状态 —— 管理一次用户的完整对话状态。"""

    def __init__(self, user_id: str = "default", data_dir: str | None = None):
        self.user_id = user_id
        self.session_id = str(uuid.uuid4())
        self.created_at = datetime.now().isoformat()
        self._lock = threading.Lock()

        # 向后兼容：工具注册等
        self._tool_registry: dict[str, dict] = {}

        # 工作流状态机引用（由 core.Agent 设置，供工具函数同步）
        self.workflow: Any = None
        self._plugin_handlers: dict = {}
        self._builtin_handlers: dict = {}
        self._tool_definitions: list = []
        self._plugins_loaded: bool = False
        self._last_heal_time: float = 0.0
        self._file_lessons: dict[str, list] = {}
        self._spawned_pids: set = set()

        # 数据存储目录
        self._data_dir = data_dir or os.path.join(
            os.environ.get("CALW_DATA_DIR", os.getcwd()),
            "data",
            user_id,
        )
        os.makedirs(self._data_dir, exist_ok=True)

        # 对话历史
        self._messages: list[dict] = []
        self._message_file = os.path.join(self._data_dir, "messages.jsonl")

        # 错误日志
        self._errors: list[dict] = []
        self._error_file = os.path.join(self._data_dir, "errors.jsonl")

        # 配置
        self._config: dict = {}

        # 加载已有数据
        self._load()

    def add_message(self, role: str, content: str,
                    tool_calls: list | None = None,
                    tool_call_id: str | None = None) -> dict:
        """添加一条消息到历史。

        线程安全。

        Args:
            role: 角色 ("user", "assistant", "tool")
            content: 消息内容
            tool_calls: 工具调用列表（仅 assistant 消息）
            tool_call_id: 工具调用 ID（仅 tool 消息）

        Returns:
            添加的消息 dict
        """
        msg = {
            "role": role,
            "content": content or "",
        }
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if tool_call_id:
            msg["tool_call_id"] = tool_call_id

        with self._lock:
            self._messages.append(msg)
            # 持久化追加到文件
            try:
                with open(self._message_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            except Exception:
                pass

        return msg

    def get_recent_messages(self, max_count: int = 50) -> list[dict]:
        """获取最近的 N 条消息。

        Args:
            max_count: 最大返回条数

        Returns:
            消息列表（副本，可安全修改）
        """
        with self._lock:
            return list(self._messages[-max_count:])

    def get_all_messages(self) -> list[dict]:
        """获取全部消息历史。"""
        with self._lock:
            return list(self._messages)

    def log_error(self, source: str, message: str, details: str = "") -> dict:
        """记录一条错误日志。

        Args:
            source: 错误来源（如 "llm_complete", "tool_exec"）
            message: 错误消息
            details: 详细堆栈或附加信息

        Returns:
            错误记录 dict
        """
        error = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "message": message,
            "details": details,
        }

        with self._lock:
            self._errors.append(error)
            try:
                with open(self._error_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(error, ensure_ascii=False) + "\n")
            except Exception:
                pass

        return error

    def save_conversation(self, messages: list[dict]) -> None:
        """保存完整的对话历史（覆盖写入）。

        Args:
            messages: 完整消息列表
        """
        with self._lock:
            self._messages = list(messages)
            try:
                with open(self._message_file, "w", encoding="utf-8") as f:
                    for msg in messages:
                        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def save(self) -> None:
        """强制保存当前状态。"""
        # 消息已实时持久化，这里仅确保配置保存
        pass

    # ── 工具注册（向后兼容 tools_core）──

    def __init_extra__(self):
        """初始化工具注册相关状态。"""
        if not hasattr(self, '_tool_registry'):
            self._tool_registry: dict[str, dict] = {}
            self._plugin_handlers: dict = {}
            self._builtin_handlers: dict = {}
            self._tool_definitions: list = []
            self._plugins_loaded: bool = False
            self._last_heal_time: float = 0.0
            self._file_lessons: dict[str, list] = {}

    @property
    def plugin_handlers(self) -> dict:
        return self._plugin_handlers

    @property
    def builtin_handlers(self) -> dict:
        return self._builtin_handlers

    @property
    def tool_definitions(self) -> list:
        return self._tool_definitions

    @property
    def plugins_loaded(self) -> bool:
        return getattr(self, '_plugins_loaded', False)

    @plugins_loaded.setter
    def plugins_loaded(self, val: bool):
        self._plugins_loaded = val

    def register_tool(self, name: str, handler, definition: dict, is_plugin: bool = False):
        """注册一个工具到会话状态。"""
        self.__init_extra__()
        self._tool_registry[name] = {"handler": handler, "definition": definition}
        if is_plugin:
            self._plugin_handlers[name] = handler
        else:
            self._builtin_handlers[name] = handler
        # 确保 definition 在 tool_definitions 中
        exists = any(t.get("name") == name for t in self._tool_definitions)
        if not exists and "name" in definition:
            self._tool_definitions.append(definition)

    def get_handler(self, tool_name: str):
        """获取工具处理函数。"""
        self.__init_extra__()
        # 优先从 tools 注册表获取
        if tool_name in self._tool_registry:
            return self._tool_registry[tool_name]["handler"]
        # 其次从旧版 handlers 获取
        if tool_name in self._builtin_handlers:
            return self._builtin_handlers[tool_name]
        if tool_name in self._plugin_handlers:
            return self._plugin_handlers[tool_name]
        # 尝试从 tools.py 获取
        try:
            from .tools import get_tool
            t = get_tool(tool_name)
            if t:
                return t.get("handler")
        except Exception:
            pass
        return None

    def should_heal(self, interval: int = 60) -> bool:
        """检查是否应当执行自愈操作。"""
        now = time.time()
        if now - getattr(self, '_last_heal_time', 0) > interval:
            self._last_heal_time = now
            return True
        return False

    def get_lessons_for_file(self, file_path: str) -> list:
        """获取文件的失败教训记录。"""
        self.__init_extra__()
        return self._file_lessons.get(file_path, [])

    def add_lesson_for_file(self, file_path: str, lesson: dict):
        """添加文件的失败教训。"""
        self.__init_extra__()
        if file_path not in self._file_lessons:
            self._file_lessons[file_path] = []
        self._file_lessons[file_path].append(lesson)

    @property
    def spawned_pids(self) -> set:
        """获取已生成的子进程 PID 集合。"""
        if not hasattr(self, '_spawned_pids'):
            self._spawned_pids = set()
        return self._spawned_pids

    def _load(self):
        """从磁盘加载已有数据。"""
        self.__init_extra__()
        # 加载消息历史
        if os.path.exists(self._message_file):
            try:
                with open(self._message_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._messages.append(json.loads(line))
            except Exception:
                pass

        # 加载错误日志
        if os.path.exists(self._error_file):
            try:
                with open(self._error_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._errors.append(json.loads(line))
            except Exception:
                pass

    @property
    def message_count(self) -> int:
        """消息总数。"""
        with self._lock:
            return len(self._messages)

    @property
    def error_count(self) -> int:
        """错误记录总数。"""
        with self._lock:
            return len(self._errors)

    def clear(self):
        """清除会话状态（保留文件）。"""
        with self._lock:
            self._messages.clear()
            self._errors.clear()
            self.session_id = str(uuid.uuid4())
