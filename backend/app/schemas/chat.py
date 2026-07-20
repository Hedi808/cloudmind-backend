from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    repo_url: str | None = None
    branch: str | None = None
    environment: str = "staging"


class ChatResponse(BaseModel):
    user_message: str
    detected_intent: str
    agent_used: str
    response: str
    metadata: dict[str, Any] = {}