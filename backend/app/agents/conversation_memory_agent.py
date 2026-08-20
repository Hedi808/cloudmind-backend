from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.auth import get_current_user_id


class ConversationMemoryAgent:
    """
    Simple in-memory conversation memory for Phase 15A.

    Responsibilities:
    - store chat history by session_id
    - remember current repo_url
    - remember Azure resource group and app name
    - remember latest PR URL / PR number
    - provide context to the conversation brain

    Important:
    - This is development memory only.
    - In production, replace this with Redis, PostgreSQL, or another persistent store.
    """

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}

    def get_or_create_session(
        self,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if not session_id:
            session_id = str(uuid4())

        session_key = self._session_key(session_id)

        if session_key not in self.sessions:
            self.sessions[session_key] = {
                "session_id": session_id,
                "created_at": self._now(),
                "updated_at": self._now(),
                "messages": [],
                "state": {
                    "repo_url": None,
                    "repo_analysis": None,
                    "resource_group": None,
                    "app_name": None,
                    "health_path": "/health",
                    "latest_pr_url": None,
                    "latest_pr_number": None,
                    "latest_intent": None,
                    "latest_action": None,
                    "latest_result_status": None,
                },
            }

        return self.sessions[session_key]

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        session = self.get_or_create_session(session_id)

        session["messages"].append(
            {
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "created_at": self._now(),
            }
        )

        session["updated_at"] = self._now()

    def update_state(
        self,
        session_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        session = self.get_or_create_session(session_id)
        state = session["state"]

        for key, value in updates.items():
            if value is not None:
                state[key] = value

        session["updated_at"] = self._now()

        return state

    def get_state(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        session = self.get_or_create_session(session_id)

        return session["state"]

    def get_recent_messages(
        self,
        session_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        session = self.get_or_create_session(session_id)

        return session["messages"][-limit:]

    def clear_session(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        session_key = self._session_key(session_id)
        if session_key in self.sessions:
            del self.sessions[session_key]

        return self.get_or_create_session(session_id)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _session_key(self, session_id: str) -> str:
        return f"{get_current_user_id() or 'system'}:{session_id}"
