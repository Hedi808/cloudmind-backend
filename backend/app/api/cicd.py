from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.agents.cicd_agent import CICDAgent
from app.agents.git_agent import GitAgent
from app.schemas.cicd import (
    CICDGenerateAndPublishRequest,
    CICDGenerateAndPublishResponse,
    CICDGenerateRequest,
    CICDGenerateResponse,
)

router = APIRouter(prefix="/cicd", tags=["CI/CD"])

cicd_agent = CICDAgent()
git_agent = GitAgent()


@router.post("/generate", response_model=CICDGenerateResponse)
def generate_cicd_workflow(request: CICDGenerateRequest):
    """
    Generate GitHub Actions workflow locally.

    The workflow is generated inside:
    workspace/repos/<repo-name>/.github/workflows/docker-build.yml
    """
    try:
        result = cicd_agent.generate_for_repo(
            repo_url=request.repo_url,
            branch=request.branch,
            overwrite=request.overwrite,
            image_registry=request.image_registry,
            image_owner=request.image_owner,
            image_tag=request.image_tag,
            workflow_name=request.workflow_name,
        )

        return CICDGenerateResponse(
            status=result["status"],
            message=result["message"],
            result=result,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"CI/CD generation failed: {exc}",
        ) from exc


@router.post("/generate-and-publish", response_model=CICDGenerateAndPublishResponse)
def generate_and_publish_cicd_workflow(request: CICDGenerateAndPublishRequest):
    """
    Generate GitHub Actions workflow locally, then publish it using GitAgent.

    Safe flow:
    1. CICDAgent analyzes the repo.
    2. CICDAgent generates .github/workflows/docker-build.yml locally.
    3. GitAgent creates a CloudMind branch.
    4. GitAgent commits the workflow.
    5. GitAgent pushes the branch.
    6. GitAgent opens a pull request.
    """
    try:
        cicd_result = cicd_agent.generate_for_repo(
            repo_url=request.repo_url,
            branch=request.branch,
            overwrite=request.overwrite,
            image_registry=request.image_registry,
            image_owner=request.image_owner,
            image_tag=request.image_tag,
            workflow_name=request.workflow_name,
        )

        if cicd_result["status"] != "success":
            return CICDGenerateAndPublishResponse(
                status="failed",
                message="CI/CD generation failed, so nothing was published.",
                result={
                    "cicd": cicd_result,
                    "git": None,
                },
            )

        repo_path = Path(cicd_result["analysis"]["metadata"]["local_path"])

        generated_file_paths = _extract_generated_file_paths(
            repo_path=repo_path,
            cicd_result=cicd_result,
        )

        if not generated_file_paths:
            return CICDGenerateAndPublishResponse(
                status="no_changes",
                message="CICDAgent did not generate any new files to publish.",
                result={
                    "cicd": cicd_result,
                    "git": None,
                    "generated_file_paths": [],
                },
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

        branch_name = (
            request.publish_branch_name
            or f"cloudmind/cicd-workflow-{timestamp}"
        )

        git_result = git_agent.publish_deployment_changes(
            local_repo_path=str(repo_path),
            repo_url=request.repo_url,
            generated_files=generated_file_paths,
            base_branch=request.base_branch,
            branch_name=branch_name,
        )

        return CICDGenerateAndPublishResponse(
            status="success",
            message="CI/CD workflow generated and published to a GitHub pull request.",
            result={
                "cicd": cicd_result,
                "git": git_result,
                "generated_file_paths": generated_file_paths,
            },
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"CI/CD generate-and-publish failed: {exc}",
        ) from exc


def _extract_generated_file_paths(
    repo_path: Path,
    cicd_result: dict,
) -> list[str]:
    """
    Convert generated file paths into repo-relative paths for git add.

    Example:
    workspace/repos/test-3s/.github/workflows/docker-build.yml
    -> .github/workflows/docker-build.yml
    """
    generated_file_paths: list[str] = []

    for generated_file in cicd_result.get("generated_files", []):
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