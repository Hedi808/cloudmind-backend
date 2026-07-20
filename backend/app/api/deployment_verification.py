from fastapi import APIRouter

from app.agents.deployment_verification_agent import DeploymentVerificationAgent
from app.schemas.deployment_verification import (
    AzureOnlyDeploymentVerificationRequest,
    DeploymentVerificationRequest,
    DeploymentVerificationUrlRequest,
)

router = APIRouter(
    prefix="/api/deployment-verification",
    tags=["Phase 13 - Deployment Verification"],
)

deployment_verification_agent = DeploymentVerificationAgent()


@router.post("/verify")
def verify_deployment(request: DeploymentVerificationRequest):
    result = deployment_verification_agent.verify_pr_deployment(
        repo_url=request.repo_url,
        pull_request_number=request.pull_request_number,
        resource_group=request.resource_group,
        app_name=request.app_name,
        health_path=request.health_path,
        timeout_seconds=request.timeout_seconds,
        log_tail=request.log_tail,
        require_pr_merged=request.require_pr_merged,
        require_ci_success=request.require_ci_success,
        require_azure_healthy=request.require_azure_healthy,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Deployment verification completed."),
        "result": result,
    }


@router.post("/verify-url")
def verify_deployment_url(request: DeploymentVerificationUrlRequest):
    result = deployment_verification_agent.verify_pr_url_deployment(
        pull_request_url=request.pull_request_url,
        resource_group=request.resource_group,
        app_name=request.app_name,
        health_path=request.health_path,
        timeout_seconds=request.timeout_seconds,
        log_tail=request.log_tail,
        require_pr_merged=request.require_pr_merged,
        require_ci_success=request.require_ci_success,
        require_azure_healthy=request.require_azure_healthy,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Deployment verification completed."),
        "result": result,
    }


@router.post("/verify-azure")
def verify_azure_deployment(request: AzureOnlyDeploymentVerificationRequest):
    result = deployment_verification_agent.verify_azure_only(
        resource_group=request.resource_group,
        app_name=request.app_name,
        health_path=request.health_path,
        timeout_seconds=request.timeout_seconds,
        log_tail=request.log_tail,
        require_azure_healthy=request.require_azure_healthy,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Azure deployment verification completed."),
        "result": result,
    }