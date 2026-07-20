from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.agents.git_agent import GitAgent
from app.agents.kubernetes_agent import KubernetesAgent
from app.schemas.kubernetes import (
    KubernetesGenerateAndPublishRequest,
    KubernetesGenerateAndPublishResponse,
    KubernetesGenerateRequest,
    KubernetesGenerateResponse,
)

router = APIRouter(prefix="/kubernetes", tags=["Kubernetes"])

kubernetes_agent = KubernetesAgent()
git_agent = GitAgent()


@router.post("/generate", response_model=KubernetesGenerateResponse)
def generate_kubernetes_files(request: KubernetesGenerateRequest):
    """
    Generate Kubernetes manifests for a repository.

    The manifests are generated locally inside:
    workspace/repos/<repo-name>/k8s/
    """
    try:
        result = kubernetes_agent.generate_for_repo(
            repo_url=request.repo_url,
            branch=request.branch,
            overwrite=request.overwrite,
            namespace=request.namespace,
            image_registry=request.image_registry,
            image_owner=request.image_owner,
            image_tag=request.image_tag,
            ingress_host=request.ingress_host,
        )

        return KubernetesGenerateResponse(
            status=result["status"],
            message=result["message"],
            result=result,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Kubernetes generation failed: {exc}",
        ) from exc


@router.post("/generate-and-publish", response_model=KubernetesGenerateAndPublishResponse)
def generate_and_publish_kubernetes_files(request: KubernetesGenerateAndPublishRequest):
    """
    Generate Kubernetes manifests locally, then publish them to GitHub using GitAgent.

    Safe flow:
    1. KubernetesAgent analyzes the repo.
    2. KubernetesAgent generates k8s/*.yaml files locally.
    3. GitAgent creates a CloudMind branch.
    4. GitAgent commits the generated files.
    5. GitAgent pushes the branch.
    6. GitAgent opens a pull request.
    """
    try:
        kubernetes_result = kubernetes_agent.generate_for_repo(
            repo_url=request.repo_url,
            branch=request.branch,
            overwrite=request.overwrite,
            namespace=request.namespace,
            image_registry=request.image_registry,
            image_owner=request.image_owner,
            image_tag=request.image_tag,
            ingress_host=request.ingress_host,
        )

        if kubernetes_result["status"] != "success":
            return KubernetesGenerateAndPublishResponse(
                status="failed",
                message="Kubernetes generation failed, so nothing was published.",
                result={
                    "kubernetes": kubernetes_result,
                    "git": None,
                },
            )

        repo_path = Path(kubernetes_result["analysis"]["metadata"]["local_path"])

        generated_file_paths = _extract_generated_file_paths(
            repo_path=repo_path,
            kubernetes_result=kubernetes_result,
        )

        if not generated_file_paths:
            return KubernetesGenerateAndPublishResponse(
                status="no_changes",
                message="KubernetesAgent did not generate any new files to publish.",
                result={
                    "kubernetes": kubernetes_result,
                    "git": None,
                    "generated_file_paths": [],
                },
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

        branch_name = (
            request.publish_branch_name
            or f"cloudmind/kubernetes-files-{timestamp}"
        )

        git_result = git_agent.publish_deployment_changes(
            local_repo_path=str(repo_path),
            repo_url=request.repo_url,
            generated_files=generated_file_paths,
            base_branch=request.base_branch,
            branch_name=branch_name,
        )

        return KubernetesGenerateAndPublishResponse(
            status="success",
            message="Kubernetes manifests generated and published to a GitHub pull request.",
            result={
                "kubernetes": kubernetes_result,
                "git": git_result,
                "generated_file_paths": generated_file_paths,
            },
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Kubernetes generate-and-publish failed: {exc}",
        ) from exc


def _extract_generated_file_paths(
    repo_path: Path,
    kubernetes_result: dict,
) -> list[str]:
    """
    Convert generated file paths into repo-relative paths for git add.

    Example:
    workspace/repos/test-3s/k8s/deployment.yaml
    -> k8s/deployment.yaml
    """
    generated_file_paths: list[str] = []

    for generated_file in kubernetes_result.get("generated_files", []):
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