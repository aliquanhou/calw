"""Build error pattern recognition engine.

Matches build errors against known patterns to provide instant fixes.
Records new patterns from build output for future matching.

Usage:
    engine = PatternEngine()
    match = engine.match(build_output)
    if match:
        fix = match["fix"]  # suggested fix command/description
    else:
        engine.record(build_output, command, context)
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

PATTERNS_FILE = os.path.join(os.path.dirname(__file__), "patterns.json")

# ── Pattern definitions ──

PATTERN_SCHEMA = {
    "signature": str,       # regex to match against build output (MUST be error-specific)
    "label": str,           # human-readable name for this error
    "fix": str,             # suggested fix description or command
    "category": str,        # "incompatibility" | "missing_dep" | "config" | "syntax" | "env" | "other"
    "severity": str,        # "hint" | "warning" | "error"
    "hit_count": int,       # how many times this pattern has matched
    "first_seen": float,    # timestamp of first match
    "last_seen": float,     # timestamp of most recent match
}


def _default_patterns() -> list[dict]:
    return [
        {
            "signature": r"NativeWind.*(?:not compat|version|unrecognized|failed to resolve|only supports)",
            "label": "NativeWind 版本不兼容",
            "fix": "NativeWind 需要匹配的 Tailwind CSS 版本。NativeWind v2 需要 Tailwind v3，NativeWind v4 需要 Tailwind v4。运行 npm list tailwindcss nativewind 检查版本，然后安装兼容版本。",
            "category": "incompatibility",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"Module (?:not found|parse failed:).*'[^']*\.css'",
            "label": "CSS Module 加载失败",
            "fix": "确保 webpack/metro 配置了 CSS loader，或检查 CSS 文件路径是否正确",
            "category": "missing_dep",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"Module.*not found.*from.*node_modules",
            "label": "Node 模块依赖缺失",
            "fix": "运行 npm install 或 yarn install，检查 package.json 中是否声明了该依赖",
            "category": "missing_dep",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"Can't resolve '[^']+' in '.*node_modules'",
            "label": "嵌套依赖缺失",
            "fix": "尝试删除 node_modules 并重新安装: rm -rf node_modules && npm install",
            "category": "missing_dep",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"Property '[^']+' doesn't exist",
            "label": "TypeScript 类型错误",
            "fix": "检查类型定义是否完整，或添加类型断言/声明",
            "category": "syntax",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"TS\d+:|TypeScript.*error|Cannot find name|类型 \"[^\"]+\" 上不存在属性",
            "label": "TypeScript 编译错误",
            "fix": "运行 tsc --noEmit 查看详细错误，修复类型不匹配",
            "category": "syntax",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"Unknown word|CSS Syntax Error|Unknown property",
            "label": "CSS 语法错误",
            "fix": "检查 CSS/Tailwind 类名拼写，确保使用的 Tailwind 版本支持该类名",
            "category": "syntax",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"Duplicate identifier|Identifier '[^']+' already declared",
            "label": "重复声明错误",
            "fix": "检查是否存在同名变量/导入，使用 import type 或重命名",
            "category": "syntax",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"(?:ERR!|error|Error).*code ELIFECYCLE",
            "label": "npm 生命周期脚本失败",
            "fix": "检查 package.json 中的 scripts 配置，确认入口文件存在且路径正确",
            "category": "config",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"(?:ERR!|error).*code ENOENT",
            "label": "文件或命令不存在",
            "fix": "检查路径是否正确，确认命令已安装 (which/npm install -g)",
            "category": "env",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"(?:ERR!|error).*code EACCES|EPERM",
            "label": "权限不足",
            "fix": "以管理员身份运行，或修复目录权限 (icacls / chmod)",
            "category": "env",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"Expo.*web.*(?:not support|not compatible|error|fail)",
            "label": "Expo Web 构建失败",
            "fix": "检查 expo-cli 版本，确保 @expo/webpack-config 已安装: npm install @expo/webpack-config",
            "category": "incompatibility",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"Watchman.*(?:error|not found|fail)",
            "label": "Watchman 不可用",
            "fix": "安装 Watchman: choco install watchman 或忽略 (watchman 非必需但影响性能)",
            "category": "env",
            "severity": "warning",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"Port (\d+) .*already in use|EADDRINUSE",
            "label": "端口被占用",
            "fix": "使用不同的端口，或杀掉占用进程: netstat -ano | findstr :<端口> && taskkill /F /PID <PID>",
            "category": "env",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"npm ERR!.*peer dep|unmet peer|peer dependency",
            "label": "peer 依赖冲突",
            "fix": "使用 --legacy-peer-deps 安装: npm install --legacy-peer-deps",
            "category": "missing_dep",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"A module in BSS is trying to use the JSX name resolution callback",
            "label": "React Native 模块 JSX 名解析冲突",
            "fix": "检查是否使用了不兼容的 RN 版本，尝试 `npx react-native@latest init` 或降级模板版本",
            "category": "incompatibility",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"(?:Invariant Violation|React Native.*version mismatch|JSX value should be either an expression or a quoted JSX text)",
            "label": "React Native SDK 版本不匹配",
            "fix": "检查 react-native 版本与项目模板版本是否一致，运行 npx react-native info 查看环境信息",
            "category": "incompatibility",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"Unable to resolve module (?!.*node_modules)",
            "label": "模块解析失败（本地文件）",
            "fix": "检查 import 路径是否正确，文件是否存在，路径大小写是否匹配",
            "category": "syntax",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"Metro.*(?:has encountered an error|unexpected token|transform.*failed)",
            "label": "Metro bundler 编译错误",
            "fix": "清除 Metro 缓存: npx react-native start --reset-cache，或删除 node_modules/.cache 目录",
            "category": "env",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"error:0308010C|digital envelope routines.*unsupported|ERR_OSSL_EVP_UNSUPPORTED",
            "label": "OpenSSL 不兼容（Node.js 17+）",
            "fix": "设置 NODE_OPTIONS=--openssl-legacy-provider 环境变量",
            "category": "env",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
        {
            "signature": r"gyp(?: ERR!|:).*node-gyp|ERR! node-gyp",
            "label": "node-gyp 编译失败",
            "fix": "安装构建工具: npm install --global windows-build-tools，或检查 Python/VC++ 环境",
            "category": "env",
            "severity": "error",
            "hit_count": 0,
            "first_seen": 0,
            "last_seen": 0,
        },
    ]


# ── PatternEngine ──

class PatternEngine:
    """Load, match, and record build error patterns."""

    def __init__(self):
        self._patterns: list[dict] = []
        self._compiled: list[tuple[re.Pattern, dict]] = []
        self.load()

    # ── Public API ──

    def load(self) -> None:
        """Load patterns from disk, falling back to defaults."""
        if os.path.exists(PATTERNS_FILE):
            try:
                with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._patterns = data
                else:
                    self._patterns = data.get("patterns", [])
            except Exception:
                self._patterns = _default_patterns()
        else:
            self._patterns = _default_patterns()
        self._recompile()

    def save(self) -> str:
        """Persist patterns to disk."""
        try:
            os.makedirs(os.path.dirname(PATTERNS_FILE), exist_ok=True)
            data = {"version": 1, "updated": time.time(), "patterns": self._patterns}
            with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return f"已保存 {len(self._patterns)} 个构建错误模式"
        except Exception as e:
            return f"保存构建错误模式失败: {e}"

    def match(self, build_output: str) -> dict | None:
        """Match build output against known patterns.

        Returns the matched pattern dict (with fix info) or None.
        Sets hit_count/last_seen on match.
        """
        if not build_output:
            return None
        for compiled, pattern in self._compiled:
            if compiled.search(build_output):
                pattern["hit_count"] = pattern.get("hit_count", 0) + 1
                now = time.time()
                if pattern.get("first_seen", 0) == 0:
                    pattern["first_seen"] = now
                pattern["last_seen"] = now
                return pattern
        return None

    def record(self, build_output: str, command: str, context: str = "") -> str | None:
        """Record a new pattern from unrecognized build error.

        Extracts a signature from the first significant error line.
        Returns the new pattern label, or None if recording failed.
        """
        label = self._extract_label(build_output)
        if not label:
            return None

        sig = self._extract_signature(build_output)
        if not sig:
            return None

        # Check for near-duplicate (similar label already exists)
        for p in self._patterns:
            existing_label = p.get("label", "")
            if self._similar(label, existing_label):
                p["hit_count"] = p.get("hit_count", 0) + 1
                p["last_seen"] = time.time()
                return f"更新现有模式: {existing_label}"

        new_pattern = {
            "signature": sig,
            "label": label,
            "fix": f"自动记录的模式。命令: {command[:200]}",
            "category": "other",
            "severity": "error",
            "hit_count": 1,
            "first_seen": time.time(),
            "last_seen": time.time(),
        }
        self._patterns.append(new_pattern)
        self._recompile()
        self.save()
        return f"已记录新模式: {label}"

    def get_stats(self) -> dict:
        """Get pattern library statistics."""
        total = len(self._patterns)
        matches = sum(1 for p in self._patterns if p.get("hit_count", 0) > 0)
        cats: dict[str, int] = {}
        for p in self._patterns:
            c = p.get("category", "other")
            cats[c] = cats.get(c, 0) + 1
        return {
            "total_patterns": total,
            "matched_patterns": matches,
            "categories": cats,
        }

    # ── Internal ──

    def _recompile(self) -> None:
        self._compiled = []
        for p in self._patterns:
            sig = p.get("signature", "")
            if sig:
                try:
                    compiled = re.compile(sig, re.IGNORECASE | re.DOTALL)
                    self._compiled.append((compiled, p))
                except re.error:
                    pass  # skip invalid regex

    def _extract_label(self, output: str) -> str | None:
        """Extract a human-readable label from build error output."""
        lines = output.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(kw in line.lower() for kw in ("error", "错误", "fail", "无法")):
                return line[:120]
        return lines[0][:120] if lines else None

    def _extract_signature(self, output: str) -> str | None:
        """Extract a regex signature from build error output."""
        lines = output.split("\n")
        error_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(kw in line.lower() for kw in ("error", "错误", "fail", "无法", "exception")):
                error_lines.append(line)
            if len(error_lines) >= 3:
                break

        if not error_lines:
            error_lines = [lines[0]] if lines else []

        # Build regex: escape but preserve key patterns (quotes, numbers, paths)
        parts = []
        for el in error_lines[:2]:
            el = re.escape(el)[:200]
            parts.append(el)
        return "|".join(parts)

    def _similar(self, a: str, b: str) -> bool:
        """Simple similarity check: 60%+ common words."""
        wa = set(a.lower().split())
        wb = set(b.lower().split())
        if not wa or not wb:
            return False
        common = wa & wb
        return len(common) / max(len(wa), len(wb)) >= 0.6


# ── Module-level singleton ──

_engine: PatternEngine | None = None


def get_engine() -> PatternEngine:
    global _engine
    if _engine is None:
        _engine = PatternEngine()
    return _engine
