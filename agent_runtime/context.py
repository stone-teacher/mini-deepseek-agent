from .models import Message, Session


class ContextManager:
    def __init__(
        self,
        max_chars: int = 4000,
        recent_message_count: int = 8,
    ) -> None:
        if recent_message_count < 1:
            raise ValueError("recent_message_count must be at least 1")

        self.max_chars = max_chars
        self.recent_message_count = recent_message_count

    def build_messages(
        self,
        session: Session,
        system_prompt: str,
    ) -> list[Message]:
        system_message = Message(
            role="system",
            content=system_prompt,
        )

        history = session.messages

        if self._message_chars(history) <= self.max_chars:
            return [system_message, *history]

        start = max(0, len(history) - self.recent_message_count)

        while start > 0 and history[start].role != "user":
            start -= 1

        recent_messages = history[start:]
        summary_text = self._build_summary(history[:start])

        messages = [
            system_message,
            Message(
                role="system",
                content=summary_text,
            ),
        ]

        if session.todos:
            pending_todos = [
                todo
                for todo in session.todos
                if todo.status == "pending"
            ]

            if pending_todos:
                todo_text = "Pending todos:\n" + "\n".join(
                    f"- {todo.id}: {todo.text}"
                    for todo in pending_todos
                )
                messages.append(
                    Message(
                        role="system",
                        content=todo_text,
                    )
                )

        messages.extend(recent_messages)
        return messages

    @staticmethod
    def _message_chars(messages: list[Message]) -> int:
        return sum(
            len(message.content or "")
            for message in messages
        )

    @staticmethod
    def _build_summary(messages: list[Message]) -> str:
        if not messages:
            return "Earlier conversation summary: none."

        lines = []

        for message in messages[-6:]:
            if not message.content:
                continue

            text = message.content.replace("\n", " ").strip()

            if len(text) > 120:
                text = text[:120] + "…"

            lines.append(f"{message.role}: {text}")

        if not lines:
            return "Earlier conversation summary: no text content."

        summary = (
            "Earlier conversation excerpts (may omit details):\n"
            + "\n".join(lines)
        )

        if len(summary) > 600:
            summary = summary[:599] + "…"

        return summary