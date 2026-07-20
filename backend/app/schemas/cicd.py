from typing import Any

from pydantic import BaseModel


class CICDGenerateRequest(BaseModel):
    repo_url: str
    branch: str | None = None
    overwrite: bool = False
    image_registry: str = "ghcr.io"
    image_owner: str | None = None
    image_tag: str = "latest"
    workflow_name: str = "docker-build.yml"


class CICDGenerateResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]


class CICDGenerateAndPublishRequest(BaseModel):
    repo_url: str
    branch: str | None = "main"
    base_branch: str = "main"
    overwrite: bool = False
    image_registry: str = "ghcr.io"
    image_owner: str | None = None
    image_tag: str = "latest"
    workflow_name: str = "docker-build.yml"
    publish_branch_name: str | None = None


class CICDGenerateAndPublishResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]