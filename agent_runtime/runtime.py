import logging
import json
from datetime import datetime, timezone

from .context import ContextManager
from .llm import LLMClient
from .models import Message, Session
from .tools import (
    ToolRegistry,
    calculator_spec,
    search_spec,
    todo_spec,
    validate_arguments,
)

logger = logging.getLogger(__name__)

class AgentRuntime:
    def __init__(
        self,
        llm: LLMClient,
        context: ContextManager,
        max_steps: int = 8,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")

        self.llm = llm
        self.context = context
        self.max_steps = max_steps
        self.system_prompt = (
            "你是一个中文助手。根据需要使用提供的工具。"
            "工具结果返回后再回答，不要编造工具执行结果。"
            "search 只搜索内置文档，不是互联网搜索。"
            "todo 的 complete 只标记状态，不执行待办内容；"
            "只有用户确认完成或任务已执行并验证成功时才能标记完成。"
        )

    def handle_user_input(
        self,
        session: Session,
        user_text: str,
    ) -> str:
        registry = ToolRegistry()
        registry.register(calculator_spec())
        registry.register(search_spec())
        registry.register(todo_spec(session))

        session.messages.append(
            Message(role="user", content=user_text)
        )
        session.updated_at = datetime.now(timezone.utc)

        for _ in range(self.max_steps):
            response = self.llm.complete(
                messages=self.context.build_messages(
                    session,
                    self.system_prompt,
                ),
                tools=registry.list_specs(),
            )

            session.messages.append(
                Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls or None,
                )
            )

            if not response.tool_calls:
                session.updated_at = datetime.now(timezone.utc)
                return response.content or ""

            for call in response.tool_calls:
                logger.info(
                    "工具开始 name=%s call_id=%s",
                    call.name,
                    call.id,
                )

                try:
                    spec = registry.get(call.name)
                    validate_arguments(spec, call.arguments)
                    output = spec.handler(**call.arguments)
                    result_text = json.dumps(
                        output,
                        ensure_ascii=False,
                        allow_nan=False,
                    )

                    logger.info(
                        "工具成功 name=%s call_id=%s",
                        call.name,
                        call.id,
                    )

                except Exception as exc:
                    logger.warning(
                        "工具失败 name=%s call_id=%s error=%s",
                        call.name,
                        call.id,
                        type(exc).__name__,
                    )

                    result_text = json.dumps(
                        {
                            "tool_error": type(exc).__name__,
                            "message": str(exc)[:200],
                        },
                        ensure_ascii=False,
                    )

                session.messages.append(
                    Message(
                        role="tool",
                        content=result_text,
                        tool_call_id=call.id,
                    )
                )
                session.updated_at = datetime.now(timezone.utc)

        limit_message = "本轮已达到模型调用次数上限，请缩小任务范围后继续。"
        session.messages.append(
            Message(role="assistant", content=limit_message)
        )
        session.updated_at = datetime.now(timezone.utc)
        return limit_message