from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        description="Natural language user message.",
        examples=["Analyze this repo https://github.com/Hedi808/test-3s.git"],
    )
    session_id: str | None = Field(
        default=None,
        description="Optional conversation session id. If omitted, CloudMind creates a new session.",
    )
    repo_url: str | None = Field(
        default=None,
        description="Optional GitHub repository URL.",
        examples=["https://github.com/Hedi808/test-3s.git"],
    )
    resource_group: str | None = Field(
        default=None,
        description="Optional Azure resource group.",
        examples=["rg-cloudmind-test-3s"],
    )
    app_name: str | None = Field(
        default=None,
        description="Optional Azure Container App name.",
        examples=["test-3s-backend"],
    )
    pull_request_url: str | None = Field(
        default=None,
        description="Optional GitHub pull request URL.",
        examples=["https://github.com/Hedi808/test-3s/pull/8"],
    )
    approval_confirmed: bool = Field(
        default=False,
        description="Human approval flag for write/publish actions.",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional extra context from the frontend.",
    )


class ClearChatMemoryRequest(BaseModel):
    session_id: str = Field(
        ...,
        description="Conversation session id to clear.",
    )


class ChatSessionRequest(BaseModel):
    session_id: str = Field(
        ...,
        description="Conversation session id to inspect.",
    )