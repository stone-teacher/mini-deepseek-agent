from .models import Session


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], Session] = {}

    def get_or_create(
        self,
        user_id: str,
        session_id: str,
    ) -> Session:
        key = (user_id, session_id)

        if key not in self._sessions:
            self._sessions[key] = Session(
                user_id=user_id,
                session_id=session_id,
            )

        return self._sessions[key]