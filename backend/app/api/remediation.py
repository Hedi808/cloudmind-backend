from fastapi import APIRouter

from app.agents.remediation_planner_agent import RemediationPlannerAgent
from app.schemas.remediation import (
    RemediationPlanFromAzureRequest,
    RemediationPlanRequest,
    RemediationSimulationRequest,
)

router = APIRouter(
    prefix="/api/remediation",
    tags=["Phase 10 - Remediation Planning"],
)

remediation_planner_agent = RemediationPlannerAgent()


@router.post("/plan-azure")
def plan_azure_remediation(request: RemediationPlanFromAzureRequest):
    result = remediation_planner_agent.plan_from_azure(
        resource_group=request.resource_group,
        app_name=request.app_name,
        health_path=request.health_path,
        timeout_seconds=request.timeout_seconds,
        log_tail=request.log_tail,
        environment=request.environment,
        allow_cost_increase=request.allow_cost_increase,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Remediation plan completed."),
        "result": result,
    }


@router.post("/plan")
def plan_remediation(request: RemediationPlanRequest):
    result = remediation_planner_agent.plan_from_incident(
        incident_result=request.incident_result,
        context=request.context,
        environment=request.environment,
        allow_cost_increase=request.allow_cost_increase,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Remediation plan completed."),
        "result": result,
    }


@router.post("/simulate")
def simulate_remediation(request: RemediationSimulationRequest):
    result = remediation_planner_agent.simulate_remediation_plan(
        scenario=request.scenario,
        environment=request.environment,
        allow_cost_increase=request.allow_cost_increase,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Remediation simulation completed."),
        "result": result,
    }