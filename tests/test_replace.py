"""Tests for SEARCH/REPLACE."""
from __future__ import annotations
import os,sys,tempfile
sys.path.insert(0,os.path.join(os.path.dirname(__file__),".."))
from agent.tools_file import _handle_replace
class TestReplace:
    def test_exact(self):
        with tempfile.NamedTemporaryFile(mode="w",suffix=".py",delete=False,encoding="utf-8")as f:f.write("x=1\ny=2\nz=3\n");tmp=f.name
        try:r=_handle_replace(tmp,"y=2","y=100");assert"成功"in r;assert"y=100"in open(tmp).read()
        finally:os.unlink(tmp)
    def test_fuzzy(self):
        with tempfile.NamedTemporaryFile(mode="w",suffix=".py",delete=False,encoding="utf-8")as f:f.write("def foo():\n    pass\ndef bar():\n    return 42\n");tmp=f.name
        try:r=_handle_replace(tmp,"def bar():\n    return 42","def bar():\n    return 100",partial=True);assert"模糊"in r;assert"return 100"in open(tmp).read()
        finally:os.unlink(tmp)
    def test_not_found(self):assert"不存在"in _handle_replace("/nonexistent","x","y")
    def test_low_confidence(self):
        with tempfile.NamedTemporaryFile(mode="w",suffix=".py",delete=False,encoding="utf-8")as f:f.write("aaa bbb\n");tmp=f.name
        try:assert"无法定位"in _handle_replace(tmp,"完全不同","xxx",partial=True)
        finally:os.unlink(tmp)
    def test_backup(self):
        with tempfile.NamedTemporaryFile(mode="w",suffix=".py",delete=False,encoding="utf-8")as f:f.write("original\n");tmp=f.name
        try:from agent.tools_core import _file_backups;_file_backups.clear();_handle_replace(tmp,"original","modified");assert tmp in _file_backups
        finally:os.unlink(tmp)
