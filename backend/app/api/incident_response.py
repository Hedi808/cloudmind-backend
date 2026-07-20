from fastapi import APIRouter

from app.agents.incident_response_agent import IncidentResponseAgent
from app.schemas.incident_response import (
    AzureIncidentAnalysisRequest,
    IncidentAnalysisRequest,
)

router = APIRouter(
    prefix="/api/incidents",
    tags=["Phase 9 - Incident Response"],
)

incident_response_agent = IncidentResponseAgent()


@router.post("/analyze-azure")
def analyze_azure_incident(request: AzureIncidentAnalysisRequest):
    result = incident_response_agent.analyze_azure_incident(
        resource_group=request.resource_group,
        app_name=request.app_name,
        health_path=request.health_path,
        timeout_seconds=request.timeout_seconds,
        log_tail=request.log_tail,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Incident analysis completed."),
        "result": result,
    }


@router.post("/analyze")
def analyze_incident(request: IncidentAnalysisRequest):
    result = incident_response_agent.analyze_observability_data(
        status_result=request.status_result,
        logs_result=request.logs_result,
        context=request.context,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Incident analysis completed."),
        "result": result,
    }