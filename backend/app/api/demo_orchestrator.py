from fastapi import APIRouter

from app.agents.final_demo_orchestrator_agent import FinalDemoOrchestratorAgent
from app.schemas.demo_orchestrator import (
    FinalDemoReportRequest,
    QuickDemoReportRequest,
)

router = APIRouter(
    prefix="/api/demo",
    tags=["Phase 14 - Final Demo Orchestrator"],
)

final_demo_orchestrator_agent = FinalDemoOrchestratorAgent()


@router.get("/phase-map")
def get_phase_map():
    result = final_demo_orchestrator_agent.get_phase_map()

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Phase map generated."),
        "result": result,
    }


@router.post("/final-report")
def run_final_demo_report(request: FinalDemoReportRequest):
    result = final_demo_orchestrator_agent.run_final_report(
        repo_url=request.repo_url,
        resource_group=request.resource_group,
        app_name=request.app_name,
        pull_request_number=request.pull_request_number,
        pull_request_url=request.pull_request_url,
        health_path=request.health_path,
        timeout_seconds=request.timeout_seconds,
        log_tail=request.log_tail,
        environment=request.environment,
        run_pr_validation=request.run_pr_validation,
        run_azure_verification=request.run_azure_verification,
        run_remediation_plan=request.run_remediation_plan,
        require_ci_success_for_pr_validation=request.require_ci_success_for_pr_validation,
        allow_docs_only_without_ci=request.allow_docs_only_without_ci,
        require_human_review_for_pr_validation=request.require_human_review_for_pr_validation,
        require_pr_merged_for_deployment=request.require_pr_merged_for_deployment,
        require_ci_success_for_deployment=request.require_ci_success_for_deployment,
        require_azure_healthy=request.require_azure_healthy,
        include_raw_outputs=request.include_raw_outputs,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Final demo report generated."),
        "result": result,
    }


@router.post("/quick-report")
def run_quick_demo_report(request: QuickDemoReportRequest):
    result = final_demo_orchestrator_agent.run_final_report(
        repo_url=request.repo_url,
        resource_group=request.resource_group,
        app_name=request.app_name,
        pull_request_url=request.pull_request_url,
        health_path="/health",
        timeout_seconds=60,
        log_tail=100,
        environment="development",
        run_pr_validation=True,
        run_azure_verification=True,
        run_remediation_plan=True,
        require_ci_success_for_pr_validation=False,
        allow_docs_only_without_ci=True,
        require_human_review_for_pr_validation=False,
        require_pr_merged_for_deployment=False,
        require_ci_success_for_deployment=False,
        require_azure_healthy=True,
        include_raw_outputs=False,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Quick demo report generated."),
        "result": result,
    }