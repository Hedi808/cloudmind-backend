from typing import Any

from pydantic import BaseModel


class AzureDeploymentGenerateRequest(BaseModel):
    repo_url: str
    branch: str | None = None
    overwrite: bool = False

    azure_location: str = "francecentral"
    resource_group: str | None = None
    container_app_environment: str | None = None

    image_registry: str = "ghcr.io"
    image_owner: str | None = None
    image_tag: str = "latest"

    min_replicas: int = 0
    max_replicas: int = 1
    cpu: float = 0.25
    memory: str = "0.5Gi"


class AzureDeploymentGenerateResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]


class AzureDeploymentGenerateAndPublishRequest(BaseModel):
    repo_url: str
    branch: str | None = "main"
    base_branch: str = "main"
    overwrite: bool = False

    azure_location: str = "francecentral"
    resource_group: str | None = None
    container_app_environment: str | None = None

    image_registry: str = "ghcr.io"
    image_owner: str | None = None
    image_tag: str = "latest"

    min_replicas: int = 0
    max_replicas: int = 1
    cpu: float = 0.25
    memory: str = "0.5Gi"

    publish_branch_name: str | None = None


class AzureDeploymentGenerateAndPublishResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]