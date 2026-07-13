"""tools_browser — 浏览器自动化控制工具。

v2.1 改进：
  - 自动检测 Playwright 浏览器是否可用
  - 不可用时降级为 HTTP 抓取（同样能读网页内容）
  - 无需安装 Playwright 专用浏览器即可使用
"""

from __future__ import annotations

import time
import threading
import urllib.error
import urllib.request
from typing import Any

# ── 浏览器实例管理 ──

_browser = None
_browser_context = None
_browser_page = None
_browser_playwright = None
_browser_console_logs = []
_browser_network_errors = []
_browser_page_errors = []

_browser_lock = threading.Lock()
_playwright_available: bool | None = None  # None=未检测, True=可用, False=不可用


def _check_playwright():
    """检查 Playwright 浏览器是否可用（只检测一次）。"""
    global _playwright_available
    if _playwright_available is not None:
        return _playwright_available
    try:
        # 检查 Chromium 二进制是否存在
        import subprocess, os
        from playwright.sync_api import sync_playwright
        # 尝试启动再关闭（静默检测）
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        _playwright_available = True
    except Exception:
        _playwright_available = False
    return _playwright_available


def _get_or_create_page():
    """获取或创建浏览器页面（线程安全）。"""
    global _browser, _browser_context, _browser_page, _browser_playwright
    global _browser_console_logs, _browser_network_errors, _browser_page_errors

    if not _check_playwright():
        raise RuntimeError("Playwright 浏览器不可用，已降级为 HTTP 模式")

    with _browser_lock:
        if _browser_page is not None:
            try:
                _browser_page.title()
                return _browser_page
            except Exception:
                _cleanup_browser()

        try:
            from playwright.sync_api import sync_playwright

            _browser_playwright = sync_playwright().start()
            _browser = _browser_playwright.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            _browser_context = _browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            _browser_page = _browser_context.new_page()
            _browser_console_logs = []
            _browser_network_errors = []
            _browser_page_errors = []
            _browser_page.on("console", lambda m: _browser_console_logs.append(f"[{m.type}] {m.text[:500]}"))
            _browser_page.on("pageerror", lambda e: _browser_page_errors.append(str(e)[:500]))
            _browser_page.on("requestfailed", lambda r: _browser_network_errors.append(
                f"{r.url[:200]} -> {str(r.failure) if r.failure else 'unknown'}"
            ))
            return _browser_page
        except Exception as e:
            _cleanup_browser()
            raise RuntimeError(f"浏览器启动失败: {e}")


def _cleanup_browser():
    """彻底清理浏览器资源（线程安全）。"""
    global _browser, _browser_context, _browser_page, _browser_playwright
    with _browser_lock:
        try:
            if _browser_page is not None: _browser_page.close()
        except Exception: pass
        _browser_page = None
        try:
            if _browser_context is not None: _browser_context.close()
        except Exception: pass
        _browser_context = None
        try:
            if _browser is not None: _browser.close()
        except Exception: pass
        _browser = None
        try:
            if _browser_playwright is not None: _browser_playwright.stop()
        except Exception: pass
        _browser_playwright = None


def _http_fetch(url: str) -> str:
    """降级方案：用 HTTP 请求获取网页内容。"""
    if not url:
        return "[错误] 需要 url 参数"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        # 提取标题 + 正文文本
        import re
        title = ""
        m = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.DOTALL)
        if m: title = m.group(1).strip()
        # 去标签取可见文本
        text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.I | re.DOTALL)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.I | re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()[:3000]
        return f"标题: {title}\n\n{text}"
    except urllib.error.HTTPError as e:
        return f"[HTTP] {e.code} {e.reason}"
    except Exception as e:
        return f"[错误] 请求失败: {e}"


# ── 工具处理函数 ──

def _handle_browser(action: str = "", url: str = "", selector: str = "",
                    text: str = "", script: str = "") -> str:
    """浏览器自动化操作。

    自动检测 Playwright 浏览器是否可用：
      - 可用 → 使用真实浏览器（可执行 JS、截图等）
      - 不可用 → 降级为 HTTP 抓取（可读页面标题和正文）

    Args:
        action: open/navigate | click | type | read | screenshot | diagnose | execute_js | close
        url: 目标 URL
        selector: CSS 选择器
        text: 要输入的文本
        script: 要执行的 JavaScript

    Returns:
        操作结果字符串
    """
    # 关闭动作可以直接执行
    if action == "close":
        _cleanup_browser()
        return "浏览器已关闭"

    # 检测 Playwright
    use_playwright = _check_playwright()

    # 如果是 open/navigate 且 Playwright 不可用 → 降级到 HTTP 抓取
    if action in ("open", "navigate") and not use_playwright:
        result = _http_fetch(url)
        return f"[HTTP 降级] Playwright 浏览器未安装，已通过 HTTP 获取内容:\n\n{result}"

    # 如果 Playwright 不可用，其他操作无法执行
    if not use_playwright:
        return "[提示] Playwright 浏览器未安装，仅支持 open/navigate 操作（将通过 HTTP 获取内容）"

    # ── Playwright 模式 ──
    try:
        page = _get_or_create_page()
    except Exception as e:
        return f"浏览器错误: {e}"

    try:
        if action in ("open", "navigate"):
            if not url:
                return "open/navigate 需要 url 参数"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(0.5)
            body_text = page.inner_text("body")[:3000] if page.inner_text("body") else "(空页面)"
            return f"导航到: {url}\n标题: {page.title()}\n{body_text}"

        elif action == "click":
            if not selector: return "click 需要 selector 参数"
            page.click(selector, timeout=10000)
            time.sleep(0.3)
            return f"已点击: {selector}"

        elif action == "type":
            if not selector: return "type 需要 selector 参数"
            page.fill(selector, text or "")
            return f"已输入: {(text or '')[:100]}"

        elif action == "read":
            if selector:
                elements = page.query_selector_all(selector)
                lines = [f"[{i}] {el.inner_text()[:200]}" for i, el in enumerate(elements[:20]) if el.inner_text()]
                return "\n".join(lines) if lines else "(无匹配元素)"
            return page.inner_text("body")[:5000] or "(无文本内容)"

        elif action == "screenshot":
            import base64
            screenshot_data = page.screenshot(full_page=False, type="png")
            encoded = base64.b64encode(screenshot_data).decode("utf-8")
            return f"[BROWSER_SCREENSHOT len={len(encoded)}]\n{encoded}"

        elif action == "html":
            return page.content()[:8000]

        elif action == "get_url":
            return f"当前 URL: {page.url}"

        elif action == "console":
            logs = "\n".join(_browser_console_logs[-50:])
            return logs if logs else "(无 console 日志)"

        elif action == "network":
            errors = "\n".join(_browser_network_errors[-50:])
            return errors if errors else "(无网络错误)"

        elif action == "diagnose":
            if url:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
            import re
            html_content = page.content()
            script_srcs = re.findall(r'<script[^>]*src="([^"]*)"', html_content)
            parts = ["=== 诊断 ===", f"URL: {page.url}", f"标题: {page.title()}"]
            parts.append(f"=== Console ({len(_browser_console_logs)} 条) ===")
            for c in _browser_console_logs[-30:]: parts.append(f"  {c}")
            if _browser_page_errors:
                parts.append(f"=== JS 错误 ({len(_browser_page_errors)} 条) ===")
                for e in _browser_page_errors: parts.append(f"  {e}")
            if _browser_network_errors:
                parts.append(f"=== 网络失败 ({len(_browser_network_errors)} 条) ===")
                for n in _browser_network_errors[-20:]: parts.append(f"  {n}")
            parts.append(f"=== Script 标签 ({len(script_srcs)} 个) ===")
            for s in script_srcs[:10]: parts.append(f"  {s}")
            body_text = page.inner_text("body")[:2000].strip()
            if body_text: parts.append(f"=== 页面内容 ===\n{body_text}")
            else: parts.append("(页面内容为空)")
            return "\n".join(parts)

        elif action == "execute_js":
            if not script: return "execute_js 需要 script 参数"
            result = page.evaluate(script)
            return f"JS 执行结果:\n{result}"

        else:
            return f"未知操作: {action} (可用: open/navigate/click/type/read/screenshot/diagnose/execute_js/close)"

    except Exception as e:
        _cleanup_browser()
        return f"浏览器错误 (已自动清理): {e}"
