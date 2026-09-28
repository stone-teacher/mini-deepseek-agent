import json
import unittest
from unittest.mock import patch

from agent_runtime.context import ContextManager
from agent_runtime.llm import FakeLLM
from agent_runtime.models import AssistantResponse, Session, ToolCall
from agent_runtime.runtime import AgentRuntime


class RuntimeTests(unittest.TestCase):
    def test_invalid_arguments_do_not_execute_calculator(self):
        llm = FakeLLM([
            AssistantResponse(
                tool_calls=[
                    ToolCall(
                        id="invalid-1",
                        name="calculator",
                        arguments={"expression": 126},
                    )
                ]
            ),
            AssistantResponse(content="参数格式错误。"),
        ])

        session = Session(
            user_id="alice",
            session_id="test-session",
        )
        runtime = AgentRuntime(
            llm=llm,
            context=ContextManager(),
        )

        with patch("agent_runtime.tools.calculate") as calculator:
            runtime.handle_user_input(session, "检查非法参数")
            calculator.assert_not_called()

        tool_messages = [
            message
            for message in session.messages
            if message.role == "tool"
        ]

        self.assertEqual(len(tool_messages), 1)

        error = json.loads(tool_messages[0].content)
        self.assertEqual(error["tool_error"], "ValueError")
        self.assertEqual(
            error["message"],
            "Argument 'expression' must be a string",
        )
        self.assertEqual(tool_messages[0].tool_call_id, "invalid-1")

    def test_calculator_result_is_sent_back_to_llm(self):
        llm = FakeLLM([
            AssistantResponse(
                tool_calls=[
                    ToolCall(
                        id="calc-1",
                        name="calculator",
                        arguments={"expression": "(10 + 2) * 3"},
                    )
                ]
            ),
            AssistantResponse(content="结果是 36。"),
        ])

        session = Session(
            user_id="alice",
            session_id="calculator-test",
        )
        runtime = AgentRuntime(
            llm=llm,
            context=ContextManager(),
        )

        # 记录每次请求模型时的消息，避免后续变化影响检查。
        requests = []
        original_complete = llm.complete

        def record_complete(*, messages, tools):
            requests.append([
                (message.role, message.content, message.tool_call_id)
                for message in messages
            ])
            return original_complete(messages=messages, tools=tools)

        with patch.object(llm, "complete", side_effect=record_complete):
            answer = runtime.handle_user_input(
                session,
                "请计算 (10 + 2) * 3",
            )

        self.assertEqual(answer, "结果是 36。")
        self.assertEqual(len(requests), 2)

        self.assertIn(
            ("tool", "36", "calc-1"),
            requests[1],
        )

        self.assertEqual(
            [message.role for message in session.messages],
            ["user", "assistant", "tool", "assistant"],
        )

    def test_runtime_stops_at_max_steps(self):
        llm = FakeLLM([
            AssistantResponse(
                tool_calls=[
                    ToolCall(
                        id="limit-1",
                        name="calculator",
                        arguments={"expression": "1 + 1"},
                    )
                ]
            ),
            AssistantResponse(
                tool_calls=[
                    ToolCall(
                        id="limit-2",
                        name="calculator",
                        arguments={"expression": "2 + 2"},
                    )
                ]
            ),
        ])

        session = Session(
            user_id="alice",
            session_id="limit-test",
        )
        runtime = AgentRuntime(
            llm=llm,
            context=ContextManager(),
            max_steps=2,
        )

        with patch.object(
            llm,
            "complete",
            wraps=llm.complete,
        ) as complete:
            answer = runtime.handle_user_input(
                session,
                "连续计算",
            )

        self.assertEqual(complete.call_count, 2)
        self.assertEqual(
            answer,
            "本轮已达到模型调用次数上限，请缩小任务范围后继续。",
        )

        tool_messages = [
            message
            for message in session.messages
            if message.role == "tool"
        ]
        self.assertEqual(
            [message.content for message in tool_messages],
            ["2", "4"],
        )
        self.assertEqual(
            [message.tool_call_id for message in tool_messages],
            ["limit-1", "limit-2"],
        )

        self.assertEqual(session.messages[-1].role, "assistant")
        self.assertEqual(session.messages[-1].content, answer)

    def test_tool_exception_is_sent_back_to_llm(self):
        llm = FakeLLM([
            AssistantResponse(
                tool_calls=[
                    ToolCall(
                        id="error-1",
                        name="calculator",
                        arguments={"expression": "1 / 0"},
                    )
                ]
            ),
            AssistantResponse(content="除数不能为零。"),
        ])

        session = Session(
            user_id="alice",
            session_id="error-test",
        )
        runtime = AgentRuntime(
            llm=llm,
            context=ContextManager(),
        )

        with self.assertLogs(
            "agent_runtime.runtime",
            level="WARNING",
        ) as logs:
            with patch.object(
                llm,
                "complete",
                wraps=llm.complete,
            ) as complete:
                answer = runtime.handle_user_input(
                    session,
                    "计算 1 / 0",
                )

        self.assertEqual(answer, "除数不能为零。")
        self.assertEqual(complete.call_count, 2)

        second_request = complete.call_args_list[1].kwargs
        tool_messages = [
            message
            for message in second_request["messages"]
            if message.role == "tool"
        ]

        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0].tool_call_id, "error-1")

        error = json.loads(tool_messages[0].content)
        self.assertEqual(error["tool_error"], "ZeroDivisionError")
        self.assertTrue(error["message"])

        self.assertTrue(
            any(
                "工具失败" in line
                and "error-1" in line
                and "ZeroDivisionError" in line
                for line in logs.output
            )
        )

    def test_follow_up_request_contains_previous_conversation(self):
            llm = FakeLLM([
                AssistantResponse(content="好的，项目叫小航。"),
                AssistantResponse(content="项目叫小航，使用 Python。"),
            ])
    
            session = Session(
                user_id="alice",
                session_id="follow-up-test",
            )
            runtime = AgentRuntime(
                llm=llm,
                context=ContextManager(),
            )
    
            with patch.object(
                llm,
                "complete",
                wraps=llm.complete,
            ) as complete:
                runtime.handle_user_input(
                    session,
                    "项目叫小航，使用 Python。",
                )
                runtime.handle_user_input(
                    session,
                    "项目叫什么，用什么语言？",
                )
    
            self.assertEqual(complete.call_count, 2)
    
            second_request = complete.call_args_list[1].kwargs
            conversation = [
                (message.role, message.content)
                for message in second_request["messages"]
                if message.role != "system"
            ]
    
            self.assertEqual(
                conversation,
                [
                    ("user", "项目叫小航，使用 Python。"),
                    ("assistant", "好的，项目叫小航。"),
                    ("user", "项目叫什么，用什么语言？"),
                ],
            )
    
            self.assertEqual(
                [message.role for message in session.messages],
                ["user", "assistant", "user", "assistant"],
            )

    def test_unknown_tool_returns_error_and_loop_continues(self):
        llm = FakeLLM([
            AssistantResponse(
                tool_calls=[
                    ToolCall(
                        id="unknown-1",
                        name="weather",
                        arguments={"city": "北京"},
                    )
                ]
            ),
            AssistantResponse(content="当前没有天气查询工具。"),
        ])

        session = Session(
            user_id="alice",
            session_id="unknown-tool-test",
        )
        runtime = AgentRuntime(
            llm=llm,
            context=ContextManager(),
        )

        with self.assertLogs(
            "agent_runtime.runtime",
            level="WARNING",
        ):
            with patch.object(
                llm,
                "complete",
                wraps=llm.complete,
            ) as complete:
                answer = runtime.handle_user_input(
                    session,
                    "查询北京天气",
                )

        self.assertEqual(complete.call_count, 2)
        self.assertEqual(answer, "当前没有天气查询工具。")

        second_request = complete.call_args_list[1].kwargs
        tool_messages = [
            message
            for message in second_request["messages"]
            if message.role == "tool"
        ]

        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0].tool_call_id, "unknown-1")

        error = json.loads(tool_messages[0].content)
        self.assertEqual(error["tool_error"], "KeyError")
        self.assertIn("Unknown tool: weather", error["message"])