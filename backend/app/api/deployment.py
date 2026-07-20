from fastapi import APIRouter, HTTPException

from app.agents.deployment_prepare_agent import DeploymentPrepareAgent
from app.schemas.deployment import DeploymentPrepareRequest, DeploymentPrepareResponse

router = APIRouter(prefix="/deployment", tags=["Deployment"])

deployment_prepare_agent = DeploymentPrepareAgent()


@router.post("/prepare", response_model=DeploymentPrepareResponse)
def prepare_deployment(request: DeploymentPrepareRequest):
    """
    Prepare deployment files in one workflow.

    Safe flow:
    1. Analyze repository once.
    2. Generate Docker files.
    3. Generate Kubernetes manifests.
    4. Push all generated files to one CloudMind branch.
    5. Open one GitHub pull request.
    """
    try:
        result = deployment_prepare_agent.prepare(
            repo_url=request.repo_url,
            branch=request.branch,
            base_branch=request.base_branch,
            overwrite=request.overwrite,
            publish=request.publish,
            namespace=request.namespace,
            image_registry=request.image_registry,
            image_owner=request.image_owner,
            image_tag=request.image_tag,
            ingress_host=request.ingress_host,
            publish_branch_name=request.publish_branch_name,
        )

        return DeploymentPrepareResponse(
            status=result["status"],
            message=result["message"],
            result=result,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Deployment preparation failed: {exc}",
        ) from exc