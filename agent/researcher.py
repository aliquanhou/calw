"""researcher — 深度研究引擎。

基于多来源网页搜索的深度研究，自动分解问题、搜集资料、综合分析。
v2.1 移植版：
  - 适配 v2.1 的 provider 接口（stream_complete 返回 dict）
  - 使用统一的 web_search 工具而非内联实现
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Source:
    url: str
    title: str
    snippet: str = ""
    content: str = ""
    relevance: float = 1.0


@dataclass
class ResearchResult:
    question: str
    summary: str = ""
    key_findings: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    sub_questions: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)


def _web_search(query: str, max_results: int = 8) -> list[Source]:
    """通过 DuckDuckGo 搜索网页。"""
    sources = []
    try:
        params = urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(
            f"https://html.duckduckgo.com/html/?{params}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        for m in re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>', html
        ):
            sources.append(
                Source(
                    url=m.group(1),
                    title=re.sub(r"<[^>]+>", "", m.group(2)).strip()[:200],
                )
            )
        snippets = re.findall(
            r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>', html
        )
        for i, si in enumerate(snippets):
            if i < len(sources):
                sources[i].snippet = re.sub(r"<[^>]+>", "", si).strip()[:300]
    except Exception:
        pass
    return sources[:max_results]


def _fetch_page(url: str, max_chars: int = 5000) -> str:
    """获取网页内容（去标签纯文本）。"""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        for tag in ("script", "style"):
            html = re.sub(
                f"<{tag}[^>]*>.*?</{tag}>", "", html, flags=re.DOTALL | re.I
            )
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
        return text[:max_chars]
    except Exception:
        return ""


def _llm_complete(
    provider: Any,
    system: str,
    messages: list[dict],
) -> str:
    """使用 provider 的 stream_complete 获取完整文本。"""
    try:
        response = provider.stream_complete(
            system=system,
            messages=messages,
            tools=[],
            max_tokens=4096,
            temperature=0.3,
        )
        return response.get("content", "")
    except Exception:
        return ""


def _decompose(question: str, provider: Any) -> list[str]:
    """将问题分解为子问题。"""
    text = _llm_complete(
        provider,
        "你是研究规划师。请将研究问题分解为 3-6 个具体的子问题。只输出 JSON 数组。",
        [{"role": "user", "content": f"分解问题: {question}"}],
    )
    m = re.search(r"\[.*?\]", text, re.DOTALL)
    if m:
        try:
            qs = json.loads(m.group(0))
            return [s.strip() for s in qs if isinstance(s, str) and s.strip()]
        except Exception:
            pass
    return [line.strip() for line in text.split("\n") if "?" in line] or [question]


def _synthesize(
    question: str,
    sub_questions: list[str],
    sources: list[Source],
    provider: Any,
) -> ResearchResult:
    """综合资料生成研究报告。"""
    sources_text = "\n".join(
        f"[{i+1}] {s.title}\n    URL: {s.url}\n    内容: {s.content[:1000]}"
        for i, s in enumerate(sources[:12])
    )
    text = _llm_complete(
        provider,
        "你是研究分析师。基于提供的研究资料，生成结构化报告。",
        [{
            "role": "user",
            "content": (
                f"基于资料生成「{question}」报告:\n"
                f"子问题:\n" + "\n".join(f"- {x}" for x in sub_questions)
                + f"\n\n资料:\n{sources_text}\n\n"
                + "## 摘要\n...\n## 关键发现\n- ...\n## 矛盾/不确定\n- ...\n## 参考资料\n- [1] title (url)"
            ),
        }],
    )

    summary = ""
    sm = re.search(r"##\s*摘要\s*\n(.*?)(?=\n##)", text, re.DOTALL)
    if sm:
        summary = sm.group(1).strip()

    findings = []
    kf = re.search(r"##\s*关键发现\s*\n(.*?)(?=\n##)", text, re.DOTALL)
    if kf:
        findings = [
            l.strip("- ").strip()
            for l in kf.group(1).split("\n")
            if l.strip().startswith("-")
        ]

    contradictions = []
    ct = re.search(r"##\s*(?:矛盾|不确定)\s*\n(.*?)(?=\n##)", text, re.DOTALL)
    if ct:
        contradictions = [
            l.strip("- ").strip()
            for l in ct.group(1).split("\n")
            if l.strip().startswith("-")
        ]

    return ResearchResult(
        question=question,
        summary=summary,
        key_findings=findings,
        sources=sources,
        sub_questions=sub_questions,
        contradictions=contradictions,
    )


def deep_research(
    question: str,
    provider: Any,
    max_sources: int = 5,
    progress: Callable[[str], None] | None = None,
) -> ResearchResult:
    """执行深度研究。

    Args:
        question: 研究问题
        provider: LLM Provider 实例
        max_sources: 每子问题最大来源数
        progress: 进度回调函数

    Returns:
        结构化的研究结果
    """
    if progress:
        progress("分析问题...")

    sub_questions = _decompose(question, provider) or [question]

    if progress:
        progress(f"分解为 {len(sub_questions)} 个子问题")

    all_sources: list[Source] = []
    seen: set[str] = set()

    for sq in sub_questions:
        if progress:
            progress(f"搜索: {sq[:60]}...")
        for s in _web_search(sq, max_sources):
            if s.url not in seen and len(all_sources) < 20:
                seen.add(s.url)
                if progress:
                    progress(f"  获取: {s.title[:50]}...")
                s.content = _fetch_page(s.url, 3000)
                all_sources.append(s)

    if progress:
        progress(f"已收集 {len(all_sources)} 个来源")

    if not all_sources:
        return ResearchResult(question=question, summary="未能收集足够资料。")

    if progress:
        progress("综合分析中...")

    result = _synthesize(question, sub_questions, all_sources, provider)

    if progress:
        progress(f"完成: {len(result.key_findings)} 个发现")

    return result


def format_report(result: ResearchResult) -> str:
    """格式化研究结果为可读文本。"""
    lines = [f"研究: {result.question}", ""]
    if result.summary:
        lines.append(f"## 摘要\n{result.summary}\n")
    if result.key_findings:
        lines.append(f"## 关键发现 ({len(result.key_findings)})")
        lines.extend(f"  · {f}" for f in result.key_findings)
        lines.append("")
    if result.contradictions:
        lines.append("## 需核实")
        lines.extend(f"  ! {c}" for c in result.contradictions[:5])
        lines.append("")
    if result.sources:
        lines.append(f"## 来源 ({len(result.sources)})")
        for i, s in enumerate(result.sources[:10]):
            lines.append(f"  [{i+1}] {s.title}\n       {s.url}")
    return "\n".join(lines)
