from typing import Any

from pydantic import BaseModel


class DockerGenerateRequest(BaseModel):
    repo_url: str
    branch: str | None = None
    overwrite: bool = False


class DockerGenerateResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]


class DockerGenerateAndPublishRequest(BaseModel):
    repo_url: str
    branch: str | None = "main"
    base_branch: str = "main"
    overwrite: bool = False
    publish_branch_name: str | None = None


class DockerGenerateAndPublishResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]