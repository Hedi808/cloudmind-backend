from fastapi import APIRouter

from app.agents.remediation_pr_agent import RemediationPrAgent
from app.schemas.remediation_pr import (
    RemediationPrFromAzureRequest,
    RemediationPrFromPlanRequest,
    RemediationPrPreviewRequest,
    RemediationPrSimulationRequest,
)

router = APIRouter(
    prefix="/api/remediation-pr",
    tags=["Phase 11 - Remediation Pull Requests"],
)

remediation_pr_agent = RemediationPrAgent()


@router.post("/create-from-azure")
def create_remediation_pr_from_azure(request: RemediationPrFromAzureRequest):
    result = remediation_pr_agent.create_pr_from_azure_plan(
        repo_url=request.repo_url,
        resource_group=request.resource_group,
        app_name=request.app_name,
        approval_confirmed=request.approval_confirmed,
        health_path=request.health_path,
        timeout_seconds=request.timeout_seconds,
        log_tail=request.log_tail,
        environment=request.environment,
        allow_cost_increase=request.allow_cost_increase,
        create_pr_when_no_remediation=request.create_pr_when_no_remediation,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Remediation PR workflow completed."),
        "result": result,
    }


@router.post("/create-from-plan")
def create_remediation_pr_from_plan(request: RemediationPrFromPlanRequest):
    result = remediation_pr_agent.create_pr_from_plan(
        repo_url=request.repo_url,
        remediation_plan=request.remediation_plan,
        approval_confirmed=request.approval_confirmed,
        create_pr_when_no_remediation=request.create_pr_when_no_remediation,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Remediation PR workflow completed."),
        "result": result,
    }


@router.post("/create-from-simulation")
def create_remediation_pr_from_simulation(request: RemediationPrSimulationRequest):
    result = remediation_pr_agent.create_pr_from_simulation(
        repo_url=request.repo_url,
        scenario=request.scenario,
        approval_confirmed=request.approval_confirmed,
        environment=request.environment,
        allow_cost_increase=request.allow_cost_increase,
        create_pr_when_no_remediation=request.create_pr_when_no_remediation,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Remediation PR simulation completed."),
        "result": result,
    }


@router.post("/preview")
def preview_remediation_pr(request: RemediationPrPreviewRequest):
    result = remediation_pr_agent.preview_changes_from_plan(
        remediation_plan=request.remediation_plan,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Remediation PR preview completed."),
        "result": result,
    }