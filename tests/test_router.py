"""Tests for agent.router — classify_task, recommend_model, compare_models."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.router import classify_task, recommend_model, compare_models


class TestClassifyTask:
    def test_classify_simple(self):
        assert classify_task("search for files") == "simple"
        assert classify_task("quick search") == "simple"
        assert classify_task("find where is config") == "simple"
        assert classify_task("grep error logs") == "simple"
        assert classify_task("glob match test files") == "simple"
        assert classify_task("list directory contents") == "simple"
        assert classify_task("read this file") == "simple"

    def test_classify_code_gen(self):
        assert classify_task("写一个排序函数") == "code_gen"
        assert classify_task("实现用户登录功能") == "code_gen"
        assert classify_task("创建一个新类 UserModel") == "code_gen"
        assert classify_task("重构这个模块，拆分成两个文件") == "code_gen"
        assert classify_task("生成一个 MongoDB 的工具类") == "code_gen"

    def test_classify_code_review(self):
        assert classify_task("帮我审查这段代码") == "code_review"
        assert classify_task("检查这个文件的安全问题") == "code_review"
        assert classify_task("性能优化建议") == "code_review"

    def test_classify_debug(self):
        assert classify_task("修复这个 bug") == "debug"
        assert classify_task("这段代码报错了帮我看看") == "debug"
        assert classify_task("崩溃了，修一下") == "debug"

    def test_classify_plan(self):
        assert classify_task("规划这个项目的架构") == "plan"
        assert classify_task("设计方案") == "plan"
        assert classify_task("怎么做微服务拆分") == "plan"

    def test_fallback_to_code_gen(self):
        """无关键词匹配时默认返回 code_gen。"""
        assert classify_task("你好") == "code_gen"
        assert classify_task("这是一个测试") == "code_gen"

    def test_empty_input(self):
        """空输入也返回 code_gen。"""
        assert classify_task("") == "code_gen"

    def test_keyword_priority(self):
        """多个分类匹配时取最高分。"""
        result = classify_task("修复这个 bug 然后重构代码")
        # "bug" 命中 debug, "重构" 命中 code_gen
        assert isinstance(result, str)
        assert result in ("debug", "code_gen")


class TestRecommendModel:
    def test_simple_task_cheapest(self):
        """简单任务推荐最便宜的模型。"""
        available = ["claude-opus-4-7", "deepseek-chat", "claude-haiku-4-5"]
        result = recommend_model("快速列出文件列表", available)
        assert result == "claude-haiku-4-5"

    def test_plan_task_best_model(self):
        """规划任务推荐最强模型。"""
        available = ["claude-haiku-4-5", "claude-opus-4-7", "deepseek-chat"]
        result = recommend_model("设计系统架构", available)
        assert result == "claude-opus-4-7"

    def test_debug_recommendation(self):
        """调试任务推荐中高端模型。"""
        available = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"]
        result = recommend_model("修复这个空指针异常", available)
        # debug tier=3, claude-sonnet-4-6 tier=3 → exact match
        assert result == "claude-sonnet-4-6"

    def test_empty_available_models(self):
        """空列表返回空字符串。"""
        assert recommend_model("test", []) == ""

    def test_unranked_model_fallback(self):
        """不可识别的模型返回第一个。"""
        available = ["unknown-model", "test-model"]
        result = recommend_model("写代码", available)
        assert result == "unknown-model"

    def test_code_gen_recommends_mid(self):
        """代码生成任务推荐中间价位的模型。"""
        available = ["claude-haiku-4-5", "deepseek-chat", "claude-sonnet-4-6", "claude-opus-4-7"]
        result = recommend_model("实现用户登录模块", available)
        # code_gen tier=2, deepseek-chat tier=2 → exact match
        assert result == "deepseek-chat"

    def test_case_insensitive_classification(self):
        """任务分类不区分大小写。"""
        r1 = recommend_model("FIX BUG NOW", ["claude-haiku-4-5", "claude-sonnet-4-6"])
        r2 = recommend_model("fix bug now", ["claude-haiku-4-5", "claude-sonnet-4-6"])
        assert r1 == r2

    def test_all_models_scored(self):
        """所有可用模型都应该被评分。"""
        available = ["deepseek-chat", "claude-sonnet-4-6"]
        result = recommend_model("审查这段代码", available)
        assert result in available


class TestCompareModels:
    def test_returns_list(self):
        results = compare_models("快速搜索", ["deepseek-chat", "claude-sonnet-4-6"])
        assert isinstance(results, list)
        assert len(results) == 2

    def test_sorted_by_match_then_cost(self):
        results = compare_models("写代码", ["claude-haiku-4-5", "deepseek-chat", "claude-opus-4-7"])
        # code_gen tier=2, closest match first
        for i in range(len(results) - 1):
            assert results[i]["match"] <= results[i + 1]["match"]

    def test_each_result_has_keys(self):
        results = compare_models("测试", ["deepseek-chat"])
        assert "model" in results[0]
        assert "tier" in results[0]
        assert "match" in results[0]
        assert "cost" in results[0]

    def test_unranked_models_omitted(self):
        """不认识的模型不出现在结果中。"""
        results = compare_models("test", ["unknown-model", "deepseek-chat"])
        assert len(results) == 1
        assert results[0]["model"] == "deepseek-chat"

    def test_empty_available(self):
        assert compare_models("test", []) == []
