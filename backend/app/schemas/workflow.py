from typing import Any

from pydantic import BaseModel, Field


class WorkflowPlanRequest(BaseModel):
    project_id: str | None = Field(
        default=None,
        description="CloudMind project ID from PostgreSQL memory.",
    )
    repo_url: str | None = Field(
        default=None,
        description="GitHub repository URL.",
    )


class WorkflowPlanResponse(BaseModel):
    status: str
    message: str
    project: dict[str, Any] | None = None
    workflow: dict[str, Any] | None = None
    next_step: dict[str, Any] | None = None
    steps: list[dict[str, Any]]
    summary: dict[str, Any]
    safety: dict[str, Any] | None = None