from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc

from app.agents.workflow_engine_agent import WorkflowEngineAgent
from app.core.auth import get_current_user_id
from app.db.database import SessionLocal, create_database_tables
from app.db.models import ActionRun, DeploymentState, Project, ProjectArtifact


class FinalDemoOrchestratorAgent:
    """
    Phase 19C: Memory-aware final demo orchestrator.

    This version uses the WorkflowEngineAgent as the source of truth.

    If the workflow engine says:
        workflow_ready

    then the final demo report should not be blocked by older strict checks.

    Optional steps like Kubernetes manifests or a final report itself are warnings,
    not blockers.
    """

    def __init__(self):
        self.workflow_engine = WorkflowEngineAgent()

    def get_phase_map(self) -> dict[str, Any]:
        return {
            "status": "success",
            "message": "CloudMind phase map loaded successfully.",
            "phase": "phase_19c_memory_aware_final_demo_report",
            "phases": [
                {
                    "phase": "1-2",
                    "name": "Backend foundation and repository analyzer",
                    "status": "completed",
                },
                {
                    "phase": "3",
                    "name": "Docker generation agent",
                    "status": "completed",
                },
                {
                    "phase": "4",
                    "name": "Kubernetes generation agent",
                    "status": "completed",
                },
                {
                    "phase": "5",
                    "name": "Deployment preparation agent",
                    "status": "completed",
                },
                {
                    "phase": "6",
                    "name": "CI/CD generation agent",
                    "status": "completed",
                },
                {
                    "phase": "7",
                    "name": "Azure deployment files agent",
                    "status": "completed",
                },
                {
                    "phase": "8",
                    "name": "Observability agent",
                    "status": "completed",
                },
                {
                    "phase": "9",
                    "name": "Incident response agent",
                    "status": "completed",
                },
                {
                    "phase": "10",
                    "name": "Remediation planner agent",
                    "status": "completed",
                },
                {
                    "phase": "11",
                    "name": "Remediation pull request agent",
                    "status": "completed",
                },
                {
                    "phase": "12",
                    "name": "Post-PR validation agent",
                    "status": "completed",
                },
                {
                    "phase": "13",
                    "name": "Deployment verification agent",
                    "status": "completed",
                },
                {
                    "phase": "14",
                    "name": "Final demo orchestrator",
                    "status": "upgraded_in_phase_19c",
                },
                {
                    "phase": "15",
                    "name": "Conversation brain and frontend",
                    "status": "completed",
                },
                {
                    "phase": "16",
                    "name": "Azure runtime deployment agent",
                    "status": "completed",
                },
                {
                    "phase": "17",
                    "name": "PostgreSQL persistent project memory",
                    "status": "completed",
                },
                {
                    "phase": "18",
                    "name": "Project history API and saved project selector",
                    "status": "completed",
                },
                {
                    "phase": "19A",
                    "name": "Workflow dependency planner",
                    "status": "completed",
                },
                {
                    "phase": "19B",
                    "name": "Frontend workflow panel",
                    "status": "completed",
                },
                {
                    "phase": "19C",
                    "name": "Memory-aware final demo report",
                    "status": "current",
                },
            ],
        }

    def generate_final_report(
        self,
        project_id: str | None = None,
        repo_url: str | None = None,
        pull_request_url: str | None = None,
        resource_group: str | None = None,
        app_name: str | None = None,
        run_pr_validation: bool = False,
        run_deployment_verification: bool = False,
        save_to_memory: bool = True,
        **_: Any,
    ) -> dict[str, Any]:
        """
        Generate a final demo report using PostgreSQL memory and the workflow engine.

        This method is intentionally safe:
        - It does not create PRs.
        - It does not deploy to Azure.
        - It does not merge anything.
        - It only reads memory and saves a report artifact.
        """

        create_database_tables()

        project = self._resolve_project(
            project_id=project_id,
            repo_url=repo_url,
            resource_group=resource_group,
            app_name=app_name,
        )

        if project is None:
            return self._blocked_no_project_report(
                project_id=project_id,
                repo_url=repo_url,
                resource_group=resource_group,
                app_name=app_name,
            )

        workflow_plan = self.workflow_engine.build_deployment_plan(
            project_id=project.id,
            repo_url=project.repo_url,
        )

        prepared_workflow = self._prepare_report_workflow(workflow_plan)
        steps = prepared_workflow["steps"]
        summary = prepared_workflow["summary"]
        workflow_status = prepared_workflow["status"]
        next_step = prepared_workflow["next_step"]
        report_step_satisfied = prepared_workflow["report_step_satisfied"]

        required_blockers = self._extract_required_blockers(steps)
        warnings = self._extract_warnings(
            steps=steps,
            project=project,
            pull_request_url=pull_request_url,
        )

        demo_ready = report_step_satisfied and not required_blockers

        status = "demo_ready" if demo_ready else "demo_blocked"
        recommendation = "ready_for_demo" if demo_ready else "fix_blockers_before_demo"

        checks = self._build_checks(
            steps=steps,
            project=project,
            workflow_status=workflow_status,
        )

        report_markdown = self._build_report_markdown(
            project=project,
            status=status,
            demo_ready=demo_ready,
            recommendation=recommendation,
            workflow_status=workflow_status,
            summary=summary,
            checks=checks,
            blockers=required_blockers,
            warnings=warnings,
            next_step=next_step,
        )

        result = {
            "status": status,
            "message": (
                "Final CloudMind demo report generated from PostgreSQL memory "
                "and the workflow dependency engine."
            ),
            "phase": "phase_19c_memory_aware_final_demo_report",
            "demo_ready": demo_ready,
            "demo_recommendation": recommendation,
            "recommendation": recommendation,
            "workflow_status": workflow_status,
            "workflow_summary": summary,
            "workflow_next_step": next_step,
            "project": self._project_to_dict(project),
            "checks": checks,
            "blockers": required_blockers,
            "warnings": warnings,
            "report_markdown": report_markdown,
            "safety": {
                "read_only": True,
                "creates_pull_requests": False,
                "deploys_to_azure": False,
                "merges_pull_requests": False,
                "uses_workflow_engine_as_source_of_truth": True,
                "run_pr_validation_requested": run_pr_validation,
                "run_deployment_verification_requested": run_deployment_verification,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        if save_to_memory:
            saved_artifact = self._save_report_artifact(
                project_id=project.id,
                report=result,
            )
            result["saved_to_memory"] = saved_artifact.get("saved", False)
            result["saved_artifact_id"] = saved_artifact.get("artifact_id")
            result["memory_save_error"] = saved_artifact.get("error")
        else:
            result["saved_to_memory"] = False
            result["saved_artifact_id"] = None
            result["memory_save_error"] = None

        return result

    def _prepare_report_workflow(
        self,
        workflow_plan: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Project the final-report step as completed by this invocation.

        The workflow plan is calculated before the report action is saved. Without
        this projection, a valid report blocks itself at 90% because it requires a
        previously completed final-report action as proof that it can generate one.
        """
        steps = [dict(step) for step in workflow_plan.get("steps", [])]
        final_step = next(
            (step for step in steps if step.get("id") == "final_demo_report"),
            None,
        )
        report_step_satisfied = False

        if final_step is not None:
            final_status = str(final_step.get("status") or "").lower()
            report_step_satisfied = final_status == "completed" or (
                final_status == "required"
                and final_step.get("can_execute_now") is True
            )

            if report_step_satisfied:
                final_step["status"] = "completed"
                final_step["can_execute_now"] = False
                final_step["reason"] = "Final CloudMind demo report generated successfully."
                evidence = list(final_step.get("evidence") or [])
                evidence.append("Current report generation completed the final workflow step.")
                final_step["evidence"] = evidence

        if report_step_satisfied:
            workflow_status = "workflow_ready"
            next_step = None
        else:
            workflow_status = workflow_plan.get("status", "unknown")
            next_step = workflow_plan.get("next_step")

        return {
            "steps": steps,
            "summary": self._summarize_steps(steps),
            "status": workflow_status,
            "next_step": next_step,
            "report_step_satisfied": report_step_satisfied,
        }

    def _summarize_steps(self, steps: list[dict[str, Any]]) -> dict[str, int]:
        total = len(steps)
        completed = len([step for step in steps if step.get("status") == "completed"])

        return {
            "total_steps": total,
            "completed": completed,
            "required": len([step for step in steps if step.get("status") == "required"]),
            "blocked": len([step for step in steps if step.get("status") == "blocked"]),
            "optional": len([step for step in steps if step.get("status") == "optional"]),
            "progress_percent": int((completed / total) * 100) if total else 0,
        }

    def generate_quick_report(
        self,
        project_id: str | None = None,
        repo_url: str | None = None,
        resource_group: str | None = None,
        app_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        report = self.generate_final_report(
            project_id=project_id,
            repo_url=repo_url,
            resource_group=resource_group,
            app_name=app_name,
            save_to_memory=False,
            **kwargs,
        )

        return {
            "status": report.get("status"),
            "message": "Quick CloudMind demo report generated.",
            "demo_ready": report.get("demo_ready"),
            "demo_recommendation": report.get("demo_recommendation"),
            "workflow_status": report.get("workflow_status"),
            "workflow_summary": report.get("workflow_summary"),
            "checks": report.get("checks"),
            "blockers": report.get("blockers"),
            "warnings": report.get("warnings"),
            "project": report.get("project"),
        }

    def final_report(self, **kwargs: Any) -> dict[str, Any]:
        return self.generate_final_report(**kwargs)

    def quick_report(self, **kwargs: Any) -> dict[str, Any]:
        return self.generate_quick_report(**kwargs)

    def build_final_report(self, **kwargs: Any) -> dict[str, Any]:
        return self.generate_final_report(**kwargs)

    def run_final_demo_report(self, **kwargs: Any) -> dict[str, Any]:
        return self.generate_final_report(**kwargs)

    def _resolve_project(
        self,
        project_id: str | None,
        repo_url: str | None,
        resource_group: str | None,
        app_name: str | None,
    ) -> Project | None:
        with SessionLocal() as db:
            user_id = get_current_user_id()
            tenant_filter = (Project.owner_id == user_id,) if user_id else ()

            if project_id:
                project = (
                    db.query(Project)
                    .filter(Project.id == project_id, *tenant_filter)
                    .first()
                )
                if project:
                    return self._detach_project(project)

            if repo_url:
                project = (
                    db.query(Project)
                    .filter(Project.repo_url == repo_url, *tenant_filter)
                    .order_by(desc(Project.updated_at))
                    .first()
                )
                if project:
                    return self._detach_project(project)

            if resource_group and app_name:
                project = (
                    db.query(Project)
                    .filter(
                        Project.azure_resource_group == resource_group,
                        Project.azure_app_name == app_name,
                        *tenant_filter,
                    )
                    .order_by(desc(Project.updated_at))
                    .first()
                )
                if project:
                    return self._detach_project(project)

            if app_name:
                project = (
                    db.query(Project)
                    .filter(Project.azure_app_name == app_name, *tenant_filter)
                    .order_by(desc(Project.updated_at))
                    .first()
                )
                if project:
                    return self._detach_project(project)

        return None

    def _detach_project(self, project: Project) -> Project:
        """
        Copy values into a lightweight Project-like ORM object before the session closes.

        SQLAlchemy objects expire after session close depending on configuration.
        This prevents detached-instance issues when building the report.
        """

        detached = Project()
        detached.id = project.id
        detached.name = project.name
        detached.repo_url = project.repo_url
        detached.repo_owner = project.repo_owner
        detached.repo_name = project.repo_name
        detached.default_branch = project.default_branch
        detached.detected_language = project.detected_language
        detached.detected_framework = project.detected_framework
        detached.project_type = project.project_type
        detached.port = project.port
        detached.start_command = project.start_command
        detached.ghcr_image = project.ghcr_image
        detached.azure_resource_group = project.azure_resource_group
        detached.azure_app_name = project.azure_app_name
        detached.azure_environment_name = project.azure_environment_name
        detached.azure_app_url = project.azure_app_url
        detached.metadata_json = project.metadata_json
        detached.created_at = project.created_at
        detached.updated_at = project.updated_at

        return detached

    def _blocked_no_project_report(
        self,
        project_id: str | None,
        repo_url: str | None,
        resource_group: str | None,
        app_name: str | None,
    ) -> dict[str, Any]:
        return {
            "status": "demo_blocked",
            "message": "CloudMind could not generate a demo report because no saved project was found.",
            "phase": "phase_19c_memory_aware_final_demo_report",
            "demo_ready": False,
            "demo_recommendation": "analyze_repository_first",
            "recommendation": "analyze_repository_first",
            "workflow_status": "project_not_found",
            "workflow_summary": {
                "total_steps": 0,
                "completed": 0,
                "required": 1,
                "blocked": 0,
                "optional": 0,
                "progress_percent": 0,
            },
            "project": None,
            "checks": {},
            "blockers": [
                {
                    "id": "project_not_found",
                    "title": "Project not found in PostgreSQL memory",
                    "reason": "Analyze the repository first so CloudMind can create project memory.",
                    "user_message": "Analyze this repository",
                }
            ],
            "warnings": [],
            "input": {
                "project_id": project_id,
                "repo_url": repo_url,
                "resource_group": resource_group,
                "app_name": app_name,
            },
            "saved_to_memory": False,
            "saved_artifact_id": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _extract_required_blockers(
        self,
        steps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        required_step_ids = {
            "analyze_repository",
            "generate_docker",
            "generate_kubernetes",
            "generate_azure_files",
            "generate_cicd",
            "publish_container_image",
            "deploy_to_azure",
            "check_azure_status",
            "analyze_incident",
        }

        blockers = []

        for step in steps:
            step_id = step.get("id")
            step_status = step.get("status")

            is_required_dependency = (
                step_id in required_step_ids
                and step_status in {"required", "blocked"}
            )
            is_blocked_final_report = (
                step_id == "final_demo_report" and step_status == "blocked"
            )

            if is_required_dependency or is_blocked_final_report:
                blockers.append(
                    {
                        "id": step_id,
                        "title": step.get("title"),
                        "status": step_status,
                        "reason": step.get("reason"),
                        "requires_approval": step.get("requires_approval", False),
                        "can_execute_now": step.get("can_execute_now", False),
                        "user_message": step.get("user_message"),
                    }
                )

        return blockers

    def _extract_warnings(
        self,
        steps: list[dict[str, Any]],
        project: Project,
        pull_request_url: str | None,
    ) -> list[dict[str, Any]]:
        warnings = []

        for step in steps:
            if step.get("status") == "optional":
                warnings.append(
                    {
                        "id": step.get("id"),
                        "title": step.get("title"),
                        "status": step.get("status"),
                        "reason": step.get("reason"),
                        "user_message": step.get("user_message"),
                    }
                )

        if not project.ghcr_image:
            warnings.append(
                {
                    "id": "ghcr_image_not_saved_on_project",
                    "title": "GHCR image field is empty in project memory",
                    "status": "warning",
                    "reason": (
                        "This is not a blocker because the workflow engine found deployment evidence. "
                        "Later, store the exact GHCR image in the project table for cleaner reporting."
                    ),
                }
            )

        if not pull_request_url:
            warnings.append(
                {
                    "id": "pull_request_url_not_provided",
                    "title": "Pull request URL was not provided to the report",
                    "status": "warning",
                    "reason": (
                        "This is not a blocker if the main workflow is complete, but PR evidence "
                        "makes the professor demo stronger."
                    ),
                }
            )

        return warnings

    def _build_checks(
        self,
        steps: list[dict[str, Any]],
        project: Project,
        workflow_status: str,
    ) -> dict[str, Any]:
        step_map = {step.get("id"): step for step in steps}

        return {
            "workflow_ready": workflow_status == "workflow_ready",
            "repository_analyzed": self._step_completed(step_map, "analyze_repository"),
            "docker_ready": self._step_completed(step_map, "generate_docker"),
            "kubernetes_ready": self._step_completed(step_map, "generate_kubernetes"),
            "cicd_ready": self._step_completed(step_map, "generate_cicd"),
            "container_image_ready": self._step_completed(step_map, "publish_container_image"),
            "azure_files_ready": self._step_completed(step_map, "generate_azure_files"),
            "azure_deployed": self._step_completed(step_map, "deploy_to_azure"),
            "azure_status_checked": self._step_completed(step_map, "check_azure_status"),
            "incident_analyzed": self._step_completed(step_map, "analyze_incident"),
            "final_report_ready": self._step_completed(step_map, "final_demo_report"),
            "azure_app_url": project.azure_app_url,
            "azure_resource_group": project.azure_resource_group,
            "azure_app_name": project.azure_app_name,
            "detected_language": project.detected_language,
            "detected_framework": project.detected_framework,
            "project_type": project.project_type,
        }

    def _step_completed(
        self,
        step_map: dict[str, dict[str, Any]],
        step_id: str,
    ) -> bool:
        return step_map.get(step_id, {}).get("status") == "completed"

    def _build_report_markdown(
        self,
        project: Project,
        status: str,
        demo_ready: bool,
        recommendation: str,
        workflow_status: str,
        summary: dict[str, Any],
        checks: dict[str, Any],
        blockers: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        next_step: dict[str, Any] | None,
    ) -> str:
        blocker_lines = (
            "\n".join(
                f"- {blocker.get('title')} — {blocker.get('reason')}"
                for blocker in blockers
            )
            if blockers
            else "- None"
        )

        warning_lines = (
            "\n".join(
                f"- {warning.get('title')} — {warning.get('reason')}"
                for warning in warnings
            )
            if warnings
            else "- None"
        )

        checks_lines = "\n".join(
            f"- {key}: {value}"
            for key, value in checks.items()
        )

        next_step_text = (
            f"{next_step.get('title')} — {next_step.get('reason')}"
            if next_step
            else "No next step required."
        )

        return f"""# CloudMind Final Demo Report

## Project

- Name: {project.name}
- Repository: {project.repo_url}
- Type: {project.project_type}
- Language: {project.detected_language}
- Framework: {project.detected_framework}
- Port: {project.port}
- Start command: {project.start_command}

## Demo Status

- Status: {status}
- Demo ready: {demo_ready}
- Recommendation: {recommendation}
- Workflow status: {workflow_status}
- Progress: {summary.get("progress_percent", 0)}%
- Completed steps: {summary.get("completed", 0)}/{summary.get("total_steps", 0)}
- Required remaining: {summary.get("required", 0)}
- Blocked: {summary.get("blocked", 0)}
- Optional remaining: {summary.get("optional", 0)}

## Azure Runtime

- Resource group: {project.azure_resource_group}
- Container App: {project.azure_app_name}
- Environment: {project.azure_environment_name}
- URL: {project.azure_app_url}

## Checks

{checks_lines}

## Blockers

{blocker_lines}

## Warnings

{warning_lines}

## Next Step

{next_step_text}

## Final Explanation

CloudMind analyzed the repository, tracked the project in PostgreSQL memory, planned the deployment workflow using the dependency engine, and generated this report from stored project state.

If `demo_ready` is true, the main end-to-end demo can be presented as successful. Optional warnings can be explained as future improvements.
"""

    def _save_report_artifact(
        self,
        project_id: str,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            artifact_id = str(uuid4())

            with SessionLocal() as db:
                artifact = ProjectArtifact(
                    id=artifact_id,
                    project_id=project_id,
                    action_run_id=None,
                    artifact_type="final_report",
                    name="CloudMind final demo report",
                    path=None,
                    url=None,
                    metadata_json=report,
                )

                db.add(artifact)
                db.commit()

            return {
                "saved": True,
                "artifact_id": artifact_id,
                "error": None,
            }

        except Exception as exc:
            return {
                "saved": False,
                "artifact_id": None,
                "error": str(exc),
            }

    def _project_to_dict(self, project: Project) -> dict[str, Any]:
        return {
            "id": project.id,
            "name": project.name,
            "repo_url": project.repo_url,
            "repo_owner": project.repo_owner,
            "repo_name": project.repo_name,
            "default_branch": project.default_branch,
            "detected_language": project.detected_language,
            "detected_framework": project.detected_framework,
            "project_type": project.project_type,
            "port": project.port,
            "start_command": project.start_command,
            "ghcr_image": project.ghcr_image,
            "azure_resource_group": project.azure_resource_group,
            "azure_app_name": project.azure_app_name,
            "azure_environment_name": project.azure_environment_name,
            "azure_app_url": project.azure_app_url,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        }
