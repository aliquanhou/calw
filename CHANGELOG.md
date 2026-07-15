# Changelog

## 2.2.0 (2026-07-15) — 透明自主编程

### 透明输出层（全新模块）
- **transcript.py**: 结构化事件总线 — Agent 每步动作（session/phase/step/thought/tool/text/loop/error）都产出结构化事件
- **workflow.py**: 工作流状态机 — 计划创建→步骤分解→逐步执行→完成/失败，全程可追踪
- GUI 工作流进度条：实时展示当前步骤、下一步、完成进度
- `--transcript` CLI 模式：逐行 `@EVENT` JSON 输出，供外部 UI 消费
- Claude Code 风格 GUI 渲染：工具耗时、步骤完成摘要、下一步建议、代码块着色

### Claude Code 对标（工具调用逻辑）
- **while True** 无硬上限循环（对标 Claude Code）
- 去掉所有阻断式检测（重复调用/停滞/超时中断）
- 3600s 安全阀仅作最后防线

### 子Agent系统（全新模块）
- **agent_loader.py**: 解析 `agents/*.md` YAML frontmatter + Markdown 正文 → Agent 类型注册表
- **tools_agent.py**: `subagent` 工具 — 隔离上下文执行子 Agent，支持同步/后台/列出模式
- **agents/code-architect.md**: 架构师 Agent 定义（只分析不修改）
- **agents/code-reviewer.md**: 审查 Agent 定义（多维审查 + 结构化输出）

### MCP 集成（全新模块）
- **mcp/client.py**: MCP stdio 客户端 — JSON-RPC 2.0，tools/list + tools/call
- **tools_mcp.py**: `mcp` 工具 — connect/disconnect/list/call，自动注册 MCP 工具到工具面板
- 支持 config.json `mcp_servers` 自动连接

### 修复
- `tools_plan.py`: 兼容 LLM 用 `title`/`name`/`description` 而非 `step` 字段
- `tools_shell.py`: `_handle_bash` timeout 参数类型安全转换（LLM 传字符串）
- `core.py`: 消除流式重复推送 `on_tool_start`
- `app.py`: 新增 `📋 复制日志` 按钮 — 一键复制全会话输出到剪贴板

### 从 v2.0 移植的模块（适配 v2.1 架构）
- **retry.py**: 指数退避 + 随机抖动重试机制（装饰器/函数式/生成器三重 API）
- **router.py**: 智能模型路由（按任务类型自动选最优模型）
- **project_map.py**: 项目结构自动映射（注入 system prompt）
- **researcher.py**: 深度研究引擎（分解问题→搜集资料→综合分析）
- **reviewer.py**: 代码审查引擎（审查 diff/文件，结构化报告）
- **mcpserver.py**: MCP 协议服务器管理（filesystem/git）
- **plugin.py**: 插件系统正式暴露

### Claude Code 风格交互（CLI + GUI 双模式）
- **CLI (main.py)**: 完全重写 CliHandler
  - 工具展示 `📖 read  main.py`（工具名+目标同一行）
  - 步骤编号 `[1/3]` 多步骤计划
  - 读文件：内容预览（头5行+尾3行）
  - 写文件：写入内容预览（前12行）
  - bash 输出：最后几行输出摘要
  - 错误展示：红色大标题 + 工具参数 + 堆栈详情
  - ANSI 颜色体系：橙工具·青路径·绿成功·红错误
  - 工具执行时间显示（0.3s+ 显示耗时）

- **GUI (app.py)**: 透明交互升级
  - 工具展示：图标+名称+目标路径同一行
  - write/edit 结果：展示写入/替换的内容预览
  - read 结果：代码块展示文件内容
  - bash 结果：最后几行输出
  - 错误：红色醒目大标题 + 工具参数（方便调试）
  - 步骤进度：`📋 计划执行 N 个步骤`
  - 新增 `tool_path`/`code`/`dim`/`tool_meta` 渲染标签
  - 修复：`on_tool_start`  重复调用不重复显示

### 类型安全与错误修复
- **tools.py**: 新增 `_coerce_params()` 全局类型安全转换层
  - LLM 传 `max_results="10"` → 自动转 int(10)
  - LLM 传 `recursive="true"` → 自动转 True
  - 所有 36+ 工具统一受益
- **tools_web.py**: `_handle_web_search` 加 `int()` 转换
- **tools_shell.py**: 自动检测 Windows 系统编码（GBK/UTF-8），修复中文乱码
- **tools_plan.py**: 新增 action 别名映射（`update_step`→`update` 等）

### 安全修复
- `config.json` 停止 git 追踪（`git rm --cached` + `.gitignore`）
- 创建 `config.json.example` 模板
- system prompt 移除"完全无限制权限"等不适当表述

### 文档与示例
- **TECHNICAL_WHITEPAPER.md**: 完整技术白皮书（中英双语，12 章）
- **README.md**: 全面重写为 v2.1 版本
- **examples/dashboard.html**: Calw 自生成的 3D 全息仪表盘（Three.js）
- **CHANGELOG.md**: 更新到 2.1.1

---

## 2.1.0 (2026-07-13)

### 架构重构
- **核心循环重写** (core.py)：SessionState 集成、推测执行、流式解析
- **Provider 接口统一** (providers.py)：统一 `complete()` + 新增 `stream_complete()` 流式接口
- **会话状态管理** (session.py)：线程安全、JSONL 持久化、工具注册、错误日志
- **工具注册表** (tools.py)：消除模块级副作用，显式注册模式
- **上下文压缩集成**：4 阶段渐进压缩（截断→压缩→丢弃→摘要）嵌入 Agent 主循环

### 流式交互（全新体验）
- LLM 流式输出：逐 token 实时回调，思考过程可见
- 工具执行实时展示：每个 `bash`/`read`/`write` 即时显示
- 工具结果即时回传：执行完毕立刻看到摘要
- CLI 模式同步支持流式输出 (main.py → CliHandler)

### 推测性执行引擎 (speculative.py) ★ 全新
- 5 条规则引擎：read→edit、build→test、web→browser、write→verify、连续失败→诊断
- 闲置 CPU 时间预执行下一步工具，降低延迟

### 流式工具调用解析器 (streaming_parser.py) ★ 全新
- LLM 输出流中实时检测工具调用
- 检测到关键参数即发起预执行，不等完整 JSON

### MMAP 文件缓存 (file_cache.py) ★ 全新
- 内存映射文件读写，大文件 0.3ms
- 行级随机访问、内存 diff 替换

### 浏览器自动化增强 (tools_browser.py)
- 自动检测 Playwright 可用性
- 不可用时降级为 HTTP 抓取（读标题+正文）
- 进程泄漏修复：close 时彻底清理所有子进程

### 工具模块全面升级（11 个文件重写）
- 统一返回格式 `[前缀] 描述`
- 全部添加类型注解
- 完整异常捕获
- 统一 action 分发逻辑
- 具体：tools_memory / tools_deps / tools_test / tools_extra / tools_web / tools_plan / tools_shell / tools_system / tools_analysis / tools_core

### 基础设施
- **版本号**: `1.1.0` → `2.1.0`
- **依赖完善**: chromadb / websocket-client / playwright / pyautogui / pygetwindow
- **CI 配置**: GitHub Actions (3.10/3.11/3.12 矩阵)
- **.gitignore**: 新增 `.claude/`、`config.json` 模式
- `requirements.txt` 同步 pyproject.toml

### 测试
- 新增 5 个测试文件：test_session / test_file_cache / test_streaming_parser / test_speculative / test_command
- 重写 2 个测试文件：test_providers / test_file_ops
- 修复 13 个旧测试文件的导入和断言
- **总计 243 个测试，全部通过**

### 性能提升
| 场景 | v2.0 | v2.1 |
|------|------|------|
| 大文件读取 | ~50ms 磁盘 I/O | ~0.3ms MMAP |
| 工具调用 | 等完整 JSON | 关键参数即执行 |
| 生成反馈 | 阻塞等全部完成 | 逐 token 实时推送 |
| Provider切换 | 2家 | 5家 |

### 已知限制（v2.2 方向）
- 无命令白名单/黑名单安全层
- API 密钥明文存储
- 无 Docker 容器化
- 无国际化支持

---

## 1.1.0 (2026-06-16)

### 架构重构
- tools.py 拆分：2676行→48行门面+7子模块
- 清理死代码(utils/trading)，23个孤儿pyc
- Git stash 22→3

### Phase 1
- 并行工具执行：只读并行，写工具串行
- SEARCH/REPLACE：精确+模糊双模式替换
- Token/成本追踪：7模型定价表，/usage命令

### Phase 2+3
- 多模型路由（router.py）：任务分类+自动选模型
- 非交互模式（--run --json）：支持CI流水线
- MCP协议（mcpserver.py）：连接外部工具服务
- TF-IDF文件索引，零依赖
- 规则引擎代码补全
- 事件文件监听（watcher.py）

### 测试
- 新增85个测试，总数71→156全部通过

---

## 1.0.0 (2026-06-07)
首次公开发布。
