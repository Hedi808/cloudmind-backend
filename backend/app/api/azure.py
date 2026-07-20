from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.agents.azure_deployment_agent import AzureDeploymentAgent
from app.agents.git_agent import GitAgent
from app.schemas.azure import (
    AzureDeploymentGenerateAndPublishRequest,
    AzureDeploymentGenerateAndPublishResponse,
    AzureDeploymentGenerateRequest,
    AzureDeploymentGenerateResponse,
)

router = APIRouter(prefix="/azure", tags=["Azure"])

azure_deployment_agent = AzureDeploymentAgent()
git_agent = GitAgent()


@router.post("/generate", response_model=AzureDeploymentGenerateResponse)
def generate_azure_deployment_files(request: AzureDeploymentGenerateRequest):
    try:
        result = azure_deployment_agent.generate_for_repo(
            repo_url=request.repo_url,
            branch=request.branch,
            overwrite=request.overwrite,
            azure_location=request.azure_location,
            resource_group=request.resource_group,
            container_app_environment=request.container_app_environment,
            image_registry=request.image_registry,
            image_owner=request.image_owner,
            image_tag=request.image_tag,
            min_replicas=request.min_replicas,
            max_replicas=request.max_replicas,
            cpu=request.cpu,
            memory=request.memory,
        )

        return AzureDeploymentGenerateResponse(
            status=result["status"],
            message=result["message"],
            result=result,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Azure deployment generation failed: {exc}",
        ) from exc


@router.post("/generate-and-publish", response_model=AzureDeploymentGenerateAndPublishResponse)
def generate_and_publish_azure_deployment_files(
    request: AzureDeploymentGenerateAndPublishRequest,
):
    try:
        azure_result = azure_deployment_agent.generate_for_repo(
            repo_url=request.repo_url,
            branch=request.branch,
            overwrite=request.overwrite,
            azure_location=request.azure_location,
            resource_group=request.resource_group,
            container_app_environment=request.container_app_environment,
            image_registry=request.image_registry,
            image_owner=request.image_owner,
            image_tag=request.image_tag,
            min_replicas=request.min_replicas,
            max_replicas=request.max_replicas,
            cpu=request.cpu,
            memory=request.memory,
        )

        if azure_result["status"] != "success":
            return AzureDeploymentGenerateAndPublishResponse(
                status="failed",
                message="Azure deployment generation failed, so nothing was published.",
                result={
                    "azure": azure_result,
                    "git": None,
                },
            )

        repo_path = Path(azure_result["analysis"]["metadata"]["local_path"])

        generated_file_paths = _extract_generated_file_paths(
            repo_path=repo_path,
            azure_result=azure_result,
        )

        if not generated_file_paths:
            return AzureDeploymentGenerateAndPublishResponse(
                status="no_changes",
                message="AzureDeploymentAgent did not generate any new files to publish.",
                result={
                    "azure": azure_result,
                    "git": None,
                    "generated_file_paths": [],
                },
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

        branch_name = (
            request.publish_branch_name
            or f"cloudmind/azure-deployment-{timestamp}"
        )

        git_result = git_agent.publish_deployment_changes(
            local_repo_path=str(repo_path),
            repo_url=request.repo_url,
            generated_files=generated_file_paths,
            base_branch=request.base_branch,
            branch_name=branch_name,
        )

        return AzureDeploymentGenerateAndPublishResponse(
            status="success",
            message="Azure deployment files generated and published to a GitHub pull request.",
            result={
                "azure": azure_result,
                "git": git_result,
                "generated_file_paths": generated_file_paths,
            },
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Azure deployment generate-and-publish failed: {exc}",
        ) from exc


def _extract_generated_file_paths(
    repo_path: Path,
    azure_result: dict,
) -> list[str]:
    generated_file_paths: list[str] = []

    for generated_file in azure_result.get("generated_files", []):
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