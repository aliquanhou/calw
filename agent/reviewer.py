"""Code review engine — reviews diffs for bugs, security, and style problems.
Uses the configured LLM provider to analyze code and generate structured reports.
"""
from __future__ import annotations
import re, os, subprocess
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class ReviewFinding:
    severity: str
    category: str
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

CATEGORY_ICONS = {"bug":"\U0001f41b","security":"\U0001f512","performance":"⚡","style":"\U0001f3a8","best_practice":"\U0001f4d0","logic":"\U0001f9e0"}

def _get_diff(repo_path=None):
    try:
        cwd = repo_path or os.getcwd()
        for cmd in [["git","diff","--no-color"], ["git","diff","--cached","--no-color"], ["git","diff","HEAD","--no-color"]]:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout
    except: pass
    return ""

def _count_diff_stats(dt):
    lines=dt.split("\n"); added=sum(1 for l in lines if l.startswith("+") and not l.startswith("+++")); removed=sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    files=set()
    for l in lines:
        m=re.match(r'^\+\+\+\s+(?:b/)?(.+)',l)
        if m: files.add(m.group(1).strip())
    return {"files_changed":len(files),"lines_added":added,"lines_removed":removed}

def _parse_findings(text):
    findings=[]; cf="unknown"
    for l in text.split("\n"):
        m=re.match(r'^##?\s*(?:文件|File)[：:]\s*(.+)',l.strip(),re.I)
        if m: cf=m.group(1).strip()
    p=re.compile(r'\*\*(critical|major|minor|suggestion)\*\*\s*\|\s*(bug|security|performance|style|best_practice|logic)\s*\|\s*(.+?)\s*\|\s*line\s*(\d+)?.*?\n(.+?)(?=\n\*\*|\Z)',re.DOTALL|re.I)
    for m in p.finditer(text):
        findings.append(ReviewFinding(severity=m.group(1).lower(),category=m.group(2).lower(),file=cf,line=int(m.group(4)) if m.group(4) else None,title=m.group(3).strip(),description=m.group(5).strip()[:500]))
    return findings

def review_diff(dt,llm_func,effort="medium"):
    if not dt.strip(): return ReviewReport(summary="没有可审查的差异。")
    stats=_count_diff_stats(dt); acc=""
    prompt=f"""审查以下差异，输出格式：**<severity>** | **<category>** | **<title>** | line <num>\\n<desc>\\n**建议:** <suggestion>\\n严重: critical/major/minor/suggestion 分类: bug/security/performance/style/best_practice/logic\\n\\n```diff\\n{dt}\\n```"""
    try:
        for e in llm_func("代码审查助手。中文。",[{"role":"user","content":prompt}],[]):
            if e.type=="text_delta": acc+=e.delta
    except: pass
    findings=_parse_findings(acc)
    if effort=="low": findings=[f for f in findings if f.severity in ("critical","major")]
    elif effort=="medium": findings=[f for f in findings if f.severity in ("critical","major","minor")]
    findings.sort(key=lambda f:{"critical":0,"major":1,"minor":2,"suggestion":3}.get(f.severity,99))
    return ReviewReport(summary=f"审查完成: {len(findings)} 个问题",findings=findings,stats=stats,raw=acc)

def review_file(path,llm_func,effort="medium"):
    if not os.path.exists(path): return ReviewReport(summary=f"文件不存在: {path}")
    with open(path,"r",encoding="utf-8",errors="replace") as f: c=f.read()
    acc=""
    try:
        for e in llm_func("代码审查助手。",[{"role":"user","content":f"审查文件 {path}:\n```\n{c[:8000]}\n```"}],[]):
            if e.type=="text_delta": acc+=e.delta
    except: pass
    findings=_parse_findings(acc)
    if effort=="low": findings=[f for f in findings if f.severity in ("critical","major")]
    return ReviewReport(summary=f"审查完成: {len(findings)} 个问题",findings=findings,stats={"file":path})

def review_working_tree(repo_path,llm_func,effort="medium"):
    dt=_get_diff(repo_path)
    if not dt: return ReviewReport(summary="没有检测到代码变更。"),""
    return review_diff(dt,llm_func,effort),dt

def format_report(r):
    lines=[f"\U0001f4cb {r.summary}"]
    lines.append(f"  文件: {r.stats.get('files_changed','?')}  +{r.stats.get('lines_added',0)}/-{r.stats.get('lines_removed',0)}\\n")
    if not r.findings: lines.append("✅ 未发现明显问题。"); return "\n".join(lines)
    for f in r.findings:
        lines.append(f"{CATEGORY_ICONS.get(f.category,'\U0001f4cc')} [{f.severity}] {f.title}{' #'+str(f.line) if f.line else ''}")
        lines.append(f"   {f.description[:200]}")
        if f.suggestion: lines.append(f"   \U0001f4a1 {f.suggestion[:200]}")
        lines.append("")
    return "\n".join(lines)
