import unittest

from agent_runtime.context import ContextManager
from agent_runtime.models import Message, Session, Todo, ToolCall


class ContextTests(unittest.TestCase):
    def test_long_history_is_shortened_and_pending_todos_are_kept(self):
        session = Session(
            user_id="alice",
            session_id="context-test",
        )

        session.messages = [
            Message(role="user", content="较早的问题。" * 200),
            Message(role="assistant", content="较早的回答。" * 200),
            Message(role="user", content="现在继续讨论。"),
        ]
        session.todos = [
            Todo(id="todo-1", text="完成 README"),
            Todo(id="todo-2", text="安装依赖", status="done"),
        ]

        original_contents = [
            message.content
            for message in session.messages
        ]

        context = ContextManager(
            max_chars=100,
            recent_message_count=1,
        )
        messages = context.build_messages(
            session,
            "你是一个助手。",
        )

        before_chars = sum(
            len(content or "")
            for content in original_contents
        )
        after_chars = sum(
            len(message.content or "")
            for message in messages
        )

        self.assertLess(after_chars, before_chars)
        self.assertLessEqual(len(messages[1].content), 600)

        self.assertEqual(messages[0].role, "system")
        self.assertEqual(messages[0].content, "你是一个助手。")
        self.assertIs(messages[-1], session.messages[-1])

        pending_text = messages[2].content
        self.assertIn("todo-1: 完成 README", pending_text)
        self.assertNotIn("todo-2", pending_text)

        self.assertEqual(
            [message.content for message in session.messages],
            original_contents,
        )

    def test_compression_keeps_a_complete_tool_round(self):
        session = Session(
            user_id="alice",
            session_id="tool-context-test",
        )

        current_round = [
            Message(role="user", content="请分别计算 1+1 和 2+2"),
            Message(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        id="call-a",
                        name="calculator",
                        arguments={"expression": "1 + 1"},
                    ),
                    ToolCall(
                        id="call-b",
                        name="calculator",
                        arguments={"expression": "2 + 2"},
                    ),
                ],
            ),
            Message(
                role="tool",
                content="2",
                tool_call_id="call-a",
            ),
            Message(
                role="tool",
                content="4",
                tool_call_id="call-b",
            ),
        ]

        session.messages = [
            Message(role="user", content="旧问题。" * 200),
            Message(role="assistant", content="旧回答。" * 200),
            *current_round,
        ]

        context = ContextManager(
            max_chars=100,
            recent_message_count=1,
        )
        messages = context.build_messages(session, "你是一个助手。")

        kept_history = [
            message
            for message in messages
            if message.role != "system"
        ]

        self.assertEqual(kept_history, current_round)
        self.assertEqual(
            [message.role for message in kept_history],
            ["user", "assistant", "tool", "tool"],
        )