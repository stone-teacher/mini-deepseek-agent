import os
import json
from collections.abc import Sequence
from typing import Any, Protocol

from .models import (
    AssistantResponse,
    Message,
    ToolCall,
    ToolSpec,
)


class LLMClient(Protocol):
    def complete(
        self,
        *, #后面必须使用关键字，更易读
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> AssistantResponse:
        ...


class FakeLLM:
    def __init__(self, responses: Sequence[AssistantResponse]):
        self._responses = list(responses)
        self._index = 0

    def complete(
        self,
        *,
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> AssistantResponse:
        if self._index >= len(self._responses):
            raise RuntimeError("FakeLLM has no more responses")

        response = self._responses[self._index]
        self._index += 1
        return response

def _message_to_api(message: Message) -> dict[str, Any]:
    result: dict[str, Any] = {
        "role": message.role,
    }

    if message.content is not None:
        result["content"] = message.content

    if message.name is not None:
        result["name"] = message.name

    if message.tool_call_id is not None:
        result["tool_call_id"] = message.tool_call_id

    if message.tool_calls:
        result["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": json.dumps(
                        tool_call.arguments,
                        ensure_ascii=False,
                    ),
                },
            }
            for tool_call in message.tool_calls
        ]

    return result


def _tool_to_api(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }

def _api_to_response(payload: dict[str, Any]) -> AssistantResponse:
    choices = payload.get("choices")

    if not choices:
        raise ValueError("LLM response has no choices")

    message = choices[0].get("message")

    if not isinstance(message, dict):
        raise ValueError("LLM response has no valid message")

    tool_calls: list[ToolCall] = []

    for raw_tool_call in message.get("tool_calls") or []:
        function = raw_tool_call.get("function") or {}

        tool_name = function.get("name")
        arguments_text = function.get("arguments", "{}")

        if not tool_name:
            raise ValueError("Tool call has no function name")

        try:
            arguments = json.loads(arguments_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON arguments for tool: {tool_name}"
            ) from exc

        if not isinstance(arguments, dict):
            raise ValueError(
                f"Tool arguments must be an object: {tool_name}"
            )

        tool_calls.append(
            ToolCall(
                id=raw_tool_call.get("id", ""),
                name=tool_name,
                arguments=arguments,
            )
        )

    return AssistantResponse(
        content=message.get("content"),
        tool_calls=tool_calls,
        reasoning_content=message.get("reasoning_content"),
        raw=payload,
    )


class DeepSeekLLMClient:
    def __init__(
        self,
        client: Any,
        model: str = "deepseek-chat",
    ) -> None:
        self._client = client
        self._model = model

    def complete(
        self,
        *,
        messages: list[Message],
        tools: list[ToolSpec],
    ) -> AssistantResponse:
        request: dict[str, Any] = {
            "model": self._model,
            "messages": [
                _message_to_api(message)
                for message in messages
            ],
        }

        if tools:
            request["tools"] = [
                _tool_to_api(tool)
                for tool in tools
            ]

        response = self._client.chat.completions.create(**request)

        return _api_to_response(response.model_dump())


def create_deepseek_llm() -> DeepSeekLLMClient:
    from openai import OpenAI

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY is not configured")

    client = OpenAI(
        api_key=api_key,
        base_url=os.environ.get(
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com",
        ),
        timeout=30.0,
        max_retries=0,
    )

    return DeepSeekLLMClient(
        client=client,
        model=os.environ.get(
            "DEEPSEEK_MODEL",
            "deepseek-chat",
        ),
    )