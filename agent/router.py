"""router — 智能模型路由：按任务类型自动选择最优模型。

v2.1 移植版：
  - 适配 v2.1 的 model 命名风格（如 anthropic/claude-sonnet-4-20250514）
  - 与 providers.py 的 create_llm_provider() 配合使用
"""

from __future__ import annotations

_MODEL_RANK: dict[str, int] = {
    "claude-haiku-4-5-20251001": 1,
    "claude-haiku-4-5": 1,
    "claude-sonnet-4-20250514": 3,
    "claude-sonnet-4-6": 3,
    "claude-opus-4-7": 4,
    "deepseek-chat": 2,
    "deepseek-reasoner": 3,
    "gpt-4o-mini": 2,
    "gpt-4o": 3,
    "gemini-2.0-flash": 2,
    "gemini-2.5-pro": 3,
}

_TASK_PATTERNS: dict[str, list[str]] = {
    "simple": [
        "grep", "glob", "read", "search", "list", "ls", "find",
        "简单的", "快速", "给我", "多少", "什么", "哪个",
    ],
    "code_gen": [
        "write", "create", "implement", "重构", "实现", "编写",
        "创建", "写一个", "生成", "新建", "function", "class",
    ],
    "code_review": [
        "review", "audit", "检查", "审查", "bug", "安全", "性能",
    ],
    "debug": [
        "error", "fix", "修复", "不对", "报错", "崩溃", "失败",
    ],
    "plan": [
        "plan", "design", "架构", "设计", "方案", "规划", "计划",
    ],
}

_MODEL_TIER: dict[str, int] = {
    "simple": 1, "code_gen": 2,
    "code_review": 3, "debug": 3, "plan": 4,
}


def classify_task(user_input: str) -> str:
    """根据用户输入推断任务类型。"""
    text = user_input.lower()
    scores: dict[str, int] = {}
    for task, keywords in _TASK_PATTERNS.items():
        s = sum(1 for kw in keywords if kw in text)
        if s:
            scores[task] = s
    if not scores:
        return "code_gen"
    return max(scores, key=scores.get)


def _strip_provider_prefix(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[1]
    return model


def recommend_model(user_input: str, available_models: list[str]) -> str:
    """根据任务类型推荐最优模型。"""
    task = classify_task(user_input)
    target = _MODEL_TIER.get(task, 2)

    ranked = []
    for m in available_models:
        base = _strip_provider_prefix(m)
        rank = _MODEL_RANK.get(base, 99)
        ranked.append((m, rank))

    if not ranked:
        return available_models[0] if available_models else ""

    best_model, best_dist = ranked[0], abs(ranked[0][1] - target)
    for m, rank in ranked[1:]:
        d = abs(rank - target)
        if d < best_dist:
            best_dist, best_model = d, m
    return best_model


def compare_models(user_input: str, available_models: list[str]) -> list[dict]:
    """对比各模型对特定任务的适用度。"""
    task = classify_task(user_input)
    target = _MODEL_TIER.get(task, 2)

    results = []
    for m in available_models:
        base = _strip_provider_prefix(m)
        rank = _MODEL_RANK.get(base, 99)
        if rank < 99:
            results.append({"model": m, "tier": rank, "match": abs(rank - target)})
    results.sort(key=lambda x: (x["match"], x["tier"]))
    return results
