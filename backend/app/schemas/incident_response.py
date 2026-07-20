from typing import Any

from pydantic import BaseModel, Field


class AzureIncidentAnalysisRequest(BaseModel):
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


class IncidentAnalysisRequest(BaseModel):
    status_result: dict[str, Any] = Field(
        ...,
        description="Result returned by the observability status endpoint.",
    )
    logs_result: dict[str, Any] | None = Field(
        default=None,
        description="Optional result returned by the observability logs endpoint.",
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata such as app name, platform, resource group.",
    )