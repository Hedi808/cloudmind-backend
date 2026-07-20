from fastapi import APIRouter

from app.agents.post_pr_validation_agent import PostPrValidationAgent
from app.schemas.pr_validation import (
    PullRequestUrlValidationRequest,
    PullRequestValidationRequest,
)

router = APIRouter(
    prefix="/api/pr-validation",
    tags=["Phase 12 - Post-PR Validation"],
)

post_pr_validation_agent = PostPrValidationAgent()


@router.post("/validate")
def validate_pull_request(request: PullRequestValidationRequest):
    result = post_pr_validation_agent.validate_pull_request(
        repo_url=request.repo_url,
        pull_request_number=request.pull_request_number,
        require_ci_success=request.require_ci_success,
        allow_docs_only_without_ci=request.allow_docs_only_without_ci,
        require_human_review=request.require_human_review,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Post-PR validation completed."),
        "result": result,
    }


@router.post("/validate-url")
def validate_pull_request_url(request: PullRequestUrlValidationRequest):
    result = post_pr_validation_agent.validate_pull_request_url(
        pull_request_url=request.pull_request_url,
        require_ci_success=request.require_ci_success,
        allow_docs_only_without_ci=request.allow_docs_only_without_ci,
        require_human_review=request.require_human_review,
    )

    return {
        "status": result.get("status", "completed"),
        "message": result.get("message", "Post-PR validation completed."),
        "result": result,
    }