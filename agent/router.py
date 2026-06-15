"""router — 智能模型路由：按任务类型自动选择最优模型。"""
from __future__ import annotations
# 内联价格数据（与 providers.py MODEL_PRICING 同步）
_MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-7":     {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":   {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":    {"input": 0.80,  "output": 4.00},
    "deepseek-chat":       {"input": 0.27,  "output": 1.10},
    "deepseek-reasoner":   {"input": 0.55,  "output": 2.19},
    "gpt-4o":              {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":         {"input": 0.15,  "output": 0.60},
}
_TASK_PATTERNS: dict[str, list[str]] = {
    "simple": ["grep","glob","read","search","list","ls","find","where","简单的","快速","给我","多少","什么","哪个"],
    "code_gen": ["write","create","implement","重构","实现","编写","创建","写一个","生成","新建","function","class"],
    "code_review": ["review","audit","检查","审查","bug","问题","安全","性能","优化"],
    "debug": ["error","bug","fix","修复","不对","报错","崩溃","不工作","失败","修一下"],
    "plan": ["plan","design","架构","设计","方案","规划","计划","思路","怎么做"],
}
_MODEL_RANK: dict[str, int] = {
    "claude-haiku-4-5": 1, "deepseek-chat": 2, "gpt-4o-mini": 2,
    "claude-sonnet-4-6": 3, "gpt-4o": 3, "deepseek-reasoner": 3, "claude-opus-4-7": 4,
}
_MODEL_TIER: dict[str, int] = {"simple": 1, "code_gen": 2, "code_review": 3, "debug": 3, "plan": 4}
def classify_task(user_input: str) -> str:
    text = user_input.lower(); scores: dict[str, int] = {}
    for task, keywords in _TASK_PATTERNS.items():
        s = sum(1 for kw in keywords if kw in text)
        if s: scores[task] = s
    if not scores: return "code_gen"
    return max(scores, key=scores.get)
def recommend_model(user_input: str, available_models: list[str]) -> str:
    task = classify_task(user_input); target = _MODEL_TIER.get(task, 2)
    ranked = sorted([m for m in available_models if m in _MODEL_RANK], key=lambda m: _MODEL_RANK.get(m, 99))
    if not ranked: return available_models[0] if available_models else ""
    best, best_dist = ranked[0], abs(_MODEL_RANK.get(ranked[0], 99) - target)
    for m in ranked:
        d = abs(_MODEL_RANK.get(m, 99) - target)
        if d < best_dist: best_dist, best = d, m
    return best
def compare_models(user_input: str, available_models: list[str]) -> list[dict]:
    task = classify_task(user_input); target = _MODEL_TIER.get(task, 2)
    results = []
    for m in available_models:
        if m in _MODEL_RANK:
            results.append({"model": m, "tier": _MODEL_RANK[m], "match": abs(_MODEL_RANK[m] - target),
                           "cost": _MODEL_PRICING.get(m, {}).get("input", 3.0)})
    results.sort(key=lambda x: (x["match"], x["cost"]))
    return results
