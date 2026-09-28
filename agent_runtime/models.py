from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal
#callable 可定义的函数
#literal 字符串只能是几个确定值

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]


@dataclass
class AssistantResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning_content: str | None = None
    raw: dict[str, Any] = field(default_factory=dict) #保留一份原始回答


@dataclass
class Todo:
    id: str
    text: str
    status: Literal["pending", "done"] = "pending"


@dataclass
class Session:
    user_id: str
    session_id: str
    messages: list[Message] = field(default_factory=list)
    todos: list[Todo] = field(default_factory=list)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )