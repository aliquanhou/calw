# Changelog

## 1.0.0 (2026-06-07)

### 修复
- Edit 工具写入可靠性：读回校验 + 路径规范化 + 自动重试
- 多轮自主执行：改为 continue（有工具调用）/ break（纯文本回复）逻辑
- tool_call_id 重复 400 错误：从消息内容扫描 ID，不依赖内存集合
- tool_results 重复追加：移出 for-tch 循环，仅追加一次
- sanitize 双集合验证：区分 requested_ids vs received_ids 防自验证

### 新增
- 110 个单元测试全部通过
- GUI 工具面板、活动日志、上下文监控
- 跨会话持久记忆
- 多 LLM 提供商支持（DeepSeek / Anthropic / OpenAI）

### 说明
- 本版本基于 claw 完整重构，修复了核心循环的多个关键缺陷
- 首次公开发布
