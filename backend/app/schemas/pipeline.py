from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    project_id: str | None = None
    repo_url: str | None = None
    resource_group: str | None = None
    app_name: str | None = None
    pull_request_url: str | None = None

    approval_confirmed: bool = False

    max_steps: int = Field(default=5, ge=1, le=10)
    dry_run: bool = False

    run_optional: bool = False
    run_optional_reporting: bool = True
    stop_after_gitops: bool = True

    overwrite: bool = True
    publish_to_github: bool = True

    session_id: str | None = None


class PipelineStepResult(BaseModel):
    step_id: str
    title: str
    status: str
    message: str
    tool_intent: str | None = None
    requires_approval: bool = False
    output: dict[str, Any] | None = None


class PipelineRunResponse(BaseModel):
    status: str
    message: str

    project_id: str | None = None
    repo_url: str | None = None

    started: bool
    completed: bool
    paused: bool
    pause_reason: str | None = None

    executed_steps: list[PipelineStepResult] = []
    executed_count: int = 0

    workflow_status_before: str | None = None
    workflow_status_after: str | None = None

    next_step: dict[str, Any] | None = None
    workflow_summary: dict[str, Any] | None = None
    workflow_plan: dict[str, Any] | None = None

    safety: dict[str, Any]