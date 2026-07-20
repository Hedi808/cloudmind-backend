from typing import Any

from app.agents.deployment_verification_agent import DeploymentVerificationAgent
from app.agents.post_pr_validation_agent import PostPrValidationAgent
from app.agents.remediation_planner_agent import RemediationPlannerAgent


class FinalDemoOrchestratorAgent:
    """
    Phase 14 agent.

    Responsibilities:
    - create one final professor-friendly demo report
    - summarize all CloudMind phases
    - optionally run live PR validation
    - optionally run live Azure deployment verification
    - optionally run live remediation planning
    - return a clear final mission report

    Safety rules:
    - read-only
    - does not create PRs
    - does not merge PRs
    - does not deploy
    - does not change Azure infrastructure
    """

    def __init__(self) -> None:
        self.pr_validation_agent = PostPrValidationAgent()
        self.deployment_verification_agent = DeploymentVerificationAgent()
        self.remediation_planner_agent = RemediationPlannerAgent()

    def get_phase_map(self) -> dict[str, Any]:
        phases = self._phase_definitions()

        return {
            "status": "success",
            "message": "CloudMind phase map generated.",
            "phase": "phase_14_final_demo_orchestrator",
            "total_phases": len(phases),
            "phases": phases,
            "final_demo_flow": [
                "Analyze repository",
                "Generate Docker assets",
                "Generate Kubernetes assets",
                "Generate CI/CD workflow",
                "Generate Azure deployment assets",
                "Deploy to Azure Container Apps",
                "Observe status and logs",
                "Analyze incident state",
                "Plan remediation",
                "Create remediation PR",
                "Validate PR",
                "Verify Azure deployment",
                "Generate final mission report",
            ],
        }

    def run_final_report(
        self,
        repo_url: str,
        resource_group: str,
        app_name: str,
        pull_request_number: int | None = None,
        pull_request_url: str | None = None,
        health_path: str = "/health",
        timeout_seconds: int = 60,
        log_tail: int = 100,
        environment: str = "development",
        run_pr_validation: bool = True,
        run_azure_verification: bool = True,
        run_remediation_plan: bool = True,
        require_ci_success_for_pr_validation: bool = False,
        allow_docs_only_without_ci: bool = True,
        require_human_review_for_pr_validation: bool = False,
        require_pr_merged_for_deployment: bool = False,
        require_ci_success_for_deployment: bool = False,
        require_azure_healthy: bool = True,
        include_raw_outputs: bool = False,
    ) -> dict[str, Any]:
        repo_url = repo_url.strip()
        resource_group = resource_group.strip()
        app_name = app_name.strip()

        if not repo_url:
            return {
                "status": "failed",
                "message": "repo_url is required.",
                "demo_ready": False,
            }

        if not resource_group or not app_name:
            return {
                "status": "failed",
                "message": "resource_group and app_name are required.",
                "demo_ready": False,
            }

        live_results: dict[str, Any] = {}
        validation_notes: list[str] = []
        blockers: list[str] = []
        warnings: list[str] = []
        successful_checks: list[str] = []

        if run_azure_verification:
            azure_result = self.deployment_verification_agent.verify_azure_only(
                resource_group=resource_group,
                app_name=app_name,
                health_path=health_path,
                timeout_seconds=timeout_seconds,
                log_tail=log_tail,
                require_azure_healthy=require_azure_healthy,
            )

            live_results["phase_13_azure_deployment_verification"] = self._maybe_trim_azure_result(
                result=azure_result,
                include_raw_outputs=include_raw_outputs,
            )

            if azure_result.get("status") == "verification_passed":
                successful_checks.append("Azure deployment verification passed.")
            elif azure_result.get("status") == "verification_warning":
                warnings.append("Azure deployment verification completed with warnings.")
            else:
                blockers.append("Azure deployment verification failed.")

        else:
            validation_notes.append("Azure deployment verification was skipped by request.")

        if run_pr_validation:
            if pull_request_url:
                pr_validation_result = self.pr_validation_agent.validate_pull_request_url(
                    pull_request_url=pull_request_url,
                    require_ci_success=require_ci_success_for_pr_validation,
                    allow_docs_only_without_ci=allow_docs_only_without_ci,
                    require_human_review=require_human_review_for_pr_validation,
                )

                live_results["phase_12_pr_validation"] = self._maybe_trim_pr_validation_result(
                    result=pr_validation_result,
                    include_raw_outputs=include_raw_outputs,
                )

                self._collect_pr_validation_result(
                    result=pr_validation_result,
                    successful_checks=successful_checks,
                    warnings=warnings,
                    blockers=blockers,
                )

            elif pull_request_number:
                pr_validation_result = self.pr_validation_agent.validate_pull_request(
                    repo_url=repo_url,
                    pull_request_number=pull_request_number,
                    require_ci_success=require_ci_success_for_pr_validation,
                    allow_docs_only_without_ci=allow_docs_only_without_ci,
                    require_human_review=require_human_review_for_pr_validation,
                )

                live_results["phase_12_pr_validation"] = self._maybe_trim_pr_validation_result(
                    result=pr_validation_result,
                    include_raw_outputs=include_raw_outputs,
                )

                self._collect_pr_validation_result(
                    result=pr_validation_result,
                    successful_checks=successful_checks,
                    warnings=warnings,
                    blockers=blockers,
                )

            else:
                validation_notes.append(
                    "PR validation was skipped because no pull_request_number or pull_request_url was provided."
                )

        else:
            validation_notes.append("PR validation was skipped by request.")

        if run_remediation_plan:
            remediation_result = self.remediation_planner_agent.plan_from_azure(
                resource_group=resource_group,
                app_name=app_name,
                health_path=health_path,
                timeout_seconds=timeout_seconds,
                log_tail=log_tail,
                environment=environment,
                allow_cost_increase=False,
            )

            live_results["phase_10_remediation_planning"] = self._maybe_trim_remediation_result(
                result=remediation_result,
                include_raw_outputs=include_raw_outputs,
            )

            if remediation_result.get("incident_detected"):
                warnings.append("Remediation planner detected an incident or remediation need.")
            else:
                successful_checks.append("Remediation planner found no active incident.")

        else:
            validation_notes.append("Remediation planning was skipped by request.")

        if pull_request_number or pull_request_url:
            deployment_result = self._run_optional_pr_deployment_verification(
                repo_url=repo_url,
                pull_request_number=pull_request_number,
                pull_request_url=pull_request_url,
                resource_group=resource_group,
                app_name=app_name,
                health_path=health_path,
                timeout_seconds=timeout_seconds,
                log_tail=log_tail,
                require_pr_merged=require_pr_merged_for_deployment,
                require_ci_success=require_ci_success_for_deployment,
                require_azure_healthy=require_azure_healthy,
                include_raw_outputs=include_raw_outputs,
            )

            live_results["phase_13_pr_and_deployment_verification"] = deployment_result["result"]

            if deployment_result["classification"] == "success":
                successful_checks.append("PR + deployment verification passed.")
            elif deployment_result["classification"] == "warning":
                warnings.append("PR + deployment verification completed with warnings.")
            else:
                if require_pr_merged_for_deployment:
                    blockers.append("PR + deployment verification failed.")
                else:
                    warnings.append("PR + deployment verification did not fully pass, but require_pr_merged_for_deployment=false.")

        demo_decision = self._build_demo_decision(
            blockers=blockers,
            warnings=warnings,
            successful_checks=successful_checks,
            validation_notes=validation_notes,
        )

        return {
            "status": demo_decision["status"],
            "message": demo_decision["message"],
            "phase": "phase_14_final_demo_orchestrator",
            "demo_ready": demo_decision["demo_ready"],
            "demo_recommendation": demo_decision["demo_recommendation"],
            "repo_url": repo_url,
            "resource_group": resource_group,
            "app_name": app_name,
            "environment": environment,
            "executive_summary": self._build_executive_summary(
                app_name=app_name,
                demo_decision=demo_decision,
                successful_checks=successful_checks,
                warnings=warnings,
                blockers=blockers,
            ),
            "phase_coverage": self._build_phase_coverage(
                live_results=live_results,
            ),
            "successful_checks": self._deduplicate_strings(successful_checks),
            "warnings": self._deduplicate_strings(warnings),
            "blockers": self._deduplicate_strings(blockers),
            "validation_notes": self._deduplicate_strings(validation_notes),
            "professor_script": self._build_professor_script(
                app_name=app_name,
                resource_group=resource_group,
            ),
            "swagger_demo_order": self._build_swagger_demo_order(
                has_pr=bool(pull_request_number or pull_request_url),
            ),
            "live_results": live_results,
            "safety": {
                "read_only": True,
                "creates_pull_request": False,
                "merges_pull_request": False,
                "deploys_to_cloud": False,
                "changes_infrastructure": False,
                "safe_for_demo": True,
            },
        }

    def _run_optional_pr_deployment_verification(
        self,
        repo_url: str,
        pull_request_number: int | None,
        pull_request_url: str | None,
        resource_group: str,
        app_name: str,
        health_path: str,
        timeout_seconds: int,
        log_tail: int,
        require_pr_merged: bool,
        require_ci_success: bool,
        require_azure_healthy: bool,
        include_raw_outputs: bool,
    ) -> dict[str, Any]:
        if pull_request_url:
            result = self.deployment_verification_agent.verify_pr_url_deployment(
                pull_request_url=pull_request_url,
                resource_group=resource_group,
                app_name=app_name,
                health_path=health_path,
                timeout_seconds=timeout_seconds,
                log_tail=log_tail,
                require_pr_merged=require_pr_merged,
                require_ci_success=require_ci_success,
                require_azure_healthy=require_azure_healthy,
            )
        elif pull_request_number:
            result = self.deployment_verification_agent.verify_pr_deployment(
                repo_url=repo_url,
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
        else:
            return {
                "classification": "skipped",
                "result": {
                    "status": "skipped",
                    "message": "No pull request was provided.",
                },
            }

        if result.get("status") == "verification_passed":
            classification = "success"
        elif result.get("status") == "verification_warning":
            classification = "warning"
        else:
            classification = "failed"

        return {
            "classification": classification,
            "result": self._maybe_trim_deployment_result(
                result=result,
                include_raw_outputs=include_raw_outputs,
            ),
        }

    def _collect_pr_validation_result(
        self,
        result: dict[str, Any],
        successful_checks: list[str],
        warnings: list[str],
        blockers: list[str],
    ) -> None:
        status = result.get("status")

        if status == "validation_passed":
            successful_checks.append("PR validation passed.")
        elif status == "validation_warning":
            warnings.append("PR validation completed with warnings.")
        elif status == "validation_failed":
            blockers.append("PR validation failed.")
        else:
            warnings.append("PR validation returned an unexpected status.")

    def _build_demo_decision(
        self,
        blockers: list[str],
        warnings: list[str],
        successful_checks: list[str],
        validation_notes: list[str],
    ) -> dict[str, Any]:
        if blockers:
            return {
                "status": "demo_blocked",
                "message": "Final demo report generated, but blockers must be resolved before presenting it as successful.",
                "demo_ready": False,
                "demo_recommendation": "fix_blockers_before_demo",
            }

        if warnings:
            return {
                "status": "demo_ready_with_warnings",
                "message": "Final demo report generated. The system is demo-ready, but warnings should be explained.",
                "demo_ready": True,
                "demo_recommendation": "demo_ready_explain_warnings",
            }

        if successful_checks:
            return {
                "status": "demo_ready",
                "message": "Final demo report generated successfully. CloudMind is ready for presentation.",
                "demo_ready": True,
                "demo_recommendation": "ready_to_present",
            }

        if validation_notes:
            return {
                "status": "demo_report_only",
                "message": "Final demo report generated, but no live checks were executed.",
                "demo_ready": True,
                "demo_recommendation": "run_live_checks_for_stronger_demo",
            }

        return {
            "status": "demo_report_only",
            "message": "Final demo report generated.",
            "demo_ready": True,
            "demo_recommendation": "ready_to_present",
        }

    def _build_executive_summary(
        self,
        app_name: str,
        demo_decision: dict[str, Any],
        successful_checks: list[str],
        warnings: list[str],
        blockers: list[str],
    ) -> str:
        if blockers:
            return (
                f"CloudMind generated a final mission report for {app_name}, "
                "but the demo currently has blockers. Resolve them before presenting the flow as fully successful."
            )

        if warnings:
            return (
                f"CloudMind generated a final mission report for {app_name}. "
                "The core flow is demo-ready, but some warnings should be explained during the presentation."
            )

        return (
            f"CloudMind generated a final mission report for {app_name}. "
            "The live verification checks passed and the platform is ready to present."
        )

    def _build_phase_coverage(
        self,
        live_results: dict[str, Any],
    ) -> list[dict[str, Any]]:
        coverage = []

        for phase in self._phase_definitions():
            phase_number = phase["phase_number"]

            if phase_number <= 7:
                status = "implemented_earlier"
                evidence = "Implemented through previous CloudMind endpoints and GitOps workflow."
            elif phase_number == 8:
                status = "covered_by_phase_13"
                evidence = "Azure status and logs are checked during deployment verification."
            elif phase_number == 9:
                status = "covered_by_phase_13"
                evidence = "Incident analysis is executed during deployment verification."
            elif phase_number == 10:
                status = "validated_live" if "phase_10_remediation_planning" in live_results else "available_not_run"
                evidence = "Remediation planning endpoint is available and can be run live."
            elif phase_number == 11:
                status = "implemented_earlier"
                evidence = "Remediation PR creation was implemented in Phase 11."
            elif phase_number == 12:
                status = "validated_live" if "phase_12_pr_validation" in live_results else "available_not_run"
                evidence = "PR validation endpoint is available and can be run live."
            elif phase_number == 13:
                status = "validated_live" if "phase_13_azure_deployment_verification" in live_results else "available_not_run"
                evidence = "Deployment verification endpoint is available and can be run live."
            else:
                status = "current_phase"
                evidence = "Final demo report generated by this endpoint."

            coverage.append(
                {
                    "phase_number": phase_number,
                    "name": phase["name"],
                    "status": status,
                    "evidence": evidence,
                }
            )

        return coverage

    def _phase_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "phase_number": 1,
                "name": "Conversation and orchestration",
                "description": "CloudMind receives user instructions and routes them to the right agent.",
            },
            {
                "phase_number": 2,
                "name": "Repository analysis",
                "description": "CloudMind analyzes language, framework, architecture, and app start command.",
            },
            {
                "phase_number": 3,
                "name": "Docker generation",
                "description": "CloudMind generates Dockerfile, .dockerignore, and compose.yml.",
            },
            {
                "phase_number": 4,
                "name": "Kubernetes generation",
                "description": "CloudMind generates Kubernetes manifests and kustomization files.",
            },
            {
                "phase_number": 5,
                "name": "Deployment preparation",
                "description": "CloudMind prepares Docker and Kubernetes assets in one combined workflow.",
            },
            {
                "phase_number": 6,
                "name": "CI/CD generation",
                "description": "CloudMind generates GitHub Actions for building and publishing container images.",
            },
            {
                "phase_number": 7,
                "name": "Azure deployment generation",
                "description": "CloudMind generates Azure Container Apps deployment scripts.",
            },
            {
                "phase_number": 8,
                "name": "Observability",
                "description": "CloudMind reads Azure app status, health endpoint, revisions, and logs.",
            },
            {
                "phase_number": 9,
                "name": "Incident response",
                "description": "CloudMind diagnoses incidents using Azure status and logs.",
            },
            {
                "phase_number": 10,
                "name": "Remediation planning",
                "description": "CloudMind proposes safe remediation steps without executing risky changes.",
            },
            {
                "phase_number": 11,
                "name": "Remediation pull requests",
                "description": "CloudMind converts approved remediation plans into GitOps pull requests.",
            },
            {
                "phase_number": 12,
                "name": "Post-PR validation",
                "description": "CloudMind validates changed files, CI state, mergeability, and review status.",
            },
            {
                "phase_number": 13,
                "name": "Deployment verification after merge",
                "description": "CloudMind verifies Azure runtime health, logs, and incident resolution.",
            },
            {
                "phase_number": 14,
                "name": "Final demo orchestrator",
                "description": "CloudMind generates a final professor-friendly mission report.",
            },
        ]

    def _build_professor_script(
        self,
        app_name: str,
        resource_group: str,
    ) -> list[str]:
        return [
            "CloudMind is a multi-agent DevOps assistant.",
            "It analyzes a Git repository and understands the application stack.",
            "It generates Docker, Kubernetes, CI/CD, and Azure deployment assets.",
            "It follows GitOps principles by creating pull requests instead of pushing directly to main.",
            "It deploys the application to Azure Container Apps using a cost-aware configuration.",
            "It observes the deployed app through Azure status, health checks, revisions, and logs.",
            "It diagnoses incidents from runtime signals and logs.",
            "It proposes safe remediation plans with human approval gates.",
            "It can create remediation pull requests for human review.",
            "It validates pull requests before merge by checking changed files, CI, and risk level.",
            f"It verifies the final Azure runtime state of {app_name} in {resource_group}.",
            "The system is designed to assist DevOps workflows safely, not to replace human approval.",
        ]

    def _build_swagger_demo_order(
        self,
        has_pr: bool,
    ) -> list[dict[str, str]]:
        order = [
            {
                "step": "1",
                "endpoint": "POST /api/deployment-verification/verify-azure",
                "purpose": "Show that the deployed Azure app is healthy.",
            },
            {
                "step": "2",
                "endpoint": "POST /api/incidents/analyze-azure",
                "purpose": "Show that CloudMind can diagnose the runtime state.",
            },
            {
                "step": "3",
                "endpoint": "POST /api/remediation/plan-azure",
                "purpose": "Show safe remediation planning.",
            },
            {
                "step": "4",
                "endpoint": "POST /api/demo/final-report",
                "purpose": "Show the final CloudMind mission report.",
            },
        ]

        if has_pr:
            order.insert(
                1,
                {
                    "step": "2",
                    "endpoint": "POST /api/pr-validation/validate-url",
                    "purpose": "Show PR validation and GitOps safety.",
                },
            )

            for index, item in enumerate(order, start=1):
                item["step"] = str(index)

        return order

    def _maybe_trim_azure_result(
        self,
        result: dict[str, Any],
        include_raw_outputs: bool,
    ) -> dict[str, Any]:
        if include_raw_outputs:
            return result

        azure = result.get("azure", {}) or {}
        status_result = azure.get("status_result", {}) or {}
        status_body = status_result.get("result", status_result)
        azure_body = status_body.get("azure", {}) or {}
        health = status_body.get("health", {}) or {}
        logs_result = azure.get("logs_result", {}) or {}
        incident_result = azure.get("incident_result", {}) or {}

        return {
            "status": result.get("status"),
            "message": result.get("message"),
            "verified": result.get("verified"),
            "verification_scope": result.get("verification_scope"),
            "deployment_recommendation": result.get("deployment_recommendation"),
            "azure_summary": {
                "azure_healthy": azure.get("azure_healthy"),
                "logs_available": azure.get("logs_available"),
                "incident_detected": azure.get("incident_detected"),
                "app_url": status_body.get("app_url"),
                "health_status_code": health.get("status_code"),
                "response_time_seconds": health.get("response_time_seconds"),
                "provisioning_state": azure_body.get("provisioning_state"),
                "running_status": azure_body.get("running_status"),
                "revision": azure_body.get("latest_ready_revision_name"),
                "image": self._extract_image(azure_body),
                "min_replicas": azure_body.get("min_replicas"),
                "max_replicas": azure_body.get("max_replicas"),
                "log_count": logs_result.get("log_count"),
                "incident_status": incident_result.get("status"),
                "incident_severity": incident_result.get("severity"),
            },
            "merge_blockers": result.get("merge_blockers", []),
            "warnings": result.get("warnings", []),
            "risk_notes": result.get("risk_notes", []),
        }

    def _maybe_trim_pr_validation_result(
        self,
        result: dict[str, Any],
        include_raw_outputs: bool,
    ) -> dict[str, Any]:
        if include_raw_outputs:
            return result

        return {
            "status": result.get("status"),
            "message": result.get("message"),
            "validated": result.get("validated"),
            "pull_request": result.get("pull_request"),
            "file_summary": result.get("file_summary"),
            "ci": {
                "status": result.get("ci", {}).get("status"),
                "blocking": result.get("ci", {}).get("blocking"),
                "failed_checks": result.get("ci", {}).get("failed_checks"),
                "pending_checks": result.get("ci", {}).get("pending_checks"),
                "successful_checks": result.get("ci", {}).get("successful_checks"),
                "warnings": result.get("ci", {}).get("warnings"),
            },
            "merge_blockers": result.get("merge_blockers", []),
            "warnings": result.get("warnings", []),
            "merge_recommendation": result.get("merge_recommendation"),
            "safe_for_human_merge": result.get("safe_for_human_merge"),
        }

    def _maybe_trim_remediation_result(
        self,
        result: dict[str, Any],
        include_raw_outputs: bool,
    ) -> dict[str, Any]:
        if include_raw_outputs:
            return result

        steps = result.get("remediation_steps", []) or []

        return {
            "status": result.get("status"),
            "message": result.get("message"),
            "app_name": result.get("app_name"),
            "environment": result.get("environment"),
            "incident_detected": result.get("incident_detected"),
            "severity": result.get("severity"),
            "remediation_required": result.get("remediation_required"),
            "human_approval_required": result.get("human_approval_required"),
            "safe_to_auto_fix": result.get("safe_to_auto_fix"),
            "remediation_step_count": len(steps),
            "remediation_steps": [
                {
                    "id": step.get("id"),
                    "title": step.get("title"),
                    "risk": step.get("risk"),
                    "requires_human_approval": step.get("requires_human_approval"),
                    "safe_to_auto_fix": step.get("safe_to_auto_fix"),
                }
                for step in steps
            ],
            "risk_notes": result.get("risk_notes", []),
        }

    def _maybe_trim_deployment_result(
        self,
        result: dict[str, Any],
        include_raw_outputs: bool,
    ) -> dict[str, Any]:
        if include_raw_outputs:
            return result

        return {
            "status": result.get("status"),
            "message": result.get("message"),
            "verified": result.get("verified"),
            "verification_scope": result.get("verification_scope"),
            "pr": {
                "status": result.get("pr", {}).get("status"),
                "merged": result.get("pr", {}).get("merged"),
                "message": result.get("pr", {}).get("message"),
                "pull_request": result.get("pr", {}).get("pull_request"),
            },
            "ci": {
                "status": result.get("ci", {}).get("status"),
                "blocking": result.get("ci", {}).get("blocking"),
                "warnings": result.get("ci", {}).get("warnings"),
            },
            "azure": {
                "status": result.get("azure", {}).get("status"),
                "azure_healthy": result.get("azure", {}).get("azure_healthy"),
                "logs_available": result.get("azure", {}).get("logs_available"),
                "incident_detected": result.get("azure", {}).get("incident_detected"),
            },
            "merge_blockers": result.get("merge_blockers", []),
            "warnings": result.get("warnings", []),
            "deployment_recommendation": result.get("deployment_recommendation"),
        }

    def _extract_image(
        self,
        azure_body: dict[str, Any],
    ) -> str | None:
        containers = azure_body.get("containers", []) or []

        if not containers:
            return None

        return containers[0].get("image")

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