import os
import re
from typing import Any
from urllib.parse import urlparse

import requests

from app.agents.incident_response_agent import IncidentResponseAgent
from app.agents.observability_agent import ObservabilityAgent


class DeploymentVerificationAgent:
    """
    Phase 13 agent.

    Read-only deployment verification:
    - checks whether a PR is merged
    - checks CI on the merge commit
    - checks Azure Container App health
    - retrieves logs
    - runs incident analysis
    - returns a deployment verification decision
    """

    def __init__(self) -> None:
        self.observability_agent = ObservabilityAgent()
        self.incident_response_agent = IncidentResponseAgent()

    def verify_pr_deployment(
        self,
        repo_url: str,
        pull_request_number: int,
        resource_group: str,
        app_name: str,
        health_path: str = "/health",
        timeout_seconds: int = 60,
        log_tail: int = 100,
        require_pr_merged: bool = True,
        require_ci_success: bool = True,
        require_azure_healthy: bool = True,
    ) -> dict[str, Any]:
        repo_url = repo_url.strip()
        resource_group = resource_group.strip()
        app_name = app_name.strip()

        if not repo_url:
            return {
                "status": "failed",
                "message": "repo_url is required.",
                "verified": False,
            }

        if pull_request_number <= 0:
            return {
                "status": "failed",
                "message": "pull_request_number must be greater than 0.",
                "verified": False,
            }

        if not resource_group or not app_name:
            return {
                "status": "failed",
                "message": "resource_group and app_name are required.",
                "verified": False,
            }

        repo_info = self._parse_github_repo_url(repo_url)

        if not repo_info["success"]:
            return {
                "status": "failed",
                "message": repo_info["message"],
                "verified": False,
            }

        return self._verify(
            owner=repo_info["owner"],
            repo_name=repo_info["repo"],
            pull_request_number=pull_request_number,
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
            log_tail=log_tail,
            require_pr_merged=require_pr_merged,
            require_ci_success=require_ci_success,
            require_azure_healthy=require_azure_healthy,
        )

    def verify_pr_url_deployment(
        self,
        pull_request_url: str,
        resource_group: str,
        app_name: str,
        health_path: str = "/health",
        timeout_seconds: int = 60,
        log_tail: int = 100,
        require_pr_merged: bool = True,
        require_ci_success: bool = True,
        require_azure_healthy: bool = True,
    ) -> dict[str, Any]:
        pull_request_url = pull_request_url.strip()
        resource_group = resource_group.strip()
        app_name = app_name.strip()

        if not resource_group or not app_name:
            return {
                "status": "failed",
                "message": "resource_group and app_name are required.",
                "verified": False,
            }

        pr_info = self._parse_pull_request_url(pull_request_url)

        if not pr_info["success"]:
            return {
                "status": "failed",
                "message": pr_info["message"],
                "verified": False,
            }

        return self._verify(
            owner=pr_info["owner"],
            repo_name=pr_info["repo"],
            pull_request_number=pr_info["pull_request_number"],
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
            log_tail=log_tail,
            require_pr_merged=require_pr_merged,
            require_ci_success=require_ci_success,
            require_azure_healthy=require_azure_healthy,
        )

    def verify_azure_only(
        self,
        resource_group: str,
        app_name: str,
        health_path: str = "/health",
        timeout_seconds: int = 60,
        log_tail: int = 100,
        require_azure_healthy: bool = True,
    ) -> dict[str, Any]:
        resource_group = resource_group.strip()
        app_name = app_name.strip()

        if not resource_group or not app_name:
            return {
                "status": "failed",
                "message": "resource_group and app_name are required.",
                "verified": False,
            }

        azure_verification = self._verify_azure_runtime(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
            log_tail=log_tail,
        )

        decision = self._build_final_decision(
            pr_verification=None,
            ci_verification=None,
            azure_verification=azure_verification,
            require_pr_merged=False,
            require_ci_success=False,
            require_azure_healthy=require_azure_healthy,
        )

        return {
            "status": decision["status"],
            "message": decision["message"],
            "phase": "phase_13_deployment_verification",
            "verified": decision["verified"],
            "verification_scope": "azure_only",
            "azure": azure_verification,
            "merge_blockers": decision["merge_blockers"],
            "warnings": decision["warnings"],
            "risk_notes": decision["risk_notes"],
            "deployment_recommendation": decision["deployment_recommendation"],
            "next_steps": decision["next_steps"],
            "safety": self._safety_block(),
        }

    def _verify(
        self,
        owner: str,
        repo_name: str,
        pull_request_number: int,
        resource_group: str,
        app_name: str,
        health_path: str,
        timeout_seconds: int,
        log_tail: int,
        require_pr_merged: bool,
        require_ci_success: bool,
        require_azure_healthy: bool,
    ) -> dict[str, Any]:
        token = self._get_github_token()

        pr_verification = self._verify_pr_merge_state(
            owner=owner,
            repo_name=repo_name,
            pull_request_number=pull_request_number,
            token=token,
        )

        merge_commit_sha = None

        if pr_verification.get("status") != "failed":
            merge_commit_sha = pr_verification.get("pull_request", {}).get("merge_commit_sha")

        ci_verification = self._verify_ci_for_commit(
            owner=owner,
            repo_name=repo_name,
            sha=merge_commit_sha,
            token=token,
            require_ci_success=require_ci_success,
        )

        azure_verification = self._verify_azure_runtime(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
            log_tail=log_tail,
        )

        decision = self._build_final_decision(
            pr_verification=pr_verification,
            ci_verification=ci_verification,
            azure_verification=azure_verification,
            require_pr_merged=require_pr_merged,
            require_ci_success=require_ci_success,
            require_azure_healthy=require_azure_healthy,
        )

        return {
            "status": decision["status"],
            "message": decision["message"],
            "phase": "phase_13_deployment_verification",
            "verified": decision["verified"],
            "verification_scope": "pr_and_azure",
            "repo": {
                "owner": owner,
                "name": repo_name,
            },
            "pull_request_number": pull_request_number,
            "pr": pr_verification,
            "ci": ci_verification,
            "azure": azure_verification,
            "merge_blockers": decision["merge_blockers"],
            "warnings": decision["warnings"],
            "risk_notes": decision["risk_notes"],
            "deployment_recommendation": decision["deployment_recommendation"],
            "next_steps": decision["next_steps"],
            "safety": self._safety_block(),
        }

    def _verify_pr_merge_state(
        self,
        owner: str,
        repo_name: str,
        pull_request_number: int,
        token: str | None,
    ) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls/{pull_request_number}"
        response_result = self._github_get(url=url, token=token)

        if not response_result["success"]:
            return {
                "status": "failed",
                "merged": False,
                "message": "Could not read pull request from GitHub.",
                "github_api": response_result,
            }

        data = response_result["json"]
        merged_at = data.get("merged_at")
        merged = bool(data.get("merged", False) or merged_at)
        state = data.get("state")

        if merged:
            status = "merged"
            message = "Pull request is merged."
        elif state == "closed":
            status = "closed_not_merged"
            message = "Pull request is closed but not merged."
        else:
            status = "not_merged"
            message = "Pull request is not merged yet."

        return {
            "status": status,
            "message": message,
            "merged": merged,
            "pull_request": {
                "number": data.get("number"),
                "title": data.get("title"),
                "url": data.get("html_url"),
                "state": state,
                "draft": data.get("draft", False),
                "merged": merged,
                "merged_at": merged_at,
                "merge_commit_sha": data.get("merge_commit_sha"),
                "base_branch": data.get("base", {}).get("ref"),
                "head_branch": data.get("head", {}).get("ref"),
                "head_sha": data.get("head", {}).get("sha"),
                "author": data.get("user", {}).get("login"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
            },
        }

    def _verify_ci_for_commit(
        self,
        owner: str,
        repo_name: str,
        sha: str | None,
        token: str | None,
        require_ci_success: bool,
    ) -> dict[str, Any]:
        if not sha:
            return {
                "status": "missing_commit_sha",
                "message": "No merge commit SHA was available, so CI could not be verified.",
                "blocking": require_ci_success,
                "commit_sha": None,
                "has_any_ci": False,
                "check_runs": [],
                "statuses": [],
                "failed_checks": [],
                "pending_checks": [],
                "successful_checks": [],
                "failed_statuses": [],
                "pending_statuses": [],
                "successful_statuses": [],
                "warnings": ["No merge commit SHA was available."],
            }

        check_runs_result = self._get_check_runs(
            owner=owner,
            repo_name=repo_name,
            sha=sha,
            token=token,
        )

        combined_status_result = self._get_combined_status(
            owner=owner,
            repo_name=repo_name,
            sha=sha,
            token=token,
        )

        check_runs = check_runs_result.get("check_runs", []) if check_runs_result.get("success") else []
        statuses = combined_status_result.get("statuses", []) if combined_status_result.get("success") else []

        failed_conclusions = [
            "failure",
            "cancelled",
            "timed_out",
            "action_required",
            "startup_failure",
        ]

        failed_checks = []
        pending_checks = []
        successful_checks = []

        for check_run in check_runs:
            name = check_run.get("name", "unknown")
            check_status = check_run.get("status")
            conclusion = check_run.get("conclusion")

            if check_status != "completed":
                pending_checks.append(name)
            elif conclusion in failed_conclusions:
                failed_checks.append(name)
            elif conclusion in ["success", "skipped", "neutral"]:
                successful_checks.append(name)
            else:
                pending_checks.append(name)

        failed_statuses = []
        pending_statuses = []
        successful_statuses = []

        for status_item in statuses:
            context = status_item.get("context", "unknown")
            state = status_item.get("state")

            if state in ["failure", "error"]:
                failed_statuses.append(context)
            elif state == "pending":
                pending_statuses.append(context)
            elif state == "success":
                successful_statuses.append(context)

        has_any_ci = bool(check_runs or statuses)
        has_failures = bool(failed_checks or failed_statuses)
        has_pending = bool(pending_checks or pending_statuses)
        has_success = bool(successful_checks or successful_statuses)

        warnings = []
        blocking = False

        if has_failures:
            ci_status = "failed"
            blocking = require_ci_success
            warnings.append("CI has failed checks or statuses.")
        elif has_pending:
            ci_status = "pending"
            blocking = require_ci_success
            warnings.append("CI is still pending.")
        elif has_success:
            ci_status = "passed"
        elif not has_any_ci:
            ci_status = "not_configured"
            blocking = require_ci_success
            warnings.append("No CI checks were found for the merge commit.")
        else:
            ci_status = "unknown"
            blocking = require_ci_success
            warnings.append("CI status could not be determined.")

        if require_ci_success and ci_status != "passed":
            warnings.append("CI success is required for deployment verification.")

        return {
            "status": ci_status,
            "message": self._build_ci_message(status=ci_status, require_ci_success=require_ci_success),
            "blocking": blocking,
            "commit_sha": sha,
            "has_any_ci": has_any_ci,
            "check_runs_available": check_runs_result.get("success", False),
            "combined_status_available": combined_status_result.get("success", False),
            "check_runs": check_runs,
            "statuses": statuses,
            "failed_checks": failed_checks,
            "pending_checks": pending_checks,
            "successful_checks": successful_checks,
            "failed_statuses": failed_statuses,
            "pending_statuses": pending_statuses,
            "successful_statuses": successful_statuses,
            "warnings": warnings,
            "raw_errors": {
                "check_runs_error": None if check_runs_result.get("success", False) else check_runs_result,
                "combined_status_error": None if combined_status_result.get("success", False) else combined_status_result,
            },
        }

    def _verify_azure_runtime(
        self,
        resource_group: str,
        app_name: str,
        health_path: str,
        timeout_seconds: int,
        log_tail: int,
    ) -> dict[str, Any]:
        status_result = self.observability_agent.check_azure_container_app_status(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
        )

        logs_result = self.observability_agent.get_azure_container_app_logs(
            resource_group=resource_group,
            app_name=app_name,
            tail=log_tail,
        )

        incident_result = self.incident_response_agent.analyze_observability_data(
            status_result=status_result,
            logs_result=logs_result,
            context={
                "platform": "azure_container_apps",
                "resource_group": resource_group,
                "app_name": app_name,
                "health_path": health_path,
                "verification_phase": "post_merge_deployment_verification",
            },
        )

        status_body = status_result.get("result", status_result)
        logs_body = logs_result.get("result", logs_result)

        azure_healthy = bool(status_body.get("healthy", False))
        logs_available = logs_body.get("status") == "success"
        incident_detected = bool(incident_result.get("incident_detected", False))

        warnings = []
        blocking = False

        if not azure_healthy:
            warnings.append("Azure health check is not healthy.")
            blocking = True

        if not logs_available:
            warnings.append("Azure logs could not be retrieved.")

        if incident_detected:
            warnings.append("IncidentResponseAgent detected an active incident.")
            blocking = True

        if azure_healthy and not incident_detected:
            runtime_status = "healthy"
            message = "Azure app is healthy and no active incident was detected."
        elif incident_detected:
            runtime_status = "incident_detected"
            message = "Azure app verification found an active incident."
        else:
            runtime_status = "unhealthy"
            message = "Azure app verification failed health checks."

        return {
            "status": runtime_status,
            "message": message,
            "blocking": blocking,
            "resource_group": resource_group,
            "app_name": app_name,
            "health_path": health_path,
            "azure_healthy": azure_healthy,
            "logs_available": logs_available,
            "incident_detected": incident_detected,
            "warnings": warnings,
            "status_result": status_result,
            "logs_result": {
                "status": logs_body.get("status"),
                "message": logs_body.get("message"),
                "method": logs_body.get("method"),
                "tail": logs_body.get("tail"),
                "log_count": len(logs_body.get("logs", []) or []),
                "recommendations": logs_body.get("recommendations", []),
            },
            "incident_result": incident_result,
        }

    def _build_final_decision(
        self,
        pr_verification: dict[str, Any] | None,
        ci_verification: dict[str, Any] | None,
        azure_verification: dict[str, Any],
        require_pr_merged: bool,
        require_ci_success: bool,
        require_azure_healthy: bool,
    ) -> dict[str, Any]:
        merge_blockers = []
        warnings = []
        risk_notes = []

        if pr_verification is not None:
            if pr_verification.get("status") == "failed":
                merge_blockers.append("Could not verify pull request merge state.")
            elif require_pr_merged and not pr_verification.get("merged", False):
                merge_blockers.append("Pull request is not merged yet.")

            if pr_verification.get("status") == "closed_not_merged":
                merge_blockers.append("Pull request is closed but not merged.")

        if ci_verification is not None:
            warnings.extend(ci_verification.get("warnings", []))

            if ci_verification.get("blocking", False):
                merge_blockers.append("CI verification is blocking deployment verification.")

            if ci_verification.get("status") == "failed" and not require_ci_success:
                risk_notes.append("CI failed, but require_ci_success=false, so it is non-blocking.")

            if ci_verification.get("status") == "not_configured":
                risk_notes.append("No CI checks were found for the merge commit.")

        warnings.extend(azure_verification.get("warnings", []))

        if require_azure_healthy and azure_verification.get("blocking", False):
            merge_blockers.append("Azure runtime verification is blocking deployment verification.")

        if azure_verification.get("azure_healthy", False):
            risk_notes.append("Azure health check passed.")

        if azure_verification.get("logs_available", False):
            risk_notes.append("Azure logs were retrieved successfully.")

        if not azure_verification.get("incident_detected", True):
            risk_notes.append("No active incident was detected after verification.")

        if merge_blockers:
            final_status = "verification_failed"
            verified = False
            deployment_recommendation = "do_not_consider_deployment_verified"
            message = "Deployment verification failed. Resolve blockers before considering the deployment successful."
        elif warnings:
            final_status = "verification_warning"
            verified = False
            deployment_recommendation = "manual_review_required"
            message = "Deployment verification completed with warnings. Manual review is required."
        else:
            final_status = "verification_passed"
            verified = True
            deployment_recommendation = "deployment_verified"
            message = "Deployment verification passed. The PR is merged, checks are acceptable, and Azure is healthy."

        return {
            "status": final_status,
            "message": message,
            "verified": verified,
            "merge_blockers": self._deduplicate_strings(merge_blockers),
            "warnings": self._deduplicate_strings(warnings),
            "risk_notes": self._deduplicate_strings(risk_notes),
            "deployment_recommendation": deployment_recommendation,
            "next_steps": self._build_next_steps(
                merge_blockers=merge_blockers,
                warnings=warnings,
                pr_verification=pr_verification,
                ci_verification=ci_verification,
                azure_verification=azure_verification,
            ),
        }

    def _build_next_steps(
        self,
        merge_blockers: list[str],
        warnings: list[str],
        pr_verification: dict[str, Any] | None,
        ci_verification: dict[str, Any] | None,
        azure_verification: dict[str, Any],
    ) -> list[str]:
        if merge_blockers:
            steps = [
                "Resolve all deployment verification blockers.",
            ]

            if pr_verification is not None and not pr_verification.get("merged", False):
                steps.append("Merge the PR only after review and validation.")

            if ci_verification is not None and ci_verification.get("status") in ["failed", "pending"]:
                steps.append("Inspect GitHub Actions and wait for CI success or fix failed jobs.")

            if azure_verification.get("incident_detected", False):
                steps.append("Run /api/incidents/analyze-azure and create a remediation plan.")

            if not azure_verification.get("azure_healthy", False):
                steps.append("Run /api/observability/azure/status with timeout_seconds=60 and inspect logs.")

            return steps

        if warnings:
            return [
                "Review all warnings manually.",
                "Confirm the deployed app is the expected version.",
                "Run /api/observability/azure/status again after a few minutes.",
                "Run /api/incidents/analyze-azure to confirm no incident is active.",
            ]

        return [
            "Deployment is verified.",
            "Keep monitoring the app with /api/observability/azure/status.",
            "Use /api/incidents/analyze-azure if a future health check fails.",
        ]

    def _get_check_runs(
        self,
        owner: str,
        repo_name: str,
        sha: str,
        token: str | None,
    ) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{owner}/{repo_name}/commits/{sha}/check-runs"
        response_result = self._github_get(url=url, token=token)

        if not response_result["success"]:
            return response_result

        data = response_result["json"]

        return {
            "success": True,
            "total_count": data.get("total_count", 0),
            "check_runs": [
                {
                    "name": item.get("name"),
                    "status": item.get("status"),
                    "conclusion": item.get("conclusion"),
                    "url": item.get("html_url"),
                    "started_at": item.get("started_at"),
                    "completed_at": item.get("completed_at"),
                }
                for item in data.get("check_runs", [])
            ],
        }

    def _get_combined_status(
        self,
        owner: str,
        repo_name: str,
        sha: str,
        token: str | None,
    ) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{owner}/{repo_name}/commits/{sha}/status"
        response_result = self._github_get(url=url, token=token)

        if not response_result["success"]:
            return response_result

        data = response_result["json"]

        return {
            "success": True,
            "state": data.get("state"),
            "total_count": data.get("total_count", 0),
            "statuses": [
                {
                    "context": item.get("context"),
                    "state": item.get("state"),
                    "description": item.get("description"),
                    "target_url": item.get("target_url"),
                }
                for item in data.get("statuses", [])
            ],
        }

    def _build_ci_message(
        self,
        status: str,
        require_ci_success: bool,
    ) -> str:
        if status == "passed":
            return "CI checks passed for the merge commit."

        if status == "failed":
            if require_ci_success:
                return "CI checks failed and are blocking verification."
            return "CI checks failed but are not blocking because require_ci_success=false."

        if status == "pending":
            return "CI checks are still pending."

        if status == "missing_commit_sha":
            return "No merge commit SHA was available, so CI could not be verified."

        if status == "not_configured":
            return "No CI checks were found for the merge commit."

        return "CI status could not be determined."

    def _parse_github_repo_url(
        self,
        repo_url: str,
    ) -> dict[str, Any]:
        parsed = urlparse(repo_url)

        if parsed.netloc.lower() != "github.com":
            return {
                "success": False,
                "message": "Only github.com repository URLs are supported.",
            }

        path = parsed.path.strip("/")

        if path.endswith(".git"):
            path = path[:-4]

        parts = path.split("/")

        if len(parts) < 2:
            return {
                "success": False,
                "message": "Could not parse owner/repo from GitHub URL.",
            }

        return {
            "success": True,
            "owner": parts[0],
            "repo": parts[1],
        }

    def _parse_pull_request_url(
        self,
        pull_request_url: str,
    ) -> dict[str, Any]:
        parsed = urlparse(pull_request_url)

        if parsed.netloc.lower() != "github.com":
            return {
                "success": False,
                "message": "Only github.com pull request URLs are supported.",
            }

        path = parsed.path.strip("/")
        parts = path.split("/")

        if len(parts) < 4:
            return {
                "success": False,
                "message": "Could not parse pull request URL.",
            }

        if parts[2] != "pull":
            return {
                "success": False,
                "message": "URL must look like https://github.com/owner/repo/pull/123",
            }

        try:
            pull_request_number = int(parts[3])
        except ValueError:
            return {
                "success": False,
                "message": "Pull request number must be an integer.",
            }

        return {
            "success": True,
            "owner": parts[0],
            "repo": parts[1],
            "pull_request_number": pull_request_number,
        }

    def _github_get(
        self,
        url: str,
        token: str | None,
    ) -> dict[str, Any]:
        try:
            response = requests.get(
                url,
                headers=self._github_headers(token),
                timeout=30,
            )
        except requests.RequestException as exc:
            return {
                "success": False,
                "status_code": None,
                "message": f"GitHub API request failed: {self._safe_error_message(exc)}",
            }

        if not (200 <= response.status_code < 300):
            return {
                "success": False,
                "status_code": response.status_code,
                "message": response.text[:2000],
            }

        try:
            json_data = response.json()
        except ValueError:
            return {
                "success": False,
                "status_code": response.status_code,
                "message": "GitHub returned non-JSON response.",
                "body": response.text[:1000],
            }

        return {
            "success": True,
            "status_code": response.status_code,
            "json": json_data,
        }

    def _github_headers(
        self,
        token: str | None,
    ) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if token:
            headers["Authorization"] = f"Bearer {token}"

        return headers

    def _get_github_token(self) -> str | None:
        return (
            os.getenv("GITHUB_TOKEN")
            or os.getenv("GH_TOKEN")
            or os.getenv("GIT_TOKEN")
        )

    def _safe_error_message(
        self,
        exc: Exception,
    ) -> str:
        message = str(exc)

        message = re.sub(
            r"x-access-token:[^@]+@github\.com",
            "x-access-token:***@github.com",
            message,
        )

        message = re.sub(
            r"ghp_[A-Za-z0-9_]+",
            "ghp_***",
            message,
        )

        message = re.sub(
            r"github_pat_[A-Za-z0-9_]+",
            "github_pat_***",
            message,
        )

        return message

    def _deduplicate_strings(
        self,
        items: list[str],
    ) -> list[str]:
        seen = set()
        result = []

        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)

        return result

    def _safety_block(self) -> dict[str, bool]:
        return {
            "read_only": True,
            "auto_merge": False,
            "auto_deploy": False,
            "infrastructure_change": False,
        }