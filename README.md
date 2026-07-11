
<p align="center">
  <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/Tests-266%20passed-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/Tools-31-orange" alt="Tools">
  <img src="https://img.shields.io/badge/Release-v2.0-brightgreen" alt="Version">
</p>

<h1 align="center">Calw — Autonomous AI Agent for Software Engineering</h1>
<p align="center"><b>v2.0</b> · 31 tools · 266 tests · Full system control · Semantic memory</p>

---

> **Calw** is a provider-agnostic autonomous AI agent for programming. It supports **DeepSeek / Anthropic / OpenAI** models, executes tools in parallel, and can fully control a Windows system — from file editing to service management, registry operations, GUI automation, and semantic memory with vector search.

> **Calw** 是一个与 LLM 提供商无关的自主 AI 编程智能体。支持 DeepSeek / Anthropic / OpenAI 模型，并行执行工具，可完全接管 Windows 系统——从文件编辑到服务管理、注册表操作、GUI 自动化、以及基于向量搜索的语义记忆。

---

## 📦 Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10+ |
| GUI | customtkinter (desktop) / CLI (terminal) |
| LLM | Anthropic Claude · DeepSeek · OpenAI |
| Vector DB | ChromaDB |
| Browser | Playwright |
| GUI Automation | pyautogui |
| Testing | pytest (266 tests) |

---

## 🏗️ Architecture

```
calw-v2.0/
├── agent/                          # Core engine
│   ├── core.py                     # Main loop: streaming + parallel tool dispatch
│   ├── providers.py                # LLM abstraction (Anthropic/DeepSeek/OpenAI)
│   ├── context.py                  # 4-level context compression
│   ├── prompt.py                   # System prompt
│   ├── retry.py                    # Exponential backoff + jitter
│   │
│   ├── tools.py                    # Facade (68 lines) → dispatches to all modules
│   ├── tools_core.py               # Tool definitions + shared state
│   ├── tools_file.py               # read/write/edit/replace/glob/grep/revert/move/copy/delete/mkdir/download
│   ├── tools_shell.py              # bash
│   ├── tools_web.py                # web/web_search/ask_user
│   ├── tools_browser.py            # browser (Playwright)
│   ├── tools_plan.py               # plan/task/background/project_memory
│   ├── tools_analysis.py           # ast/dep_graph/call_chain/trace_error
│   ├── tools_system.py             # process/service/registry/gui/monitor
│   ├── tools_test.py               # test driver
│   ├── tools_deps.py               # dependency auto-fix
│   ├── tools_extra.py              # schedule/watch/websocket
│   ├── tools_memory.py             # remember (semantic memory tool)
│   │
│   ├── memory.py                   # Legacy JSON memory
│   ├── memory_v2.py                # V2 vector memory (ChromaDB)
│   ├── project_map.py              # Auto project scanner
│   ├── scheduler.py                # Cron scheduler
│   ├── watcher.py                  # File/process watcher
│   ├── reviewer.py                 # Code review engine
│   ├── researcher.py               # Deep research engine
│   ├── router.py                   # Smart model router
│   ├── plugin.py                   # Plugin system
│   ├── app.py                      # GUI (customtkinter)
│   └── __main__.py                 # Entry point
│
├── tests/                          # 266 tests across 15 files
├── main.py                         # Quick launcher
├── requirements.txt                # Dependencies
└── README.md
```

### Agent Loop

```
User Input → LLM Stream → Tool Calls → Parallel Execute → Results → Loop
                                      ↑                          |
                                      └── Continue if tool_use ──┘
```

### Tool System (31 tools)

| Category | Tools | Count |
|----------|-------|-------|
| **File** | `read, write, edit, replace, glob, grep, revert, move, copy, delete, mkdir, download` | **12** |
| **System** | `process, service, registry, monitor` | **4** |
| **Network** | `web, web_search, websocket, browser, gui` | **5** |
| **AI** | `test, dep, plan, task, project_memory, remember` | **6** |
| **Analysis** | `ast, dep_graph, call_chain, trace_error` | **4** |
| **Utility** | `bash, background, schedule, watch, ask_user` | **5** |
| | **Total** | **31** |

---

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/aliquanhou/calw.git
cd calw
git checkout calw-v2.0

# 2. Install
pip install -r requirements.txt

# 3. Optional extras
pip install chromadb pyautogui websocket-client watchdog

# 4. Set API key (pick one)
# PowerShell:
$env:DEEPSEEK_API_KEY = "sk-your-key"
# OR:
$env:ANTHROPIC_API_KEY = "sk-ant-your-key"

# 5. Run
python main.py              # GUI mode (recommended)
python -m agent --cli       # CLI mode
python -m agent --cli "帮我看看项目结构"  # Single command
```

### requirements.txt

```
customtkinter
anthropic
openai
playwright
requests
```

---

## 🎮 Usage

### GUI

```bash
python main.py
```

Opens a desktop window with:
- Chat panel (streaming responses)
- Tool execution panel (real-time progress)
- API key / model selector

### CLI REPL

```bash
python -m agent --cli
```

Commands: `/exit`, `/clear`, `/help`, `/tokens`

### CLI Single Shot

```bash
python -m agent --cli "分析项目结构"
python -m agent --cli "安装缺失依赖"
python -m agent --cli "查看CPU使用率"
```

---

## 🧪 Testing

```bash
# Full suite
python -m pytest tests/ -v

# Specific modules
python -m pytest tests/test_replace.py -v
python -m pytest tests/test_memory_v2.py -v
python -m pytest tests/test_tools_system.py -v
```

| File | Tests | What it covers |
|------|-------|----------------|
| test_all.py | 71 | Core dispatch, tools, write/edit, glob, AST, bash, memory, BuildRunner |
| test_replace.py | 21 | SEARCH/REPLACE 4 strategies |
| test_project_map.py | 16 | Project scanner |
| test_tools_test.py | 11 | Test driver |
| test_tools_deps.py | 17 | Dependency fixer |
| test_tools_system.py | 23 | Service/registry/process |
| test_file_ops.py | 17 | Move/copy/delete/mkdir |
| test_gui.py | 8 | GUI automation |
| test_monitor.py | 10 | Resource monitor |
| test_tools_extra.py | 14 | Schedule/watch/websocket |
| test_memory_v2.py | 6 | Semantic memory |
| test_router.py | 16 | Model routing |
| test_providers.py | 8 | LLM providers |
| test_ask_user.py | 8 | Smart ask_user |
| **Total** | **266** | |

---

## 🔧 Tool Reference

### File Operations

| Tool | Parameters | Description |
|------|-----------|-------------|
| `read` | file_path | Read file with smart truncation |
| `write` | file_path, content | Write; auto diff; syntax validation; auto rollback |
| `edit` | file_path, old_string, new_string | Edit exact string; diff output; auto rollback |
| `replace` | file_path, search, replace_text | **4-strategy**: exact → anchor → fuzzy → line-ref |
| `glob` | pattern, path | Recursive file search |
| `grep` | pattern, path, glob, output_mode | Content search (regex) |
| `revert` | file_path | Restore from backup |
| `move` | source, destination | Move/rename |
| `copy` | source, destination, recursive | Copy file/directory |
| `delete` | path, recursive | Delete file/directory |
| `mkdir` | path, parents | Create directory |
| `download` | url, destination | Download from URL |

### System Control

| Tool | Parameters | Description |
|------|-----------|-------------|
| `process` | action, name, pid, sort_by | list, top, tree, wait_exit, launch, kill |
| `service` | action, name, start_type | list, search, status, start, stop, restart, set_startup |
| `registry` | action, key, name, value | read, write, delete, list_keys |
| `monitor` | action | resources, cpu, memory, disk, network, uptime, process_count |

### GUI Automation

| Tool | actions |
|------|---------|
| `gui` | info, click, double_click, right_click, move, drag, type, keypress, scroll, screenshot, locate, get_window |

### Network

| Tool | Description |
|------|-------------|
| `web` | HTTP GET/POST |
| `web_search` | DuckDuckGo search |
| `websocket` | WebSocket client: connect, send, ping |
| `browser` | Playwright browser control |

### AI Enhancement

| Tool | Description |
|------|-------------|
| `test` | Discover & run tests, parse failures |
| `dep` | Auto-install missing packages |
| `plan` | Persistent plan with dependency chain |
| `task` | Task status tracker |
| `project_memory` | Read/write CLAUDE.md |
| `remember` | **Semantic memory**: search, store, stats, context |

### Utilities

| Tool | Description |
|------|-------------|
| `ask_user` | Smart question with analysis + options + recommendation |
| `schedule` | Cron scheduler: list, add, remove, events |
| `watch` | File/process watcher: list, add, remove, events |
| `background` | Background process runner |

---

## 🧠 Semantic Memory (V2)

Powered by ChromaDB vector database.

### How it works

```
Tool results → Vector embedding → ChromaDB
Agent start → Load relevant memories → System prompt
User query "remember search" → Semantic similarity → Ranked results
```

### Commands

```
remember store content="修复了import报错" mem_type="error"
remember search query="import错误"
remember stats
remember context
```

### Memory Types

`note`, `tool_result`, `file_change`, `error`, `user_decision`, `task_complete`

---

## 🔌 Development Guide

### Adding a new tool

```python
# 1. Create handler
# agent/tools_myfeature.py
def _handle_myfeature(action="hello"):
    return f"Hello {action}!"

# 2. Register in agent/tools.py
from .tools_myfeature import _handle_myfeature
# Add to BUILTIN_HANDLERS: "myfeature": _handle_myfeature

# 3. Define schema in agent/tools_core.py
{"name":"myfeature", "description":"...", "input_schema":{...}}

# 4. Add icon + verb in agent/core.py
_TOOL_ICONS["myfeature"] = "🛠️"
_TOOL_VERBS["myfeature"] = "我的功能"

# 5. Write tests
```

### Code Style

- PEP 8, type annotations (`from __future__ import annotations`)
- Error messages in Chinese (project convention)
- One domain per file, facade via `tools.py`
- Plugins in `agent/plugins/`

### Architecture Principles

| Principle | Detail |
|-----------|--------|
| Provider-agnostic | `LLMProvider` ABC for all models |
| Tool isolation | One file per domain, facade pattern |
| Fail-safe | File backups + auto-rollback on syntax error |
| Self-healing | Kill zombies, retry transient errors |
| Context-aware | 4-level compression + project snapshot |
| Dual memory | JSON file memory + ChromaDB vector memory |

---

## 📊 Version History

```
v2.0 (2026-07-11)  ← CURRENT
  - Semantic memory (ChromaDB)
  - Code cleanup: -600 lines, removed 4 redundant modules
  - 31 tools, 266 tests

v1.1.0 (2026-06-16)
  - Tool splitting: monolith → facade + 7 sub-modules
  - Parallel execution, SEARCH/REPLACE, token tracking
  - Multi-model routing, non-interactive mode

v1.0.0 (2026-06-07)
  - Initial release
```

---

## 🤝 Contributing

```bash
git clone https://github.com/aliquanhou/calw.git
git checkout calw-v2.0
# Make changes
python -m pytest tests/ -v  # Ensure all pass
git push origin calw-v2.0
```

- PRs welcome
- Apache 2.0 license
- All tests must pass before merge

---

<p align="center">
  <b>Calw v2.0</b> — Built for developers, by an AI agent 🤖
  <br>
  <a href="https://github.com/aliquanhou/calw">GitHub</a> ·
  <a href="https://github.com/aliquanhou/calw/tree/calw-v2.0">calw-v2.0</a>
</p>
