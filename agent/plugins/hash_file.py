"""Sample plugin — hash_file: compute file hash.

Install: copy this file to agent/plugins/hash_file.py
"""
from __future__ import annotations
import hashlib
import os


def register():
    return {
        "name": "hash_file",
        "description": "计算文件的 MD5 / SHA256 哈希值",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要计算哈希的文件路径",
                },
                "algorithm": {
                    "type": "string",
                    "enum": ["md5", "sha256"],
                    "description": "哈希算法（默认 md5）",
                },
            },
            "required": ["file_path"],
        },
        "handler": handler,
    }


def handler(params: dict) -> str:
    path = params.get("file_path", "")
    algo = params.get("algorithm", "md5")

    if not os.path.exists(path):
        return f"错误: 文件不存在: {path}"

    try:
        h = hashlib.new(algo)
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return f"{algo.upper()}({os.path.basename(path)}) = {h.hexdigest()}"
    except Exception as e:
        return f"错误: {e}"
