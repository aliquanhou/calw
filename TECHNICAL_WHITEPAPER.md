# Calw v2.1 Technical Whitepaper

> **取优补短** — Autonomous AI Engineering Agent for Windows

| Version | Date | Author |
|---------|------|--------|
| 2.1.0 | 2026-07-13 | aliquanhou & Claude Code |

---

## Table of Contents

1. [Abstract](#1-abstract)
2. [Architecture Overview](#2-architecture-overview)
3. [Core Modules](#3-core-modules)
4. [Modules Ported from v2.0](#4-modules-ported-from-v20)
5. [Innovation Engines](#5-innovation-engines)
6. [Transparent Interaction](#6-transparent-interaction)
7. [Tool System](#7-tool-system)
8. [Testing](#8-testing)
9. [Security](#9-security)
10. [Quick Start](#10-quick-start)
11. [Benchmarks](#11-benchmarks)
12. [Contribution Guide](#12-contribution-guide)

---

## 1. Abstract

**English:**

Calw v2.1 is a provider-agnostic autonomous AI engineering agent for Windows. This release represents a major architectural evolution — combining the clean explicit-initialization architecture of v2.1 with the best modules carried forward from v2.0 (retry, router, researcher, reviewer, project_map, mcpserver, plugin), creating a unified, production-ready agent framework.

Key innovations:
- **Speculative execution engine** — predicts next tool calls during LLM thinking time
- **Streaming progressive parser** — detects tool calls mid-stream before full JSON
- **MMAP file cache** — 166× faster file reads via memory-mapped I/O
- **Session state persistence** — thread-safe, JSONL-backed conversation storage
- **5 LLM providers** — Anthropic, OpenAI, DeepSeek, Gemini, Ollama
- **Type-safe dispatch** — auto type coercion for all LLM-provided parameters
- **Transparent interaction** — Claude Code-style tool output in CLI and GUI

**中文：**

Calw v2.1 是一个与 LLM 提供商无关的自主 AI 工程智能体，专为 Windows 系统设计。本版本代表了从 v2.0 以来的重大架构演进——将 v2.1 清晰的显式初始化架构与 v2.0 的最佳模块（重试、路由器、研究员、审查员、项目地图、MCP、插件）融合为一，打造统一的生产级智能体框架。

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   User Interface Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  CLI (main.py)│  │  GUI (app.py)│  │  Programmatic API  │  │
│  │  CliHandler   │  │UIStreamHandler│  │  Agent API         │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬──────────┘  │
└─────────┼──────────────────┼───────────────────┼──────────────┘
          │                  │                   │
┌─────────▼──────────────────▼───────────────────▼──────────────┐
│                    Agent Core Layer                             │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  Agent (core.py)                                        │  │
│  │  • Main loop with tool execution                        │  │
│  │  • Exponential backoff retry                            │  │
│  │  • Context-aware compression                            │  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  SessionState (session.py)                              │  │
│  │  • Thread-safe message persistence                      │  │
│  │  • JSONL-backed storage                                 │  │
│  │  • Error logging                                        │  │
│  └─────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────▼─────────────────────────────────────┐
│                    LLM Provider Layer                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────┐  │
│  │Anthropic │ │  OpenAI  │ │ DeepSeek │ │ Gemini │ │Ollama│  │
│  └──────────┘ └──────────┘ └──────────┘ └────────┘ └──────┘  │
└───────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────▼─────────────────────────────────────┐
│                    Tool Execution Layer                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │tools.py  │ │tools_core│ │tool_*.py  │ │ Type Coercion    │  │
│  │Registry  │ │Compat    │ │11 modules │ │ _coerce_params() │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘  │
└───────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────▼─────────────────────────────────────┐
│              Enhancement Engines                                │
│  ┌──────────────────┐ ┌───────────────────┐ ┌──────────────┐  │
│  │  Speculative     │ │  Streaming        │ │  MMAP File   │  │
│  │  Execution       │ │  Parser           │ │  Cache       │  │
│  │  (speculative.py)│ │  (streaming_      │ │  (file_cache │  │
│  │                  │ │   parser.py)      │ │   .py)       │  │
│  └──────────────────┘ └───────────────────┘ └──────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

### Architecture Principles

| Principle | v2.0 (Before) | v2.1 (After) |
|-----------|---------------|--------------|
| Module initialization | Implicit side effects on import | Explicit `init_tools()` call |
| State management | Global variables at module level | `SessionState` with `threading.Lock` |
| Tool registration | Automatic on module import | `register_tool()` explicit API |
| Parameter types | Assumed correct from LLM | Auto-coerced via annotations |
| Retry logic | Fixed 1s sleep | Exponential backoff + jitter |

---

## 3. Core Modules

### 3.1 Agent Main Loop (`core.py`)

```python
while tool_round < max_tool_rounds:
    # 1. Call LLM (streaming)
    response = self.provider.stream_complete(...)

    # 2. Extract & execute tool calls
    for tc in tool_calls:
        pre_result = self.speculative.consume(name, args)
        result = pre_result or execute_tool(name, args)

    # 3. Compress context if needed
    self._compact_context(messages)
```

### 3.2 Session State (`session.py`)

Thread-safe conversation persistence:
```
data/{user_id}/
├── messages.jsonl   # Conversation history (append + full save)
└── errors.jsonl     # Error log
```

### 3.3 LLM Providers (`providers.py`)

| Provider | Models | Key Feature |
|----------|--------|-------------|
| `AnthropicProvider` | claude-opus-4-7, sonnet-4-*, haiku-4-5 | Thinking blocks |
| `OpenAIProvider` | gpt-4o, gpt-4o-mini, deepseek-* | Streaming |
| `GeminiProvider` | gemini-2.0-flash, gemini-2.5-pro | Google AI |
| `Ollama fallback` | via OpenAI-compatible API | Local models |

### 3.4 Tool Registry (`tools.py`)

```python
# v2.0: Module-level side effects
import agent.tools  # side effects happen here!

# v2.1: Explicit initialization
init_tools()  # called once at Agent.__init__()
register_tool("name", handler, desc, params)
```

**Type Safety Layer** — automatic parameter coercion:
```python
# LLM sends strings → automatically converted
_coerce_params(handler, {"max_results": "10"})  # → {"max_results": 10}
_coerce_params(handler, {"recursive": "true"})  # → {"recursive": True}
```

### 3.5 Context Compression (`context.py`)

Four-stage progressive compression:

1. **Truncate** — smart truncation of tool results (preserves error tail)
2. **Compact** — reduce old message content to 300 chars
3. **Drop** — keep only recent turns that fit in 70% of budget
4. **Snapshot** — generate project state summary before dropping

Plus integrity sanitization: removes orphan tool results, validates pairing.

---

## 4. Modules Ported from v2.0

Six modules were adapted from v2.0 into the v2.1 architecture:

### 4.1 retry.py — Exponential Backoff Retry

Three APIs for different use cases:

```python
# Decorator form
@retryable(max_retries=3)
def call_api(): ...

# Functional form
result = with_retry(func, arg1, arg2)

# Generator form (for streaming APIs)
for chunk in retry_generator(lambda: client.stream(...)):
    yield chunk
```

Backoff formula: `min(1 × 2^attempt, 30s) × (1 ± 10% jitter)`

### 4.2 router.py — Smart Model Router

```python
task = classify_task("检查这段代码的安全性")  # → "code_review"
model = recommend_model("检查这段代码的安全性", available_models)
# → selects model closest to tier 3 (code_review capability)
```

Task tiers: `simple` (1), `code_gen` (2), `code_review` (3), `debug` (3), `plan` (4)

### 4.3 project_map.py — Project Structure Scanner

Auto-scans and injects into system prompt:
```
## 项目地图
项目: calw
Python: 28 文件 (320 KB)
JavaScript: 5 文件 (45 KB)
入口: main.py, app.py
```

### 4.4 researcher.py — Deep Research Engine

Pipeline: **Decompose → Search → Fetch → Synthesize**

```python
result = deep_research("量子计算最新进展", provider, progress=print)
# → ResearchResult with summary, key_findings, sources, contradictions
```

### 4.5 reviewer.py — Code Review Engine

```python
report = review_diff(diff_text, provider, effort="medium")
for f in report.findings:
    print(f"[{f.severity}] {f.title} at {f.file}:{f.line}")
```

Three effort levels: `low` (critical only), `medium` (critical+major+minor), `high` (all).

### 4.6 mcpserver.py — MCP Protocol Server

```python
mcp = get_mcp()
mcp.start_server("filesystem")  # Launches npx @modelcontextprotocol/server-filesystem
```

Built-in servers: filesystem, git.

### 4.7 plugin.py — Plugin System

Drop-in plugins in `agent/plugins/`:
```python
def register():
    return {
        "name": "my_tool",
        "description": "What it does",
        "input_schema": {"type": "object", "properties": {...}},
        "handler": my_handler,  # accepts **kwargs
    }
```

---

## 5. Innovation Engines

### 5.1 Speculative Execution (`speculative.py`)

Five prediction rules to anticipate the next tool call:

| Rule | Trigger | Prediction | Confidence |
|------|---------|------------|------------|
| read→edit | File read completes | edit/write to same file | 75% |
| build→test | Build succeeds | pytest/npm test | 85% |
| web→browser | HTML response received | browser navigate | 90% |
| write→verify | Python/JSON file written | py_compile/json.load check | 95% |
| consecutive fail | 3+ failures in last 6 calls | process monitor + resource check | 70% |

### 5.2 Streaming Progressive Parser (`streaming_parser.py`)

Detects key parameters in the LLM output stream **before** the complete JSON is generated:

```python
ESSENTIAL_PARAMS = {
    "read": {"file_path"},
    "write": {"file_path", "content"},
    "bash": {"command"},
    "web": {"url"},
    # ... 25+ tools
}
```

When all essential params are detected → background execution starts immediately.

### 5.3 MMAP File Cache (`file_cache.py`)

| Operation | Disk I/O | MMAP | Speedup |
|-----------|---------|------|---------|
| Read 50-line file | ~5ms | ~0.3ms | 16× |
| Read 1000+ line file | ~50ms | ~0.3ms | 166× |
| Line-level random access | Full load | Direct mmap seek | N/A |

---

## 6. Transparent Interaction

### 6.1 CLI Mode (Claude Code Style)

```
▶ 帮我查一下磁盘使用

  📋 计划执行 2 个步骤
  [1/2]💻 bash  Get-CimInstance Win32_LogicalDisk
    ✔ 15 行输出
      DeviceID 总(GB) 可用(GB) 使用率
      C:       55.4    10.4     81.2%
      D:       55.8    7.3      86.9%

  [2/2]💻 bash  Get-CimInstance Win32_OperatingSystem
    ✔ 运行时间: 12天 4小时 32分钟

────────────────────────────────────────
```

Color scheme:
- `📖 read` `✏️ write` `💻 bash` — orange tool name
- `file.py`, `command` — cyan path
- `✔ 15 行输出` — green success
- `── ❌ 错误 ──` — red with parameters

### 6.2 GUI Mode

Same transparency in the desktop application:
- Tool invocations show icon + name + target on one line
- `write` shows content preview (first 12 lines)
- `read` shows file content in code blocks
- `bash` shows last lines of output
- Errors show bright red with full tool parameters
- Step progress: `[1/3]` numbering when multi-step plans execute

---

## 7. Tool System

### 7.1 Complete Tool Inventory (36+)

| Category | Tools |
|----------|-------|
| **File Operations** | read, write, edit, replace, glob, grep, move, copy, delete, mkdir, download, revert |
| **Command Execution** | bash, background |
| **Browser & Web** | browser, web, web_search |
| **System Control** | process, service, registry, monitor, gui |
| **Code Analysis** | ast, dep_graph, call_chain, trace_error |
| **Planning** | plan, task, project_memory |
| **Memory** | remember |
| **Automation** | schedule, watch, websocket |
| **Testing & Deps** | test, dep |
| **Utility** | ask_user, hash_file |

### 7.2 Tool Handler Convention

```python
def _handle_read(file_path: str = "") -> str:
    """读取文件内容。"""
    ...
```

Auto-registered by `load_tools_from_module()`:
1. Scans module for `_handle_*` functions
2. Generates JSON Schema from Python type annotations
3. Registers with `register_tool()`

### 7.3 Action Aliases

LLMs often call actions differently than tool names:
```python
# tools_plan.py: update_step → update, show_plan → show, create_plan → create
action_aliases = {"update_step": "update", "show_plan": "show", ...}
```

---

## 8. Testing

**243 tests total — all passing.**

| Test Suite | Tests | Features Covered |
|-----------|-------|-----------------|
| `test_all.py` | 100+ | Registry, file ops, web, analysis, plan |
| `test_session.py` | 15+ | State persistence, messages, errors |
| `test_file_cache.py` | 10+ | MMAP read/write/diff |
| `test_streaming_parser.py` | 15+ | Token parsing, signals, early exec |
| `test_speculative.py` | 12+ | Rule matching, confidence, consume |
| `test_command.py` | 8+ | CLI entry, argument parsing |
| `test_providers.py` | 20+ | Message formatting, streaming |
| `test_file_ops.py` | 15+ | File operations edge cases |
| `test_memory_v2.py` | 8+ | Semantic memory CRUD |
| Others | 40+ | GUI, monitor, deps, extra |

Run tests: `pytest` or `python -m pytest tests/`

---

## 9. Security

### Configuration Security

```bash
# config.json is NEVER tracked by git
.gitignore: config.json
git rm --cached config.json  # remove from index

# Use template instead
cp config.json.example config.json
# Edit with your real API keys (never commit!)
```

### Search Protection

- Automatic detection of `node_modules/`, `bin/`, `obj/`, `.git/` paths
- Prevents slow searches over binary directories
- `grep` over `node_modules` shows warning

### System Prompt Safety

v2.1 replaced the v2.0's "你有完全、无限制的系统权限" ("you have unlimited system permissions") with:
```
## 安全规范
- 请遵循最小权限原则，只执行必要的修改
- 系统级操作（服务/注册表/进程）请谨慎使用
- API 密钥等敏感信息不要写入代码或日志
```

---

## 10. Quick Start

### Prerequisites

```bash
# Python 3.10+
python --version

# Install core dependencies
pip install -r requirements.txt

# Optional features
pip install chromadb>=0.4.0  # Semantic memory
pip install playwright>=1.40.0 && playwright install chromium  # Browser automation
```

### Configure

```bash
cp config.json.example config.json
# Edit config.json with your API keys:
# {
#   "provider": "DeepSeek",
#   "api_key": "sk-...",
#   "model": "deepseek-chat",
#   "base_url": "https://api.deepseek.com"
# }
```

### Launch

```bash
# CLI Mode (recommended — Claude Code style)
python main.py

# GUI Mode (desktop application)
python launch_gui.py

# Programmatic
python -c "
from agent import create_agent
agent = create_agent(config={'model': 'deepseek-chat', 'api_key': '...'})
agent.run_iteration('查看系统状态')
"
```

### Examples

Open `examples/dashboard.html` in your browser — a 3D holographic dashboard created by Calw itself, featuring:
- Three.js animated particle system
- Rotating rings with real-time clock
- Keyboard interaction (R/G/B/Space)
- FPS counter and system status display

---

## 11. Benchmarks

### Performance vs v2.0

| Scenario | v2.0 | v2.1 | Improvement |
|----------|------|------|-------------|
| Large file read (1000+ lines) | ~50ms | ~0.3ms | **166×** |
| Tool call start | Wait for full JSON | Execute on key params | **30-50% earlier** |
| Sequential ops (read→edit) | Manual trigger | Predictive pre-load | **Near-zero latency** |
| Test count | 156 | 243 | **+56%** |
| LLM Providers | 2 | 5 | **+150%** |

### Code Quality Metrics

| Metric | v2.0 | v2.1 |
|--------|------|------|
| Total lines | ~7,800 | ~9,500 |
| Agent modules | 23 | 28 |
| Tools | 36 | 36+ |
| Tests | 156 | 243 |
| Module-level side effects | Yes (implicit) | No (explicit) |

---

## 12. Contribution Guide

### Code Structure

```
calw/
├── agent/
│   ├── core.py              # Agent main loop
│   ├── session.py           # Session state
│   ├── providers.py         # LLM abstractions
│   ├── tools.py             # Registry + dispatch
│   ├── tools_core.py        # Backward compat layer
│   ├── tools_file.py        # File operations
│   ├── tools_shell.py       # Command execution
│   ├── tools_web.py         # HTTP + search
│   ├── tools_browser.py     # Playwright browser
│   ├── tools_system.py      # Service/registry/process/GUI
│   ├── tools_analysis.py    # AST/dep graph/call chain
│   ├── tools_plan.py        # Plans + background tasks
│   ├── tools_memory.py      # Semantic memory
│   ├── tools_extra.py       # Schedule/watch/websocket
│   ├── tools_test.py        # Test runner
│   ├── tools_deps.py        # Dependency auto-install
│   ├── speculative.py       # Speculative execution ★
│   ├── streaming_parser.py  # Streaming parser ★
│   ├── file_cache.py        # MMAP cache ★
│   ├── context.py           # 4-stage compression
│   ├── retry.py             # Exponential backoff
│   ├── router.py            # Smart model routing
│   ├── project_map.py       # Project scanner
│   ├── researcher.py        # Deep research
│   ├── reviewer.py          # Code review
│   ├── mcpserver.py         # MCP protocol
│   ├── plugin.py            # Plugin system
│   ├── prompt.py            # System prompt builder
│   └── plugins/             # User plugins
├── tests/                   # 243 tests
├── examples/                # Example outputs
├── main.py                  # CLI entry
├── launch_gui.py            # GUI entry
└── config.json.example      # Config template
```

### Add a New Tool

```python
# 1. Create handler function in appropriate tools_*.py
def _handle_my_tool(param1: str = "", param2: int = 0) -> str:
    """Description. Args and return documented."""
    ...

# 2. Auto-discovered by load_tools_from_module() via _handle_ prefix
# Or register explicitly:
register_tool("my_tool", _handle_my_tool, "Description", parameters_schema)

# 3. Write tests
# 4. Run: pytest
```

### Add a New Provider

```python
class MyProvider(LLMProvider):
    """Custom provider implementation."""

    def complete(self, system, messages, tools=None, ...):
        """Return {"content": str, "tool_calls": list}"""
        ...

    def stream_complete(self, system, messages, tools=None, ...):
        """Streaming with callbacks."""
        ...

# Add factory mapping in create_llm_provider()
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

*Built with ❤️ by aliquanhou — Architecture guidance from Claude Code (Anthropic)*
