from fastapi import APIRouter, HTTPException

from app.agents.workflow_engine_agent import WorkflowEngineAgent
from app.schemas.workflow import WorkflowPlanRequest, WorkflowPlanResponse


router = APIRouter(
    prefix="/workflows",
    tags=["Phase 19A - Workflow Engine"],
)

workflow_engine = WorkflowEngineAgent()


@router.post("/plan", response_model=WorkflowPlanResponse)
def build_workflow_plan(request: WorkflowPlanRequest):
    if not request.project_id and not request.repo_url:
        raise HTTPException(
            status_code=400,
            detail="Provide either project_id or repo_url.",
        )

    return workflow_engine.build_deployment_plan(
        project_id=request.project_id,
        repo_url=request.repo_url,
    )


@router.get("/plan/by-project/{project_id}", response_model=WorkflowPlanResponse)
def build_workflow_plan_by_project(project_id: str):
    return workflow_engine.build_deployment_plan(project_id=project_id)