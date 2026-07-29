from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter

from app.agents.pipeline_executor_agent import PipelineExecutorAgent
from app.schemas.pipeline import PipelineRunRequest, PipelineRunResponse


router = APIRouter(
    prefix="/pipeline",
    tags=["Phase 20B - Backend Pipeline Executor"],
)


@lru_cache(maxsize=1)
def get_pipeline_executor() -> PipelineExecutorAgent:
    """
    Lazy singleton.

    Important:
    Do not instantiate PipelineExecutorAgent at module import time.
    Uvicorn reload imports app.main many times, so heavy agents should be created
    only when the endpoint is actually called.
    """
    return PipelineExecutorAgent()


@router.get("/health")
def pipeline_health():
    return {
        "status": "healthy",
        "service": "pipeline-executor",
        "phase": "phase_20b_backend_pipeline_executor",
        "safety": {
            "approval_required_for_write_steps": True,
            "approval_required_for_azure_deploy": True,
            "pauses_after_gitops_by_default": True,
            "does_not_merge_pull_requests": True,
            "does_not_push_directly_to_main": True,
        },
    }


@router.post("/preview")
def preview_pipeline(request: PipelineRunRequest):
    pipeline_executor = get_pipeline_executor()

    return pipeline_executor.preview(
        project_id=request.project_id,
        repo_url=request.repo_url,
    )


@router.post("/next-step", response_model=PipelineRunResponse)
def run_next_pipeline_step(request: PipelineRunRequest):
    pipeline_executor = get_pipeline_executor()

    return pipeline_executor.run_next_step(
        project_id=request.project_id,
        repo_url=request.repo_url,
        resource_group=request.resource_group,
        app_name=request.app_name,
        pull_request_url=request.pull_request_url,
        approval_confirmed=request.approval_confirmed,
        dry_run=request.dry_run,
        run_optional=request.run_optional,
        run_optional_reporting=request.run_optional_reporting,
        overwrite=request.overwrite,
        publish_to_github=request.publish_to_github,
        session_id=request.session_id,
    )


@router.post("/run", response_model=PipelineRunResponse)
def run_pipeline(request: PipelineRunRequest):
    pipeline_executor = get_pipeline_executor()

    return pipeline_executor.run_pipeline(
        project_id=request.project_id,
        repo_url=request.repo_url,
        resource_group=request.resource_group,
        app_name=request.app_name,
        pull_request_url=request.pull_request_url,
        approval_confirmed=request.approval_confirmed,
        max_steps=request.max_steps,
        dry_run=request.dry_run,
        run_optional=request.run_optional,
        run_optional_reporting=request.run_optional_reporting,
        stop_after_gitops=request.stop_after_gitops,
        overwrite=request.overwrite,
        publish_to_github=request.publish_to_github,
        session_id=request.session_id,
    )