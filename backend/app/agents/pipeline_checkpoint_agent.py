from __future__ import annotations

from typing import Any

from app.agents.azure_runtime_deployment_agent import AzureRuntimeDeploymentAgent
from app.agents.deployment_verification_agent import DeploymentVerificationAgent


class PipelineCheckpointAgent:
    """Read-only verification for durable pipeline wait states."""

    def __init__(self) -> None:
        self.deployment_verifier = DeploymentVerificationAgent()
        self.azure_runtime_agent = AzureRuntimeDeploymentAgent()

    def check_pull_request(self, pull_request_url: str) -> dict[str, Any]:
        parsed = self.deployment_verifier._parse_pull_request_url(pull_request_url)

        if not parsed.get("success"):
            return {
                "status": "failed",
                "message": parsed.get("message") or "Could not parse pull request URL.",
                "merged": False,
            }

        return self.deployment_verifier._verify_pr_merge_state(
            owner=parsed["owner"],
            repo_name=parsed["repo"],
            pull_request_number=parsed["pull_request_number"],
            token=self.deployment_verifier._get_github_token(),
        )

    def check_ci(
        self,
        repo_url: str,
        merge_commit_sha: str,
    ) -> dict[str, Any]:
        parsed = self.deployment_verifier._parse_github_repo_url(repo_url)

        if not parsed.get("success"):
            return {
                "status": "failed",
                "message": parsed.get("message") or "Could not parse repository URL.",
                "blocking": True,
            }

        return self.deployment_verifier._verify_ci_for_commit(
            owner=parsed["owner"],
            repo_name=parsed["repo"],
            sha=merge_commit_sha,
            token=self.deployment_verifier._get_github_token(),
            require_ci_success=True,
        )

    def check_image(self, image: str) -> dict[str, Any]:
        return self.azure_runtime_agent._check_container_image_access(image)

    def safety(self) -> dict[str, bool]:
        return {
            "read_only": True,
            "merges_pull_requests": False,
            "retries_ci": False,
            "publishes_images": False,
            "deploys_resources": False,
        }
