import unittest

from agent_runtime.models import Message
from agent_runtime.session import SessionStore
from agent_runtime.tools import todo_spec


class SessionTests(unittest.TestCase):
    def test_sessions_are_isolated_and_state_is_preserved(self):
        store = SessionStore()

        first = store.get_or_create("alice", "window-1")
        second = store.get_or_create("alice", "window-2")
        other_user = store.get_or_create("bob", "window-1")

        first_tool = todo_spec(first)
        second_tool = todo_spec(second)
        other_tool = todo_spec(other_user)

        created = first_tool.handler(
            action="create",
            text="完成 README",
        )
        first.messages.append(
            Message(role="user", content="请创建一条待办：完成 README。")
        )

        # 不同窗口、不同用户都应拥有独立的会话。
        self.assertIsNot(first, second)
        self.assertIsNot(first, other_user)

        self.assertEqual(
            second_tool.handler(action="list")["todos"],
            [],
        )
        self.assertEqual(
            other_tool.handler(action="list")["todos"],
            [],
        )
        self.assertEqual(second.messages, [])
        self.assertEqual(other_user.messages, [])

        # 相同用户和会话编号，应取回原对象。
        resumed = store.get_or_create("alice", "window-1")

        self.assertIs(resumed, first)

        listed = todo_spec(resumed).handler(action="list")
        self.assertEqual(
            listed["todos"],
            [
                {
                    "id": created["todo"]["id"],
                    "text": "完成 README",
                    "status": "pending",
                }
            ],
        )
        self.assertEqual(len(resumed.messages), 1)
        self.assertEqual(
            resumed.messages[0].content,
            "请创建一条待办：完成 README。",
        )

    