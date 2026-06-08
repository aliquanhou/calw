"""
file_ops 模块的单元测试
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from agent.utils.file_ops import (
    append_file,
    file_hash,
    file_size,
    list_directory_tree,
    list_files,
    read_file,
    read_json,
    safe_filename,
    write_file,
    write_json,
)


class TestFileOps(unittest.TestCase):
    """文件操作工具函数测试"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test.txt")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_and_read_file(self):
        """测试写入和读取文件"""
        content = "Hello, Claw!"
        write_file(self.test_file, content)
        result = read_file(self.test_file)
        self.assertEqual(result, content)

    def test_read_file_not_found(self):
        """测试读取不存在的文件"""
        with self.assertRaises(FileNotFoundError):
            read_file("nonexistent_file.txt")

    def test_append_file(self):
        """测试追加文件内容"""
        write_file(self.test_file, "第一行\n")
        append_file(self.test_file, "第二行\n")
        result = read_file(self.test_file)
        self.assertEqual(result, "第一行\n第二行\n")

    def test_file_size(self):
        """测试获取文件大小"""
        content = "测试内容"
        write_file(self.test_file, content)
        size = file_size(self.test_file)
        # 中文字符 UTF-8 下每个占 3 字节
        self.assertGreater(size, 0)

    def test_file_hash_md5(self):
        """测试 MD5 哈希计算"""
        content = "Hello, Claw!"
        write_file(self.test_file, content)
        h = file_hash(self.test_file, "md5")
        self.assertEqual(len(h), 32)  # MD5 是 32 位十六进制

    def test_file_hash_sha256(self):
        """测试 SHA256 哈希计算"""
        content = "Hello, Claw!"
        write_file(self.test_file, content)
        h = file_hash(self.test_file, "sha256")
        self.assertEqual(len(h), 64)  # SHA256 是 64 位十六进制

    def test_file_hash_invalid_algorithm(self):
        """测试不支持的哈希算法"""
        with self.assertRaises(ValueError):
            file_hash(self.test_file, "sha512")

    def test_list_files(self):
        """测试列出文件"""
        write_file(os.path.join(self.temp_dir, "a.py"), "a")
        write_file(os.path.join(self.temp_dir, "b.py"), "b")
        write_file(os.path.join(self.temp_dir, "c.txt"), "c")

        py_files = list_files(self.temp_dir, "*.py")
        self.assertEqual(len(py_files), 2)

    def test_list_files_recursive(self):
        """测试递归列出文件"""
        sub_dir = os.path.join(self.temp_dir, "sub")
        os.makedirs(sub_dir)
        write_file(os.path.join(sub_dir, "deep.py"), "deep")

        py_files = list_files(self.temp_dir, "*.py", recursive=True)
        self.assertEqual(len(py_files), 1)

    def test_list_files_directory_not_found(self):
        """测试列出不存在的目录"""
        with self.assertRaises(FileNotFoundError):
            list_files("nonexistent_dir")

    def test_read_write_json(self):
        """测试 JSON 读写"""
        data = {"name": "Claw", "version": 1.0, "enabled": True}
        json_path = os.path.join(self.temp_dir, "test.json")
        write_json(json_path, data)
        result = read_json(json_path)
        self.assertEqual(result, data)

    def test_write_json_invalid_data(self):
        """测试写入无效 JSON 数据"""
        json_path = os.path.join(self.temp_dir, "bad.json")
        # 写入无效的 JSON
        write_file(json_path, "这不是 json")
        with self.assertRaises(json.JSONDecodeError):
            read_json(json_path)

    def test_safe_filename(self):
        """测试安全文件名转换"""
        self.assertEqual(safe_filename("hello<world>"), "hello_world_")
        self.assertEqual(safe_filename('file:name"test'), "file_name_test")
        self.assertEqual(safe_filename("a/b\\c"), "a_b_c")

    def test_list_directory_tree(self):
        """测试目录树形结构"""
        sub_dir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(sub_dir)
        write_file(os.path.join(sub_dir, "nested.txt"), "content")

        tree = list_directory_tree(self.temp_dir)
        self.assertIn("subdir", tree)
        self.assertIn("nested.txt", tree)


if __name__ == "__main__":
    unittest.main()
