#!/usr/bin/env python3
"""PR review script for GitHub Actions."""
import json, os, re, subprocess, sys, urllib.request

def get_pr_diff():
    try:
        r = subprocess.run(["git","fetch","origin",os.environ.get("GITHUB_BASE_REF","main")],capture_output=True,timeout=30)
        r = subprocess.run(["git","diff",f"origin/{os.environ.get('GITHUB_BASE_REF','main')}...HEAD","--no-color"],capture_output=True,text=True,timeout=30)
        if r.stdout.strip(): return r.stdout
    except: pass
    try:
        r = subprocess.run(["git","diff","HEAD~1","--no-color"],capture_output=True,text=True,timeout=30)
        if r.stdout.strip(): return r.stdout
    except: pass
    return ""

def call_llm(dt,effort,provider,key,model):
    inst = "只关注 critical/major。" if effort=="low" else "全面审查。" if effort=="high" else "关注 critical/major/minor。"
    prompt = f"""审查以下差异。{inst}\n## 维度\n1. Bug 2. Security 3. Performance 4. Style 5. Best Practice 6. Logic\n## 格式\n**<severity>** | **<category>** | **<title>** | line <n>\n<desc>\n**建议:** <suggestion>\n严重: critical/major/minor/suggestion 分类: bug/security/performance/style/best_practice/logic\n## 差异\n```diff\n{dt}\n```"""
    if provider == "Anthropic Claude":
        return _anthropic(prompt,key,model)
    return _openai(prompt,key,model)

def _openai(prompt,key,model):
    if not model: model="deepseek-chat"
    base=os.environ.get("LLM_BASE_URL","https://api.deepseek.com")
    body=json.dumps({"model":model,"messages":[{"role":"user","content":prompt}],"stream":False,"max_tokens":4096}).encode()
    req=urllib.request.Request(f"{base}/chat/completions",data=body,headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"})
    with urllib.request.urlopen(req,timeout=120) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

def _anthropic(prompt,key,model):
    if not model: model="claude-sonnet-4-6"
    body=json.dumps({"model":model,"max_tokens":4096,"messages":[{"role":"user","content":prompt}]}).encode()
    req=urllib.request.Request("https://api.anthropic.com/v1/messages",data=body,headers={"Content-Type":"application/json","x-api-key":key,"anthropic-version":"2023-06-01"})
    with urllib.request.urlopen(req,timeout=120) as resp:
        return json.loads(resp.read().decode())["content"][0]["text"]

def main():
    effort="medium"
    if "--effort" in sys.argv:
        i=sys.argv.index("--effort")
        if i+1<len(sys.argv): effort=sys.argv[i+1]
    provider=os.environ.get("LLM_PROVIDER","DeepSeek")
    key=os.environ.get("LLM_API_KEY","")
    model=os.environ.get("LLM_MODEL","")
    if not key: print("❌ LLM_API_KEY 未设置"); sys.exit(1)
    dt=get_pr_diff()
    if not dt: print("没有检测到代码变更，跳过审查。"); sys.exit(0)
    added=sum(1 for l in dt.split("\n") if l.startswith("+") and not l.startswith("+++"))
    removed=sum(1 for l in dt.split("\n") if l.startswith("-") and not l.startswith("---"))
    files=len(set(re.findall(r'^\+\+\+\s+(?:b/)?(.+)',dt,re.MULTILINE)))
    review=call_llm(dt,effort,provider,key,model)
    sev={s:review.lower().count(f"**{s}**") for s in ("critical","major","minor","suggestion")}
    sev_s=", ".join(f"{s}: {c}" for s,c in sev.items() if c)
    print(f"## 🤖 AI 代码审查\n\n**深度:** {effort} | **引擎:** Calw Review Engine\n\n**统计:** {len(re.findall(r'\*\*(?:critical|major|minor|suggestion)\*\*',review,re.I))} 问题 ({sev_s}) | 文件: {files} 个 | +{added}/-{removed}\n\n---\n\n{review}",flush=True)

if __name__=="__main__": main()
