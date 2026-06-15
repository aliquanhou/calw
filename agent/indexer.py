"""indexer — 项目文件索引与语义搜索（轻量级 TF-IDF）。"""
from __future__ import annotations
import math, os, re, threading, time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
SKIP_DIRS = {".git","__pycache__","node_modules",".venv",".env","venv",".tox","build","dist",".idea",".vscode",".claude"}
SKIP_EXTS = {".pyc",".pyo",".exe",".dll",".so",".dylib",".png",".jpg",".jpeg",".gif",".ico",".svg",".zip",".tar",".gz",".7z"}
MAX_FILE_SIZE = 512*1024
_WORD_RE = re.compile(r'[a-zA-Z_]\w{2,}')
@dataclass
class FileIndex:
    path: str; name: str; ext: str; size: int; lines: int; mtime: float
    words: Counter = field(default_factory=Counter); imports: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
class Indexer:
    def __init__(self, root: str | None = None):
        self.root = root or os.getcwd()
        self._files: dict[str, FileIndex] = {}; self._inverted: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.Lock(); self._dirty = True
    def build(self, force: bool = False) -> int:
        if not force and not self._dirty: return len(self._files)
        files: dict[str, FileIndex] = {}; inverted: dict[str, set[str]] = defaultdict(set)
        for root, dirs, fnames in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in SKIP_EXTS: continue
                fpath = os.path.join(root, fname)
                try:
                    st = os.stat(fpath)
                    if st.st_size > MAX_FILE_SIZE: continue
                    content = open(fpath, "r", encoding="utf-8", errors="replace").read()
                except: continue
                idx = FileIndex(path=fpath, name=fname, ext=ext, size=st.st_size, lines=content.count("\n")+1, mtime=st.st_mtime)
                idx.words = Counter(_WORD_RE.findall(content.lower()))
                if ext == ".py":
                    for m in re.finditer(r'^(?:from|import)\s+(\S+)', content, re.MULTILINE): idx.imports.append(m.group(1))
                    for m in re.finditer(r'^\s*(?:class|def|async def)\s+(\w+)', content, re.MULTILINE): idx.symbols.append(m.group(1))
                for word, count in idx.words.items():
                    if count >= 2: inverted[word].add(fpath)
                files[fpath] = idx
        with self._lock: self._files = files; self._inverted = inverted; self._dirty = False
        return len(files)
    def search(self, query: str, top_n: int = 10) -> list[dict]:
        if self._dirty or not self._files: self.build()
        with self._lock: files = dict(self._files); inverted = dict(self._inverted)
        words = _WORD_RE.findall(query.lower())
        if not words: return []
        n_docs = len(files); scores: dict[str, float] = Counter()
        for word in words:
            if word not in inverted: continue
            idf = math.log(1 + n_docs / (1 + len(inverted[word])))
            for fpath in inverted[word]:
                scores[fpath] += math.log(1 + files[fpath].words.get(word, 0)) * idf
        for word in words:
            for fpath in files:
                if word in files[fpath].name.lower(): scores[fpath] += 0.5
        results = []
        for fpath, score in scores.most_common(top_n):
            if score > 0:
                idx = files[fpath]
                results.append({"path":fpath,"name":idx.name,"ext":idx.ext,"lines":idx.lines,
                               "score":round(score,2),"symbols":idx.symbols[:5]})
        return results
    def search_code(self, keyword: str, top_n: int = 20) -> list[str]:
        if self._dirty or not self._files: self.build()
        with self._lock: files = dict(self._files)
        results = []; seen = set(); kw = keyword.lower()
        for fpath, idx in files.items():
            for sym in idx.symbols:
                if kw in sym.lower() and (fpath, sym) not in seen: seen.add((fpath, sym)); results.append(f"{sym} → {os.path.relpath(fpath, self.root)}")
        return results[:top_n]
    def get_stats(self) -> dict:
        if self._dirty or not self._files: return {"files":0,"words":0}
        with self._lock: return {"files":len(self._files),"words":len(self._inverted),
                                 "last_index":time.strftime("%H:%M:%S",time.localtime(time.time()))}
_indexer: Indexer | None = None
def get_indexer(root: str | None = None) -> Indexer:
    global _indexer
    if _indexer is None: _indexer = Indexer(root)
    return _indexer
def quick_search(query: str, root: str | None = None) -> list[dict]:
    return get_indexer(root).search(query)
