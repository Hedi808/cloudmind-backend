import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests


class PostPrValidationAgent:
    """
    Phase 12 agent.

    Responsibilities:
    - validate a remediation pull request
    - inspect changed files
    - detect risky/sensitive changes
    - inspect CI/check-runs/status
    - inspect PR mergeability
    - return a safe human merge recommendation

    Safety rules:
    - never merges a PR
    - never pushes code
    - never changes infrastructure
    - only reads GitHub metadata and returns a recommendation
    """

    def validate_pull_request(
        self,
        repo_url: str,
        pull_request_number: int,
        require_ci_success: bool = False,
        allow_docs_only_without_ci: bool = True,
        require_human_review: bool = False,
    ) -> dict[str, Any]:
        repo_url = repo_url.strip()

        if not repo_url:
            return {
                "status": "failed",
                "message": "repo_url is required.",
                "validated": False,
            }

        if pull_request_number <= 0:
            return {
                "status": "failed",
                "message": "pull_request_number must be greater than 0.",
                "validated": False,
            }

        repo_info = self._parse_github_repo_url(repo_url)

        if not repo_info["success"]:
            return {
                "status": "failed",
                "message": repo_info["message"],
                "validated": False,
            }

        return self._validate(
            owner=repo_info["owner"],
            repo_name=repo_info["repo"],
            pull_request_number=pull_request_number,
            require_ci_success=require_ci_success,
            allow_docs_only_without_ci=allow_docs_only_without_ci,
            require_human_review=require_human_review,
        )

    def validate_pull_request_url(
        self,
        pull_request_url: str,
        require_ci_success: bool = False,
        allow_docs_only_without_ci: bool = True,
        require_human_review: bool = False,
    ) -> dict[str, Any]:
        pr_info = self._parse_pull_request_url(pull_request_url.strip())

        if not pr_info["success"]:
            return {
                "status": "failed",
                "message": pr_info["message"],
                "validated": False,
            }

        return self._validate(
            owner=pr_info["owner"],
            repo_name=pr_info["repo"],
            pull_request_number=pr_info["pull_request_number"],
            require_ci_success=require_ci_success,
            allow_docs_only_without_ci=allow_docs_only_without_ci,
            require_human_review=require_human_review,
        )

    def _validate(
        self,
        owner: str,
        repo_name: str,
        pull_request_number: int,
        require_ci_success: bool,
        allow_docs_only_without_ci: bool,
        require_human_review: bool,
    ) -> dict[str, Any]:
        token = self._get_github_token()

        pr_result = self._get_pull_request(
            owner=owner,
            repo_name=repo_name,
            pull_request_number=pull_request_number,
            token=token,
        )

        if not pr_result["success"]:
            return {
                "status": "failed",
                "message": "Could not read pull request.",
                "validated": False,
                "github_api": pr_result,
                "recommendations": [
                    "Verify the PR number.",
                    "Verify the repository URL.",
                    "If the repository is private, verify that GITHUB_TOKEN has access.",
                ],
            }

        pull_request = pr_result["pull_request"]

        files_result = self._get_pull_request_files(
            owner=owner,
            repo_name=repo_name,
            pull_request_number=pull_request_number,
            token=token,
        )

        if not files_result["success"]:
            return {
                "status": "failed",
                "message": "Could not read pull request files.",
                "validated": False,
                "pull_request": pull_request,
                "github_api": files_result,
            }

        raw_files = files_result["files"]
        file_analysis = self._analyze_changed_files(raw_files)

        head_sha = pull_request["head_sha"]

        check_runs_result = self._get_check_runs(
            owner=owner,
            repo_name=repo_name,
            sha=head_sha,
            token=token,
        )

        combined_status_result = self._get_combined_status(
            owner=owner,
            repo_name=repo_name,
            sha=head_sha,
            token=token,
        )

        ci_analysis = self._analyze_ci(
            check_runs_result=check_runs_result,
            combined_status_result=combined_status_result,
            files_are_docs_only=file_analysis["docs_only"],
            require_ci_success=require_ci_success,
            allow_docs_only_without_ci=allow_docs_only_without_ci,
        )

        reviews_result = self._get_pull_request_reviews(
            owner=owner,
            repo_name=repo_name,
            pull_request_number=pull_request_number,
            token=token,
        )

        review_analysis = self._analyze_reviews(
            reviews_result=reviews_result,
            require_human_review=require_human_review,
        )

        decision = self._build_validation_decision(
            pull_request=pull_request,
            file_analysis=file_analysis,
            ci_analysis=ci_analysis,
            review_analysis=review_analysis,
            require_human_review=require_human_review,
        )

        return {
            "status": decision["status"],
            "message": decision["message"],
            "phase": "phase_12_post_pr_validation",
            "validated": True,
            "repo": {
                "owner": owner,
                "name": repo_name,
            },
            "pull_request": pull_request,
            "changed_files": file_analysis["changed_files"],
            "file_summary": file_analysis["summary"],
            "ci": ci_analysis,
            "reviews": review_analysis,
            "merge_blockers": decision["merge_blockers"],
            "warnings": decision["warnings"],
            "risk_notes": decision["risk_notes"],
            "merge_recommendation": decision["merge_recommendation"],
            "safe_for_human_merge": decision["safe_for_human_merge"],
            "safety": {
                "auto_merge": False,
                "direct_main_push": False,
                "read_only_validation": True,
                "human_review_required": True,
            },
            "next_steps": decision["next_steps"],
        }

    def _get_pull_request(
        self,
        owner: str,
        repo_name: str,
        pull_request_number: int,
        token: str | None,
    ) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls/{pull_request_number}"

        last_response: dict[str, Any] | None = None

        for attempt in range(3):
            response_result = self._github_get(url=url, token=token)

            if not response_result["success"]:
                return response_result

            data = response_result["json"]
            last_response = data

            if data.get("mergeable") is not None:
                break

            if attempt < 2:
                time.sleep(1)

        if last_response is None:
            return {
                "success": False,
                "message": "GitHub returned an empty PR response.",
            }

        data = last_response

        return {
            "success": True,
            "pull_request": {
                "number": data.get("number"),
                "title": data.get("title"),
                "url": data.get("html_url"),
                "state": data.get("state"),
                "draft": data.get("draft", False),
                "mergeable": data.get("mergeable"),
                "mergeable_state": data.get("mergeable_state"),
                "base_branch": data.get("base", {}).get("ref"),
                "head_branch": data.get("head", {}).get("ref"),
                "head_sha": data.get("head", {}).get("sha"),
                "author": data.get("user", {}).get("login"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "additions": data.get("additions"),
                "deletions": data.get("deletions"),
                "changed_files_count": data.get("changed_files"),
            },
        }

    def _get_pull_request_files(
        self,
        owner: str,
        repo_name: str,
        pull_request_number: int,
        token: str | None,
    ) -> dict[str, Any]:
        files = []
        page = 1

        while True:
            url = (
                f"https://api.github.com/repos/{owner}/{repo_name}"
                f"/pulls/{pull_request_number}/files"
                f"?per_page=100&page={page}"
            )

            response_result = self._github_get(url=url, token=token)

            if not response_result["success"]:
                return response_result

            page_files = response_result["json"]

            if not isinstance(page_files, list):
                return {
                    "success": False,
                    "message": "GitHub returned an invalid files response.",
                    "json": page_files,
                }

            files.extend(page_files)

            if len(page_files) < 100:
                break

            page += 1

            if page > 10:
                return {
                    "success": False,
                    "message": "PR has too many changed files to validate safely.",
                    "files_read": len(files),
                }

        return {
            "success": True,
            "files": files,
        }

    def _get_check_runs(
        self,
        owner: str,
        repo_name: str,
        sha: str,
        token: str | None,
    ) -> dict[str, Any]:
        if not sha:
            return {
                "success": False,
                "message": "Missing head SHA.",
            }

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
        if not sha:
            return {
                "success": False,
                "message": "Missing head SHA.",
            }

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

    def _get_pull_request_reviews(
        self,
        owner: str,
        repo_name: str,
        pull_request_number: int,
        token: str | None,
    ) -> dict[str, Any]:
        url = (
            f"https://api.github.com/repos/{owner}/{repo_name}"
            f"/pulls/{pull_request_number}/reviews"
        )

        response_result = self._github_get(url=url, token=token)

        if not response_result["success"]:
            return response_result

        data = response_result["json"]

        if not isinstance(data, list):
            return {
                "success": False,
                "message": "GitHub returned an invalid reviews response.",
                "json": data,
            }

        return {
            "success": True,
            "reviews": [
                {
                    "user": item.get("user", {}).get("login"),
                    "state": item.get("state"),
                    "submitted_at": item.get("submitted_at"),
                    "body": item.get("body"),
                }
                for item in data
            ],
        }

    def _analyze_changed_files(
        self,
        raw_files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        changed_files = []
        sensitive_files = []
        infra_files = []
        app_code_files = []
        workflow_files = []
        remediation_report_files = []
        documentation_files = []
        dependency_files = []
        deleted_important_files = []
        warnings = []

        total_additions = 0
        total_deletions = 0

        for item in raw_files:
            filename = item.get("filename", "")
            status = item.get("status", "")
            additions = int(item.get("additions", 0) or 0)
            deletions = int(item.get("deletions", 0) or 0)
            changes = int(item.get("changes", 0) or 0)

            category = self._classify_file(filename)
            risk = self._risk_for_file(filename=filename, category=category, status=status)

            total_additions += additions
            total_deletions += deletions

            file_record = {
                "filename": filename,
                "status": status,
                "additions": additions,
                "deletions": deletions,
                "changes": changes,
                "category": category,
                "risk": risk,
            }

            changed_files.append(file_record)

            if category == "sensitive":
                sensitive_files.append(filename)

            if category == "infrastructure":
                infra_files.append(filename)

            if category == "application_code":
                app_code_files.append(filename)

            if category == "workflow":
                workflow_files.append(filename)

            if category == "remediation_report":
                remediation_report_files.append(filename)

            if category == "documentation":
                documentation_files.append(filename)

            if category == "dependency":
                dependency_files.append(filename)

            if status == "removed" and category in [
                "infrastructure",
                "workflow",
                "application_code",
                "dependency",
            ]:
                deleted_important_files.append(filename)

        if len(changed_files) == 0:
            warnings.append("The PR has no changed files.")

        if len(changed_files) > 20:
            warnings.append("The PR changes many files. Manual review should be stricter.")

        if total_additions + total_deletions > 500:
            warnings.append("The PR has a large diff. Manual review should be stricter.")

        if workflow_files:
            warnings.append("The PR modifies GitHub Actions workflow files.")

        if infra_files:
            warnings.append("The PR modifies infrastructure/deployment files.")

        if app_code_files:
            warnings.append("The PR modifies application code.")

        if dependency_files:
            warnings.append("The PR modifies dependency files.")

        if deleted_important_files:
            warnings.append("The PR deletes important files.")

        docs_only = all(
            file_item["category"] in ["documentation", "remediation_report"]
            for file_item in changed_files
        ) if changed_files else False

        cloudmind_remediation_pr = len(remediation_report_files) > 0

        return {
            "changed_files": changed_files,
            "docs_only": docs_only,
            "cloudmind_remediation_pr": cloudmind_remediation_pr,
            "summary": {
                "file_count": len(changed_files),
                "total_additions": total_additions,
                "total_deletions": total_deletions,
                "docs_only": docs_only,
                "cloudmind_remediation_pr": cloudmind_remediation_pr,
                "sensitive_files": sensitive_files,
                "infra_files": infra_files,
                "workflow_files": workflow_files,
                "app_code_files": app_code_files,
                "dependency_files": dependency_files,
                "deleted_important_files": deleted_important_files,
                "warnings": warnings,
            },
        }

    def _analyze_ci(
        self,
        check_runs_result: dict[str, Any],
        combined_status_result: dict[str, Any],
        files_are_docs_only: bool,
        require_ci_success: bool,
        allow_docs_only_without_ci: bool,
    ) -> dict[str, Any]:
        check_runs = []
        statuses = []

        check_runs_available = check_runs_result.get("success", False)
        combined_status_available = combined_status_result.get("success", False)

        if check_runs_available:
            check_runs = check_runs_result.get("check_runs", []) or []

        if combined_status_available:
            statuses = combined_status_result.get("statuses", []) or []

        failed_checks = []
        pending_checks = []
        successful_checks = []

        for check_run in check_runs:
            name = check_run.get("name", "unknown")
            status = check_run.get("status")
            conclusion = check_run.get("conclusion")

            if status != "completed":
                pending_checks.append(name)
                continue

            if conclusion in ["failure", "cancelled", "timed_out", "action_required", "startup_failure"]:
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

        ci_warnings = []
        ci_blocking = False

        docs_only_ci_failure_allowed = (
            files_are_docs_only
            and allow_docs_only_without_ci
            and not require_ci_success
        )

        if has_failures:
            if docs_only_ci_failure_allowed:
                ci_status = "failed_but_non_blocking_for_docs_only"
                ci_blocking = False
                ci_warnings.append(
                    "CI failed, but the PR is documentation/remediation-report only and require_ci_success=false."
                )
            else:
                ci_status = "failed"
                ci_blocking = True
                ci_warnings.append("CI has failed checks or statuses.")

        elif has_pending:
            ci_status = "pending"
            ci_warnings.append("CI is still pending.")

            if require_ci_success:
                ci_blocking = True
                ci_warnings.append("CI success is required but checks are still pending.")

        elif has_success:
            ci_status = "passed"

        elif not has_any_ci:
            if files_are_docs_only and allow_docs_only_without_ci:
                ci_status = "not_required_for_docs_only"
            else:
                ci_status = "not_configured"
                ci_warnings.append("No CI checks were found for this PR.")

                if require_ci_success:
                    ci_blocking = True
                    ci_warnings.append("CI success is required but no CI checks were found.")

        else:
            ci_status = "unknown"
            ci_warnings.append("CI status could not be determined.")

            if require_ci_success:
                ci_blocking = True
                ci_warnings.append("CI success is required but was not confirmed.")

        return {
            "status": ci_status,
            "blocking": ci_blocking,
            "has_any_ci": has_any_ci,
            "docs_only_ci_failure_allowed": docs_only_ci_failure_allowed,
            "check_runs_available": check_runs_available,
            "combined_status_available": combined_status_available,
            "check_runs": check_runs,
            "statuses": statuses,
            "failed_checks": failed_checks,
            "pending_checks": pending_checks,
            "successful_checks": successful_checks,
            "failed_statuses": failed_statuses,
            "pending_statuses": pending_statuses,
            "successful_statuses": successful_statuses,
            "warnings": ci_warnings,
            "raw_errors": {
                "check_runs_error": None if check_runs_available else check_runs_result,
                "combined_status_error": None if combined_status_available else combined_status_result,
            },
        }

    def _analyze_reviews(
        self,
        reviews_result: dict[str, Any],
        require_human_review: bool,
    ) -> dict[str, Any]:
        if not reviews_result.get("success", False):
            return {
                "status": "unavailable",
                "approved": False,
                "blocking": require_human_review,
                "approvals": [],
                "changes_requested": [],
                "warnings": [
                    "Could not read PR reviews."
                ],
                "raw_error": reviews_result,
            }

        reviews = reviews_result.get("reviews", []) or []

        latest_by_user = {}

        for review in reviews:
            user = review.get("user")

            if not user:
                continue

            latest_by_user[user] = review

        approvals = [
            review
            for review in latest_by_user.values()
            if review.get("state") == "APPROVED"
        ]

        changes_requested = [
            review
            for review in latest_by_user.values()
            if review.get("state") == "CHANGES_REQUESTED"
        ]

        warnings = []

        if changes_requested:
            warnings.append("At least one reviewer requested changes.")

        if require_human_review and not approvals:
            warnings.append("Human review is required but no approval was found.")

        blocking = bool(changes_requested) or (require_human_review and not approvals)

        if approvals and not changes_requested:
            status = "approved"
        elif changes_requested:
            status = "changes_requested"
        elif reviews:
            status = "reviewed_without_approval"
        else:
            status = "no_reviews"

        return {
            "status": status,
            "approved": bool(approvals) and not bool(changes_requested),
            "blocking": blocking,
            "approvals": approvals,
            "changes_requested": changes_requested,
            "review_count": len(reviews),
            "warnings": warnings,
        }

    def _build_validation_decision(
        self,
        pull_request: dict[str, Any],
        file_analysis: dict[str, Any],
        ci_analysis: dict[str, Any],
        review_analysis: dict[str, Any],
        require_human_review: bool,
    ) -> dict[str, Any]:
        merge_blockers = []
        warnings = []
        risk_notes = []

        pr_state = pull_request.get("state")
        draft = pull_request.get("draft")
        mergeable = pull_request.get("mergeable")
        mergeable_state = pull_request.get("mergeable_state")
        base_branch = pull_request.get("base_branch")
        head_branch = pull_request.get("head_branch")

        if pr_state != "open":
            merge_blockers.append("The pull request is not open.")

        if draft:
            merge_blockers.append("The pull request is still a draft.")

        if head_branch == base_branch:
            merge_blockers.append("The pull request head branch is the same as the base branch.")

        if mergeable is False:
            merge_blockers.append("GitHub says this pull request is not mergeable.")

        if mergeable is None:
            warnings.append("GitHub mergeability is still unknown. Retry validation in a few seconds.")

        if mergeable_state in ["dirty", "blocked", "behind"]:
            warnings.append(f"GitHub mergeable_state is {mergeable_state}.")

        if mergeable_state == "unstable":
            warnings.append("GitHub mergeable_state is unstable because one or more checks failed.")

        file_summary = file_analysis["summary"]

        if file_summary["sensitive_files"]:
            merge_blockers.append(
                "Sensitive files were changed. Do not merge until reviewed."
            )

        if file_summary["deleted_important_files"]:
            warnings.append(
                "Important files were deleted. Review carefully before merging."
            )

        warnings.extend(file_summary["warnings"])

        if not file_summary["cloudmind_remediation_pr"]:
            warnings.append(
                "No CloudMind remediation report file was found in this PR."
            )

        if ci_analysis["blocking"]:
            merge_blockers.append("CI validation is blocking this PR.")

        warnings.extend(ci_analysis["warnings"])

        if review_analysis["blocking"]:
            if require_human_review:
                merge_blockers.append("Human review requirement is not satisfied.")
            else:
                warnings.append("Review status is blocking or changes were requested.")

        warnings.extend(review_analysis["warnings"])

        if file_summary["docs_only"]:
            risk_notes.append("This PR is documentation/remediation-report only.")
        else:
            risk_notes.append("This PR changes executable, infrastructure, or dependency files.")

        if ci_analysis["status"] == "not_required_for_docs_only":
            risk_notes.append("CI was not required because the PR is documentation-only.")

        if ci_analysis["status"] == "failed_but_non_blocking_for_docs_only":
            risk_notes.append(
                "CI failed, but this PR only changes remediation documentation. The CI failure is treated as non-blocking unless require_ci_success=true."
            )

        if merge_blockers:
            validation_status = "validation_failed"
            merge_recommendation = "do_not_merge"
            safe_for_human_merge = False
            message = "PR validation failed. Do not merge until blockers are resolved."
        elif warnings:
            validation_status = "validation_warning"
            merge_recommendation = "review_required_before_merge"
            safe_for_human_merge = False
            message = "PR validation completed with warnings. Human review is required before merge."
        else:
            validation_status = "validation_passed"
            merge_recommendation = "safe_for_human_merge_after_review"
            safe_for_human_merge = True
            message = "PR validation passed. It is safe for a human to review and merge."

        next_steps = self._build_next_steps(
            merge_blockers=merge_blockers,
            warnings=warnings,
            ci_analysis=ci_analysis,
            review_analysis=review_analysis,
            file_analysis=file_analysis,
        )

        return {
            "status": validation_status,
            "message": message,
            "merge_blockers": self._deduplicate_strings(merge_blockers),
            "warnings": self._deduplicate_strings(warnings),
            "risk_notes": self._deduplicate_strings(risk_notes),
            "merge_recommendation": merge_recommendation,
            "safe_for_human_merge": safe_for_human_merge,
            "next_steps": next_steps,
        }

    def _build_next_steps(
        self,
        merge_blockers: list[str],
        warnings: list[str],
        ci_analysis: dict[str, Any],
        review_analysis: dict[str, Any],
        file_analysis: dict[str, Any],
    ) -> list[str]:
        if merge_blockers:
            steps = [
                "Resolve all merge blockers before merging.",
            ]

            if ci_analysis["status"] == "failed":
                steps.append("Open GitHub Actions, inspect failed jobs, and fix the PR branch.")

            if review_analysis["status"] == "changes_requested":
                steps.append("Address reviewer change requests before merging.")

            if file_analysis["summary"]["sensitive_files"]:
                steps.append("Remove sensitive files from the PR and rotate any exposed secrets.")

            return steps

        if warnings:
            steps = [
                "Review all warnings manually.",
                "Confirm the changed files match the remediation plan.",
            ]

            if ci_analysis["status"] == "failed_but_non_blocking_for_docs_only":
                steps.append(
                    "CI failed, but the PR is documentation-only. You may inspect the failed job, but it is not blocking unless require_ci_success=true."
                )

            steps.append("Validate the app after merge using CloudMind observability endpoints.")

            return steps

        return [
            "Review the PR content manually.",
            "Merge only if the reviewer agrees with the remediation report.",
            "After merge, validate with /api/observability/azure/status and /api/incidents/analyze-azure.",
        ]

    def _classify_file(
        self,
        filename: str,
    ) -> str:
        normalized = filename.replace("\\", "/").lower()
        basename = normalized.split("/")[-1]

        if self._is_sensitive_file(normalized):
            return "sensitive"

        if normalized.startswith("cloudmind/remediation/") and normalized.endswith(".md"):
            return "remediation_report"

        if normalized.startswith(".github/workflows/"):
            return "workflow"

        if normalized.startswith("azure/"):
            return "infrastructure"

        if normalized.startswith("k8s/"):
            return "infrastructure"

        if basename in [
            "dockerfile",
            "compose.yml",
            "compose.yaml",
            "docker-compose.yml",
            "docker-compose.yaml",
        ]:
            return "infrastructure"

        if basename in [
            "requirements.txt",
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "pyproject.toml",
            "poetry.lock",
        ]:
            return "dependency"

        if normalized.endswith(".md") or normalized.endswith(".txt"):
            return "documentation"

        if normalized.startswith("app/") or normalized.startswith("src/"):
            return "application_code"

        if basename == "main.py":
            return "application_code"

        if normalized.endswith(
            (
                ".py",
                ".js",
                ".ts",
                ".tsx",
                ".jsx",
                ".java",
                ".cs",
                ".go",
                ".php",
                ".rb",
            )
        ):
            return "application_code"

        return "other"

    def _risk_for_file(
        self,
        filename: str,
        category: str,
        status: str,
    ) -> str:
        if category == "sensitive":
            return "critical"

        if category in ["workflow", "infrastructure"]:
            return "high"

        if category in ["application_code", "dependency"]:
            return "medium"

        if status == "removed":
            return "medium"

        if category in ["documentation", "remediation_report"]:
            return "low"

        return "low"

    def _is_sensitive_file(
        self,
        filename: str,
    ) -> bool:
        normalized = filename.replace("\\", "/").lower()
        basename = normalized.split("/")[-1]

        if basename == ".env":
            return True

        if basename.startswith(".env."):
            return True

        if basename in [
            "id_rsa",
            "id_dsa",
            "id_ecdsa",
            "id_ed25519",
        ]:
            return True

        if normalized.endswith(
            (
                ".pem",
                ".pfx",
                ".p12",
                ".key",
                ".keystore",
            )
        ):
            return True

        return False

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