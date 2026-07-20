from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.agents.docker_agent import DockerAgent
from app.agents.git_agent import GitAgent
from app.schemas.docker import (
    DockerGenerateAndPublishRequest,
    DockerGenerateAndPublishResponse,
    DockerGenerateRequest,
    DockerGenerateResponse,
)

router = APIRouter(prefix="/docker", tags=["Docker"])

docker_agent = DockerAgent()
git_agent = GitAgent()


@router.post("/generate", response_model=DockerGenerateResponse)
def generate_docker_files(request: DockerGenerateRequest):
    """
    Generate or review Docker-related files for a repository.

    If Docker files already exist and overwrite=False,
    CloudMind skips them and returns a review.
    """
    try:
        result = docker_agent.generate_for_repo(
            repo_url=request.repo_url,
            branch=request.branch,
            overwrite=request.overwrite,
        )

        return DockerGenerateResponse(
            status=result["status"],
            message=result["message"],
            result=result,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Docker generation failed: {exc}",
        ) from exc


@router.post("/generate-and-publish", response_model=DockerGenerateAndPublishResponse)
def generate_and_publish_docker_files(request: DockerGenerateAndPublishRequest):
    """
    Generate Docker files locally, then publish them to GitHub using GitAgent.

    Safe flow:
    1. DockerAgent analyzes the repo.
    2. DockerAgent generates Dockerfile, .dockerignore, and compose.yml locally.
    3. GitAgent creates a CloudMind branch.
    4. GitAgent commits the generated files.
    5. GitAgent pushes the branch.
    6. GitAgent opens a pull request.
    """
    try:
        docker_result = docker_agent.generate_for_repo(
            repo_url=request.repo_url,
            branch=request.branch,
            overwrite=request.overwrite,
        )

        if docker_result["status"] != "success":
            return DockerGenerateAndPublishResponse(
                status="failed",
                message="Docker generation failed, so nothing was published.",
                result={
                    "docker": docker_result,
                    "git": None,
                },
            )

        repo_path = Path(docker_result["analysis"]["metadata"]["local_path"])

        generated_file_paths = _extract_generated_file_paths(
            repo_path=repo_path,
            docker_result=docker_result,
        )

        if not generated_file_paths:
            return DockerGenerateAndPublishResponse(
                status="no_changes",
                message="DockerAgent did not generate any new files to publish.",
                result={
                    "docker": docker_result,
                    "git": None,
                    "generated_file_paths": [],
                },
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

        branch_name = (
            request.publish_branch_name
            or f"cloudmind/docker-files-{timestamp}"
        )

        git_result = git_agent.publish_deployment_changes(
            local_repo_path=str(repo_path),
            repo_url=request.repo_url,
            generated_files=generated_file_paths,
            base_branch=request.base_branch,
            branch_name=branch_name,
        )

        return DockerGenerateAndPublishResponse(
            status="success",
            message="Docker files generated and published to a GitHub pull request.",
            result={
                "docker": docker_result,
                "git": git_result,
                "generated_file_paths": generated_file_paths,
            },
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Docker generate-and-publish failed: {exc}",
        ) from exc


def _extract_generated_file_paths(
    repo_path: Path,
    docker_result: dict,
) -> list[str]:
    """
    Convert generated file paths into repo-relative paths for git add.

    Example:
    workspace/repos/test-3s/Dockerfile
    -> Dockerfile
    """
    generated_file_paths: list[str] = []

    for generated_file in docker_result.get("generated_files", []):
        raw_path = generated_file.get("path")

        if not raw_path:
            continue

        file_path = Path(raw_path)

        try:
            relative_path = file_path.relative_to(repo_path)
            generated_file_paths.append(relative_path.as_posix())
        except ValueError:
            generated_file_paths.append(file_path.as_posix())

    return generated_file_paths