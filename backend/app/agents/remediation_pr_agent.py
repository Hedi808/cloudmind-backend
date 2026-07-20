import gc
import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from git import Repo

from app.agents.remediation_planner_agent import RemediationPlannerAgent


class RemediationPrAgent:
    """
    Phase 11 agent.

    Responsibilities:
    - take an approved remediation plan
    - create a safe Git branch
    - add a remediation report file
    - optionally apply safe infrastructure changes
    - commit the changes
    - push the branch
    - open a GitHub pull request

    Safety rules:
    - never pushes directly to main/master
    - requires explicit approval_confirmed=True
    - does not auto-merge
    - does not apply risky fixes automatically
    - always creates a PR for human review
    """

    def __init__(self) -> None:
        self.remediation_planner_agent = RemediationPlannerAgent()

    def create_pr_from_azure_plan(
        self,
        repo_url: str,
        resource_group: str,
        app_name: str,
        approval_confirmed: bool,
        health_path: str = "/health",
        timeout_seconds: int = 60,
        log_tail: int = 100,
        environment: str = "development",
        allow_cost_increase: bool = False,
        create_pr_when_no_remediation: bool = False,
    ) -> dict[str, Any]:
        plan_result = self.remediation_planner_agent.plan_from_azure(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
            log_tail=log_tail,
            environment=environment,
            allow_cost_increase=allow_cost_increase,
        )

        return self.create_pr_from_plan(
            repo_url=repo_url,
            remediation_plan=plan_result,
            approval_confirmed=approval_confirmed,
            create_pr_when_no_remediation=create_pr_when_no_remediation,
        )

    def create_pr_from_simulation(
        self,
        repo_url: str,
        scenario: str,
        approval_confirmed: bool,
        environment: str = "development",
        allow_cost_increase: bool = False,
        create_pr_when_no_remediation: bool = True,
    ) -> dict[str, Any]:
        plan_result = self.remediation_planner_agent.simulate_remediation_plan(
            scenario=scenario,
            environment=environment,
            allow_cost_increase=allow_cost_increase,
        )

        return self.create_pr_from_plan(
            repo_url=repo_url,
            remediation_plan=plan_result,
            approval_confirmed=approval_confirmed,
            create_pr_when_no_remediation=create_pr_when_no_remediation,
        )

    def create_pr_from_plan(
        self,
        repo_url: str,
        remediation_plan: dict[str, Any],
        approval_confirmed: bool,
        create_pr_when_no_remediation: bool = False,
    ) -> dict[str, Any]:
        repo_url = repo_url.strip()

        if not repo_url:
            return {
                "status": "failed",
                "message": "repo_url is required.",
                "pr_created": False,
                "recommendations": [
                    "Provide a GitHub repository URL.",
                ],
            }

        if not approval_confirmed:
            return {
                "status": "approval_required",
                "message": "Human approval is required before creating a remediation pull request.",
                "pr_created": False,
                "approval_confirmed": False,
                "recommendations": [
                    "Review the remediation plan first.",
                    "Call this endpoint again with approval_confirmed=true only when you want CloudMind to create a PR.",
                ],
            }

        normalized_plan = remediation_plan.get("result", remediation_plan)
        remediation_required = bool(normalized_plan.get("remediation_required", False))
        incident_detected = bool(normalized_plan.get("incident_detected", False))
        app_name = normalized_plan.get("app_name", "application")

        if not remediation_required and not incident_detected and not create_pr_when_no_remediation:
            return {
                "status": "skipped",
                "message": "No remediation is required, so no PR was created.",
                "pr_created": False,
                "remediation_required": remediation_required,
                "incident_detected": incident_detected,
                "recommendations": [
                    "Set create_pr_when_no_remediation=true only if you want a documentation/hardening PR.",
                    "Otherwise continue monitoring.",
                ],
            }

        token = self._get_github_token()

        if not token:
            return {
                "status": "failed",
                "message": "GitHub token was not found.",
                "pr_created": False,
                "recommendations": [
                    "Set GITHUB_TOKEN in your backend .env file.",
                    "Use a GitHub token with Contents: Read/write and Pull requests: Read/write.",
                    "Never paste tokens into chat or Swagger responses.",
                ],
            }

        repo_info = self._parse_github_repo_url(repo_url)

        if not repo_info["success"]:
            return {
                "status": "failed",
                "message": repo_info["message"],
                "pr_created": False,
                "recommendations": [
                    "Use a normal GitHub HTTPS URL like https://github.com/Hedi808/test-3s.git",
                ],
            }

        owner = repo_info["owner"]
        repo_name = repo_info["repo"]

        default_branch_result = self._get_default_branch(
            owner=owner,
            repo_name=repo_name,
            token=token,
        )

        if not default_branch_result["success"]:
            return {
                "status": "failed",
                "message": "Could not determine repository default branch.",
                "pr_created": False,
                "github_api": default_branch_result,
                "recommendations": [
                    "Verify that the GitHub token can read repository metadata.",
                    "Verify that the repository exists and the token has access.",
                ],
            }

        default_branch = default_branch_result["default_branch"]
        branch_name = self._build_branch_name(app_name=app_name)

        if branch_name in ["main", "master", default_branch]:
            return {
                "status": "failed",
                "message": "Refusing to use the default branch as remediation branch.",
                "pr_created": False,
            }

        temp_dir = Path(tempfile.mkdtemp(prefix="cloudmind-remediation-"))
        repo_dir = temp_dir / repo_name
        repo: Repo | None = None

        try:
            clone_url = self._build_authenticated_clone_url(
                repo_url=repo_url,
                token=token,
            )

            try:
                repo = Repo.clone_from(
                    clone_url,
                    repo_dir,
                    branch=default_branch,
                )
            except Exception as exc:
                return {
                    "status": "failed",
                    "message": f"Failed to clone repository: {self._safe_error_message(exc)}",
                    "pr_created": False,
                    "recommendations": [
                        "Verify the repository URL.",
                        "Verify that the GitHub token has Contents read access.",
                    ],
                }

            repo.git.config("user.name", "CloudMind Bot")
            repo.git.config("user.email", "cloudmind-bot@example.com")

            try:
                repo.git.checkout("-b", branch_name)
            except Exception as exc:
                return {
                    "status": "failed",
                    "message": f"Failed to create remediation branch: {self._safe_error_message(exc)}",
                    "pr_created": False,
                }

            change_result = self._apply_remediation_changes(
                repo_dir=repo_dir,
                remediation_plan=normalized_plan,
            )

            if not change_result["changed_files"]:
                return {
                    "status": "skipped",
                    "message": "No file changes were generated, so no PR was created.",
                    "pr_created": False,
                    "change_result": change_result,
                    "recommendations": [
                        "Use create_pr_when_no_remediation=true for documentation-only remediation PRs.",
                        "Verify the remediation plan contains remediation_steps.",
                    ],
                }

            try:
                repo.git.add(A=True)
                repo.index.commit(
                    self._build_commit_message(
                        app_name=app_name,
                        remediation_plan=normalized_plan,
                    )
                )
            except Exception as exc:
                return {
                    "status": "failed",
                    "message": f"Failed to commit remediation changes: {self._safe_error_message(exc)}",
                    "pr_created": False,
                    "changed_files": change_result["changed_files"],
                }

            try:
                origin = repo.remote(name="origin")
                origin.push(refspec=f"{branch_name}:{branch_name}")
            except Exception as exc:
                return {
                    "status": "failed",
                    "message": f"Failed to push remediation branch: {self._safe_error_message(exc)}",
                    "pr_created": False,
                    "changed_files": change_result["changed_files"],
                    "recommendations": [
                        "Verify that the GitHub token has Contents read/write permission.",
                        "Verify that branch creation is allowed in the repository.",
                    ],
                }

            pr_result = self._create_pull_request(
                owner=owner,
                repo_name=repo_name,
                token=token,
                branch_name=branch_name,
                base_branch=default_branch,
                remediation_plan=normalized_plan,
                changed_files=change_result["changed_files"],
            )

            if not pr_result["success"]:
                return {
                    "status": "failed",
                    "message": "Branch was pushed but GitHub PR creation failed.",
                    "pr_created": False,
                    "branch_name": branch_name,
                    "changed_files": change_result["changed_files"],
                    "github_api": pr_result,
                    "recommendations": [
                        "Open the PR manually from the pushed branch.",
                        "Verify that the token has Pull requests read/write permission.",
                    ],
                }

            return {
                "status": "success",
                "message": "Remediation pull request created successfully.",
                "pr_created": True,
                "execution_mode": "gitops_pull_request",
                "repo": {
                    "owner": owner,
                    "name": repo_name,
                    "default_branch": default_branch,
                },
                "branch_name": branch_name,
                "changed_files": change_result["changed_files"],
                "applied_safe_changes": change_result["applied_safe_changes"],
                "skipped_changes": change_result["skipped_changes"],
                "pull_request": pr_result["pull_request"],
                "safety": {
                    "direct_main_push": False,
                    "auto_merge": False,
                    "human_review_required": True,
                    "approval_confirmed": approval_confirmed,
                },
                "cleanup": {
                    "temporary_directory": str(temp_dir),
                    "cleanup_is_best_effort": True,
                },
            }

        finally:
            self._close_repo(repo)
            self._safe_remove_directory(temp_dir)

    def preview_changes_from_plan(
        self,
        remediation_plan: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_plan = remediation_plan.get("result", remediation_plan)
        report_content = self._build_remediation_report(normalized_plan)
        safe_change_preview = self._build_safe_change_preview(normalized_plan)

        return {
            "status": "preview_ready",
            "message": "Remediation PR preview generated.",
            "report_preview": report_content,
            "safe_change_preview": safe_change_preview,
            "would_create_report_file": True,
            "would_open_pr": False,
        }

    def _apply_remediation_changes(
        self,
        repo_dir: Path,
        remediation_plan: dict[str, Any],
    ) -> dict[str, Any]:
        changed_files = []
        applied_safe_changes = []
        skipped_changes = []

        report_path = self._write_remediation_report(
            repo_dir=repo_dir,
            remediation_plan=remediation_plan,
        )
        changed_files.append(str(report_path.relative_to(repo_dir)).replace("\\", "/"))
        applied_safe_changes.append(
            "Created remediation report for human review."
        )

        steps = remediation_plan.get("remediation_steps", []) or []
        environment = remediation_plan.get("environment", "development")
        detected_signals = remediation_plan.get("detected_signals", {}) or {}

        for step in steps:
            step_id = step.get("id")

            if step_id == "handle-cold-start":
                if environment == "production" and step.get("requires_human_approval") is True:
                    result = self._try_update_min_replicas(
                        repo_dir=repo_dir,
                        min_replicas=1,
                    )

                    changed_files.extend(result["changed_files"])
                    applied_safe_changes.extend(result["applied_safe_changes"])
                    skipped_changes.extend(result["skipped_changes"])
                else:
                    skipped_changes.append(
                        "Skipped min_replicas change because environment is not production or approval-sensitive cost change is not requested."
                    )

            elif step_id == "production-scaling-hardening":
                if environment == "production":
                    result = self._try_update_max_replicas(
                        repo_dir=repo_dir,
                        max_replicas=2,
                    )

                    changed_files.extend(result["changed_files"])
                    applied_safe_changes.extend(result["applied_safe_changes"])
                    skipped_changes.extend(result["skipped_changes"])
                else:
                    skipped_changes.append(
                        "Skipped max_replicas change because environment is not production."
                    )

            elif step_id in [
                "fix-image-pull",
                "fix-missing-dependency",
                "fix-application-exception",
                "fix-port-mismatch",
                "fix-ingress",
                "fix-no-ready-revision",
                "fix-out-of-memory",
                "fix-crash-loop",
                "fix-dependency-connection",
                "fix-logs-unavailable",
            ]:
                skipped_changes.append(
                    f"Step '{step_id}' requires human implementation. CloudMind documented it in the remediation report but did not modify risky files automatically."
                )

        if detected_signals.get("max_replicas_one") and environment == "production":
            result = self._try_update_max_replicas(
                repo_dir=repo_dir,
                max_replicas=2,
            )
            changed_files.extend(result["changed_files"])
            applied_safe_changes.extend(result["applied_safe_changes"])
            skipped_changes.extend(result["skipped_changes"])

        return {
            "changed_files": self._deduplicate_list(changed_files),
            "applied_safe_changes": self._deduplicate_list(applied_safe_changes),
            "skipped_changes": self._deduplicate_list(skipped_changes),
        }

    def _write_remediation_report(
        self,
        repo_dir: Path,
        remediation_plan: dict[str, Any],
    ) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        app_name = self._slugify(remediation_plan.get("app_name", "application"))

        report_dir = repo_dir / "cloudmind" / "remediation"
        report_dir.mkdir(parents=True, exist_ok=True)

        report_path = report_dir / f"{timestamp}-{app_name}-remediation-plan.md"
        report_path.write_text(
            self._build_remediation_report(remediation_plan),
            encoding="utf-8",
        )

        return report_path

    def _build_remediation_report(
        self,
        remediation_plan: dict[str, Any],
    ) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        app_name = remediation_plan.get("app_name", "application")
        environment = remediation_plan.get("environment", "unknown")
        severity = remediation_plan.get("severity", "unknown")
        incident_detected = remediation_plan.get("incident_detected")
        remediation_required = remediation_plan.get("remediation_required")
        human_approval_required = remediation_plan.get("human_approval_required")
        safe_to_auto_fix = remediation_plan.get("safe_to_auto_fix")
        summary = remediation_plan.get("summary", remediation_plan.get("message", ""))

        findings = remediation_plan.get("findings", []) or []
        likely_causes = remediation_plan.get("likely_causes", []) or []
        risk_notes = remediation_plan.get("risk_notes", []) or []
        evidence = remediation_plan.get("evidence", []) or []
        remediation_steps = remediation_plan.get("remediation_steps", []) or []

        lines = [
            "# CloudMind Remediation Plan",
            "",
            f"Generated at: `{timestamp}`",
            "",
            "## Summary",
            "",
            f"- App: `{app_name}`",
            f"- Environment: `{environment}`",
            f"- Severity: `{severity}`",
            f"- Incident detected: `{incident_detected}`",
            f"- Remediation required: `{remediation_required}`",
            f"- Human approval required: `{human_approval_required}`",
            f"- Safe to auto-fix: `{safe_to_auto_fix}`",
            "",
            summary or "No summary provided.",
            "",
            "## Findings",
            "",
        ]

        if findings:
            for item in findings:
                lines.append(f"- {item}")
        else:
            lines.append("- No findings provided.")

        lines.extend(
            [
                "",
                "## Likely Causes",
                "",
            ]
        )

        if likely_causes:
            for item in likely_causes:
                lines.append(f"- {item}")
        else:
            lines.append("- No likely causes provided.")

        lines.extend(
            [
                "",
                "## Risk Notes",
                "",
            ]
        )

        if risk_notes:
            for item in risk_notes:
                lines.append(f"- {item}")
        else:
            lines.append("- No risk notes provided.")

        lines.extend(
            [
                "",
                "## Remediation Steps",
                "",
            ]
        )

        if remediation_steps:
            for index, step in enumerate(remediation_steps, start=1):
                lines.extend(
                    [
                        f"### {index}. {step.get('title', 'Untitled step')}",
                        "",
                        f"- ID: `{step.get('id', 'unknown')}`",
                        f"- Problem: {step.get('problem', 'N/A')}",
                        f"- Recommended fix: {step.get('recommended_fix', 'N/A')}",
                        f"- Risk: `{step.get('risk', 'unknown')}`",
                        f"- Requires human approval: `{step.get('requires_human_approval')}`",
                        f"- Safe to auto-fix: `{step.get('safe_to_auto_fix')}`",
                        f"- Cost impact: {step.get('cost_impact', 'unknown')}",
                        f"- Availability impact: {step.get('availability_impact', 'unknown')}",
                        "",
                        "Target files:",
                    ]
                )

                target_files = step.get("target_files", []) or []

                if target_files:
                    for file_path in target_files:
                        lines.append(f"- `{file_path}`")
                else:
                    lines.append("- No target files.")

                lines.extend(
                    [
                        "",
                        "Proposed changes:",
                    ]
                )

                proposed_changes = step.get("proposed_changes", []) or []

                if proposed_changes:
                    for change in proposed_changes:
                        lines.append(f"- {change}")
                else:
                    lines.append("- No proposed changes.")

                lines.extend(
                    [
                        "",
                        "Validation commands:",
                    ]
                )

                validation_commands = step.get("validation_commands", []) or []

                if validation_commands:
                    for command in validation_commands:
                        lines.append(f"- `{command}`")
                else:
                    lines.append("- No validation commands.")

                lines.extend(
                    [
                        "",
                        f"Rollback plan: {step.get('rollback_plan', 'No rollback plan provided.')}",
                        "",
                    ]
                )
        else:
            lines.append("- No remediation steps provided.")

        lines.extend(
            [
                "",
                "## Evidence",
                "",
            ]
        )

        if evidence:
            for item in evidence[:30]:
                lines.append(f"- `{item}`")
        else:
            lines.append("- No evidence provided.")

        lines.extend(
            [
                "",
                "## Safety",
                "",
                "- This PR was created by CloudMind in GitOps mode.",
                "- CloudMind did not merge this PR.",
                "- CloudMind did not push directly to the default branch.",
                "- A human must review the changes before merge.",
                "",
            ]
        )

        return "\n".join(lines)

    def _build_safe_change_preview(
        self,
        remediation_plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        steps = remediation_plan.get("remediation_steps", []) or []
        environment = remediation_plan.get("environment", "development")
        preview = []

        for step in steps:
            step_id = step.get("id")

            if step_id == "handle-cold-start" and environment == "production":
                preview.append(
                    {
                        "type": "safe_infra_hardening",
                        "description": "Would update min_replicas from 0 to 1 in Azure deployment scripts if found.",
                        "requires_human_approval": True,
                    }
                )

            elif step_id == "production-scaling-hardening" and environment == "production":
                preview.append(
                    {
                        "type": "safe_infra_hardening",
                        "description": "Would update max_replicas from 1 to 2 in Azure deployment scripts if found.",
                        "requires_human_approval": True,
                    }
                )

            else:
                preview.append(
                    {
                        "type": "documentation_only",
                        "description": f"Would document remediation step '{step_id}' in the remediation report.",
                        "requires_human_approval": step.get("requires_human_approval", False),
                    }
                )

        if not preview:
            preview.append(
                {
                    "type": "documentation_only",
                    "description": "Would create a remediation report only.",
                    "requires_human_approval": False,
                }
            )

        return preview

    def _try_update_min_replicas(
        self,
        repo_dir: Path,
        min_replicas: int,
    ) -> dict[str, Any]:
        changed_files = []
        applied_safe_changes = []
        skipped_changes = []

        candidate_files = [
            repo_dir / "azure" / "deploy-container-app.ps1",
            repo_dir / "azure" / "deploy-container-app.sh",
        ]

        for file_path in candidate_files:
            if not file_path.exists():
                skipped_changes.append(
                    f"Could not update min_replicas because {self._relative(repo_dir, file_path)} was not found."
                )
                continue

            original = file_path.read_text(encoding="utf-8")
            updated = original

            updated = re.sub(
                r"(--min-replicas\s+)0\b",
                rf"\g<1>{min_replicas}",
                updated,
            )

            updated = re.sub(
                r"(min_replicas\s*=\s*)0\b",
                rf"\g<1>{min_replicas}",
                updated,
                flags=re.IGNORECASE,
            )

            updated = re.sub(
                r"(MIN_REPLICAS\s*=\s*)0\b",
                rf"\g<1>{min_replicas}",
                updated,
            )

            if updated != original:
                file_path.write_text(updated, encoding="utf-8")
                changed_files.append(self._relative(repo_dir, file_path))
                applied_safe_changes.append(
                    f"Updated min replicas to {min_replicas} in {self._relative(repo_dir, file_path)}."
                )
            else:
                skipped_changes.append(
                    f"No min_replicas pattern was found in {self._relative(repo_dir, file_path)}."
                )

        return {
            "changed_files": changed_files,
            "applied_safe_changes": applied_safe_changes,
            "skipped_changes": skipped_changes,
        }

    def _try_update_max_replicas(
        self,
        repo_dir: Path,
        max_replicas: int,
    ) -> dict[str, Any]:
        changed_files = []
        applied_safe_changes = []
        skipped_changes = []

        candidate_files = [
            repo_dir / "azure" / "deploy-container-app.ps1",
            repo_dir / "azure" / "deploy-container-app.sh",
        ]

        for file_path in candidate_files:
            if not file_path.exists():
                skipped_changes.append(
                    f"Could not update max_replicas because {self._relative(repo_dir, file_path)} was not found."
                )
                continue

            original = file_path.read_text(encoding="utf-8")
            updated = original

            updated = re.sub(
                r"(--max-replicas\s+)1\b",
                rf"\g<1>{max_replicas}",
                updated,
            )

            updated = re.sub(
                r"(max_replicas\s*=\s*)1\b",
                rf"\g<1>{max_replicas}",
                updated,
                flags=re.IGNORECASE,
            )

            updated = re.sub(
                r"(MAX_REPLICAS\s*=\s*)1\b",
                rf"\g<1>{max_replicas}",
                updated,
            )

            if updated != original:
                file_path.write_text(updated, encoding="utf-8")
                changed_files.append(self._relative(repo_dir, file_path))
                applied_safe_changes.append(
                    f"Updated max replicas to {max_replicas} in {self._relative(repo_dir, file_path)}."
                )
            else:
                skipped_changes.append(
                    f"No max_replicas pattern was found in {self._relative(repo_dir, file_path)}."
                )

        return {
            "changed_files": changed_files,
            "applied_safe_changes": applied_safe_changes,
            "skipped_changes": skipped_changes,
        }

    def _create_pull_request(
        self,
        owner: str,
        repo_name: str,
        token: str,
        branch_name: str,
        base_branch: str,
        remediation_plan: dict[str, Any],
        changed_files: list[str],
    ) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls"

        title = self._build_pr_title(remediation_plan)
        body = self._build_pr_body(
            remediation_plan=remediation_plan,
            branch_name=branch_name,
            changed_files=changed_files,
        )

        payload = {
            "title": title,
            "head": branch_name,
            "base": base_branch,
            "body": body,
            "maintainer_can_modify": True,
        }

        try:
            response = requests.post(
                url,
                headers=self._github_headers(token),
                json=payload,
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

        data = response.json()

        return {
            "success": True,
            "pull_request": {
                "number": data.get("number"),
                "title": data.get("title"),
                "url": data.get("html_url"),
                "state": data.get("state"),
                "head": data.get("head", {}).get("ref"),
                "base": data.get("base", {}).get("ref"),
            },
        }

    def _get_default_branch(
        self,
        owner: str,
        repo_name: str,
        token: str,
    ) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{owner}/{repo_name}"

        try:
            response = requests.get(
                url,
                headers=self._github_headers(token),
                timeout=30,
            )
        except requests.RequestException as exc:
            return {
                "success": False,
                "message": f"GitHub API request failed: {self._safe_error_message(exc)}",
            }

        if not (200 <= response.status_code < 300):
            return {
                "success": False,
                "status_code": response.status_code,
                "message": response.text[:2000],
            }

        data = response.json()

        return {
            "success": True,
            "default_branch": data.get("default_branch", "main"),
        }

    def _build_pr_title(
        self,
        remediation_plan: dict[str, Any],
    ) -> str:
        app_name = remediation_plan.get("app_name", "application")
        severity = remediation_plan.get("severity", "unknown")
        incident_detected = remediation_plan.get("incident_detected", False)

        if incident_detected:
            return f"CloudMind remediation for {app_name} ({severity})"

        return f"CloudMind monitoring hardening for {app_name}"

    def _build_pr_body(
        self,
        remediation_plan: dict[str, Any],
        branch_name: str,
        changed_files: list[str],
    ) -> str:
        summary = remediation_plan.get("summary", remediation_plan.get("message", ""))
        severity = remediation_plan.get("severity", "unknown")
        incident_detected = remediation_plan.get("incident_detected", False)
        remediation_required = remediation_plan.get("remediation_required", False)
        human_approval_required = remediation_plan.get("human_approval_required", False)

        lines = [
            "## CloudMind Remediation PR",
            "",
            summary or "CloudMind generated this remediation PR.",
            "",
            "## Safety",
            "",
            "- Direct push to main: **No**",
            "- Auto-merge: **No**",
            "- Human review required: **Yes**",
            "- Execution mode: **GitOps Pull Request**",
            "",
            "## Incident Context",
            "",
            f"- Incident detected: `{incident_detected}`",
            f"- Severity: `{severity}`",
            f"- Remediation required: `{remediation_required}`",
            f"- Human approval required in plan: `{human_approval_required}`",
            f"- Branch: `{branch_name}`",
            "",
            "## Changed Files",
            "",
        ]

        for file_path in changed_files:
            lines.append(f"- `{file_path}`")

        lines.extend(
            [
                "",
                "## Validation",
                "",
                "After reviewing this PR, validate with:",
                "",
                "```text",
                "POST /api/observability/azure/status",
                "POST /api/observability/azure/logs",
                "POST /api/incidents/analyze-azure",
                "POST /api/remediation/plan-azure",
                "```",
                "",
                "Do not merge unless the proposed remediation is understood and approved.",
            ]
        )

        return "\n".join(lines)

    def _build_commit_message(
        self,
        app_name: str,
        remediation_plan: dict[str, Any],
    ) -> str:
        incident_detected = remediation_plan.get("incident_detected", False)

        if incident_detected:
            return f"chore: add CloudMind remediation plan for {app_name}"

        return f"chore: add CloudMind monitoring hardening plan for {app_name}"

    def _build_branch_name(
        self,
        app_name: str,
    ) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        slug = self._slugify(app_name)

        return f"cloudmind/remediation-{slug}-{timestamp}"

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

        owner = parts[0]
        repo_name = parts[1]

        return {
            "success": True,
            "owner": owner,
            "repo": repo_name,
        }

    def _build_authenticated_clone_url(
        self,
        repo_url: str,
        token: str,
    ) -> str:
        parsed = urlparse(repo_url)
        path = parsed.path

        return f"https://x-access-token:{token}@github.com{path}"

    def _github_headers(
        self,
        token: str,
    ) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get_github_token(self) -> str | None:
        return (
            os.getenv("GITHUB_TOKEN")
            or os.getenv("GH_TOKEN")
            or os.getenv("GIT_TOKEN")
        )

    def _close_repo(
        self,
        repo: Repo | None,
    ) -> None:
        if repo is None:
            return

        try:
            repo.close()
        except Exception:
            pass

        gc.collect()
        time.sleep(0.5)

    def _safe_remove_directory(
        self,
        directory: Path,
    ) -> None:
        if not directory.exists():
            return

        for attempt in range(5):
            try:
                shutil.rmtree(directory, ignore_errors=False)
                return
            except PermissionError:
                gc.collect()
                time.sleep(0.5 + attempt * 0.5)
            except OSError:
                gc.collect()
                time.sleep(0.5 + attempt * 0.5)

        try:
            shutil.rmtree(directory, ignore_errors=True)
        except Exception:
            pass

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

    def _slugify(
        self,
        value: str,
    ) -> str:
        value = value.lower().strip()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = value.strip("-")

        return value or "application"

    def _relative(
        self,
        repo_dir: Path,
        file_path: Path,
    ) -> str:
        return str(file_path.relative_to(repo_dir)).replace("\\", "/")

    def _deduplicate_list(
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