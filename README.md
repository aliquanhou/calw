# Calw — 自主 AI 智能体

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![CI](https://github.com/aliquanhou/calw/actions/workflows/ci.yml/badge.svg)](https://github.com/aliquanhou/calw/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-156%20passed-brightgreen)](#)

> Calw — 面向编程场景的自主 AI Agent。支持多 LLM（DeepSeek/Anthropic/OpenAI），并行工具执行、智能路由、成本追踪。

---

## 快速开始

```bash
git clone https://github.com/aliquanhou/calw.git && cd calw
pip install -r requirements.txt
export DEEPSEEK_API_KEY=sk-your-key
python main.py                    # GUI
python -m agent --cli             # CLI
```

---

## 功能

| 类别 | 能力 |
|------|------|
| ⚡ 核心引擎 | 多LLM、流式、并行工具、自动重试、失败反思、Git自动快照 |
| 📂 文件 | read/write/edit/replace(模糊)/glob/grep/revert |
| ⚡ 命令 | bash(带重试)、background |
| 🖥 系统 | system_info、process |
| 🌐 网络 | web、web_search、screencap、ask_user |
| 🌍 浏览器 | Playwright持久实例+诊断 |
| 🔬 分析 | AST/依赖图/调用链/错误追踪 |
| 🧠 增强 | 模型路由、文件索引、MCP、代码补全、非交互CI模式 |

---

## 技术骨架

```
agent/
├── core.py            # 循环引擎（并行工具执行）
├── providers.py       # LLM抽象（Anthropic/DeepSeek/OpenAI）+ 成本追踪
├── context.py         # 4级渐进压缩 + 状态快照
├── tools.py           # 48行门面
├── tools_core.py      # 共享状态/工具定义/守卫
├── tools_file.py      # read/write/edit/replace/glob/grep
├── tools_shell.py     # bash/process/system_info
├── tools_web.py       # HTTP/search/screenshot
├── tools_browser.py   # Playwright控制
├── tools_plan.py      # 后台任务/plan/memory
├── tools_analysis.py  # AST/调用链/错误追踪
├── router.py          # 模型路由
├── indexer.py         # TF-IDF搜索
├── mcpserver.py       # MCP协议
├── completions.py     # 代码补全
├── reviewer.py        # 代码审查
├── researcher.py      # 深度研究
├── scheduler.py       # 定时任务
├── watcher.py         # 文件监控
├── retry.py           # 重试机制
├── memory.py          # 跨会话记忆
├── plugin.py          # 插件加载
└── plugins/hash_file.py
```

---

## CLI / CI模式

```bash
python -m agent --cli "列出文件"          # 单次
python -m agent --run "修复bug" --json   # 非交互+JSON输出
python -m agent --run "重构" --router    # 智能路由选模型
```

---

## 测试

```bash
python -m pytest tests/ -v                     # 156个全量
python -m pytest tests/test_router.py -v       # 按模块
```

---

## 版本历史

- **v1.1.0** (2026-06-16) — 工具拆分、并行执行、SEARCH/REPLACE、成本追踪、模型路由、文件索引、MCP、CI模式
- **v1.0.0** (2026-06-07) — 首次发布

---

[Apache License 2.0](LICENSE) © 2026 aliquanhou
