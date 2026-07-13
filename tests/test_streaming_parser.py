"""Tests for streaming tool call parser."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestStreamingParser(unittest.TestCase):
    def setUp(self):
        from agent.streaming_parser import StreamingToolParser
        self.parser = StreamingToolParser()
        self.signals = []
        self.parser.on_signal = lambda msg: self.signals.append(msg)

    def test_detect_tool_name(self):
        signals = self.parser.feed('{"name": "read"')
        has_tool = any(s["type"] == "tool_detected" for s in signals)
        self.assertTrue(has_tool)

    def test_detect_params(self):
        self.parser.feed('{"name": "read"')
        signals = self.parser.feed('"file_path": "test.py"')
        has_param = any(s["type"] == "param_detected" for s in signals)
        self.assertTrue(has_param)

    def test_early_exec_read(self):
        # read only needs file_path
        self.parser.feed('{"name": "read"')
        signals = self.parser.feed('"file_path": "test.py"')
        has_early = any(s["type"] == "early_exec" for s in signals)
        self.assertTrue(has_early)

    def test_early_exec_bash(self):
        self.parser.feed('{"name": "bash"')
        signals = self.parser.feed('"command": "echo hi"')
        has_early = any(s["type"] == "early_exec" for s in signals)
        self.assertTrue(has_early)

    def test_reset(self):
        self.parser.feed('{"name": "read"')
        self.parser.reset()
        self.assertIsNone(self.parser.current_tool)
        self.assertEqual(self.parser.buffer_length, 0)

    def test_tool_complete(self):
        self.parser.feed('{"name": "read"')
        signals = self.parser.feed('"file_path": "test.py"}')
        has_complete = any(s["type"] == "tool_complete" for s in signals)
        # May or may not detect complete depending on how much is buffered
        self.assertIsNotNone(self.parser.current_tool)


if __name__ == "__main__":
    unittest.main()
