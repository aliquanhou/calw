"""tools_browser"""
from __future__ import annotations
import time
_b=None;_bc=None;_bp=None;_cl=[];_ne=[];_pe=[]
_browser=_b;_browser_context=_bc;_browser_page=_bp;_browser_console_logs=_cl;_browser_network_errors=_ne;_browser_page_errors=_pe
def _gbp():
    global _b,_bc,_bp
    if _bp is not None:
        try:_bp.title();return _bp
        except:_bp=None
    from playwright.sync_api import sync_playwright
    p=sync_playwright().start();_b=p.chromium.launch(headless=False);_bc=_b.new_context(viewport={"width":1280,"height":800},locale="zh-CN");_bp=_bc.new_page()
    _bp.on("console",lambda m:_cl.append(f"[{m.type}]{m.text[:500]}"));_bp.on("pageerror",lambda e:_pe.append(str(e)[:500]));_bp.on("requestfailed",lambda r:_ne.append(f"{r.url[:200]}->{str(r.failure)if r.failure else'unknown'}"))
    return _bp
def _handle_browser(action,url="",selector="",text="",script=""):
    try:page=_gbp()
    except Exception as e:return str(e)
    try:
        if action=="navigate":
            if not url:return"navigate需url"
            page.goto(url,wait_until="domcontentloaded",timeout=30000);time.sleep(0.5)
            return f"导航到:{url}\n标题:{page.title()}\n{page.inner_text('body')[:3000]}"
        elif action=="click":
            if not selector:return"click需selector"
            page.click(selector,timeout=10000);time.sleep(0.3);return f"已点击:{selector}"
        elif action=="type":
            if not selector:return"type需selector"
            page.fill(selector,text);return f"已输入:{text[:100]}"
        elif action=="read":return"\n".join(f"[{i}]{el.inner_text()[:200]}"for i,el in enumerate(page.query_selector_all(selector)[:20])if el.inner_text())if selector else(page.inner_text("body")[:5000]or"(无文本)")
        elif action=="screenshot":
            import base64;e=base64.b64encode(page.screenshot(full_page=False,type="png")).decode("utf-8")
            return f"[BROWSER_SCREENSHOT len={len(e)}]\n{e}"
        elif action=="html":return page.content()[:8000]
        elif action=="get_url":return f"URL:{page.url}"
        elif action=="console":return"\n".join(_cl[-50:])if _cl else"(无console)"
        elif action=="network":return"\n".join(_ne[-50:])if _ne else"(无network)"
        elif action=="diagnose":
            if url:page.goto(url,wait_until="domcontentloaded",timeout=30000);time.sleep(2)
            import re;ss=[m.group(1)for m in re.finditer(r'<script[^>]*src="([^"]*)"',page.content())]
            p=[f"===诊断===",f"URL:{page.url}",f"标题:{page.title()}",f"===Console({len(_cl)}条)==="]
            for c in _cl[-30:]:p.append(f"  {c}")
            if _pe:p.append(f"===JS错误({len(_pe)}条)===")
            for e in _pe:p.append(f"  {e}")
            if _ne:p.append(f"===Network失败===")
            for n in _ne[-20:]:p.append(f"  {n}")
            p.append("===Script标签===")
            for s in ss[:10]:p.append(f"  {s}")
            bt=page.inner_text("body")[:2000]
            if bt.strip():p.append(f"===内容===");p.append(bt)
            else:p.append("=空=")
            return"\n".join(p)
        elif action=="execute_js":return f"JS结果:\n{page.evaluate(script)}"if script else"需script"
        elif action=="close":
            global _b,_bc,_bp
            try:_bp=None;_bc=None;_b and _b.close();_b=None
            except:pass
            return"浏览器已关闭"
        else:return f"未知操作:{action}"
    except Exception as e:return f"浏览器错:{e}"
