from typing import Any

from pydantic import BaseModel


class DeploymentPrepareRequest(BaseModel):
    repo_url: str
    branch: str | None = "main"
    base_branch: str = "main"
    overwrite: bool = False
    publish: bool = True

    namespace: str = "cloudmind-staging"
    image_registry: str = "ghcr.io"
    image_owner: str | None = None
    image_tag: str = "latest"
    ingress_host: str | None = None

    publish_branch_name: str | None = None


class DeploymentPrepareResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]