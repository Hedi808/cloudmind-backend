from pydantic import BaseModel, Field


class DeploymentVerificationRequest(BaseModel):
    repo_url: str = Field(
        ...,
        description="GitHub repository URL.",
        examples=["https://github.com/Hedi808/test-3s.git"],
    )
    pull_request_number: int = Field(
        ...,
        ge=1,
        description="Pull request number to verify after merge.",
        examples=[9],
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
        description="Number of recent Azure logs to inspect.",
    )
    require_pr_merged: bool = Field(
        default=True,
        description="If true, verification fails until the PR is merged.",
    )
    require_ci_success: bool = Field(
        default=True,
        description="If true, verification fails unless CI succeeds for the merge commit.",
    )
    require_azure_healthy: bool = Field(
        default=True,
        description="If true, verification fails unless Azure health and incident checks are clean.",
    )


class DeploymentVerificationUrlRequest(BaseModel):
    pull_request_url: str = Field(
        ...,
        description="GitHub pull request URL.",
        examples=["https://github.com/Hedi808/test-3s/pull/9"],
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
        description="Number of recent Azure logs to inspect.",
    )
    require_pr_merged: bool = Field(
        default=True,
        description="If true, verification fails until the PR is merged.",
    )
    require_ci_success: bool = Field(
        default=True,
        description="If true, verification fails unless CI succeeds for the merge commit.",
    )
    require_azure_healthy: bool = Field(
        default=True,
        description="If true, verification fails unless Azure health and incident checks are clean.",
    )


class AzureOnlyDeploymentVerificationRequest(BaseModel):
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
        description="Number of recent Azure logs to inspect.",
    )
    require_azure_healthy: bool = Field(
        default=True,
        description="If true, verification fails unless Azure health and incident checks are clean.",
    )