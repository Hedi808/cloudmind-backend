from fastapi import APIRouter

from app.agents.final_demo_orchestrator_agent import FinalDemoOrchestratorAgent
from app.schemas.demo_orchestrator import (
    FinalDemoReportRequest,
    FinalDemoReportResponse,
    PhaseMapResponse,
    QuickDemoReportRequest,
)


router = APIRouter(
    prefix="/demo",
    tags=["Phase 19C - Memory-Aware Final Demo"],
)

final_demo_orchestrator = FinalDemoOrchestratorAgent()


@router.get("/phase-map", response_model=PhaseMapResponse)
def get_phase_map():
    return final_demo_orchestrator.get_phase_map()


@router.post("/final-report", response_model=FinalDemoReportResponse)
def generate_final_report(request: FinalDemoReportRequest):
    return final_demo_orchestrator.generate_final_report(
        project_id=request.project_id,
        repo_url=request.repo_url,
        pull_request_url=request.pull_request_url,
        resource_group=request.resource_group,
        app_name=request.app_name,
        run_pr_validation=request.run_pr_validation,
        run_deployment_verification=request.run_deployment_verification,
        save_to_memory=request.save_to_memory,
    )


@router.post("/quick-report")
def generate_quick_report(request: QuickDemoReportRequest):
    return final_demo_orchestrator.generate_quick_report(
        project_id=request.project_id,
        repo_url=request.repo_url,
        resource_group=request.resource_group,
        app_name=request.app_name,
    )