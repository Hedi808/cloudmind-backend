from typing import Any

from pydantic import BaseModel, Field


class AnalyzeRepoRequest(BaseModel):
    repo_url: str
    branch: str | None = None


class ProjectComponent(BaseModel):
    name: str
    type: str
    language: str | None = None
    framework: str | None = None
    package_file: str | None = None
    port: int | None = None
    start_command: str | None = None
    build_command: str | None = None


class RepoAnalysisResponse(BaseModel):
    repo_url: str
    repo_name: str
    status: str
    project_type: str
    detected_languages: list[str] = Field(default_factory=list)
    detected_frameworks: list[str] = Field(default_factory=list)
    components: list[ProjectComponent] = Field(default_factory=list)
    important_files: list[str] = Field(default_factory=list)
    missing_devops_files: list[str] = Field(default_factory=list)
    tree_preview: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)