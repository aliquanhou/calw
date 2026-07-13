"""reviewer — 代码审查引擎。

审查 diff 或文件，基于 LLM 分析 bug、安全、性能、风格问题。
v2.1 移植版：
  - 适配 v2.1 的 provider 接口（stream_complete 返回 dict）
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable
from ._encoding import run as _run, popen as _popen


@dataclass
class ReviewFinding:
    severity: str  # critical | major | minor | suggestion
    category: str  # bug | security | performance | style | best_practice | logic
    file: str
    line: int | None
    title: str
    description: str
    suggestion: str | None = None


@dataclass
class ReviewReport:
    summary: str
    findings: list[ReviewFinding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    raw: str = ""


CATEGORY_ICONS = {
    "bug": "bug", "security": "security", "performance": "zap",
    "style": "art", "best_practice": "book", "logic": "brain",
}


def _get_diff(repo_path: str | None = None) -> str:
    """获取当前工作区的 git diff。"""
    try:
        cwd = repo_path or os.getcwd()
        for cmd in [
            ["git", "diff", "--no-color"],
            ["git", "diff", "--cached", "--no-color"],
            ["git", "diff", "HEAD", "--no-color"],
        ]:
            r = _run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout
    except Exception:
        pass
    return ""


def _count_diff_stats(diff_text: str) -> dict:
    """统计 diff 的基本数据。"""
    lines = diff_text.split("\n")
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    files = set()
    for l in lines:
        m = re.match(r'^\+\+\+\s+(?:b/)?(.+)', l)
        if m:
            files.add(m.group(1).strip())
    return {"files_changed": len(files), "lines_added": added, "lines_removed": removed}


def _parse_findings(text: str) -> list[ReviewFinding]:
    """从 LLM 输出解析审查结果。"""
    findings = []
    current_file = "unknown"

    for l in text.split("\n"):
        m = re.match(r'^##?\s*(?:文件|File)[：:]\s*(.+)', l.strip(), re.I)
        if m:
            current_file = m.group(1).strip()

    pattern = re.compile(
        r'\*\*(critical|major|minor|suggestion)\*\*\s*\|\s*'
        r'(bug|security|performance|style|best_practice|logic)\s*\|\s*'
        r'(.+?)\s*\|\s*line\s*(\d+)?.*?\n(.+?)(?=\n\*\*|\Z)',
        re.DOTALL | re.I,
    )
    for m in pattern.finditer(text):
        findings.append(ReviewFinding(
            severity=m.group(1).lower(),
            category=m.group(2).lower(),
            file=current_file,
            line=int(m.group(4)) if m.group(4) else None,
            title=m.group(3).strip(),
            description=m.group(5).strip()[:500],
        ))
    return findings


def _llm_complete(provider: Any, system: str, messages: list[dict]) -> str:
    """使用 provider 获取完整响应文本。"""
    try:
        response = provider.stream_complete(
            system=system, messages=messages, tools=[],
            max_tokens=8192, temperature=0.1,
        )
        return response.get("content", "")
    except Exception:
        return ""


def review_diff(
    diff_text: str,
    provider: Any,
    effort: str = "medium",
) -> ReviewReport:
    """审查 git diff。

    Args:
        diff_text: git diff 文本
        provider: LLM Provider 实例
        effort: low | medium | high

    Returns:
        结构化审查报告
    """
    if not diff_text.strip():
        return ReviewReport(summary="没有可审查的差异。")

    stats = _count_diff_stats(diff_text)

    prompt = (
        "审查以下代码差异，输出格式：\n"
        "**<severity>** | **<category>** | **<title>** | line <num>\n"
        "<description>\n**建议:** <suggestion>\n\n"
        "严重程度: critical/major/minor/suggestion\n"
        "分类: bug/security/performance/style/best_practice/logic\n\n"
        f"```diff\n{diff_text}\n```"
    )

    text = _llm_complete(
        provider,
        "你是代码审查助手。仔细审查代码差异，找出所有问题。用中文回复。",
        [{"role": "user", "content": prompt}],
    )

    findings = _parse_findings(text)
    if effort == "low":
        findings = [f for f in findings if f.severity in ("critical", "major")]
    elif effort == "medium":
        findings = [f for f in findings if f.severity in ("critical", "major", "minor")]

    findings.sort(key=lambda f: {"critical": 0, "major": 1, "minor": 2, "suggestion": 3}.get(f.severity, 99))

    return ReviewReport(
        summary=f"审查完成: {len(findings)} 个问题",
        findings=findings,
        stats=stats,
        raw=text,
    )


def review_file(
    file_path: str,
    provider: Any,
    effort: str = "medium",
) -> ReviewReport:
    """审查单个文件。"""
    if not os.path.exists(file_path):
        return ReviewReport(summary=f"文件不存在: {file_path}")

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    text = _llm_complete(
        provider,
        "你是代码审查助手。",
        [{"role": "user", "content": f"审查文件 {file_path}:\n```\n{content[:8000]}\n```"}],
    )

    findings = _parse_findings(text)
    if effort == "low":
        findings = [f for f in findings if f.severity in ("critical", "major")]

    return ReviewReport(
        summary=f"审查完成: {len(findings)} 个问题",
        findings=findings,
        stats={"file": file_path},
    )


def review_working_tree(
    repo_path: str | None,
    provider: Any,
    effort: str = "medium",
) -> tuple[ReviewReport, str]:
    """审查当前工作区变更。"""
    diff_text = _get_diff(repo_path)
    if not diff_text:
        return ReviewReport(summary="没有检测到代码变更。"), ""
    return review_diff(diff_text, provider, effort), diff_text


def format_report(report: ReviewReport) -> str:
    """格式化审查报告为可读文本。"""
    lines = [f"审查: {report.summary}"]
    lines.append(
        f"  文件: {report.stats.get('files_changed', '?')}"
        f"  +{report.stats.get('lines_added', 0)}"
        f"/-{report.stats.get('lines_removed', 0)}\n"
    )
    if not report.findings:
        lines.append("未发现明显问题。")
        return "\n".join(lines)

    for f in report.findings:
        icon = CATEGORY_ICONS.get(f.category, "info")
        loc = f" #{f.line}" if f.line else ""
        lines.append(f"[{f.severity}] {f.title}{loc}")
        lines.append(f"   {f.description[:200]}")
        if f.suggestion:
            lines.append(f"   建议: {f.suggestion[:200]}")
        lines.append("")

    return "\n".join(lines)
