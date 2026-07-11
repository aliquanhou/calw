"""project_map — 自动扫描项目结构，生成项目地图注入 system prompt。"""
from __future__ import annotations

import os
from pathlib import Path

SKIP_DIRS: set[str] = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", ".env",
    ".tox", "build", "dist", ".idea", ".vscode", ".mypy_cache",
    ".pytest_cache", ".claude", ".github", "site-packages",
}

ENTRY_PATTERNS: set[str] = {
    "main.py", "app.py", "index.py", "cli.py", "__main__.py",
    "index.js", "index.ts", "index.tsx", "server.js", "server.ts",
    "entry.py", "entry.js", "entry.ts", "index.html", "index.htm",
}

DEP_FILES: set[str] = {
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "Pipfile", "Pipfile.lock", "poetry.lock",
    "package.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
    "Gemfile", "Gemfile.lock", "Makefile",
}

_SOURCE_EXTENSIONS: dict[str, dict] = {
    ".py":   {"lang": "Python",      "test_markers": ("test_", "_test")},
    ".js":   {"lang": "JavaScript",  "test_markers": (".test.", ".spec.")},
    ".ts":   {"lang": "TypeScript",  "test_markers": (".test.", ".spec.")},
    ".tsx":  {"lang": "TSX/React",   "test_markers": (".test.", ".spec.")},
    ".jsx":  {"lang": "JSX/React",   "test_markers": (".test.", ".spec.")},
    ".go":   {"lang": "Go",          "test_markers": ("_test",)},
    ".rs":   {"lang": "Rust",        "test_markers": ("_test",)},
    ".java": {"lang": "Java",        "test_markers": ("Test", "test")},
    ".c":    {"lang": "C",           "test_markers": ()},
    ".cpp":  {"lang": "C++",         "test_markers": ()},
    ".h":    {"lang": "C Header",    "test_markers": ()},
    ".hpp":  {"lang": "C++ Header",  "test_markers": ()},
    ".rb":   {"lang": "Ruby",        "test_markers": ("_test", "_spec")},
    ".swift":{"lang": "Swift",       "test_markers": ("Test",)},
    ".kt":   {"lang": "Kotlin",      "test_markers": ("Test",)},
    ".vue":  {"lang": "Vue",         "test_markers": (".test.", ".spec.")},
    ".css":  {"lang": "CSS",         "test_markers": ()},
    ".scss": {"lang": "SCSS",        "test_markers": ()},
    ".html": {"lang": "HTML",        "test_markers": ()},
    ".sql":  {"lang": "SQL",         "test_markers": ()},
    ".sh":   {"lang": "Shell",       "test_markers": ()},
    ".bat":  {"lang": "Batch",       "test_markers": ()},
    ".ps1":  {"lang": "PowerShell",  "test_markers": ()},
}


class ProjectMap:
    def __init__(self, root_path: str | None = None):
        self.root_path = Path(root_path or os.getcwd()).resolve()
        self._cache: dict | None = None

    def scan(self) -> dict:
        if self._cache is not None:
            return self._cache
        root = self.root_path
        result = {
            "project_root": str(root), "project_name": root.name,
            "language_stats": {}, "entry_points": [], "source_files": [],
            "test_files": [], "dependencies": {}, "build_scripts": [],
            "config_files": [], "total_files": 0, "total_dirs": 0,
        }
        lang_counts = {}; lang_sizes = {}
        total_files = 0; total_dirs = 0
        try:
            for dirpath, dirnames, filenames in os.walk(str(root)):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                rel_dir = os.path.relpath(dirpath, str(root))
                if rel_dir == ".": rel_dir = ""
                total_dirs += len(dirnames)
                total_files += len(filenames)
                for f in filenames:
                    rel_path = os.path.join(rel_dir, f) if rel_dir else f
                    ext = os.path.splitext(f)[1].lower()
                    filepath = os.path.join(dirpath, f)
                    if ext in _SOURCE_EXTENSIONS:
                        info = _SOURCE_EXTENSIONS[ext]
                        lang = info["lang"]
                        lang_counts[lang] = lang_counts.get(lang, 0) + 1
                        try:
                            lang_sizes[lang] = lang_sizes.get(lang, 0) + os.path.getsize(filepath)
                        except OSError: pass
                        is_test = self._is_test_file(rel_path, info["test_markers"])
                        entry = {"path": rel_path, "language": lang, "is_test": is_test}
                        result["source_files"].append(entry)
                        if is_test:
                            result["test_files"].append(rel_path)
                    if f in ENTRY_PATTERNS:
                        result["entry_points"].append(rel_path)
                    if f in DEP_FILES:
                        try:
                            content = open(filepath, "r", encoding="utf-8", errors="replace").read()
                            result["dependencies"][rel_path] = content[:3000]
                        except Exception:
                            result["dependencies"][rel_path] = "(不可读)"
                    base = f.lower()
                    if base in ("makefile", "dockerfile", "justfile", "rakefile"):
                        result["build_scripts"].append(rel_path)
                    elif ext in (".bat", ".sh", ".ps1") and "build" in base:
                        result["build_scripts"].append(rel_path)
                    if ext in (".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".conf"):
                        if f not in DEP_FILES and "package" not in f.lower():
                            result["config_files"].append(rel_path)
        except PermissionError: pass
        result["language_stats"] = {
            lang: {"count": count, "size_kb": round(lang_sizes.get(lang, 0) / 1024, 1)}
            for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1])
        }
        result["total_files"] = total_files; result["total_dirs"] = total_dirs
        self._cache = result
        return result

    @staticmethod
    def _is_test_file(rel_path: str, markers: tuple[str, ...]) -> bool:
        if "test" in rel_path.lower(): return True
        fname = os.path.basename(rel_path)
        stem = os.path.splitext(fname)[0]
        for m in markers:
            if m in stem: return True
        return False

    def to_prompt_block(self) -> str:
        m = self.scan()
        if not m.get("source_files"):
            return ""
        lines = []; self._add_overview(lines, m)
        self._add_languages(lines, m); self._add_entry_points(lines, m)
        self._add_source_files(lines, m); self._add_test_files(lines, m)
        self._add_dependencies(lines, m); self._add_build_and_config(lines, m)
        return "\n".join(lines)

    def _add_overview(self, lines, m):
        lines.append("## 📁 项目地图"); lines.append("")
        lines.append(f"**项目**: {m['project_name']}")
        lines.append(f"**根目录**: `{m['project_root']}`")
        lines.append(f"**源文件**: {len(m['source_files'])} 个 | 总 {m['total_files']} 文件 / {m['total_dirs']} 目录")
        lines.append("")

    def _add_languages(self, lines, m):
        stats = m.get("language_stats")
        if stats:
            lines.append("### 语言分布")
            for lang, s in stats.items():
                bar = "█" * min(s["count"], 24)
                lines.append(f"  {lang}: {s['count']} 文件 ({s['size_kb']} KB) {bar}")
            lines.append("")

    def _add_entry_points(self, lines, m):
        eps = m.get("entry_points", [])
        if eps:
            lines.append("### 入口文件")
            for ep in eps: lines.append(f"  🚪 `{ep}`")
            lines.append("")

    def _add_source_files(self, lines, m):
        by_lang = {}
        for sf in m["source_files"]:
            by_lang.setdefault(sf["language"], []).append(sf["path"])
        lines.append("### 源码结构")
        for lang, files in sorted(by_lang.items()):
            test_count = sum(1 for f in files if "test" in f.lower())
            total = len(files)
            lines.append(f"  📦 **{lang}** ({total} 文件, {test_count} 测试)")
            shown = 0
            for f in files:
                if shown >= 12: break
                if "test" not in f.lower():
                    lines.append(f"    📄 `{f}`"); shown += 1
            if total - shown - test_count > 0:
                lines.append(f"    ... 还有 {total - shown - test_count} 个非测试文件")
        lines.append("")

    def _add_test_files(self, lines, m):
        tfs = m.get("test_files", [])
        if tfs:
            lines.append(f"### 测试文件 ({len(tfs)} 个)")
            lines.append(f"框架: `pytest`")
            for tf in tfs[:15]: lines.append(f"  🧪 `{tf}`")
            if len(tfs) > 15: lines.append(f"  ... 还有 {len(tfs)-15} 个")
            lines.append("")

    def _add_dependencies(self, lines, m):
        deps = m.get("dependencies", {})
        if deps:
            lines.append("### 依赖配置")
            for dep_file, content in list(deps.items())[:4]:
                short_lines = content.split("\n")[:6]
                lines.append(f"  📦 `{dep_file}`")
                for sl in short_lines:
                    stripped = sl.strip()
                    if stripped: lines.append(f"    {stripped}")
            lines.append("")

    def _add_build_and_config(self, lines, m):
        builds = m.get("build_scripts", [])
        configs = m.get("config_files", [])
        if builds:
            lines.append(f"### 构建脚本 ({len(builds)})")
            for b in builds[:8]: lines.append(f"  🔧 `{b}`")
            lines.append("")
        if configs:
            lines.append(f"### 配置文件 ({len(configs)})")
            for c in configs[:8]: lines.append(f"  ⚙️ `{c}`")
            lines.append("")

    def invalidate(self):
        self._cache = None
