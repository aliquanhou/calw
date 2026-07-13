"""Tests for session state management."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSessionState(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        from agent.session import SessionState
        self.state = SessionState(user_id="test", data_dir=self.data_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_add_message(self):
        msg = self.state.add_message("user", "hello")
        self.assertEqual(msg["role"], "user")
        self.assertEqual(msg["content"], "hello")
        self.assertEqual(self.state.message_count, 1)

    def test_get_recent_messages(self):
        for i in range(5):
            self.state.add_message("user", f"msg{i}")
        recent = self.state.get_recent_messages(max_count=3)
        self.assertEqual(len(recent), 3)
        self.assertIn("msg2", recent[0]["content"])

    def test_add_tool_message(self):
        self.state.add_message("assistant", "", tool_calls=[{"id": "tc1", "function": {"name": "read"}}])
        self.state.add_message("tool", 'file content', tool_call_id="tc1")
        self.assertEqual(self.state.message_count, 2)
        recent = self.state.get_recent_messages(5)
        self.assertEqual(recent[0]["role"], "assistant")
        self.assertEqual(recent[1]["role"], "tool")

    def test_log_error(self):
        err = self.state.log_error("test", "something failed", "details here")
        self.assertEqual(err["source"], "test")
        self.assertEqual(err["message"], "something failed")
        self.assertEqual(self.state.error_count, 1)

    def test_persistence(self):
        self.state.add_message("user", "persist test")
        self.state.add_message("assistant", "response")
        # Create new state from same file
        from agent.session import SessionState
        state2 = SessionState(user_id="test", data_dir=self.data_dir)
        self.assertEqual(state2.message_count, 2)
        recent = state2.get_recent_messages(5)
        self.assertEqual(recent[0]["content"], "persist test")

    def test_get_all_messages(self):
        self.state.add_message("user", "a")
        self.state.add_message("assistant", "b")
        all_msgs = self.state.get_all_messages()
        self.assertEqual(len(all_msgs), 2)

    def test_clear(self):
        self.state.add_message("user", "hello")
        self.state.clear()
        self.assertEqual(self.state.message_count, 0)


if __name__ == "__main__":
    unittest.main()
