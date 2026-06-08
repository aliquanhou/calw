# Calw — 自主 AI 智能体

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#)

> **Calw** 是一个支持多 LLM 提供商的自主 AI 智能体框架，具备系统操控、文件管理、代码分析、进程管理等核心能力。  
> 脱胎于 claw，经过全面修复和重构，提供更稳定可靠的多轮自主执行体验。

---

## 技术骨架

```
calw/
├── main.py                  # 入口文件
├── requirements.txt         # Python 依赖
├── build.bat                # Windows 打包脚本
├── tests/                   # 110 个单元测试
│   ├── test_all.py          # 核心功能测试（89 个）
│   ├── test_file_ops.py     # 文件操作测试
│   └── test_math_utils.py   # 数学工具测试
└── agent/                   # 核心代码
    ├── __main__.py          # CLI 入口
    ├── app.py               # GUI 界面（基于 customtkinter）
    ├── core.py              # 核心循环引擎
    ├── context.py           # 上下文管理 & 压缩
    ├── providers.py         # LLM 提供商抽象
    ├── tools.py             # 工具注册 & 执行（~110KB）
    ├── retry.py             # 指数退避重试
    ├── prompt.py            # 系统提示词
    ├── memory.py            # 跨会话记忆
    ├── plugin.py            # 插件加载器
    ├── utils/               # 工具函数
    │   ├── file_ops.py      # 文件系统操作
    │   └── math_utils.py    # 数学工具
    ├── plugins/             # 官方插件
    │   └── hash_file.py     # 文件哈希插件
    └── build_patterns/      # 构建模式库
```

### 核心架构

```
用户输入
    │
    ▼
┌─────────────┐     ┌──────────────┐
│  core.py    │────▶│  providers   │────▶ LLM API
│  循环引擎    │     │  (OpenAI /   │      (流式)
│             │◀────│   Anthropic) │◀───
└─────────────┘     └──────────────┘
    │
    ▼
┌─────────────┐     ┌──────────────┐
│  tools.py   │────▶│  系统工具     │
│  工具调度    │     │  bash/文件/  │
│             │     │  网络/分析    │
└─────────────┘     └──────────────┘
    │
    ▼
┌─────────────┐
│  context.py │    自动压缩 & 清理
│  上下文管理   │    tool_call 配对
└─────────────┘
```

### 版本说明

当前版本基于 claw 完整重构，修复了以下核心问题：

| 修复项 | 说明 |
|--------|------|
| 🛠️ Edit 工具写入可靠性 | 读回校验 + 路径规范化 + 自动重试 |
| 🔄 多轮自主执行 | 改为 `continue`(有工具调用) / `break`(纯文本回复) 逻辑 |
| 🆔 tool_call_id 重复 | 从消息内容扫描 ID，不依赖内存集合 |
| 📦 tool_results 重复追加 | 移出 for-tch 循环，仅追加一次 |
| 🔐 sanitize 双集合验证 | 区分 `requested_ids` vs `received_ids` 防自验证 |
| ✅ 测试覆盖 | 110 个测试全部通过 |

---

## 快速开始

### 1. 克隆

```bash
git clone https://github.com/aliquanhou/calw.git
cd calw
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

依赖清单见 [requirements.txt](requirements.txt)，主要包括：`anthropic`, `openai`, `customtkinter`, `pytest` 等。

### 3. 配置 API Key

**方式 A — 环境变量（推荐）**

```bash
# Windows PowerShell
$env:DEEPSEEK_API_KEY = "sk-your-key"

# 或使用 Anthropic
$env:ANTHROPIC_API_KEY = "sk-ant-your-key"

# Linux / macOS
export DEEPSEEK_API_KEY="sk-your-key"
```

**方式 B — GUI 设置**  
启动后在界面右上角点击 ⚙ 设置，填入 API Key 和模型参数。

**方式 C — config.json**  
程序自动在项目根目录生成 `config.json`，也可手动编辑。

### 4. 启动

```bash
# GUI 模式（Windows 推荐）
python main.py

# CLI 模式
python -m agent --cli
```

---

## 使用场景

### 📂 文件系统操作
```
读取/写入/编辑文件 · 递归搜索路径 · 内容搜索(grep)
```

### ⚡ 系统命令执行
```
运行任意命令 · 安装软件包 · 编译构建
```

### 🖥️ 系统控制
```
系统信息采集 · 进程管理 · 注册表操作 · 环境变量
```

### 🌐 网络 & 外部
```
HTTP 请求 · 网页内容提取 · 屏幕截图
```

### 🔬 代码分析
```
AST 结构分析 · 依赖图 · 调用链追踪 · 代码审查
```

### 📋 任务规划
```
创建结构化计划 · 多步骤自动推进 · 状态跟踪
```

---

## 开发者指南

### 运行测试

```bash
# 全量测试（110 个）
python -m pytest tests/ -v --tb=short

# 按模块测试
python -m pytest tests/test_all.py -v
python -m pytest tests/test_file_ops.py -v
python -m pytest tests/test_math_utils.py -v

# 单个测试
python -m pytest tests/test_all.py::TestSanitizeMessages::test_drops_orphan_tool_result -v
```

### 添加新工具

在 `agent/tools.py` 中添加 `_handle_xxx` 函数，然后在 `TOOL_DEFINITIONS` 注册：

```python
TOOL_DEFINITIONS = [
    {
        "name": "my_tool",
        "description": "我的自定义工具",
        "input_schema": {"type": "object", ...},
    },
    # ... 已有工具
]

TOOL_HANDLERS = {
    "my_tool": _handle_my_tool,
}
```

### 添加新 Provider

在 `agent/providers.py` 中继承 `LLMProvider`，实现 `stream_chat` 和 `messages_to_provider`：

```python
class MyProvider(LLMProvider):
    name = "MyProvider"
    default_model = "my-model"

    def stream_chat(self, system_prompt, messages, tools):
        ...

    def messages_to_provider(self, messages, system_prompt):
        ...
```

### 添加插件

在 `agent/plugins/` 下创建 `.py` 文件，系统自动加载：

```python
# agent/plugins/my_plugin.py
from agent.plugin import ToolPlugin

class MyPlugin(ToolPlugin):
    name = "my_plugin"

    def execute(self, **kwargs) -> str:
        ...
```

---

## 配置参考

### 模型支持

| Provider | 默认模型 | 可用模型 |
|----------|---------|---------|
| DeepSeek | `deepseek-chat` | `deepseek-chat`, `deepseek-reasoner` |
| Anthropic Claude | `claude-opus-4-7` | `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5` |
| OpenAI | `gpt-4o` | `gpt-4o`, `gpt-4o-mini` |

### 环境变量

| 变量名 | 说明 | 必填 |
|--------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | 否 |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | 否 |
| `OPENAI_API_KEY` | OpenAI API 密钥 | 否 |
| `LLM_MODEL` | 模型名（默认 `deepseek-chat`） | 否 |

---

## 开源协议

[Apache License 2.0](LICENSE) © 2026 aliquanhou

---

## 项目背景

Calw 是一个专注于**自主执行能力**的 AI 智能体项目。  
与纯粹的代码补全工具不同，Calw 能主动操控系统、执行命令、管理进程，形成**规划 → 执行 → 反馈 → 调整**的完整闭环。
