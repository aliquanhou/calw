"""Tests for agent.indexer — Indexer, FileIndex, search, search_code."""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.indexer import Indexer, FileIndex, get_indexer, quick_search, SKIP_DIRS, SKIP_EXTS


class TestFileIndex:
    def test_defaults(self):
        idx = FileIndex(path="/a.py", name="a.py", ext=".py", size=100, lines=5, mtime=time.time())
        assert idx.path == "/a.py"
        assert idx.words == {}
        assert idx.imports == []
        assert idx.symbols == []


class TestIndexerBuild:
    def test_build_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = Indexer(tmp)
            count = idx.build()
            assert count == 0
            stats = idx.get_stats()
            assert stats["files"] == 0

    def test_build_single_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "hello.py"), "w") as f:
                f.write("def foo():\n    pass\n")
            idx = Indexer(tmp)
            count = idx.build()
            assert count == 1

    def test_build_multiple_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ["a.py", "b.py", "c.py"]:
                with open(os.path.join(tmp, name), "w") as f:
                    f.write("x = 1\n")
            idx = Indexer(tmp)
            count = idx.build()
            assert count == 3

    def test_skips_pycache(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "__pycache__"))
            with open(os.path.join(tmp, "__pycache__", "cache.pyc"), "w") as f:
                f.write("garbage")
            with open(os.path.join(tmp, "real.py"), "w") as f:
                f.write("code = 1")
            idx = Indexer(tmp)
            count = idx.build()
            assert count == 1  # 只索引了 real.py

    def test_skips_binary_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ext in [".exe", ".png", ".zip"]:
                with open(os.path.join(tmp, f"file{ext}"), "w") as f:
                    f.write("garbage")
            with open(os.path.join(tmp, "real.py"), "w") as f:
                f.write("code = 1")
            idx = Indexer(tmp)
            count = idx.build()
            assert count == 1

    def test_extracts_symbols_from_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "mymod.py"), "w") as f:
                f.write("""
class MyClass:
    def my_method(self):
        pass

def my_function():
    pass
""")
            idx = Indexer(tmp)
            idx.build()
            with idx._lock:
                file_idx = list(idx._files.values())[0]
            assert "MyClass" in file_idx.symbols
            assert "my_method" in file_idx.symbols
            assert "my_function" in file_idx.symbols

    def test_extracts_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "mymod.py"), "w") as f:
                f.write("import os\nfrom collections import defaultdict\n")
            idx = Indexer(tmp)
            idx.build()
            with idx._lock:
                file_idx = list(idx._files.values())[0]
            assert "os" in file_idx.imports
            assert "collections" in file_idx.imports

    def test_skip_large_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "large.py"), "w") as f:
                f.write("x" * (600 * 1024))  # 600KB > max 512KB
            idx = Indexer(tmp)
            count = idx.build()
            assert count == 0

    def test_force_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.py"), "w") as f:
                f.write("def foo(): pass\n")
            idx = Indexer(tmp)
            idx.build()
            count1 = idx._dirty = True  # simulate new changes
            count2 = idx.build(force=True)
            assert count2 >= 1


class TestIndexerSearch:
    def test_search_basic(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "utils.py"), "w") as f:
                f.write("""
def parse_config(config_path):
    import json
    with open(config_path) as f:
        data = json.load(f)
    return validate_config(data)

def validate_config(config):
    if not isinstance(config, dict):
        return False
    for key in config:
        if not key:
            return False
    return True
""")
            idx = Indexer(tmp)
            idx.build()
            results = idx.search("config")
            assert len(results) >= 1
            assert any("utils.py" in r["path"] for r in results)

    def test_search_score_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "server.py"), "w") as f:
                f.write("""
import requests

def start_server(host, port):
    return f"http://{host}:{port}"

def stop_server():
    pass

server = start_server
""")
            idx = Indexer(tmp)
            idx.build()
            results = idx.search("server")
            assert len(results) >= 1
            assert results[0]["score"] > 0

    def test_search_empty_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.py"), "w") as f:
                f.write("x = 1\n")
            idx = Indexer(tmp)
            idx.build()
            assert idx.search("") == []

    def test_search_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.py"), "w") as f:
                f.write("x = 1\n")
            idx = Indexer(tmp)
            idx.build()
            assert idx.search("xyznonexistent") == []

    def test_search_multiple_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "user_auth.py"), "w") as f:
                f.write("""
def login(username, password):
    return authenticate(username, password)

def logout(session):
    session.clear()
""")
            with open(os.path.join(tmp, "payment.py"), "w") as f:
                f.write("""
def process_payment(amount, currency):
    return charge(amount, currency)
""")
            idx = Indexer(tmp)
            idx.build()
            # 搜索 auth 应该优先返回 user_auth.py
            results = idx.search("login auth")
            paths = [r["path"] for r in results]
            assert any("user_auth" in p for p in paths)


class TestIndexerSearchCode:
    def test_search_code_finds_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "mymod.py"), "w") as f:
                f.write("class DataProcessor:\n    pass\n")
            idx = Indexer(tmp)
            idx.build()
            results = idx.search_code("DataProcessor")
            assert len(results) >= 1
            assert "DataProcessor" in results[0]

    def test_search_code_partial_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "mymod.py"), "w") as f:
                f.write("class DataProcessor:\n    pass\nclass DataLoader:\n    pass\n")
            idx = Indexer(tmp)
            idx.build()
            results = idx.search_code("Data")
            assert len(results) >= 2

    def test_search_code_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "mymod.py"), "w") as f:
                f.write("x = 1\n")
            idx = Indexer(tmp)
            idx.build()
            assert idx.search_code("NotFound") == []

    def test_search_code_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "mymod.py"), "w") as f:
                f.write("class USERMODEL:\n    pass\n")
            idx = Indexer(tmp)
            idx.build()
            results = idx.search_code("usermodel")
            assert len(results) >= 1


class TestIndexerStats:
    def test_stats_before_build(self):
        idx = Indexer()
        stats = idx.get_stats()
        assert stats["files"] == 0
        assert stats["words"] == 0

    def test_stats_after_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "test.py"), "w") as f:
                f.write("""
def hello():
    return "hello world"
hello()
""")
            idx = Indexer(tmp)
            idx.build()
            stats = idx.get_stats()
            assert stats["files"] >= 1
            assert stats["words"] > 0
            assert isinstance(stats["last_index"], str)


class TestIndexerSingleton:
    def test_get_indexer_singleton(self):
        from agent.indexer import get_indexer
        i1 = get_indexer()
        i2 = get_indexer()
        assert i1 is i2

    def test_quick_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "app.py"), "w") as f:
                f.write("""
def main():
    app = create_app()
    app.run()

def create_app():
    flask_app = Flask(__name__)
    return flask_app

if __name__ == "__main__":
    app = create_app()
    app.run()
""")
            from agent.indexer import Indexer
            idx = Indexer(tmp)
            idx.build()
            results = idx.search("app")
            assert len(results) >= 1


class TestSkipDirs:
    def test_all_skip_dirs_defined(self):
        """SKIP_DIRS 包含所有常见的忽略目录。"""
        essential = {".git", "__pycache__", "node_modules", ".venv", "build"}
        for d in essential:
            assert d in SKIP_DIRS, f"缺少 {d}"

    def test_skip_dirs_suppresses_walk(self):
        """Indexer 的 build 应该跳过 SKIP_DIRS 中的目录。"""
        with tempfile.TemporaryDirectory() as tmp:
            for d in SKIP_DIRS:
                if d and not d.startswith("."):
                    continue
                try:
                    os.makedirs(os.path.join(tmp, d, "sub"))
                    with open(os.path.join(tmp, d, "sub", "code.py"), "w") as f:
                        f.write("x=1\n")
                except OSError:
                    pass
            with open(os.path.join(tmp, "main.py"), "w") as f:
                f.write("x=1\n")
            idx = Indexer(tmp)
            count = idx.build()
            # 应该只索引 main.py，跳过所有 SKIP_DIRS
            assert count <= 1
