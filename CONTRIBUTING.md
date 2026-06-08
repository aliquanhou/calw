# 贡献指南

感谢你愿意为 Calw 贡献代码！请遵循以下规范：

## 提交 Issue

- **Bug 报告**：请使用 [Bug Report 模板](.github/ISSUE_TEMPLATE/bug_report.md)
- **功能请求**：请使用 [Feature Request 模板](.github/ISSUE_TEMPLATE/feature_request.md)

## 开发流程

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feat/your-feature`
3. 编写代码并确保测试通过
4. 提交 PR

## 代码规范

- 遵循现有代码风格（PEP 8）
- 纯 Python + Type Hints
- 新增工具需在 `agent/tools.py` 中注册
- 新增功能需添加对应测试

## 测试

```bash
# 运行全量测试
python -m pytest tests/ -v

# 确保 110 个测试全部通过
```

## PR 规范

- PR 标题描述改动要点
- 关联相关 Issue 编号
- 更新 CHANGELOG.md
