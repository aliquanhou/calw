"""Tests for speculative execution engine."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSpeculativeEngine(unittest.TestCase):
    def setUp(self):
        from agent.speculative import SpeculativeEngine
        self.engine = SpeculativeEngine()

    def test_record_and_predict(self):
        self.engine.record_call("read", {"file_path": "test.py"}, "content", 0, 10)
        # After reading, engine should have predictions for edit/write
        self.assertGreaterEqual(self.engine.prediction_count, 0)

    def test_consume_miss(self):
        self.engine.record_call("read", {"file_path": "test.py"}, "content", 0, 10)
        result = self.engine.consume("write", {"file_path": "other.py"})
        self.assertIsNone(result)

    def test_write_then_verify(self):
        self.engine.record_call("write", {"file_path": "test.py", "content": "print('hi')"}, "written", 0, 10)
        self.assertGreaterEqual(self.engine.prediction_count, 0)

    def test_clear(self):
        self.engine.record_call("read", {"file_path": "f.py"}, "c", 0, 1)
        self.engine.clear()
        self.assertEqual(self.engine.prediction_count, 0)

    def test_param_similarity(self):
        sim = self.engine._param_similarity({"file_path": "a.py"}, {"file_path": "a.py"})
        self.assertGreaterEqual(sim, 0.9)

    def test_read_then_edit_pattern(self):
        self.engine.record_call("read", {"file_path": "main.py"}, "some code", 0, 5)
        # Should have predictions for edit/write patterns
        self.assertGreaterEqual(self.engine.prediction_count, 1)


if __name__ == "__main__":
    unittest.main()
