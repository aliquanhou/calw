
<p align="center">
  <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/Tests-243%20passed-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/Tools-36%2B-orange" alt="Tools">
  <img src="https://img.shields.io/badge/Release-v2.1-brightgreen" alt="Version">
  <img src="https://img.shields.io/badge/LLM-5%20providers-purple" alt="Providers">
</p>

<h1 align="center">Calw v2.1 — Autonomous AI Engineering Agent</h1>
<p align="center"><b>取优补短</b> · 36+ tools · 243 tests · 5 LLM providers · Speculative execution · MMAP cache</p>

<p align="center">
  <a href="#10-quick-start">Quick Start</a> ·
  <a href="TECHNICAL_WHITEPAPER.md">Whitepaper</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="examples/dashboard.html">Demo</a>
</p>

---

> **English:** Calw v2.1 is a provider-agnostic autonomous AI agent for software engineering on Windows. It supports **5 LLM providers** (Anthropic, OpenAI, DeepSeek, Gemini, Ollama), executes 36+ tools for full system control, and features a **speculative execution engine** + **MMAP file cache** for near-zero latency. Built by combining the best of v2.0 and v2.1 architectures.
>
> **中文:** Calw v2.1 是一个与 LLM 提供商无关的自主 AI 工程智能体，专为 Windows 系统设计。支持 5 家 LLM 提供商（Anthropic、OpenAI、DeepSeek、Gemini、Ollama），执行 36+ 工具实现全系统控制，具备推测性执行引擎和 MMAP 文件缓存实现近零延迟。取 v2.0 之长补 v2.1 之短。

---

## Key Features / 核心亮点

| Feature | Description |
|---------|-------------|
| 🚀 **Speculative Execution** | Predicts next tool calls during LLM thinking, pre-executes for zero latency |
| ⚡ **MMAP File Cache** | 166× faster file reads via memory-mapped I/O |
| 🔄 **Streaming Parser** | Detects tool calls mid-stream before full JSON is generated |
| 🖥️ **Claude Code UI** | Transparent tool output in both CLI and GUI |
| 🔧 **5 LLM Providers** | Anthropic · OpenAI · DeepSeek · Gemini · Ollama |
| 🛡️ **Type Safety** | Auto type coercion for all LLM-provided parameters |
| 🧠 **Semantic Memory** | ChromaDB vector search for persistent context |
| 📦 **36+ Tools** | File, system, browser, web, analysis, planning, automation |
| 🔄 **Exponential Backoff** | Intelligent retry with jitter for API resilience |
| 🧪 **243 Tests** | Comprehensive test suite across all modules |

---

## Demo / 示例

A 3D holographic dashboard **created by Calw itself** — open `examples/dashboard.html` in your browser:

- Three.js animated particle system with rotating rings
- Real-time clock with running uptime counter
- Keyboard interaction: `R` auto-rotate, `G` color schemes, `B` particle burst, `Space` reset
- FPS counter and system status display

---

## Architecture / 架构

```
calw-v2.1/
├── agent/                      # Core agent package
│   ├── core.py                 # Agent main loop (streaming + tool execution)
│   ├── session.py              # Thread-safe session state (JSONL persistence)
│   ├── providers.py            # LLM abstraction (5 providers)
│   ├── tools.py                # Tool registry + type-safe dispatch
│   ├── tools_core.py           # Backward compat layer (v2.0 APIs)
│   │
│   ├── tools_file.py           # read/write/edit/replace/glob/grep/move/copy/delete/mkdir/download
│   ├── tools_shell.py          # bash + BuildRunner + auto-encoding
│   ├── tools_web.py            # web/web_search/ask_user
│   ├── tools_browser.py        # Playwright browser automation
│   ├── tools_plan.py           # plan/task/background/project_memory
│   ├── tools_analysis.py       # ast/dep_graph/call_chain/trace_error
│   ├── tools_system.py         # process/service/registry/gui/monitor
│   ├── tools_memory.py         # Semantic memory tool
│   ├── tools_test.py           # Test runner
│   ├── tools_deps.py           # Auto install missing deps
│   ├── tools_extra.py          # schedule/watch/websocket
│   │
│   ├── speculative.py          # ★ Speculative execution engine
│   ├── streaming_parser.py     # ★ Streaming progressive parser
│   ├── file_cache.py           # ★ MMAP file cache
│   ├── context.py              # 4-stage context compression
│   ├── retry.py                # ★ Exponential backoff (ported from v2.0)
│   ├── router.py               # ★ Smart model router (ported from v2.0)
│   ├── project_map.py          # ★ Project structure scanner (ported from v2.0)
│   ├── researcher.py           # ★ Deep research engine (ported from v2.0)
│   ├── reviewer.py             # ★ Code review engine (ported from v2.0)
│   ├── mcpserver.py            # ★ MCP protocol (ported from v2.0)
│   ├── plugin.py               # ★ Plugin system (ported from v2.0)
│   ├── prompt.py               # System prompt builder
│   └── app.py                  # GUI (customtkinter)
│
├── tests/                      # 243 tests across 16 files
├── examples/                   # Example outputs (dashboard.html)
├── main.py                     # CLI entry (Claude Code style)
├── launch_gui.py               # GUI entry
├── TECHNICAL_WHITEPAPER.md     # Full technical documentation
├── config.json.example         # Configuration template
└── requirements.txt            # Dependencies
```

---

## Quick Start / 快速开始

### Prerequisites

```bash
# Python 3.10+
python --version

# Install core dependencies
pip install -r requirements.txt

# Optional: Semantic memory
pip install chromadb>=0.4.0

# Optional: Browser automation
pip install playwright>=1.40.0
playwright install chromium
```

### Configure

```bash
cp config.json.example config.json
```

Edit `config.json` with your API key:

```json
{
  "provider": "DeepSeek",
  "api_key": "sk-your-key-here",
  "model": "deepseek-chat",
  "base_url": "https://api.deepseek.com"
}
```

Environment variables also supported:
```bash
# PowerShell
$env:CALW_MODEL = "anthropic/claude-sonnet-4-20250514"
$env:ANTHROPIC_API_KEY = "sk-ant-your-key"
```

### Run

```bash
# CLI Mode (Claude Code-style transparent output) — recommended
python main.py

# GUI Mode (desktop application)
python launch_gui.py

# Single command (programmatic)
python -c "
from agent import create_agent
agent = create_agent(config={'model': 'deepseek-chat', 'api_key': '...'})
agent.run_iteration('查看系统CPU和内存使用')
"
```

### CLI Demo Output

```
▶ 帮我查看系统状态

  📋 计划执行 2 个步骤
  [1/2]💻 bash  Get-CimInstance Win32_Processor
    ✔ CPU: Intel Core i7, 4 cores, 15% usage
      Name                    Cores  Speed   Load%
      Intel Core i7-12700H   14      2.3GHz  15%

  [2/2]💻 bash  Get-CimInstance Win32_OperatingSystem
    ✔ 内存: 16.0GB (8.2GB 已用, 使用率 51%)
      运行时间: 12天 4小时

────────────────────────────────────────
```

---

## CLI vs GUI / 两种使用方式

| Feature | CLI (`main.py`) | GUI (`launch_gui.py`) |
|---------|-----------------|----------------------|
| Interface | Terminal with ANSI colors | Desktop window (customtkinter) |
| Tool transparency | Claude Code style | Same, plus code blocks |
| Real-time streaming | ✅ | ✅ |
| Keyboard shortcuts | N/A | Ctrl+Enter stop, Ctrl+R retry, Ctrl+I context |
| Tool status panel | N/A | Right-side panel with status dots |
| Settings dialog | ENV vars + config.json | GUI dialog |
| Dashboard | N/A | Mission Control header + progress bar |

---

## Tools / 工具列表

| Category | Tools | Description |
|----------|-------|-------------|
| 📁 **File** | read, write, edit, replace, glob, grep, move, copy, delete, mkdir, download, revert | Full filesystem operations |
| 💻 **Shell** | bash, background | Command execution + long-running tasks |
| 🌐 **Web** | web, web_search, browser | HTTP requests, search, Playwright browser |
| 🖥️ **System** | process, service, registry, monitor, gui | Windows system control & automation |
| 🔬 **Analysis** | ast, dep_graph, call_chain, trace_error | Static code analysis |
| 📋 **Planning** | plan, task, project_memory | Structured execution plans (persistent) |
| 🧠 **Memory** | remember | Semantic memory (ChromaDB vector search) |
| ⚙️ **Automation** | schedule, watch, websocket | Cron tasks, file watcher, WebSocket client |
| 🧪 **Testing** | test, dep | Test runner + auto dependency install |
| 💬 **Utility** | ask_user, hash_file | Smart user interaction + file hashing |

---

## Testing / 测试

```bash
# Run full suite
pytest

# Run with coverage-style output
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_session.py -v
python -m pytest tests/test_all.py -v
```

**243 tests across 16 files** — covering tool dispatch, file operations, web searches, code analysis, session persistence, MMAP cache, streaming parser, speculative execution, CLI commands, and GUI components.

---

## v2.0 vs v2.1 Comparison / 版本对比

| Aspect | v2.0 | v2.1 |
|--------|------|------|
| Lines of code | ~7,800 | ~9,500 |
| Agent modules | 23 | 28 |
| Tests | 156 | 243 |
| LLM Providers | 2 (Anthropic, OpenAI) | 5 (+DeepSeek, Gemini, Ollama) |
| Module init | Implicit side effects | Explicit `init_tools()` |
| State | Global variables | SessionState (JSONL persistence) |
| Tool dispatch | v2.0 `handle_tool_call` | Both v2.0 compat + v2.1 registry |
| File cache | None | MMAP (166× speedup) |
| Speculative exec | None | Rule engine (5 patterns) |
| Streaming parser | None | Key-param early execution |
| Retry logic | Fixed 1s sleep | Exponential backoff + jitter |
| Type safety | No | Auto coercion via `_coerce_params()` |
| UI | Basic | Claude Code-style transparent output |

---

## Learn More / 了解更多

- **[Technical Whitepaper](TECHNICAL_WHITEPAPER.md)** — Full architecture documentation, benchmark data, contribution guide
- **[Changelog](CHANGELOG.md)** — Version history and release notes
- **[Examples](examples/dashboard.html)** — 3D dashboard created by Calw (open in browser)

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

*Built with ❤️ by aliquanhou — Architecture guidance from Claude Code (Anthropic)*
