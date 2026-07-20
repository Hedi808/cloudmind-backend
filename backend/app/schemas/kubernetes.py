from typing import Any

from pydantic import BaseModel


class KubernetesGenerateRequest(BaseModel):
    repo_url: str
    branch: str | None = None
    overwrite: bool = False
    namespace: str = "cloudmind-staging"
    image_registry: str = "ghcr.io"
    image_owner: str | None = None
    image_tag: str = "latest"
    ingress_host: str | None = None


class KubernetesGenerateResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]


class KubernetesGenerateAndPublishRequest(BaseModel):
    repo_url: str
    branch: str | None = "main"
    base_branch: str = "main"
    overwrite: bool = False
    namespace: str = "cloudmind-staging"
    image_registry: str = "ghcr.io"
    image_owner: str | None = None
    image_tag: str = "latest"
    ingress_host: str | None = None
    publish_branch_name: str | None = None


class KubernetesGenerateAndPublishResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]