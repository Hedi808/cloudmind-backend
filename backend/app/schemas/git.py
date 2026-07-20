from typing import Any

from pydantic import BaseModel


class GitTestPublishRequest(BaseModel):
    repo_url: str
    base_branch: str = "main"


class GitTestPublishResponse(BaseModel):
    status: str
    message: str
    result: dict[str, Any]