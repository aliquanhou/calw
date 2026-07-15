"""tools_web — 网络工具：HTTP 请求、网络搜索、用户提问。

v2.1 重写：
  - 统一返回格式 + 类型注解
  - 更清晰的错误处理
  - JSON 自动解析与格式化
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def _handle_web(url: str = "", method: str = "GET", data: str = "", headers: str = "") -> str:
    """HTTP 请求。发送 GET/POST 请求并返回响应内容。

    Args:
        url: 请求 URL
        method: GET | POST
        data: POST 请求体
        headers: JSON 格式的请求头，如 '{"Authorization": "Bearer xxx"}'

    Returns:
        响应内容
    """
    if not url:
        return "[错误] web 需要 url 参数"

    try:
        req = urllib.request.Request(url, method=method)
        if headers:
            try:
                for k, v in json.loads(headers).items():
                    req.add_header(k, v)
            except json.JSONDecodeError:
                pass
        if method == "POST" and data:
            req.data = data.encode("utf-8")
            req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            info = f"[HTTP] {resp.status} {resp.reason} | {len(body)} 字节"
            if len(body) > 5000:
                body = body[:5000] + f"\n...(截断，共 {len(body)} 字节)"
            return f"{info}\n\n{body}"

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:1000]
        return f"[HTTP] {e.code} {e.reason}\n{err_body}"
    except Exception as e:
        return f"[错误] 请求失败: {e}"


def _handle_web_search(query: str = "", max_results: int = 5) -> str:
    """网络搜索。通过搜索引擎获取实时信息。

    Args:
        query: 搜索关键词
        max_results: 结果数量（1-10）

    Returns:
        搜索结果
    """
    if not query:
        return "[错误] web_search 需要 query 参数"

    # LLM 可能传字符串，确保转为 int
    try:
        max_results = int(max_results)
    except (ValueError, TypeError):
        max_results = 5
    max_results = min(max(max_results, 1), 10)

    try:
        import requests as rqs
        import re as _re

        resp = rqs.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        resp.raise_for_status()
        html = resp.text

        results = [
            (_re.sub(r'<[^>]+>', "", m.group(2)).strip(), m.group(1))
            for m in _re.finditer(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>',
                html,
            )
        ]
        snippets = [
            _re.sub(r'<[^>]+>', "", s).strip()[:200]
            for s in _re.findall(
                r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>',
                html,
            )
        ]

        lines = [f"[搜索] 🔍 {query}", ""]
        for i, (title, link) in enumerate(results[:max_results]):
            lines.append(f"{i+1}. {title}")
            if i < len(snippets) and snippets[i]:
                lines.append(f"   {snippets[i]}")
            lines.append(f"   {link}")
            lines.append("")

        output = "\n".join(lines).strip()
        return output if output else f"[搜索] 无结果: {query}"

    except ImportError:
        return "[错误] 需安装 requests 库: pip install requests"
    except Exception as e:
        return f"[错误] 搜索失败: {e}"


def _handle_ask_user(question: str = "", options: str = "",
                     analysis: str = "", recommended: str = "") -> str:
    """智能提问用户：带分析 + 多选项 + 推荐。

    Args:
        question: 问题描述
        options: JSON 格式的选项列表
        analysis: 分析文本（用 \\n 换行）
        recommended: 推荐选项索引或名称

    Returns:
        格式化后的提问界面
    """
    if not question:
        return "[错误] ask_user 需要 question 参数"

    lines = [
        "",
        "=" * 50,
        "🤔 需要你的决定",
        "=" * 50,
        "",
        f"📌 **{question}**",
        "",
    ]

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
                    is_recommended = (
                        recommended and (
                            str(i) == str(recommended)
                            or str(i + 1) == str(recommended)
                            or v.startswith(str(recommended))
                            or recommended in v
                        )
                    )
                    rec_str = " ⭐" if is_recommended else ""
                    letter = chr(65 + i)
                    lines.append(f"  [{letter}] {v}{rec_str}")
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
