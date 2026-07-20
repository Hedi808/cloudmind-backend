from typing import Any, Literal

from pydantic import BaseModel, Field


EnvironmentName = Literal["development", "staging", "production"]

SimulationScenario = Literal[
    "healthy",
    "cold_start",
    "image_pull_failure",
    "missing_dependency",
    "wrong_port",
    "oom",
    "crash_loop",
    "dependency_connection_failure",
]


class RemediationPrFromAzureRequest(BaseModel):
    repo_url: str = Field(
        ...,
        description="GitHub repository URL where the remediation PR should be opened.",
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
    approval_confirmed: bool = Field(
        default=False,
        description="Must be true before CloudMind creates a Git branch and PR.",
    )
    health_path: str = Field(
        default="/health",
        description="Health endpoint path.",
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
        description="Number of recent logs to analyze.",
    )
    environment: EnvironmentName = Field(
        default="development",
        description="Deployment environment.",
    )
    allow_cost_increase: bool = Field(
        default=False,
        description="Whether cost-increasing changes can be proposed.",
    )
    create_pr_when_no_remediation: bool = Field(
        default=False,
        description="If true, creates a documentation/hardening PR even when no active incident exists.",
    )


class RemediationPrFromPlanRequest(BaseModel):
    repo_url: str = Field(
        ...,
        description="GitHub repository URL where the remediation PR should be opened.",
        examples=["https://github.com/Hedi808/test-3s.git"],
    )
    remediation_plan: dict[str, Any] = Field(
        ...,
        description="Result returned by /api/remediation/plan-azure, /api/remediation/plan, or /api/remediation/simulate.",
    )
    approval_confirmed: bool = Field(
        default=False,
        description="Must be true before CloudMind creates a Git branch and PR.",
    )
    create_pr_when_no_remediation: bool = Field(
        default=False,
        description="If true, creates a documentation/hardening PR even when no active incident exists.",
    )


class RemediationPrSimulationRequest(BaseModel):
    repo_url: str = Field(
        ...,
        description="GitHub repository URL where the remediation PR should be opened.",
        examples=["https://github.com/Hedi808/test-3s.git"],
    )
    scenario: SimulationScenario = Field(
        ...,
        description="Synthetic incident scenario used to test remediation PR creation.",
        examples=["missing_dependency"],
    )
    approval_confirmed: bool = Field(
        default=False,
        description="Must be true before CloudMind creates a Git branch and PR.",
    )
    environment: EnvironmentName = Field(
        default="development",
        description="Deployment environment.",
    )
    allow_cost_increase: bool = Field(
        default=False,
        description="Whether cost-increasing changes can be proposed.",
    )
    create_pr_when_no_remediation: bool = Field(
        default=True,
        description="If true, creates a documentation/hardening PR even when no active incident exists.",
    )


class RemediationPrPreviewRequest(BaseModel):
    remediation_plan: dict[str, Any] = Field(
        ...,
        description="A remediation plan to preview before opening a PR.",
    )