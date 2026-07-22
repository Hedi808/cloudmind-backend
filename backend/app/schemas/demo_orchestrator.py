from typing import Any

from pydantic import BaseModel, Field


class FinalDemoReportRequest(BaseModel):
    project_id: str | None = Field(
        default=None,
        description="CloudMind project ID from PostgreSQL memory.",
    )
    repo_url: str | None = Field(
        default=None,
        description="GitHub repository URL.",
    )
    pull_request_url: str | None = Field(
        default=None,
        description="Optional GitHub pull request URL used as demo evidence.",
    )
    resource_group: str | None = Field(
        default=None,
        description="Azure resource group.",
    )
    app_name: str | None = Field(
        default=None,
        description="Azure Container App name.",
    )
    run_pr_validation: bool = Field(
        default=False,
        description="Compatibility field. The memory-aware report does not require this by default.",
    )
    run_deployment_verification: bool = Field(
        default=False,
        description="Compatibility field. The memory-aware report uses workflow memory by default.",
    )
    save_to_memory: bool = Field(
        default=True,
        description="Save the generated report as a PostgreSQL project artifact.",
    )


class QuickDemoReportRequest(BaseModel):
    project_id: str | None = Field(default=None)
    repo_url: str | None = Field(default=None)
    resource_group: str | None = Field(default=None)
    app_name: str | None = Field(default=None)


class FinalDemoReportResponse(BaseModel):
    status: str
    message: str
    phase: str | None = None
    demo_ready: bool
    demo_recommendation: str
    recommendation: str | None = None
    workflow_status: str | None = None
    workflow_summary: dict[str, Any] | None = None
    workflow_next_step: dict[str, Any] | None = None
    project: dict[str, Any] | None = None
    checks: dict[str, Any] | None = None
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    report_markdown: str | None = None
    safety: dict[str, Any] | None = None
    saved_to_memory: bool | None = None
    saved_artifact_id: str | None = None
    memory_save_error: str | None = None
    generated_at: str | None = None


class PhaseMapResponse(BaseModel):
    status: str
    message: str
    phase: str | None = None
    phases: list[dict[str, Any]]