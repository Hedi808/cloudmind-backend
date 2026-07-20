from typing import Literal

from pydantic import BaseModel, Field


EnvironmentName = Literal["development", "staging", "production"]


class FinalDemoReportRequest(BaseModel):
    repo_url: str = Field(
        ...,
        description="GitHub repository URL used in the demo.",
        examples=["https://github.com/Hedi808/test-3s.git"],
    )
    resource_group: str = Field(
        ...,
        description="Azure resource group containing the Container App.",
        examples=["rg-cloudmind-test-3s"],
    )
    app_name: str = Field(
        ...,
        description="Azure Container App name.",
        examples=["test-3s-backend"],
    )
    pull_request_number: int | None = Field(
        default=None,
        ge=1,
        description="Optional PR number to validate during the final demo.",
        examples=[9],
    )
    pull_request_url: str | None = Field(
        default=None,
        description="Optional PR URL to validate during the final demo.",
        examples=["https://github.com/Hedi808/test-3s/pull/9"],
    )
    health_path: str = Field(
        default="/health",
        description="Health endpoint path.",
        examples=["/health"],
    )
    timeout_seconds: int = Field(
        default=60,
        ge=5,
        le=120,
        description="HTTP health check timeout.",
    )
    log_tail: int = Field(
        default=100,
        ge=10,
        le=300,
        description="Number of Azure log lines to inspect.",
    )
    environment: EnvironmentName = Field(
        default="development",
        description="Demo environment.",
    )
    run_pr_validation: bool = Field(
        default=True,
        description="Run Phase 12 PR validation if PR information is provided.",
    )
    run_azure_verification: bool = Field(
        default=True,
        description="Run Phase 13 Azure deployment verification.",
    )
    run_remediation_plan: bool = Field(
        default=True,
        description="Run Phase 10 remediation planning.",
    )
    require_ci_success_for_pr_validation: bool = Field(
        default=False,
        description="If true, Phase 12 requires CI success.",
    )
    allow_docs_only_without_ci: bool = Field(
        default=True,
        description="If true, docs-only PRs can be accepted even when CI is not required.",
    )
    require_human_review_for_pr_validation: bool = Field(
        default=False,
        description="If true, PR validation requires a human approval.",
    )
    require_pr_merged_for_deployment: bool = Field(
        default=False,
        description="If true, deployment verification fails until the PR is merged.",
    )
    require_ci_success_for_deployment: bool = Field(
        default=False,
        description="If true, deployment verification requires CI success on the merge commit.",
    )
    require_azure_healthy: bool = Field(
        default=True,
        description="If true, Azure must be healthy for the demo to pass.",
    )
    include_raw_outputs: bool = Field(
        default=False,
        description="If true, include full raw outputs from lower-level agents.",
    )


class QuickDemoReportRequest(BaseModel):
    repo_url: str = Field(
        default="https://github.com/Hedi808/test-3s.git",
        description="GitHub repository URL used in the demo.",
    )
    resource_group: str = Field(
        default="rg-cloudmind-test-3s",
        description="Azure resource group containing the Container App.",
    )
    app_name: str = Field(
        default="test-3s-backend",
        description="Azure Container App name.",
    )
    pull_request_url: str | None = Field(
        default=None,
        description="Optional PR URL to validate during the demo.",
        examples=["https://github.com/Hedi808/test-3s/pull/9"],
    )