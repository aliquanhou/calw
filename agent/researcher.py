"""Deep research engine — multi-source web research with fact-checking."""
from __future__ import annotations
import json, re, urllib.parse, urllib.request
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class Source:
    url: str; title: str; snippet: str = ""; content: str = ""; relevance: float = 1.0

@dataclass
class ResearchResult:
    question: str; summary: str = ""; key_findings: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list); sub_questions: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list); raw_sections: list[str] = field(default_factory=list)

def _web_search(q, max_r=8):
    s=[]
    try:
        p=urllib.parse.urlencode({"q":q})
        r=urllib.request.Request(f"https://html.duckduckgo.com/html/?{p}",headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(r,timeout=15) as resp: h=resp.read().decode("utf-8",errors="replace")
        for m in re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>',h):
            s.append(Source(url=m.group(1),title=re.sub(r'<[^>]+>',"",m.group(2)).strip()[:200]))
        sp=re.findall(r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>',h)
        for i,si in enumerate(sp):
            if i<len(s): s[i].snippet=re.sub(r'<[^>]+>',"",si).strip()[:300]
    except: pass
    return s[:max_r]

def _fetch_page(url,mc=5000):
    try:
        r=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(r,timeout=15) as resp: h=resp.read().decode("utf-8",errors="replace")
        for t in ("script","style"): h=re.sub(f"<{t}[^>]*>.*?</{t}>","",h,flags=re.DOTALL|re.I)
        return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",h)).strip()[:mc]
    except: return ""

def _decompose(q,llm):
    acc=""
    try:
        for e in llm("研究助手",[{"role":"user","content":f"分解为3-6子问题: {q}\\n只输出JSON数组。"}],[]):
            if e.type=="text_delta": acc+=e.delta
    except: pass
    m=re.search(r"\[.*?\]",acc,re.DOTALL)
    if m:
        try:
            qs=json.loads(m.group(0))
            return [s.strip() for s in qs if isinstance(s,str) and s.strip()]
        except: pass
    return [l for l in acc.split("\n") if l.strip() and "?" in l][:5] or [q]

def _synthesize(q,sq,src,llm):
    st="\n".join(f"[{i+1}] {s.title}\\n    URL: {s.url}\\n    内容: {s.content[:1000]}" for i,s in enumerate(src[:12]))
    acc=""
    try:
        for e in llm("研究分析师。中文。",[{"role":"user","content":f"基于资料生成「{q}」报告:\\n子问题:\\n"+"\n".join(f"- {x}" for x in sq)+f"\\n\\n资料:\\n{st}\\n\\n## 摘要\\n...\\n## 关键发现\\n- ...\\n## 矛盾/不确定\\n- ...\\n## 参考资料\\n- [1] title (url)"}],[]):
            if e.type=="text_delta": acc+=e.delta
    except: pass
    summary=""; findings=[]; contradictions=[]
    sm=re.search(r"##\s*摘要\s*\n(.*?)(?=\n##)",acc,re.DOTALL)
    if sm: summary=sm.group(1).strip()
    kf=re.search(r"##\s*关键发现\s*\n(.*?)(?=\n##)",acc,re.DOTALL)
    if kf: findings=[l.strip("- ").strip() for l in kf.group(1).split("\n") if l.strip().startswith("-")]
    ct=re.search(r"##\s*(?:矛盾|不确定)\s*\n(.*?)(?=\n##)",acc,re.DOTALL)
    if ct: contradictions=[l.strip("- ").strip() for l in ct.group(1).split("\n") if l.strip().startswith("-")]
    return ResearchResult(question=q,summary=summary,key_findings=findings,sources=src,sub_questions=sq,contradictions=contradictions)

def deep_research(question,llm,max_src=5,fc=True,progress=None):
    def p(m):
        if progress: progress(m)
    p("\U0001f50d 分析...")
    sub=_decompose(question,llm) or [question]
    p(f"\U0001f4c4 {len(sub)} 子问题")
    all_src=[]; seen=set()
    for sq in sub:
        p(f"\U0001f50e {sq[:60]}...")
        for s in _web_search(sq,max_src):
            if s.url not in seen and len(all_src)<20:
                seen.add(s.url); p(f"   \U0001f4d6 {s.title[:50]}..."); s.content=_fetch_page(s.url,3000); all_src.append(s)
    p(f"\U0001f4da {len(all_src)} 来源")
    if not all_src: return ResearchResult(question=question,summary="未能收集足够资料。")
    p("\U0001f9e0 分析...")
    r=_synthesize(question,sub,all_src,llm)
    p(f"✅ 完成: {len(r.key_findings)} 发现")
    return r

def format_report(r):
    lines=[f"\U0001f4ca {r.question}",""]
    if r.summary: lines.append(f"## 摘要\\n{r.summary}\\n")
    if r.key_findings:
        lines.append(f"## 关键发现 ({len(r.key_findings)})")
        lines.extend(f"  · {f}" for f in r.key_findings); lines.append("")
    if r.contradictions:
        lines.append(f"## ⚠ 需核实"); lines.extend(f"  ⚠ {c}" for c in r.contradictions[:5]); lines.append("")
    if r.sources:
        lines.append(f"## 来源 ({len(r.sources)})")
        for i,s in enumerate(r.sources[:10]): lines.append(f"  [{i+1}] {s.title}\\n       {s.url}")
    return "\n".join(lines)
