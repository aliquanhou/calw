"""tools_web"""
from __future__ import annotations
import json,urllib.request,urllib.error
def _handle_web(url,method="GET",data=None,headers=None):
    try:
        req=urllib.request.Request(url,method=method)
        if headers:
            try:
                for k,v in json.loads(headers).items():req.add_header(k,v)
            except:pass
        if method=="POST"and data:req.data=data.encode("utf-8");req.add_header("Content-Type","application/json")
        with urllib.request.urlopen(req,timeout=30)as resp:
            body=resp.read().decode("utf-8",errors="replace");info=f"HTTP {resp.status} {resp.reason}|{len(body)}字节"
            if len(body)>5000:body=body[:5000]+f"\n...(截断,共{len(body)}字节)"
            return f"{info}\n\n{body}"
    except urllib.error.HTTPError as e:return f"HTTP {e.code}:{e.reason}\n{e.read().decode('utf-8',errors='replace')[:1000]}"
    except Exception as e:return f"请求失败:{e}"
def _handle_web_search(query,max_results=5):
    max_results=min(max(max_results,1),10)
    try:
        import requests as rqs,re
        resp=rqs.get("https://html.duckduckgo.com/html/",params={"q":query},headers={"User-Agent":"Mozilla/5.0"},timeout=15);resp.raise_for_status()
        html=resp.text
        results=[(re.sub(r'<[^>]+>',"",m.group(2)).strip(),m.group(1))for m in re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>',html)]
        snippets=[re.sub(r'<[^>]+>',"",s).strip()[:200]for s in re.findall(r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>',html)]
        lines=[f"搜索:{query}",""]
        for i,(t,u)in enumerate(results[:max_results]):
            lines.append(f"{i+1}.{t}")
            if i<len(snippets)and snippets[i]:lines.append(f"  {snippets[i]}")
            lines.append(f"  {u}");lines.append("")
        return"\n".join(lines).strip()if lines else f"无结果:{query}"
    except Exception as e:return f"搜索失败:{e}"
def _handle_ask_user(question, options="", analysis="", recommended=""):
    """智能询问用户：带分析 + 多选项 + 推荐。"""
    lines = []
    lines.append("")
    lines.append("=" * 50)
    lines.append("🤔 需要你的决定")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"📌 **{question}**")
    lines.append("")
    if analysis:
        lines.append("📊 **分析**:")
        for a_line in analysis.split("\\n"):
            a_line = a_line.strip()
            if a_line:
                lines.append(f"   {a_line}")
        lines.append("")
    if options:
        try:
            o = json.loads(options)
            if isinstance(o, list) and o:
                lines.append("🔀 **可选方案**:")
                for i, v in enumerate(o):
                    recommended_str = ""
                    if recommended and (str(i) == str(recommended) or str(i + 1) == str(recommended) or v.startswith(str(recommended)) or recommended in v):
                        recommended_str = " ⭐"
                    letter = chr(65 + i)
                    lines.append(f"  [{letter}]{v}{recommended_str}")
                lines.append("")
                if recommended:
                    lines.append(f"💡 **推荐**: 选项 {recommended}")
                    lines.append("")
        except json.JSONDecodeError:
            lines.append(f"  选项: {options}")
            lines.append("")
    lines.append("💬 请回复你的选择（输入 A/B/C... 或直接说）")
    lines.append("=" * 50)
    return "\n".join(lines)
