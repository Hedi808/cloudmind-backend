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


class RemediationPlanFromAzureRequest(BaseModel):
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
    health_path: str = Field(
        default="/health",
        description="Health endpoint path to test.",
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
        description="Number of recent log lines to analyze.",
    )
    environment: EnvironmentName = Field(
        default="development",
        description="Deployment environment.",
    )
    allow_cost_increase: bool = Field(
        default=False,
        description="Whether remediation planning may suggest cost-increasing changes such as more replicas or memory.",
    )


class RemediationPlanRequest(BaseModel):
    incident_result: dict[str, Any] = Field(
        ...,
        description="Result returned by /api/incidents/analyze-azure or /api/incidents/analyze.",
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata such as app name, platform, and resource group.",
    )
    environment: EnvironmentName = Field(
        default="development",
        description="Deployment environment.",
    )
    allow_cost_increase: bool = Field(
        default=False,
        description="Whether remediation planning may suggest cost-increasing changes.",
    )


class RemediationSimulationRequest(BaseModel):
    scenario: SimulationScenario = Field(
        ...,
        description="Synthetic incident scenario used to test remediation planning.",
        examples=["missing_dependency"],
    )
    environment: EnvironmentName = Field(
        default="development",
        description="Deployment environment.",
    )
    allow_cost_increase: bool = Field(
        default=False,
        description="Whether remediation planning may suggest cost-increasing changes.",
    )