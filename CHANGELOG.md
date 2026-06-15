# Changelog

## 1.1.0 (2026-06-16)

### 架构重构
- tools.py 拆分：2676行→48行门面+7子模块
- 删除死代码：agent/utils/(475行)、agent/trading/(MT5残留)
- 清理孤儿文件：23个孤儿pyc、Git stash 22→3

### Phase 1
- 并行工具执行：只读并行，写工具串行
- SEARCH/REPLACE：精确+模糊双模式替换
- Token/成本追踪：7模型定价表，/usage命令

### Phase 2+3
- 多模型路由（router.py）：任务分类+自动选模型
- 非交互模式（--run --json）：支持CI流水线
- MCP协议（mcpserver.py）：连接外部工具服务
- 文件索引（indexer.py）：TF-IDF语义搜索，零依赖
- 代码补全（completions.py）：规则引擎
- 事件文件监听：watcher.py支持watchdog

### 测试
- 新增85个测试，总数71→156全部通过

---

## 1.0.0 (2026-06-07)
首次公开发布。
