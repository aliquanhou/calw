"""tools_browser — 浏览器自动化控制工具。

使用 Playwright 控制 Chromium 浏览器。
v2.1 修复：
  - Playwright 进程泄漏修复：close 时彻底清理所有资源
  - 添加 playwright.stop() 调用
  - 添加显式的进程树清理
  - 自动管理浏览器生命周期
"""

from __future__ import annotations

import time
import threading
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


def _get_or_create_page():
    """获取或创建浏览器页面（线程安全）。"""
    global _browser, _browser_context, _browser_page, _browser_playwright
    global _browser_console_logs, _browser_network_errors, _browser_page_errors

    with _browser_lock:
        # 检查现有页面是否可用
        if _browser_page is not None:
            try:
                _browser_page.title()
                return _browser_page
            except Exception:
                _cleanup_browser()

        # 创建新的浏览器实例
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

            # 监听事件
            _browser_console_logs = []
            _browser_network_errors = []
            _browser_page_errors = []

            _browser_page.on("console", lambda m: _browser_console_logs.append(
                f"[{m.type}] {m.text[:500]}"
            ))
            _browser_page.on("pageerror", lambda e: _browser_page_errors.append(
                str(e)[:500]
            ))
            _browser_page.on("requestfailed", lambda r: _browser_network_errors.append(
                f"{r.url[:200]} -> {str(r.failure) if r.failure else 'unknown'}"
            ))

            return _browser_page

        except Exception as e:
            _cleanup_browser()
            raise RuntimeError(f"浏览器启动失败: {e}")


def _cleanup_browser():
    """彻底清理浏览器资源（线程安全）。

    确保：
      1. 关闭页面
      2. 关闭 context
      3. 关闭浏览器
      4. 停止 playwright（关闭所有子进程）
    """
    global _browser, _browser_context, _browser_page, _browser_playwright

    with _browser_lock:
        try:
            if _browser_page is not None:
                _browser_page.close()
        except Exception:
            pass
        _browser_page = None

        try:
            if _browser_context is not None:
                _browser_context.close()
        except Exception:
            pass
        _browser_context = None

        try:
            if _browser is not None:
                _browser.close()
        except Exception:
            pass
        _browser = None

        try:
            if _browser_playwright is not None:
                _browser_playwright.stop()  # ← 关键修复：杀掉所有 Chromium 子进程
        except Exception:
            pass
        _browser_playwright = None


# ── 工具处理函数 ──


def _handle_browser(action: str = "", url: str = "", selector: str = "",
                    text: str = "", script: str = "") -> str:
    """浏览器自动化操作。

    Args:
        action: 操作类型（navigate/click/type/read/screenshot/diagnose/execute_js/close）
        url: 目标 URL
        selector: CSS 选择器
        text: 要输入的文本
        script: 要执行的 JavaScript

    Returns:
        操作结果字符串
    """
    if action == "close":
        _cleanup_browser()
        return "浏览器已关闭，所有子进程已清理"

    try:
        page = _get_or_create_page()
    except Exception as e:
        return f"浏览器错误: {e}"

    try:
        if action == "navigate":
            if not url:
                return "navigate 需要 url 参数"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(0.5)
            body_text = page.inner_text("body")[:3000] if page.inner_text("body") else "(空页面)"
            return f"导航到: {url}\n标题: {page.title()}\n{body_text}"

        elif action == "click":
            if not selector:
                return "click 需要 selector 参数"
            page.click(selector, timeout=10000)
            time.sleep(0.3)
            return f"已点击: {selector}"

        elif action == "type":
            if not selector:
                return "type 需要 selector 参数"
            page.fill(selector, text or "")
            return f"已输入: {(text or '')[:100]}"

        elif action == "read":
            if selector:
                elements = page.query_selector_all(selector)
                lines = []
                for i, el in enumerate(elements[:20]):
                    if el.inner_text():
                        lines.append(f"[{i}] {el.inner_text()[:200]}")
                return "\n".join(lines) if lines else "(无匹配元素)"
            body = page.inner_text("body")[:5000]
            return body or "(无文本内容)"

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

            parts = ["=== 诊断 ==="]
            parts.append(f"URL: {page.url}")
            parts.append(f"标题: {page.title()}")

            parts.append(f"=== Console ({len(_browser_console_logs)} 条) ===")
            for c in _browser_console_logs[-30:]:
                parts.append(f"  {c}")

            if _browser_page_errors:
                parts.append(f"=== JS 错误 ({len(_browser_page_errors)} 条) ===")
                for e in _browser_page_errors:
                    parts.append(f"  {e}")

            if _browser_network_errors:
                parts.append(f"=== 网络失败 ({len(_browser_network_errors)} 条) ===")
                for n in _browser_network_errors[-20:]:
                    parts.append(f"  {n}")

            parts.append(f"=== Script 标签 ({len(script_srcs)} 个) ===")
            for s in script_srcs[:10]:
                parts.append(f"  {s}")

            body_text = page.inner_text("body")[:2000].strip()
            if body_text:
                parts.append("=== 页面内容 ===")
                parts.append(body_text)
            else:
                parts.append("(页面内容为空)")

            return "\n".join(parts)

        elif action == "execute_js":
            if not script:
                return "execute_js 需要 script 参数"
            result = page.evaluate(script)
            return f"JS 执行结果:\n{result}"

        else:
            return f"未知操作: {action} (可用: navigate/click/type/read/screenshot/diagnose/execute_js/close)"

    except Exception as e:
        # 发生异常时自动清理浏览器实例避免泄漏
        _cleanup_browser()
        return f"浏览器错误 (已自动清理): {e}"
