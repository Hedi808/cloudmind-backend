from pydantic import BaseModel, Field


class PullRequestValidationRequest(BaseModel):
    repo_url: str = Field(
        ...,
        description="GitHub repository URL.",
        examples=["https://github.com/Hedi808/test-3s.git"],
    )
    pull_request_number: int = Field(
        ...,
        ge=1,
        description="Pull request number to validate.",
        examples=[8],
    )
    require_ci_success: bool = Field(
        default=False,
        description="If true, validation fails unless CI is confirmed successful.",
    )
    allow_docs_only_without_ci: bool = Field(
        default=True,
        description="If true, documentation-only PRs can pass even when no CI exists.",
    )
    require_human_review: bool = Field(
        default=False,
        description="If true, validation blocks until at least one approval exists.",
    )


class PullRequestUrlValidationRequest(BaseModel):
    pull_request_url: str = Field(
        ...,
        description="GitHub pull request URL.",
        examples=["https://github.com/Hedi808/test-3s/pull/8"],
    )
    require_ci_success: bool = Field(
        default=False,
        description="If true, validation fails unless CI is confirmed successful.",
    )
    allow_docs_only_without_ci: bool = Field(
        default=True,
        description="If true, documentation-only PRs can pass even when no CI exists.",
    )
    require_human_review: bool = Field(
        default=False,
        description="If true, validation blocks until at least one approval exists.",
    )