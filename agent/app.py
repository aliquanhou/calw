"""GUI application for the Multi-LLM Agent with tool panel."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import tkinter as tk
from typing import Any

import customtkinter as ctk

from .core import Agent, StreamHandler
from .prompt import SYSTEM_PROMPT
from .providers import (
    AnthropicProvider,
    OpenAIProvider,
)
from .scheduler import get_scheduler
from .watcher import get_watcher
from .app_dialogs import CodeReviewDialog, ResearchDialog, SchedulerDialog, WatcherDialog


# ── Color / style ──

COLOR_USER = "#4CAF50"
COLOR_ASSISTANT = "#E0E0E0"
COLOR_THINKING = "#888888"
COLOR_TOOL_NAME = "#FF9800"
COLOR_TOOL_RESULT = "#FFB74D"
COLOR_TOOL_IDLE = "#555555"
COLOR_TOOL_RUNNING = "#FFC107"
COLOR_TOOL_DONE = "#4CAF50"
COLOR_TOOL_ERROR = "#F44336"
COLOR_ERROR = "#F44336"
COLOR_SYSTEM = "#64B5F6"
COLOR_SEPARATOR = "#333333"

FONT_FAMILY = "Microsoft YaHei"
FONT_MONO = "Consolas"

TOOL_ICONS = {
    "read": "📖", "write": "✏️", "edit": "🔧",
    "glob": "🔍", "grep": "🔎", "bash": "💻", "think": "🧠",
    "system_info": "🖥️", "process": "⚙️", "web": "🌐", "screencap": "📸",
    "browser": "🌍", "background": "⏳", "plan": "📋", "task": "✅",
    "ast": "🌳", "dep_graph": "🕸", "call_chain": "🔗",
}

TOOL_CATEGORIES = [
    ("📂 文件系统", ["read", "write", "edit", "glob", "grep"]),
    ("⚡ 命令执行", ["bash", "background"]),
    ("🖥️ 系统控制", ["system_info", "process"]),
    ("🧠 智能与网络", ["think", "web", "screencap"]),
    ("🌍 浏览器", ["browser"]),
    ("🔬 代码分析", ["ast", "dep_graph", "call_chain"]),
    ("📋 工具链", ["plan", "task"]),
]

TOOL_DESCRIPTIONS = {
    "read": "读取文件", "write": "写入文件", "edit": "编辑文件",
    "glob": "搜索路径", "grep": "搜索内容", "bash": "执行命令",
    "think": "内部推理", "system_info": "系统信息",
    "process": "进程管理", "web": "网络请求", "screencap": "屏幕截图",
    "browser": "浏览器控制", "background": "后台任务",
    "ast": "AST结构分析", "dep_graph": "依赖图分析",
    "call_chain": "调用链追踪",
    "plan": "计划管理", "task": "任务状态",
}

CATEGORY_COLORS = {
    "📂 文件系统": "#42A5F5",
    "⚡ 命令执行": "#EF5350",
    "🖥️ 系统控制": "#AB47BC",
    "🧠 智能与网络": "#FFA726",
    "🌍 浏览器": "#26C6DA",
    "🔬 代码分析": "#FF7043",
    "📋 工具链": "#66BB6A",
}

PROVIDER_PRESETS = {
    "DeepSeek": {"base_url": "https://api.deepseek.com"},
    "Anthropic Claude": {"base_url": ""},
    "OpenAI": {"base_url": "https://api.openai.com/v1"},
}

PROVIDER_NAMES = list(PROVIDER_PRESETS.keys())

# ── v2.0 兼容：get_default_provider / get_provider 内联 ──

def _get_default_provider() -> str:
    return PROVIDER_NAMES[0] if PROVIDER_NAMES else "OpenAI"

def _get_provider(provider_name: str, api_key: str, model: str, base_url: str | None = None) -> OpenAIProvider | AnthropicProvider:
    if provider_name == "Anthropic Claude":
        return AnthropicProvider({
            "api_key": api_key,
            "model": model or "claude-sonnet-4-20250514",
            "base_url": base_url or "",
        })
    else:
        return OpenAIProvider({
            "api_key": api_key,
            "model": model or "gpt-4o",
            "base_url": base_url or PROVIDER_PRESETS.get(provider_name, {}).get("base_url", ""),
        })

get_default_provider = _get_default_provider
get_provider = _get_provider


# ── UI Stream Handler ──

class UIStreamHandler(StreamHandler):
    def __init__(self, msg_queue: queue.Queue):
        self.queue = msg_queue

    def on_text(self, text: str) -> None:
        self.queue.put(("text", text))

    def on_thinking(self, text: str) -> None:
        self.queue.put(("thinking", text))

    def on_tool_start(self, name: str, input_data: dict) -> None:
        self.queue.put(("tool_start", (name, input_data)))

    def on_tool_result(self, result: str) -> None:
        self.queue.put(("tool_result", result))

    def on_tool_output(self, text: str) -> None:
        # Empty string = heartbeat signal (update watchdog timer but don't display)
        if not text:
            self.queue.put(("heartbeat", None))
            return
        self.queue.put(("tool_output", text))

    def on_error(self, error: str) -> None:
        self.queue.put(("error", error))

    def on_turn_end(self) -> None:
        self.queue.put(("turn_end", None))

    def on_turn_plan(self, tool_count: int) -> None:
        self.queue.put(("turn_plan", tool_count))

    def on_complete(self) -> None:
        self.queue.put(("complete", None))


# ── Settings Dialog ──

class SettingsDialog(ctk.CTkToplevel):
    def __init__(
        self, parent: ctk.CTk,
        provider_name: str = "", api_key: str = "",
        model: str = "", base_url: str = "",
        system_prompt: str = "",
    ):
        super().__init__(parent)
        self.title("设置")
        self.geometry("640x620")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: dict | None = None

        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - 640) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 620) // 2
        self.geometry(f"+{max(0, px)}+{max(0, py)}")

        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(f, text="LLM 提供商", font=(FONT_FAMILY, 14, "bold")).pack(anchor="w", pady=(0, 4))
        self.provider_var = ctk.StringVar(value=provider_name or get_default_provider())
        ctk.CTkOptionMenu(f, variable=self.provider_var, values=PROVIDER_NAMES,
                          font=(FONT_FAMILY, 13), dropdown_font=(FONT_FAMILY, 13), height=35,
                          command=self._on_provider_change).pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(f, text="API 密钥", font=(FONT_FAMILY, 14, "bold")).pack(anchor="w", pady=(0, 4))
        self.api_key_var = ctk.StringVar(value=api_key)
        ctk.CTkEntry(f, textvariable=self.api_key_var, show="•",
                     font=(FONT_MONO, 13), height=35).pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(f, text="API 地址（OpenAI 兼容接口）", font=(FONT_FAMILY, 14, "bold")).pack(anchor="w", pady=(0, 4))
        self.base_url_var = ctk.StringVar(value=base_url)
        ctk.CTkEntry(f, textvariable=self.base_url_var, font=(FONT_MONO, 13), height=35,
                     placeholder_text="https://api.deepseek.com").pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(f, text="模型", font=(FONT_FAMILY, 14, "bold")).pack(anchor="w", pady=(0, 4))
        self.model_var = ctk.StringVar(value=model)
        self.model_menu = ctk.CTkOptionMenu(f, variable=self.model_var,
                                            values=self._models(), font=(FONT_MONO, 13),
                                            dropdown_font=(FONT_MONO, 13), height=35)
        self.model_menu.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(f, text="系统提示词", font=(FONT_FAMILY, 14, "bold")).pack(anchor="w", pady=(0, 4))
        self.prompt_text = ctk.CTkTextbox(f, font=(FONT_MONO, 12), height=200, wrap="word")
        self.prompt_text.pack(fill="both", expand=True, pady=(0, 16))
        self.prompt_text.insert("1.0", system_prompt or SYSTEM_PROMPT)

        btn = ctk.CTkFrame(f, fg_color="transparent")
        btn.pack(fill="x")
        ctk.CTkButton(btn, text="恢复默认", command=self._reset_prompt,
                      font=(FONT_FAMILY, 13), fg_color="#555", hover_color="#666", width=110).pack(side="left")
        ctk.CTkButton(btn, text="取消", command=self.destroy,
                      font=(FONT_FAMILY, 13), fg_color="#555", hover_color="#666", width=90).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn, text="保存", command=self._save,
                      font=(FONT_FAMILY, 13), width=90).pack(side="right")

    def _models(self):
        p = self.provider_var.get()
        return AnthropicProvider.models if p == "Anthropic Claude" else OpenAIProvider.models

    def _on_provider_change(self, c):
        if c == "Anthropic Claude":
            self.model_menu.configure(values=AnthropicProvider.models)
            self.model_var.set(AnthropicProvider.default_model)
        else:
            self.model_menu.configure(values=OpenAIProvider.models)
            self.model_var.set(OpenAIProvider.default_model)
        preset = PROVIDER_PRESETS.get(c, {})
        self.base_url_var.set(preset.get("base_url", ""))

    def _save(self):
        self.result = {
            "provider": self.provider_var.get(),
            "api_key": self.api_key_var.get().strip(),
            "model": self.model_var.get(),
            "base_url": self.base_url_var.get().strip(),
            "system_prompt": self.prompt_text.get("1.0", "end-1c"),
        }
        self.destroy()

    def _reset_prompt(self):
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", SYSTEM_PROMPT)


# ── Main Application ──

class AgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI Agent")
        self.geometry("1280x760")
        self.minsize(960, 600)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # State
        self.agent: Agent | None = None
        self.provider_name: str = get_default_provider()
        self.api_key: str = ""
        self.model: str = ""
        self.base_url: str = ""
        self.system_prompt: str = SYSTEM_PROMPT
        self.busy = False
        self.ui_queue: queue.Queue = queue.Queue()

        # Tool tracking
        self.tool_status: dict[str, str] = {t: "idle" for t in TOOL_ICONS}
        self.tool_activity: list[dict] = []
        self._active_tool: str | None = None
        self._active_tool_input: dict = {}  # 保存工具调用时的参数，用于结果展示
        self._active_tool_start: float = 0.0
        self._tool_start_time: float = 0.0
        self._last_output_time: float = time.time()
        self._watchdog_armed: bool = False
        self._watchdog_warned: bool = False
        self._stop_requested: bool = False
        self._highlight_pending: bool = False
        self._last_input: str = ""
        self._turn_total: int = 0
        self._turn_done: int = 0
        self._chat_needs_scroll: bool = False

        self._build_ui()
        self._load_config()
        self._poll_queue()
        self.entry.focus()

    # ── UI ──

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1, minsize=500)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # ══ Mission Control Dashboard ══
        self._build_dashboard()

        # ══ Main: Chat + Tool Panel ══
        # Chat
        chat_frame = ctk.CTkFrame(self)
        chat_frame.grid(row=1, column=0, sticky="nsew", padx=(10, 2), pady=5)
        chat_frame.grid_columnconfigure(0, weight=1)
        chat_frame.grid_rowconfigure(0, weight=1)

        self.chat = tk.Text(chat_frame, wrap="word", font=(FONT_MONO, 13),
                            bg="#1e1e1e", fg="#e0e0e0", insertbackground="#e0e0e0",
                            borderwidth=0, highlightthickness=0, padx=14, pady=12,
                            state="disabled", relief="flat")
        self.chat.grid(row=0, column=0, sticky="nsew")

        sb = ctk.CTkScrollbar(chat_frame, command=self.chat.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.chat.configure(yscrollcommand=sb.set)

        # Chat tags
        for tag, color, font in [
            ("user", COLOR_USER, (FONT_FAMILY, 13, "bold")),
            ("user_c", COLOR_USER, (FONT_MONO, 13)),
            ("asst", COLOR_ASSISTANT, (FONT_MONO, 13)),
            ("think", COLOR_THINKING, (FONT_MONO, 12)),
            ("tool", COLOR_TOOL_NAME, (FONT_MONO, 12, "bold")),
            ("tool_path", "#64B5F6", (FONT_MONO, 12)),
            ("tool_r", COLOR_TOOL_RESULT, (FONT_MONO, 12)),
            ("tool_meta", "#888", (FONT_MONO, 11)),
            ("code", "#82AAFF", (FONT_MONO, 12)),
            ("code_block", "#A8D8EA", (FONT_MONO, 12)),
            ("err", COLOR_ERROR, (FONT_MONO, 12, "bold")),
            ("sys", COLOR_SYSTEM, (FONT_FAMILY, 12)),
            ("sep", COLOR_SEPARATOR, (FONT_MONO, 8)),
            ("dim", "#666", (FONT_MONO, 11)),
            ("num", "#F78C6C", (FONT_MONO, 12)),
        ]:
            self.chat.tag_config(tag, foreground=color, font=font)

        # Code syntax highlighting tags
        code_font = (FONT_MONO, 13)
        for ctag, ccolor, cfont in [
            ("code_kw", "#C792EA", code_font),
            ("code_builtin", "#82AAFF", code_font),
            ("code_str", "#C3E88D", code_font),
            ("code_comment", "#676E95", (FONT_MONO, 12)),
            ("code_num", "#F78C6C", code_font),
        ]:
            self.chat.tag_config(ctag, foreground=ccolor, font=cfont)

        # ══ Tool Panel ══
        self._build_tool_panel()

        # ══ Quick Action Buttons + Input Area ══
        inp = ctk.CTkFrame(self, corner_radius=0)
        inp.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))
        inp.grid_columnconfigure(0, weight=1)

        # Action button bar (above input)
        act_frame = ctk.CTkFrame(inp, fg_color="transparent", height=30)
        act_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(4, 0))
        act_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        action_defs = [
            ("⏹", "终止", "Ctrl+Enter", self._stop_agent, "#F44336"),
            ("🔄", "重试", "Ctrl+R", self._retry_last, "#FF9800"),
            ("📸", "截屏", "Ctrl+Shift+S", self._quick_screenshot, "#AB47BC"),
            ("📊", "上下文", "Ctrl+I", self._show_context_detail, "#42A5F5"),
        ]
        self._action_btns = {}
        for i, (icon, label, shortcut, cmd, color) in enumerate(action_defs):
            text = f"{icon} {label}  {shortcut}"
            btn = ctk.CTkButton(act_frame, text=text, font=(FONT_FAMILY, 10),
                                fg_color=color, hover_color=self._darken(color),
                                height=24, corner_radius=4, command=cmd)
            btn.grid(row=0, column=i, padx=1, sticky="ew")
            self._action_btns[label] = btn

        # Input row
        inp_row = ctk.CTkFrame(inp, fg_color="transparent")
        inp_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        inp_row.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(inp_row, placeholder_text="输入指令，Enter 发送",
                                  font=(FONT_MONO, 14), height=40)
        self.entry.grid(row=0, column=0, padx=(10, 8), sticky="ew")
        self.entry.bind("<Return>", self._send)
        self.entry.bind("<Control-Return>", lambda e: self._stop_agent())
        self.entry.bind("<Control-r>", lambda e: self._retry_last())
        self.entry.bind("<Control-R>", lambda e: self._retry_last())
        self.entry.bind("<Control-Shift-S>", lambda e: self._quick_screenshot())
        self.entry.bind("<Control-Shift-s>", lambda e: self._quick_screenshot())
        self.entry.bind("<Control-i>", lambda e: self._show_context_detail())
        self.entry.bind("<Control-I>", lambda e: self._show_context_detail())

        self.send_btn = ctk.CTkButton(inp_row, text="发送", width=90, height=40,
                                      font=(FONT_FAMILY, 14), command=self._send)
        self.send_btn.grid(row=0, column=1, padx=(8, 10))

        # ══ Status Bar ══
        self.status_bar = ctk.CTkLabel(self, text="Ready — configure API in Settings",
                                       anchor="w", font=(FONT_FAMILY, 11), text_color="#888")
        self.status_bar.grid(row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 4))

    def _build_dashboard(self):
        """Build the Mission Control dashboard header."""
        dash = ctk.CTkFrame(self, height=72, corner_radius=0, fg_color="#1a1a2e")
        dash.grid(row=0, column=0, columnspan=2, sticky="ew")
        dash.grid_propagate(False)
        dash.grid_columnconfigure(4, weight=1)  # push buttons to right

        # ── Left: Brand + Status ──
        brand_frame = ctk.CTkFrame(dash, fg_color="transparent")
        brand_frame.grid(row=0, column=0, padx=(16, 8), pady=8, sticky="w")

        ctk.CTkLabel(brand_frame, text="Calw", font=(FONT_FAMILY, 20, "bold"),
                     text_color="#00d4ff").grid(row=0, column=0, sticky="w", pady=(0, 2))

        self.status_indicator = ctk.CTkLabel(brand_frame, text="Idle", font=(FONT_FAMILY, 10),
                                              text_color="#4CAF50", anchor="w")
        self.status_indicator.grid(row=1, column=0, sticky="w")

        # ── Provider + Model ──
        prov_frame = ctk.CTkFrame(dash, fg_color="transparent")
        prov_frame.grid(row=0, column=1, padx=16, pady=8, sticky="w")

        ctk.CTkLabel(prov_frame, text="Provider", font=(FONT_FAMILY, 9),
                     text_color="#666", anchor="w").grid(row=0, column=0, sticky="w")
        self.provider_label = ctk.CTkLabel(prov_frame, text="DeepSeek", font=(FONT_FAMILY, 12),
                                            text_color="#64B5F6", anchor="w")
        self.provider_label.grid(row=1, column=0, sticky="w")

        # ── Session Stats ──
        stats_frame = ctk.CTkFrame(dash, fg_color="transparent")
        stats_frame.grid(row=0, column=2, padx=16, pady=8, sticky="w")

        ctk.CTkLabel(stats_frame, text="Session", font=(FONT_FAMILY, 9),
                     text_color="#666", anchor="w").grid(row=0, column=0, sticky="w")
        self.msg_label = ctk.CTkLabel(stats_frame, text="0 turns", font=(FONT_FAMILY, 12),
                                       text_color="#aaa", anchor="w")
        self.msg_label.grid(row=1, column=0, sticky="w")

        # ── Token Usage ──
        token_frame = ctk.CTkFrame(dash, fg_color="transparent")
        token_frame.grid(row=0, column=3, padx=16, pady=8, sticky="w")

        ctk.CTkLabel(token_frame, text="Context", font=(FONT_FAMILY, 9),
                     text_color="#666", anchor="w").grid(row=0, column=0, sticky="w")
        self.ctx_label = ctk.CTkLabel(token_frame, text="0 / 0K", font=(FONT_MONO, 11),
                                       text_color="#aaa", anchor="w")
        self.ctx_label.grid(row=1, column=0, sticky="w")

        # ── Right: Action Buttons ──
        btn_frame = ctk.CTkFrame(dash, fg_color="transparent")
        btn_frame.grid(row=0, column=5, padx=(8, 16), pady=12, sticky="e")

        ctk.CTkButton(btn_frame, text="Settings", width=74, height=30,
                      font=(FONT_FAMILY, 11), command=self._open_settings,
                      fg_color="#2a2a4a", hover_color="#3a3a5a"
                      ).grid(row=0, column=0, padx=1)

        self.btn_review = ctk.CTkButton(btn_frame, text="🔍 审查", width=64, height=30,
                                        font=(FONT_FAMILY, 11), command=self._open_review,
                                        fg_color="#2a2a4a", hover_color="#3a3a5a")
        self.btn_review.grid(row=0, column=1, padx=1)

        self.btn_research = ctk.CTkButton(btn_frame, text="📊 研究", width=64, height=30,
                                          font=(FONT_FAMILY, 11), command=self._open_research,
                                          fg_color="#2a2a4a", hover_color="#3a3a5a")
        self.btn_research.grid(row=0, column=2, padx=1)

        self.btn_schedule = ctk.CTkButton(btn_frame, text="⏰ 定时", width=64, height=30,
                                          font=(FONT_FAMILY, 11), command=self._open_schedule,
                                          fg_color="#2a2a4a", hover_color="#3a3a5a")
        self.btn_schedule.grid(row=0, column=3, padx=1)

        self.btn_watch = ctk.CTkButton(btn_frame, text="👁 监控", width=64, height=30,
                                       font=(FONT_FAMILY, 11), command=self._open_watch,
                                       fg_color="#2a2a4a", hover_color="#3a3a5a")
        self.btn_watch.grid(row=0, column=4, padx=1)

        ctk.CTkButton(btn_frame, text="Clear", width=60, height=30,
                      font=(FONT_FAMILY, 11), command=self._clear_chat,
                      fg_color="#333", hover_color="#555"
                      ).grid(row=0, column=5, padx=1)

        # ── Context progress bar (thin, below dashboard) ──
        self.ctx_progress = ctk.CTkProgressBar(dash, height=3, corner_radius=0,
                                                fg_color="#333", progress_color="#00d4ff")
        self.ctx_progress.grid(row=1, column=0, columnspan=6, sticky="ew")
        self.ctx_progress.set(0)

    def _build_tool_panel(self):
        """Build the right-side tool panel with tabbed layout (工具 | 日志)."""
        panel = ctk.CTkFrame(self, width=290, corner_radius=8)
        panel.grid(row=1, column=1, sticky="nsew", padx=(2, 10), pady=5)
        panel.grid_propagate(False)
        panel.grid_rowconfigure(2, weight=1)  # tabview

        # ── Header ──
        hdr = ctk.CTkFrame(panel, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="🛠 工具面板", font=(FONT_FAMILY, 15, "bold"),
                      anchor="w").grid(row=0, column=0, sticky="w")

        # ── Task Progress Bar ──
        prog_frame = ctk.CTkFrame(panel, fg_color="transparent", height=28)
        prog_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 2))
        prog_frame.grid_columnconfigure(0, weight=1)
        prog_frame.grid_propagate(False)
        self.task_progress = ctk.CTkProgressBar(prog_frame, height=8, corner_radius=4)
        self.task_progress.grid(row=0, column=0, sticky="ew", pady=(2, 0))
        self.task_progress.set(0)
        self.task_prog_label = ctk.CTkLabel(prog_frame, text="", font=(FONT_MONO, 9),
                                             text_color="#555", anchor="w")
        self.task_prog_label.grid(row=1, column=0, sticky="w")

        # ── Tab View: 工具 | 日志 ──
        self.tab_view = ctk.CTkTabview(panel, fg_color="transparent",
                                       segmented_button_selected_color="#2a2a4a",
                                       segmented_button_unselected_color="#222",
                                       text_color="#e0e0e0",
                                       segmented_button_selected_hover_color="#3a3a5a")
        self.tab_view.grid(row=2, column=0, sticky="nsew", padx=4, pady=(4, 4))

        tab_tools = self.tab_view.add("🛠 工具")
        tab_log = self.tab_view.add("📋 日志")

        # ── Tab: 工具状态 ──
        self.tool_scroll = ctk.CTkScrollableFrame(tab_tools, fg_color="transparent")
        self.tool_scroll.pack(fill="both", expand=True, padx=4, pady=4)
        self.tool_scroll.grid_columnconfigure(0, weight=1)

        self.tool_widgets: dict[str, dict] = {}
        row_offset = 0
        for cat_name, tool_names in TOOL_CATEGORIES:
            cat_color = CATEGORY_COLORS.get(cat_name, "#888")
            cat_hdr = ctk.CTkFrame(self.tool_scroll, fg_color="#333333", height=26, corner_radius=4)
            cat_hdr.grid(row=row_offset, column=0, sticky="ew", pady=(6, 1))
            cat_hdr.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(cat_hdr, text=cat_name, font=(FONT_FAMILY, 11, "bold"),
                          text_color=cat_color, anchor="w").grid(row=0, column=0, padx=10, pady=2, sticky="w")
            row_offset += 1
            pairs = [tool_names[i:i+2] for i in range(0, len(tool_names), 2)]
            for pair in pairs:
                tag_row = ctk.CTkFrame(self.tool_scroll, fg_color="transparent", height=32)
                tag_row.grid(row=row_offset, column=0, sticky="ew", pady=1)
                tag_row.grid_columnconfigure(0, weight=1), tag_row.grid_columnconfigure(1, weight=1)
                row_offset += 1
                for ci, tname in enumerate(pair):
                    icon = TOOL_ICONS.get(tname, "🔹")
                    frame = ctk.CTkFrame(tag_row, fg_color="#2a2a2a", corner_radius=6, height=30)
                    frame.grid(row=0, column=ci, sticky="ew", padx=2)
                    frame.grid_propagate(False)
                    frame.grid_columnconfigure(1, weight=1)
                    dot = ctk.CTkLabel(frame, text="○", font=(FONT_MONO, 9),
                                       text_color=COLOR_TOOL_IDLE, width=12)
                    dot.grid(row=0, column=0, padx=(6, 2), pady=5)
                    ctk.CTkLabel(frame, text=f"{icon} {tname}",
                                 font=(FONT_MONO, 11, "bold"), anchor="w"
                                 ).grid(row=0, column=1, padx=0, pady=5, sticky="w")
                    ctk.CTkLabel(frame, text=TOOL_DESCRIPTIONS.get(tname, ""),
                                 font=(FONT_FAMILY, 9), text_color="#666", anchor="e"
                                 ).grid(row=0, column=2, padx=(2, 6), pady=5)
                    self.tool_widgets[tname] = {"dot": dot, "card": frame}
            ctk.CTkLabel(self.tool_scroll, text="", font=(FONT_MONO, 3)).grid(row=row_offset, column=0)
            row_offset += 1

        # ── Tab: 活动日志 ──
        self.activity_log = tk.Text(tab_log, wrap="word", font=(FONT_MONO, 11),
                                     bg="#1a1a1a", fg="#aaa", borderwidth=0,
                                     highlightthickness=0, padx=8, pady=6,
                                     state="disabled", relief="flat")
        self.activity_log.pack(fill="both", expand=True, padx=4, pady=4)
        self.activity_log.tag_config("log_idle", foreground="#555")
        self.activity_log.tag_config("log_run", foreground="#FFC107")
        self.activity_log.tag_config("log_done", foreground="#4CAF50")
        self.activity_log.tag_config("log_err", foreground="#F44336")

    # ── Tool Panel Updates ──

    def _set_tool_status(self, name: str, status: str):
        """Update a tool's status dot in the panel."""
        self.tool_status[name] = status
        w = self.tool_widgets.get(name)
        if not w:
            return
        color = {
            "idle": COLOR_TOOL_IDLE, "running": COLOR_TOOL_RUNNING,
            "done": COLOR_TOOL_DONE, "error": COLOR_TOOL_ERROR,
        }.get(status, COLOR_TOOL_IDLE)
        dots = {"idle": "○", "running": "●", "done": "✓", "error": "✗"}
        w["dot"].configure(text=dots.get(status, "○"), text_color=color)

    def _log_activity(self, tool: str, status: str, detail: str = ""):
        """Add a line to the activity log."""
        ts = time.strftime("%H:%M:%S")
        icon = {"running": "▶", "done": "✓", "error": "✗"}.get(status, "·")
        tag = f"log_{status}" if status in ("run", "done", "err") else "log_idle"
        line = f"{ts} {icon} {tool}"
        if detail:
            line += f"  {detail[:60]}"
        self.activity_log.configure(state="normal")
        self.activity_log.insert("end", line + "\n", tag)
        self.activity_log.see("end")
        self.activity_log.configure(state="disabled")

    def _reset_task_progress(self):
        """Clear task progress bar."""
        self._turn_total = 0
        self._turn_done = 0
        self.task_progress.set(0)
        self.task_prog_label.configure(text="")

    def _update_task_progress(self):
        """Update task step progress bar."""
        if self._turn_total <= 0:
            self.task_progress.set(0)
            self.task_prog_label.configure(text="")
            return
        ratio = min(self._turn_done / self._turn_total, 1.0)
        self.task_progress.set(ratio)
        color = "#4CAF50" if ratio >= 1.0 else "#FFC107"
        self.task_progress.configure(progress_color=color)
        self.task_prog_label.configure(text=f"步骤 {self._turn_done}/{self._turn_total}")

    def _update_context_bar(self):
        """Update the context usage progress bar with current token counts."""
        if not self.agent or not self.agent.messages:
            self.ctx_progress.set(0)
            self.ctx_label.configure(text="0 / 0K tokens")
            return
        try:
            from .context import count_total_tokens, get_context_limit
            system = self.agent.system_prompt or ""
            total = count_total_tokens(self.agent.messages, system)
            model_name = getattr(self.agent.provider, 'model_name', '') or ''
            limit = get_context_limit(model_name)
            ratio = min(total / limit, 1.0) if limit > 0 else 0
            self.ctx_progress.set(ratio)
            if ratio > 0.85:
                self.ctx_progress.configure(progress_color="#F44336")
            elif ratio > 0.65:
                self.ctx_progress.configure(progress_color="#FF9800")
            else:
                self.ctx_progress.configure(progress_color="#4CAF50")
            self.ctx_label.configure(text=f"{total/1000:.1f}K / {limit/1000:.0f}K tokens")
        except Exception:
            pass

    # ── Config ──

    def _config_path(self):
        return os.path.join(os.path.dirname(__file__), "..", "config.json")

    def _load_config(self):
        p = self._config_path()
        if os.path.exists(p):
            try:
                d = json.load(open(p, "r", encoding="utf-8"))
                self.provider_name = d.get("provider", get_default_provider())
                self.api_key = d.get("api_key", "")
                self.model = d.get("model", "")
                self.base_url = d.get("base_url", "")
                # 系统提示词始终从 prompt.py 加载，config 不覆盖
                self._init_agent()
            except Exception:
                pass

    def _save_config(self):
        try:
            with open(self._config_path(), "w", encoding="utf-8") as f:
                json.dump({"provider": self.provider_name, "api_key": self.api_key,
                           "model": self.model, "base_url": self.base_url},
                          f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _init_agent(self):
        if not self.api_key:
            return
        try:
            # Agent 配置（v2.1 新 API）
            config = {
                "api_key": self.api_key,
                "model": self.model,
                "base_url": self.base_url,
                "max_tokens": 8192,
                "temperature": 0.0,
                "request_timeout": 120,
                "max_tool_rounds": 50,
                "enable_speculative": True,
                "enable_streaming_parser": True,
            }
            self.agent = Agent(config=config)
            self.provider_label.configure(text=self.provider_name)

            # Show memory stats if available
            try:
                from .memory import get_conversation_stats, get_codebase_stats
                cs = get_conversation_stats()
                cbs = get_codebase_stats()
                mem_parts = []
                if cs.get("total_turns"):
                    mem_parts.append(f"记忆:{cs['total_turns']}轮")
                if cbs.get("cached_modules"):
                    mem_parts.append(f"缓存:{cbs['cached_modules']}模块")
                if mem_parts:
                    self.status_bar.configure(text="就绪 — " + " | ".join(mem_parts))
            except Exception:
                pass
            self._update_context_bar()
        except Exception as e:
            self.status_bar.configure(text=f"初始化失败: {e}")

    # ── Quick Actions ──

    @staticmethod
    def _darken(hex_color: str, factor: float = 0.75) -> str:
        """Darken a hex color by factor."""
        r = int(int(hex_color[1:3], 16) * factor)
        g = int(int(hex_color[3:5], 16) * factor)
        b = int(int(hex_color[5:7], 16) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _stop_agent(self):
        """Immediately stop the current agent generation."""
        if not self.busy:
            return
        self._force_reset("⏹ 用户手动终止")

    def _retry_last(self):
        """Re-send the last user input."""
        if self.busy or not self._last_input:
            return
        self._send_text(self._last_input)

    def _quick_screenshot(self):
        """Send a screenshot command to the agent."""
        if self.busy or not self.api_key:
            return
        self._send_text("截屏，然后告诉我你看到了什么")

    def _show_context_detail(self):
        """Show detailed context breakdown in the chat."""
        if not self.agent:
            self._chat_line("尚无对话", "err")
            return
        try:
            from .context import count_total_tokens, count_message_tokens, count_tool_result_tokens, get_context_limit
            system = self.agent.system_prompt or ""
            total = count_total_tokens(self.agent.messages, system)
            model_name = getattr(self.agent.provider, 'model_name', '') or ''
            limit = get_context_limit(model_name)

            lines = [f"── 上下文明细 ──", f"模型限额: {limit/1000:.0f}K tokens"]
            lines.append(f"总使用:   {total/1000:.1f}K tokens ({total/limit*100:.1f}%)")
            lines.append(f"系统提示词: ~{len(system)//4} tokens")
            # Count by role
            roles: dict[str, int] = {}
            for m in self.agent.messages:
                r = m.get("role", "?")
                if r in ("user", "assistant"):
                    roles[r] = roles.get(r, 0) + count_message_tokens(m)
                elif r == "tool":
                    roles[r] = roles.get(r, 0) + count_tool_result_tokens(m)
            for r, c in roles.items():
                lines.append(f"  {r}: {c/1000:.1f}K")
            lines.append(f"消息条数: {len(self.agent.messages)}")
            for line in lines:
                self._chat_line(line, "sys")
        except Exception as e:
            self._chat_line(f"上下文分析失败: {e}", "err")

    # ── Queue ──

    def _on_complete(self):
        self.busy = False
        self._watchdog_armed = False
        self._watchdog_warned = False
        self._stop_requested = False
        self.entry.configure(state="normal")
        self.send_btn.configure(state="normal", text="发送")
        self._set_action_buttons(False)
        self.status_indicator.configure(text="Idle", text_color="#4CAF50")
        self.entry.focus()
        n = len(self.agent.messages) // 2 if self.agent else 0
        self.msg_label.configure(text=f"{n} 轮")
        self._update_context_bar()
        # Show 100% briefly, then reset
        self._update_task_progress()
        self.after(2000, self._reset_task_progress)
        # Reset active tool
        if self._active_tool:
            self._set_tool_status(self._active_tool, "done")
            self._active_tool = None

    def _poll_queue(self):
        """Poll UI message queue. Limits per-cycle processing to keep UI responsive."""
        processed = 0
        try:
            while True:
                if processed >= 200:
                    if self._chat_needs_scroll:
                        self._chat_needs_scroll = False
                        self.chat.configure(state="normal")
                        self.chat.see("end")
                        self.chat.configure(state="disabled")
                    self.update_idletasks()
                    self.after(1, self._poll_queue)
                    return
                t, d = self.ui_queue.get_nowait()
                self._handle_msg(t, d)
                processed += 1
        except queue.Empty:
            pass

        # Batch-end scroll (throttled for streaming performance)
        if self._chat_needs_scroll:
            self._chat_needs_scroll = False
            self.chat.configure(state="normal")
            self.chat.see("end")
            self.chat.configure(state="disabled")

        # ── Watchdog: detect stuck, show running duration ──
        if self.busy and self._watchdog_armed:
            elapsed = time.time() - self._last_output_time
            if self._active_tool == "bash":
                warn_threshold = 300
                reset_threshold = 600
            else:
                warn_threshold = 180
                reset_threshold = 300

            if elapsed > warn_threshold and not self._watchdog_warned:
                self._watchdog_warned = True
                self.status_indicator.configure(text=f"⚠ 工作中 ({int(elapsed)}s 无响应)", text_color="#F44336")
                self._chat_line(f"⚠ 警告: Agent 已 {int(elapsed)}s 无输出，可能已卡死", "err")
            elif elapsed > reset_threshold:
                self._force_reset("检测到 Agent 卡死（300s 无输出），已自动重置")
            elif elapsed > warn_threshold:
                self.status_indicator.configure(text=f"⚠ 工作中 ({int(elapsed)}s)", text_color="#FF9800")
            elif self._active_tool and self._active_tool_start:
                # Show running duration for active tool
                run_sec = int(time.time() - self._active_tool_start)
                if run_sec > 0:
                    curr = self.status_indicator.cget("text")
                    # Only update duration display, preserve the tool name set in tool_start
                    if "(" not in curr or "工作中" in curr:
                        pass  # already handled above

        self.after(250, self._poll_queue)

    def _force_reset(self, reason: str = ""):
        """Force-reset the agent when stuck."""
        self.busy = False
        self._watchdog_armed = False
        self._watchdog_warned = False
        self._stop_requested = False
        # Sanitize message list: remove orphan tool_calls from broken state
        if self.agent:
            try:
                from .context import sanitize_messages
                self.agent.messages = sanitize_messages(self.agent.messages)
            except Exception:
                pass
        self.entry.configure(state="normal")
        self.send_btn.configure(state="normal", text="发送")
        self._set_action_buttons(False)
        self.status_indicator.configure(text="Idle", text_color="#4CAF50")
        self._reset_task_progress()
        if reason:
            self._chat_line(f"⛔ {reason}", "err")
            self.status_bar.configure(text=reason)
        self.entry.focus()

    def _handle_msg(self, t: str, d: Any):
        self._last_output_time = time.time()
        self._watchdog_armed = True
        self._watchdog_warned = False
        if t == "text":
            self._chat_stream(d, "asst")
        elif t == "thinking":
            self._chat_stream(d, "think")
        elif t == "tool_start":
            name, inp = d
            # Mark previous tool as done if switching
            if self._active_tool and self._active_tool != name:
                self._set_tool_status(self._active_tool, "done")
            self._active_tool = name
            self._active_tool_input = inp  # ← 保存输入参数
            self._active_tool_start = time.time()
            self._set_tool_status(name, "running")
            self._log_activity(name, "running", json.dumps(inp, ensure_ascii=False)[:80])
            self._append_tool(name, inp)
            # Update status bar: show what tool is running
            verb = TOOL_DESCRIPTIONS.get(name, name)
            cmd_preview = ""
            if name == "bash" and "command" in inp:
                cmd_preview = inp["command"][:60]
            elif "file_path" in inp:
                cmd_preview = inp["file_path"]
            if cmd_preview:
                self.status_indicator.configure(text=f"{verb}: {cmd_preview}", text_color="#FF9800")
            else:
                self.status_indicator.configure(text=f"{verb}...", text_color="#FF9800")
        elif t == "tool_result":
            self._turn_done += 1
            self._update_task_progress()
            self._append_tool_result(d)
            # 补充进度显示
            if self._turn_total > 1:
                self._chat_line(f"    → 步骤 {self._turn_done}/{self._turn_total}", "dim")
        elif t == "tool_output":
            self._chat_stream(d, "tool_r", scroll=True)
        elif t == "heartbeat":
            # Silent heartbeat from bash streaming — updates watchdog timer, no display
            pass
        elif t == "turn_plan":
            self._turn_total = d
            self._turn_done = 0
            self._update_task_progress()
        elif t == "error":
            if self._active_tool:
                self._set_tool_status(self._active_tool, "error")
                self._log_activity(self._active_tool, "error", str(d)[:60])
                self._active_tool = None
            self._chat_line(f"错误: {d}", "err")
        elif t == "turn_end":
            self._chat_line("", "sep")
        elif t == "complete":
            self._on_complete()

    # ── Chat Display ──

    def _chat_stream(self, text: str, tag: str, scroll: bool = True):
        self.chat.configure(state="normal")
        self.chat.insert("end", text, tag)
        self.chat.configure(state="disabled")
        if scroll:
            self.chat.see("end")
        else:
            self._chat_needs_scroll = True
        self._schedule_highlight()

    def _chat_line(self, text: str, tag: str = ""):
        self.chat.configure(state="normal")
        if tag:
            self.chat.insert("end", text + "\n", tag)
        else:
            self.chat.insert("end", text + "\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")
        self._schedule_highlight()

    def _schedule_highlight(self):
        """Debounce syntax highlighting — wait 200ms after last input."""
        if not self._highlight_pending:
            self._highlight_pending = True
            self.after(200, self._apply_highlight)

    def _apply_highlight(self):
        """Apply Python syntax highlighting to chat content via regex. Time-bounded."""
        self._highlight_pending = False
        try:
            content = self.chat.get("1.0", "end-1c")
            if not content or len(content) > 50000:  # skip if too large
                return

            self.chat.configure(state="normal")

            # Clear old code tags
            for tag in ("code_kw", "code_builtin", "code_str", "code_comment", "code_num"):
                self.chat.tag_remove(tag, "1.0", "end")

            # Compile patterns once
            _re = __import__('re')
            patterns = [
                ("code_comment", _re.compile(r'#[^\n]*')),
                ("code_str", _re.compile(r'""".*?"""|\'\'\'.*?\'\'\'|"[^"\\]*(?:\\.[^"\\]*)*"|\'[^\'\\]*(?:\\.[^\'\\]*)*\'')),
                ("code_kw", _re.compile(r'\b(?:def|class|return|if|else|elif|for|while|import|from|as|try|except|finally|with|yield|lambda|pass|break|continue|and|or|not|in|is|None|True|False|raise|async|await|self|del|global|nonlocal|assert|match|case|__init__|__str__|__repr__)\b')),
                ("code_num", _re.compile(r'\b\d+\.?\d*(?:[eE][+-]?\d+)?\b')),
                ("code_builtin", _re.compile(r'\b(?:print|len|range|type|super|int|str|list|dict|set|tuple|open|input|isinstance|hasattr|getattr|setattr|map|filter|sorted|reversed|enumerate|zip|min|max|sum|any|all|abs|round|hex|bin|ord|chr|repr|dir|id|help|super|object|property|staticmethod|classmethod|isinstance|issubclass|callable|iter|next|slice|vars|locals|globals|eval|exec|compile)\b')),
            ]

            deadline = time.time() + 0.15  # max 150ms
            for tag, pattern in patterns:
                if time.time() > deadline:
                    break
                for match in pattern.finditer(content):
                    if time.time() > deadline:
                        break
                    start = f"1.0 + {match.start()} chars"
                    end = f"1.0 + {match.end()} chars"
                    self.chat.tag_add(tag, start, end)

            self.chat.configure(state="disabled")
        except Exception:
            self.chat.configure(state="disabled")

    def _append_user_msg(self, text: str):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"\n>>> ", "user")
        self.chat.insert("end", f"{text}\n\n", "user_c")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _tool_label(self, name: str) -> str:
        """Get icon + label for a tool name."""
        icons = {
            "read": "📖", "write": "✏️", "edit": "🔧", "replace": "🔍",
            "glob": "🔎", "grep": "🔎", "bash": "💻", "web": "🌐",
            "web_search": "🔍", "browser": "🌍", "process": "⚙️",
            "service": "⚙️", "registry": "📋", "gui": "🖱️",
            "plan": "📋", "task": "✅", "background": "⏳",
            "remember": "🧠", "test": "🧪", "dep": "📦",
            "ast": "🌳", "dep_graph": "🕸️", "call_chain": "🔗",
            "monitor": "📊", "schedule": "⏰", "watch": "👁️",
            "websocket": "🔌", "download": "📥", "move": "📂",
            "copy": "📄", "delete": "🗑️", "mkdir": "📁",
            "ask_user": "💬", "trace_error": "🐛",
        }
        return icons.get(name, "⚡")

    def _tool_path_display(self, inp: dict) -> str:
        """从工具参数中提取要显示的目标路径/命令。"""
        if "file_path" in inp:
            return inp["file_path"]
        if "command" in inp:
            cmd = inp["command"]
            return cmd[:80] + ("..." if len(cmd) > 80 else "")
        if "url" in inp:
            return inp["url"]
        if "pattern" in inp:
            return inp["pattern"]
        if "query" in inp:
            return inp["query"]
        if "path" in inp:
            return inp["path"]
        return ""

    def _append_tool(self, name: str, inp: dict):
        """Claude Code 风格：工具名 + 目标（同一行），绿色箭头指示。"""
        self.chat.configure(state="normal")
        icon = self._tool_label(name)
        path = self._tool_path_display(inp)

        # 工具行：📖 read  main.py
        line = f"  {icon} {name}"
        self.chat.insert("end", line, "tool")
        if path:
            self.chat.insert("end", f"  {path}", "tool_path")

        # 额外参数用小字灰色显示
        extra = {k: v for k, v in inp.items()
                 if k not in ("file_path", "command", "url", "pattern", "query", "path") and v}
        if extra:
            meta = "  " + " ".join(f"{k}={v}" for k, v in extra.items())
            if len(meta) > 120:
                meta = meta[:120] + "..."
            self.chat.insert("end", f"\n    {meta}", "dim")

        self.chat.insert("end", "\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _append_tool_result(self, result: str):
        """Claude Code 风格：结果展示，按工具类型格式化。"""
        is_err = any(kw in result[:100].lower() for kw in ("错误", "error", "失败", "❌"))
        status_tag = "err" if is_err else "tool_r"

        current_tool = self._active_tool or ""
        current_inp = self._active_tool_input or {}

        self.chat.configure(state="normal")

        # 状态标记 + 结果摘要
        prefix = "✗ " if is_err else "✔ "
        summary = result[:200].replace("\n", " ")
        self.chat.insert("end", f"    {prefix}", status_tag)
        self.chat.insert("end", f"{summary}\n", status_tag)

        # ── write / edit：展示写入了什么内容 ──
        if current_tool in ("write",) and current_inp.get("content") and not is_err:
            content = current_inp["content"]
            lines = content.split("\n")
            preview = lines[:12]  # 前 12 行
            for line in preview:
                self.chat.insert("end", f"      {line[:200]}\n", "code")
            if len(lines) > 12:
                self.chat.insert("end", f"      ... 共 {len(lines)} 行\n", "dim")

        if current_tool in ("edit",) and current_inp.get("new_string") and not is_err:
            new_text = current_inp["new_string"]
            lines = new_text.split("\n")
            preview = lines[:8]
            self.chat.insert("end", f"      ↓ 替换为:\n", "tool")
            for line in preview:
                self.chat.insert("end", f"      {line[:200]}\n", "code")
            if len(lines) > 8:
                self.chat.insert("end", f"      ... 共 {len(lines)} 行\n", "dim")

        # ── read：展示文件内容 ──
        if current_tool == "read" and result and not is_err:
            lines = result.split("\n")
            shown = lines[:8]
            for line in shown:
                self.chat.insert("end", f"      {line[:200]}\n", "code")
            if len(lines) > 8:
                self.chat.insert("end", f"      ... 共 {len(lines)} 行\n", "dim")
                for line in lines[-3:]:
                    self.chat.insert("end", f"      {line[:200]}\n", "code")

        # ── bash：最后几行输出 ──
        if current_tool == "bash" and result and not is_err:
            lines = [l for l in result.split("\n") if l.strip()]
            if len(lines) > 6:
                self.chat.insert("end", f"      ... 共 {len(lines)} 行输出\n", "dim")
                for line in lines[-4:]:
                    self.chat.insert("end", f"      {line[:200]}\n", "dim")

        self.chat.see("end")
        self.chat.configure(state="disabled")

        # 更新工具状态面板
        if current_tool:
            self._set_tool_status(current_tool, "error" if is_err else "done")
            preview = result[:80].replace("\n", " ")
            self._log_activity(current_tool, "error" if is_err else "done", preview)
            self._active_tool = None
            self._active_tool_input = {}

    # ── Actions ──

    def _send(self, event=None):
        if self.busy:
            return
        text = self.entry.get().strip()
        if not text:
            return
        self._send_text(text)

    def _set_action_buttons(self, busy: bool):
        """Enable/disable quick action buttons based on busy state."""
        for label, btn in self._action_btns.items():
            if label == "终止":
                btn.configure(state="normal" if busy else "disabled")
            else:
                btn.configure(state="disabled" if busy else "normal")

    def _send_text(self, text: str):
        """Send text to the agent. Shared by _send and quick actions."""
        if self.busy:
            return
        if not self.api_key:
            self._chat_line("请先点击 ⚙ 设置 配置 API Key", "err")
            return
        if not self.agent:
            self._init_agent()
            if not self.agent:
                self._chat_line("Agent 初始化失败，请检查设置", "err")
                return

        self._last_input = text
        self.entry.delete(0, "end")
        self.entry.configure(state="disabled")
        self.send_btn.configure(state="disabled", text="工作中...")
        self.busy = True
        self._set_action_buttons(True)
        self.status_indicator.configure(text="Thinking", text_color="#FF9800")
        self._append_user_msg(text)

        # Reset tool statuses
        for t in self.tool_status:
            self._set_tool_status(t, "idle")

        t = threading.Thread(target=self._run_thread, args=(text,), daemon=True)
        t.start()

    def _run_thread(self, text: str):
        try:
            h = UIStreamHandler(self.ui_queue)
            self.agent.run_iteration(text, h)
        except Exception as e:
            self.ui_queue.put(("error", str(e)))
            self.ui_queue.put(("complete", None))

    def _open_settings(self):
        d = SettingsDialog(self, provider_name=self.provider_name, api_key=self.api_key,
                           model=self.model, base_url=self.base_url,
                           system_prompt=self.system_prompt)
        self.wait_window(d)
        if not d.result:
            return
        self.provider_name = d.result["provider"]
        self.api_key = d.result["api_key"]
        self.model = d.result["model"]
        self.base_url = d.result.get("base_url", "")
        self.system_prompt = d.result["system_prompt"]
        self._init_agent()
        self._save_config()
        parts = [f"Key: {self.api_key[:8]}..."] if self.api_key else []
        parts.append(f"{self.provider_name}/{self.model}")
        self.status_bar.configure(text="就绪 — " + " | ".join(parts))
        self.msg_label.configure(text=f"{len(self.agent.messages)//2 if self.agent else 0} 轮")

    def _clear_chat(self):
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        # Clear activity log
        self.activity_log.configure(state="normal")
        self.activity_log.delete("1.0", "end")
        self.activity_log.configure(state="disabled")
        if self.agent:
            self.agent.messages = []
        self.msg_label.configure(text="0 轮")
        for t in self.tool_status:
            self._set_tool_status(t, "idle")

    # ── New Feature Dialogs ──

    def _open_review(self):
        if not self.agent or not self.api_key:
            self._chat_line("请先配置 API Key", "err")
            return
        CodeReviewDialog(self, self.agent, None)

    def _open_research(self):
        if not self.agent or not self.api_key:
            self._chat_line("请先配置 API Key", "err")
            return
        ResearchDialog(self, self.agent, None)

    def _open_schedule(self):
        SchedulerDialog(self, get_scheduler())

    def _open_watch(self):
        WatcherDialog(self, get_watcher())


def run():
    AgentApp().mainloop()


if __name__ == "__main__":
    run()
