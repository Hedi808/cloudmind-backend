from __future__ import annotations

import inspect
from typing import Any

from app.agents.project_memory_agent import ProjectMemoryAgent
from app.agents.pipeline_checkpoint_agent import PipelineCheckpointAgent
from app.agents.pipeline_run_agent import PipelineRunAgent
from app.agents.repo_analyzer_agent import RepositoryAnalyzerAgent
from app.agents.tool_registry_agent import ToolRegistryAgent
from app.agents.workflow_engine_agent import WorkflowEngineAgent


class PipelineExecutorAgent:
    """
    Phase 20G: Backend pipeline executor.

    Correct behavior:
    - Follows WorkflowEngineAgent's strict professional order.
    - Stops after PR-generating GitOps steps when a PR is created.
    - Stops immediately after failures.
    - Stops if an active incident is detected.
    - Does not repeatedly execute the same failing final report or incident step.
    """

    GITOPS_STEP_IDS = {
        "generate_docker",
        "generate_kubernetes",
        "generate_azure_files",
        "generate_cicd",
    }

    REQUIRED_STEP_IDS = {
        "analyze_repository",
        "generate_docker",
        "generate_kubernetes",
        "generate_azure_files",
        "generate_cicd",
        "publish_container_image",
        "deploy_to_azure",
        "check_azure_status",
        "analyze_incident",
        "final_demo_report",
    }

    def __init__(self):
        self.workflow_engine = WorkflowEngineAgent()
        self.project_memory = ProjectMemoryAgent()
        self.repo_analyzer = RepositoryAnalyzerAgent()
        self.tool_registry = ToolRegistryAgent()
        self.pipeline_runs = PipelineRunAgent()
        self.pipeline_checkpoints = PipelineCheckpointAgent()

    def run_or_resume_pipeline(
        self,
        run_id: str | None = None,
        project_id: str | None = None,
        repo_url: str | None = None,
        resource_group: str | None = None,
        app_name: str | None = None,
        app_url: str | None = None,
        health_path: str | None = None,
        pull_request_url: str | None = None,
        approval_confirmed: bool = False,
        max_steps: int = 5,
        dry_run: bool = False,
        run_optional: bool = False,
        run_optional_reporting: bool = True,
        stop_after_gitops: bool = True,
        overwrite: bool = True,
        publish_to_github: bool = True,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        requested_context = {
            "project_id": project_id,
            "repo_url": repo_url,
            "resource_group": resource_group,
            "app_name": app_name,
            "app_url": app_url,
            "health_path": health_path,
            "pull_request_url": pull_request_url,
            "overwrite": overwrite,
            "publish_to_github": publish_to_github,
            "session_id": session_id,
        }

        if run_id:
            pipeline_run = self.pipeline_runs.get_run(run_id)

            if pipeline_run is None:
                return self._missing_pipeline_run_response(run_id)

            context = dict(pipeline_run.get("context") or {})

            for key, value in requested_context.items():
                is_saved_identity = key in {"project_id", "repo_url"} and context.get(key)

                if value is not None and not is_saved_identity:
                    context[key] = value
        else:
            context = {
                key: value
                for key, value in requested_context.items()
                if value is not None
            }
            pipeline_run = self.pipeline_runs.create_run(context=context)
            run_id = pipeline_run["id"]

        context["approval_confirmed"] = approval_confirmed
        pipeline_run = self.pipeline_runs.update_run(
            run_id,
            project_id=context.get("project_id"),
            session_id=context.get("session_id"),
            repo_url=context.get("repo_url"),
            pull_request_url=context.get("pull_request_url"),
            image=context.get("image"),
            context_json=context,
        )

        checkpoint_response = self._advance_durable_checkpoint(
            pipeline_run=pipeline_run,
            context=context,
            approval_confirmed=bool(context.get("approval_confirmed")),
        )

        if checkpoint_response is not None:
            return checkpoint_response

        execution = self.run_pipeline(
            project_id=context.get("project_id"),
            repo_url=context.get("repo_url"),
            resource_group=context.get("resource_group"),
            app_name=context.get("app_name"),
            app_url=context.get("app_url"),
            health_path=context.get("health_path"),
            pull_request_url=context.get("pull_request_url"),
            approval_confirmed=bool(context.get("approval_confirmed")),
            max_steps=max_steps,
            dry_run=dry_run,
            run_optional=run_optional,
            run_optional_reporting=run_optional_reporting,
            stop_after_gitops=stop_after_gitops,
            overwrite=overwrite,
            publish_to_github=publish_to_github,
            session_id=context.get("session_id"),
        )

        updated_context = dict(execution.get("pipeline_context") or context)
        updated_context["approval_confirmed"] = False
        prior_steps = list(pipeline_run.get("executed_steps") or [])
        all_steps = prior_steps + list(execution.get("executed_steps") or [])

        transition = self._transition_after_execution(
            execution=execution,
            context=updated_context,
        )
        updated_run = self.pipeline_runs.update_run(
            run_id,
            project_id=updated_context.get("project_id"),
            session_id=updated_context.get("session_id"),
            status=transition["status"],
            checkpoint_status=transition["checkpoint_status"],
            pause_reason=transition.get("pause_reason"),
            repo_url=updated_context.get("repo_url"),
            pull_request_url=updated_context.get("pull_request_url"),
            pull_request_number=transition.get("pull_request_number"),
            merge_commit_sha=updated_context.get("merge_commit_sha"),
            image=updated_context.get("image"),
            context_json=updated_context,
            executed_steps_json=all_steps,
            checkpoint_json=transition.get("checkpoint") or {},
            last_error=transition.get("last_error"),
        )

        execution["run_id"] = run_id
        execution["checkpoint_status"] = updated_run["checkpoint_status"]
        execution["pipeline_run"] = updated_run
        return execution

    def get_pipeline_run(self, run_id: str) -> dict[str, Any] | None:
        return self.pipeline_runs.get_run(run_id)

    def list_pipeline_runs(
        self,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return self.pipeline_runs.list_runs(project_id=project_id, limit=limit)

    def _advance_durable_checkpoint(
        self,
        pipeline_run: dict[str, Any],
        context: dict[str, Any],
        approval_confirmed: bool,
    ) -> dict[str, Any] | None:
        run_id = pipeline_run["id"]
        checkpoint_status = pipeline_run.get("checkpoint_status") or "ready"
        checkpoint = dict(pipeline_run.get("checkpoint") or {})

        if checkpoint_status == "waiting_for_pr_merge":
            pull_request_url = (
                context.get("pull_request_url")
                or pipeline_run.get("pull_request_url")
            )

            if not pull_request_url:
                return self._checkpoint_error_response(
                    pipeline_run=pipeline_run,
                    context=context,
                    message="Pipeline cannot verify PR merge state because no pull request URL was saved.",
                    error="missing_pull_request_url",
                )

            result = self.pipeline_checkpoints.check_pull_request(pull_request_url)
            checkpoint["pull_request"] = result

            if result.get("status") == "failed":
                updated = self.pipeline_runs.update_run(
                    run_id,
                    status="waiting",
                    checkpoint_status="waiting_for_pr_merge",
                    pause_reason="github_pr_check_failed",
                    checkpoint_json=checkpoint,
                    last_error=result.get("message"),
                )
                return self._checkpoint_wait_response(
                    pipeline_run=updated,
                    status="checkpoint_error",
                    message=result.get("message") or "Could not check pull request merge state.",
                    checkpoint_result=result,
                )

            if result.get("status") == "closed_not_merged":
                updated = self.pipeline_runs.update_run(
                    run_id,
                    status="failed",
                    checkpoint_status="failed",
                    pause_reason="pull_request_closed_without_merge",
                    checkpoint_json=checkpoint,
                    last_error="Pull request was closed without being merged.",
                )
                return self._checkpoint_wait_response(
                    pipeline_run=updated,
                    status="pipeline_failed",
                    message="Pipeline stopped because the pull request was closed without being merged.",
                    checkpoint_result=result,
                )

            if not result.get("merged"):
                updated = self.pipeline_runs.update_run(
                    run_id,
                    status="waiting",
                    checkpoint_status="waiting_for_pr_merge",
                    pause_reason="pull_request_not_merged",
                    checkpoint_json=checkpoint,
                    last_error=None,
                )
                return self._checkpoint_wait_response(
                    pipeline_run=updated,
                    status="waiting_for_pr_merge",
                    message="Pipeline is waiting for a human to review and merge the pull request.",
                    checkpoint_result=result,
                )

            pull_request = result.get("pull_request") or {}
            merge_commit_sha = pull_request.get("merge_commit_sha")
            context["merge_commit_sha"] = merge_commit_sha
            context["pull_request_number"] = pull_request.get("number")
            context["approval_confirmed"] = False

            if checkpoint.get("gitops_step_id") == "generate_cicd":
                pipeline_run = self.pipeline_runs.update_run(
                    run_id,
                    status="waiting",
                    checkpoint_status="waiting_for_ci",
                    pause_reason="ci_not_verified",
                    pull_request_number=pull_request.get("number"),
                    merge_commit_sha=merge_commit_sha,
                    context_json=context,
                    checkpoint_json=checkpoint,
                    last_error=None,
                )
                checkpoint_status = "waiting_for_ci"
            else:
                self.pipeline_runs.update_run(
                    run_id,
                    status="running",
                    checkpoint_status="ready",
                    pause_reason=None,
                    pull_request_number=pull_request.get("number"),
                    merge_commit_sha=merge_commit_sha,
                    context_json=context,
                    checkpoint_json={},
                    last_error=None,
                )
                return None

        if checkpoint_status == "waiting_for_ci":
            repo_url = context.get("repo_url") or pipeline_run.get("repo_url")
            merge_commit_sha = (
                context.get("merge_commit_sha")
                or pipeline_run.get("merge_commit_sha")
            )

            if not repo_url or not merge_commit_sha:
                return self._checkpoint_error_response(
                    pipeline_run=pipeline_run,
                    context=context,
                    message="Pipeline cannot verify CI because repository or merge commit context is missing.",
                    error="missing_ci_context",
                )

            result = self.pipeline_checkpoints.check_ci(
                repo_url=repo_url,
                merge_commit_sha=merge_commit_sha,
            )
            checkpoint["ci"] = result
            ci_status = str(result.get("status") or "unknown").lower()

            if ci_status == "failed":
                updated = self.pipeline_runs.update_run(
                    run_id,
                    status="failed",
                    checkpoint_status="failed",
                    pause_reason="ci_failed",
                    context_json=context,
                    checkpoint_json=checkpoint,
                    last_error=result.get("message") or "CI checks failed.",
                )
                return self._checkpoint_wait_response(
                    pipeline_run=updated,
                    status="pipeline_failed",
                    message=result.get("message") or "CI checks failed.",
                    checkpoint_result=result,
                )

            if ci_status != "passed":
                updated = self.pipeline_runs.update_run(
                    run_id,
                    status="waiting",
                    checkpoint_status="waiting_for_ci",
                    pause_reason=f"ci_{ci_status}",
                    context_json=context,
                    checkpoint_json=checkpoint,
                    last_error=None,
                )
                return self._checkpoint_wait_response(
                    pipeline_run=updated,
                    status="waiting_for_ci",
                    message=result.get("message") or "Pipeline is waiting for CI checks to pass.",
                    checkpoint_result=result,
                )

            pipeline_run = self.pipeline_runs.update_run(
                run_id,
                status="waiting",
                checkpoint_status="waiting_for_image",
                pause_reason="image_not_verified",
                context_json=context,
                checkpoint_json=checkpoint,
                last_error=None,
            )
            checkpoint_status = "waiting_for_image"

        if checkpoint_status == "waiting_for_image":
            image = context.get("image") or pipeline_run.get("image")

            if not image:
                return self._checkpoint_error_response(
                    pipeline_run=pipeline_run,
                    context=context,
                    message="Pipeline cannot verify the published image because no image name was saved.",
                    error="missing_image_context",
                )

            result = self.pipeline_checkpoints.check_image(image)
            checkpoint["image"] = result

            if not result.get("accessible"):
                updated = self.pipeline_runs.update_run(
                    run_id,
                    status="waiting",
                    checkpoint_status="waiting_for_image",
                    pause_reason=(
                        "image_not_published"
                        if result.get("definitive_missing")
                        else "image_not_verifiable"
                    ),
                    context_json=context,
                    checkpoint_json=checkpoint,
                    last_error=None,
                )
                return self._checkpoint_wait_response(
                    pipeline_run=updated,
                    status="waiting_for_image",
                    message="Pipeline is waiting for the expected GHCR image manifest to become available.",
                    checkpoint_result=result,
                )

            updated = self.pipeline_runs.update_run(
                run_id,
                status="waiting",
                checkpoint_status="waiting_for_deployment_approval",
                pause_reason="deployment_approval_required",
                context_json=context,
                checkpoint_json=checkpoint,
                last_error=None,
            )
            return self._checkpoint_wait_response(
                pipeline_run=updated,
                status="waiting_for_deployment_approval",
                message="CI passed and the GHCR image exists. Human approval is required before Azure deployment.",
                checkpoint_result=result,
            )

        if checkpoint_status in {"waiting_for_approval", "waiting_for_deployment_approval"}:
            if not approval_confirmed:
                return self._checkpoint_wait_response(
                    pipeline_run=pipeline_run,
                    status=checkpoint_status,
                    message=(
                        "Human approval is required before Azure deployment."
                        if checkpoint_status == "waiting_for_deployment_approval"
                        else "Human approval is required before the next write action."
                    ),
                    checkpoint_result=checkpoint,
                )

            self.pipeline_runs.update_run(
                run_id,
                status="running",
                checkpoint_status="ready",
                pause_reason=None,
                context_json=context,
                checkpoint_json={},
                last_error=None,
            )

        return None

    def _transition_after_execution(
        self,
        execution: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        execution_status = str(execution.get("status") or "").lower()
        pause_reason = execution.get("pause_reason")
        executed_steps = execution.get("executed_steps") or []

        if execution_status == "manual_review_required":
            latest_step = executed_steps[-1] if executed_steps else {}
            output = latest_step.get("output") or {}
            pull_request = self._extract_pull_request(output)

            if not pull_request:
                return {
                    "status": "failed",
                    "checkpoint_status": "failed",
                    "pause_reason": "missing_pull_request_after_gitops",
                    "last_error": "GitOps step completed without a pull request to review.",
                }

            pull_request_url = pull_request.get("url") or pull_request.get("html_url")
            pull_request_number = pull_request.get("number") or pull_request.get("pr_number")
            context["pull_request_url"] = pull_request_url
            context["pull_request_number"] = pull_request_number

            return {
                "status": "waiting",
                "checkpoint_status": "waiting_for_pr_merge",
                "pause_reason": "manual_pr_review_required",
                "pull_request_number": pull_request_number,
                "checkpoint": {
                    "gitops_step_id": latest_step.get("step_id"),
                    "pull_request": pull_request,
                },
                "last_error": None,
            }

        if execution_status == "approval_required":
            next_step = execution.get("next_step") or {}
            deployment_approval = next_step.get("id") == "deploy_to_azure"
            return {
                "status": "waiting",
                "checkpoint_status": (
                    "waiting_for_deployment_approval"
                    if deployment_approval
                    else "waiting_for_approval"
                ),
                "pause_reason": "approval_required",
                "checkpoint": {"next_step": next_step},
                "last_error": None,
            }

        if execution_status in {"pipeline_complete", "workflow_ready"}:
            return {
                "status": "completed",
                "checkpoint_status": "completed",
                "pause_reason": None,
                "last_error": None,
            }

        if execution_status == "active_incident_detected":
            return {
                "status": "blocked_incident",
                "checkpoint_status": "blocked_incident",
                "pause_reason": pause_reason,
                "last_error": execution.get("message"),
            }

        if execution_status == "pipeline_failed":
            return {
                "status": "failed",
                "checkpoint_status": "failed",
                "pause_reason": pause_reason,
                "last_error": execution.get("message"),
            }

        return {
            "status": "paused" if execution.get("paused") else "running",
            "checkpoint_status": "ready",
            "pause_reason": pause_reason,
            "last_error": None,
        }

    def _checkpoint_wait_response(
        self,
        pipeline_run: dict[str, Any],
        status: str,
        message: str,
        checkpoint_result: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": status,
            "message": message,
            "run_id": pipeline_run["id"],
            "checkpoint_status": pipeline_run.get("checkpoint_status"),
            "project_id": pipeline_run.get("project_id"),
            "repo_url": pipeline_run.get("repo_url"),
            "started": True,
            "completed": pipeline_run.get("status") == "completed",
            "paused": True,
            "pause_reason": pipeline_run.get("pause_reason"),
            "executed_steps": [],
            "executed_count": 0,
            "workflow_status_before": None,
            "workflow_status_after": None,
            "next_step": None,
            "workflow_summary": None,
            "workflow_plan": None,
            "pipeline_context": pipeline_run.get("context") or {},
            "checkpoint_result": checkpoint_result,
            "pipeline_run": pipeline_run,
            "safety": self._safety(),
        }

    def _checkpoint_error_response(
        self,
        pipeline_run: dict[str, Any],
        context: dict[str, Any],
        message: str,
        error: str,
    ) -> dict[str, Any]:
        updated = self.pipeline_runs.update_run(
            pipeline_run["id"],
            status="waiting",
            pause_reason=error,
            context_json=context,
            last_error=message,
        )
        return self._checkpoint_wait_response(
            pipeline_run=updated,
            status="checkpoint_error",
            message=message,
            checkpoint_result={"status": "failed", "error": error},
        )

    def _missing_pipeline_run_response(self, run_id: str) -> dict[str, Any]:
        return {
            "status": "pipeline_run_not_found",
            "message": f"Pipeline run was not found: {run_id}",
            "run_id": run_id,
            "checkpoint_status": None,
            "project_id": None,
            "repo_url": None,
            "started": False,
            "completed": False,
            "paused": True,
            "pause_reason": "pipeline_run_not_found",
            "executed_steps": [],
            "executed_count": 0,
            "workflow_status_before": None,
            "workflow_status_after": None,
            "next_step": None,
            "workflow_summary": None,
            "workflow_plan": None,
            "pipeline_context": {},
            "checkpoint_result": None,
            "pipeline_run": None,
            "safety": self._safety(),
        }

    def run_pipeline(
        self,
        project_id: str | None = None,
        repo_url: str | None = None,
        resource_group: str | None = None,
        app_name: str | None = None,
        app_url: str | None = None,
        health_path: str | None = None,
        pull_request_url: str | None = None,
        approval_confirmed: bool = False,
        max_steps: int = 5,
        dry_run: bool = False,
        run_optional: bool = False,
        run_optional_reporting: bool = True,
        stop_after_gitops: bool = True,
        overwrite: bool = True,
        publish_to_github: bool = True,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        context = {
            "project_id": project_id,
            "repo_url": repo_url,
            "resource_group": resource_group,
            "app_name": app_name,
            "app_url": app_url,
            "health_path": health_path,
            "pull_request_url": pull_request_url,
            "approval_confirmed": approval_confirmed,
            "overwrite": overwrite,
            "publish_to_github": publish_to_github,
            "session_id": session_id,
        }

        initial_plan = self.workflow_engine.build_deployment_plan(
            project_id=project_id,
            repo_url=repo_url,
        )

        workflow_status_before = initial_plan.get("status")
        project = initial_plan.get("project") or {}

        self._hydrate_context_from_project(context=context, project=project)

        if initial_plan.get("status") == "project_not_found":
            if not context.get("repo_url"):
                return self._response(
                    status="missing_context",
                    message="Pipeline cannot start because no project or repository URL was provided.",
                    started=False,
                    completed=False,
                    paused=True,
                    pause_reason="missing_repo_url",
                    executed_steps=[],
                    workflow_status_before=workflow_status_before,
                    workflow_status_after=workflow_status_before,
                    plan=initial_plan,
                    context=context,
                )

        if dry_run:
            return self._response(
                status="dry_run",
                message="Dry run complete. No tools were executed.",
                started=False,
                completed=False,
                paused=False,
                pause_reason=None,
                executed_steps=[],
                workflow_status_before=workflow_status_before,
                workflow_status_after=workflow_status_before,
                plan=initial_plan,
                context=context,
            )

        executed_steps: list[dict[str, Any]] = []
        current_plan = initial_plan
        executed_step_ids: set[str] = set()

        for _ in range(max_steps):
            step = self._next_step_from_plan(current_plan=current_plan)

            if not step:
                return self._response(
                    status="pipeline_complete",
                    message="Pipeline complete. No next step is required.",
                    started=True,
                    completed=True,
                    paused=False,
                    pause_reason=None,
                    executed_steps=executed_steps,
                    workflow_status_before=workflow_status_before,
                    workflow_status_after=current_plan.get("status"),
                    plan=current_plan,
                    context=context,
                )

            step_id = step.get("id")
            step_status = step.get("status")

            if step_id in executed_step_ids:
                refreshed_plan = self._refresh_plan(context)

                return self._response(
                    status="pipeline_loop_prevented",
                    message=(
                        f"Pipeline stopped because step '{step.get('title')}' was selected again. "
                        "This prevents duplicate execution loops."
                    ),
                    started=True,
                    completed=False,
                    paused=True,
                    pause_reason="duplicate_step_selected",
                    executed_steps=executed_steps,
                    workflow_status_before=workflow_status_before,
                    workflow_status_after=refreshed_plan.get("status"),
                    plan=refreshed_plan,
                    context=context,
                )

            if current_plan.get("status") == "workflow_ready":
                return self._response(
                    status="workflow_ready",
                    message="Full pipeline is already ready. All required steps are complete.",
                    started=True,
                    completed=True,
                    paused=False,
                    pause_reason=None,
                    executed_steps=executed_steps,
                    workflow_status_before=workflow_status_before,
                    workflow_status_after=current_plan.get("status"),
                    plan=current_plan,
                    context=context,
                )

            if step_status == "blocked":
                return self._response(
                    status="pipeline_blocked",
                    message=f"Pipeline stopped because the next step is blocked: {step.get('title')}.",
                    started=True,
                    completed=False,
                    paused=True,
                    pause_reason="blocked_step",
                    executed_steps=executed_steps,
                    workflow_status_before=workflow_status_before,
                    workflow_status_after=current_plan.get("status"),
                    plan=current_plan,
                    context=context,
                )

            if step.get("requires_approval") and not approval_confirmed:
                return self._response(
                    status="approval_required",
                    message=f"Pipeline paused. Human approval is required before running: {step.get('title')}.",
                    started=True,
                    completed=False,
                    paused=True,
                    pause_reason="approval_required",
                    executed_steps=executed_steps,
                    workflow_status_before=workflow_status_before,
                    workflow_status_after=current_plan.get("status"),
                    plan=current_plan,
                    context=context,
                )

            executed_step_ids.add(str(step_id))

            result = self._execute_step(step=step, context=context)
            executed_steps.append(result)

            self._save_execution_result(
                step=step,
                result=result,
                context=context,
            )

            self._hydrate_context_from_output(
                context=context,
                output=result.get("output") or {},
            )

            if self._is_failure_status(result.get("status")):
                refreshed_plan = self._refresh_plan(context)

                return self._response(
                    status="pipeline_failed",
                    message=f"Pipeline stopped because step failed: {step.get('title')}.",
                    started=True,
                    completed=False,
                    paused=True,
                    pause_reason="step_failed",
                    executed_steps=executed_steps,
                    workflow_status_before=workflow_status_before,
                    workflow_status_after=refreshed_plan.get("status"),
                    plan=refreshed_plan,
                    context=context,
                )

            if step_id == "analyze_incident" and self._output_has_active_incident(result.get("output") or {}):
                refreshed_plan = self._refresh_plan(context)

                return self._response(
                    status="active_incident_detected",
                    message=(
                        "Pipeline stopped because an active incident was detected. "
                        "CloudMind will not repeat incident analysis or generate the final report until a clean incident analysis is recorded."
                    ),
                    started=True,
                    completed=False,
                    paused=True,
                    pause_reason="active_incident_detected",
                    executed_steps=executed_steps,
                    workflow_status_before=workflow_status_before,
                    workflow_status_after=refreshed_plan.get("status"),
                    plan=refreshed_plan,
                    context=context,
                )

            if step_id in self.GITOPS_STEP_IDS and stop_after_gitops and self._gitops_result_needs_manual_review(result):
                refreshed_plan = self._refresh_plan(context)

                return self._response(
                    status="manual_review_required",
                    message=(
                        f"Pipeline paused after GitOps step: {step.get('title')}. "
                        "Review and merge the generated pull request, then run the pipeline again."
                    ),
                    started=True,
                    completed=False,
                    paused=True,
                    pause_reason="manual_pr_review_required",
                    executed_steps=executed_steps,
                    workflow_status_before=workflow_status_before,
                    workflow_status_after=refreshed_plan.get("status"),
                    plan=refreshed_plan,
                    context=context,
                )

            current_plan = self._refresh_plan(context)

            if current_plan.get("status") == "workflow_ready":
                return self._response(
                    status="pipeline_complete",
                    message="Pipeline complete. All required workflow steps are ready.",
                    started=True,
                    completed=True,
                    paused=False,
                    pause_reason=None,
                    executed_steps=executed_steps,
                    workflow_status_before=workflow_status_before,
                    workflow_status_after=current_plan.get("status"),
                    plan=current_plan,
                    context=context,
                )

        refreshed_plan = self._refresh_plan(context)

        return self._response(
            status="max_steps_reached",
            message="Pipeline paused because the configured max_steps limit was reached.",
            started=True,
            completed=False,
            paused=True,
            pause_reason="max_steps_reached",
            executed_steps=executed_steps,
            workflow_status_before=workflow_status_before,
            workflow_status_after=refreshed_plan.get("status"),
            plan=refreshed_plan,
            context=context,
        )

    def run_next_step(
        self,
        project_id: str | None = None,
        repo_url: str | None = None,
        resource_group: str | None = None,
        app_name: str | None = None,
        app_url: str | None = None,
        health_path: str | None = None,
        pull_request_url: str | None = None,
        approval_confirmed: bool = False,
        dry_run: bool = False,
        run_optional: bool = False,
        run_optional_reporting: bool = True,
        overwrite: bool = True,
        publish_to_github: bool = True,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        return self.run_pipeline(
            project_id=project_id,
            repo_url=repo_url,
            resource_group=resource_group,
            app_name=app_name,
            app_url=app_url,
            health_path=health_path,
            pull_request_url=pull_request_url,
            approval_confirmed=approval_confirmed,
            max_steps=1,
            dry_run=dry_run,
            run_optional=run_optional,
            run_optional_reporting=run_optional_reporting,
            stop_after_gitops=True,
            overwrite=overwrite,
            publish_to_github=publish_to_github,
            session_id=session_id,
        )

    def preview(
        self,
        project_id: str | None = None,
        repo_url: str | None = None,
    ) -> dict[str, Any]:
        plan = self.workflow_engine.build_deployment_plan(
            project_id=project_id,
            repo_url=repo_url,
        )

        return {
            "status": "preview_ready",
            "message": "Pipeline preview generated. No tools were executed.",
            "workflow_plan": plan,
            "next_step": plan.get("next_step"),
            "workflow_summary": plan.get("summary"),
            "safety": self._safety(),
        }

    def _next_step_from_plan(self, current_plan: dict[str, Any]) -> dict[str, Any] | None:
        if current_plan.get("status") == "project_not_found":
            return {
                "id": "analyze_repository",
                "title": "Analyze repository",
                "tool_intent": "analyze_repo",
                "status": "required",
                "requires_approval": False,
                "can_execute_now": True,
                "user_message": "Analyze this repository",
                "reason": "Repository is not tracked yet.",
            }

        return current_plan.get("next_step")

    def _execute_step(
        self,
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        step_id = step.get("id")
        title = step.get("title") or step_id or "Unknown step"
        tool_intent = step.get("tool_intent")

        try:
            if step_id == "analyze_repository":
                output = self._execute_analyze_repository(context)

            elif step_id == "generate_docker":
                output = self._execute_tool_registry_step(
                    method_names=["_generate_docker_and_publish", "generate_docker_and_publish"],
                    context=context,
                )

            elif step_id == "generate_kubernetes":
                output = self._execute_tool_registry_step(
                    method_names=["_generate_kubernetes_and_publish", "generate_kubernetes_and_publish"],
                    context=context,
                )

            elif step_id == "generate_azure_files":
                output = self._execute_tool_registry_step(
                    method_names=["_generate_azure_and_publish", "generate_azure_and_publish"],
                    context=context,
                )

            elif step_id == "generate_cicd":
                output = self._execute_tool_registry_step(
                    method_names=["_generate_cicd_and_publish", "generate_cicd_and_publish"],
                    context=context,
                )

            elif step_id == "publish_container_image":
                output = {
                    "status": "completed",
                    "message": (
                        "Container image publication is verified from project memory. "
                        "CloudMind does not manually push the image here; GitHub Actions publishes it."
                    ),
                }

            elif step_id == "deploy_to_azure":
                output = self._execute_tool_registry_step(
                    method_names=["_deploy_azure_runtime", "deploy_azure_runtime"],
                    context=context,
                )

            elif step_id == "check_azure_status":
                output = self._execute_tool_registry_step(
                    method_names=["_check_azure_status", "check_azure_status"],
                    context=context,
                )

            elif step_id == "analyze_incident":
                output = self._execute_tool_registry_step(
                    method_names=["_analyze_incident", "analyze_incident"],
                    context=context,
                )

            elif step_id == "final_demo_report":
                output = self._execute_tool_registry_step(
                    method_names=["_final_demo_report", "final_demo_report"],
                    context=context,
                )

            else:
                return {
                    "step_id": step_id,
                    "title": title,
                    "status": "tool_not_available",
                    "message": f"No executor is configured for workflow step: {step_id}.",
                    "tool_intent": tool_intent,
                    "requires_approval": bool(step.get("requires_approval")),
                    "output": None,
                }

            status = self._normalize_execution_status(output)

            return {
                "step_id": step_id,
                "title": title,
                "status": status,
                "message": self._execution_message(step=step, output=output, status=status),
                "tool_intent": tool_intent,
                "requires_approval": bool(step.get("requires_approval")),
                "output": output if isinstance(output, dict) else {"result": output},
            }

        except Exception as exc:
            return {
                "step_id": step_id,
                "title": title,
                "status": "execution_error",
                "message": f"Step execution failed: {exc}",
                "tool_intent": tool_intent,
                "requires_approval": bool(step.get("requires_approval")),
                "output": {
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
            }

    def _execute_analyze_repository(self, context: dict[str, Any]) -> dict[str, Any]:
        repo_url = context.get("repo_url")

        if not repo_url:
            raise ValueError("repo_url is required for repository analysis.")

        analysis = self.repo_analyzer.analyze(repo_url=repo_url)

        project = self.project_memory.create_or_get_project(repo_url=repo_url)
        context["project_id"] = context.get("project_id") or project.get("id")

        self.project_memory.save_repo_analysis(
            project_id=project["id"],
            analysis=analysis,
        )

        return {
            "status": "success",
            "message": "Repository analyzed and saved in PostgreSQL memory.",
            "analysis": analysis,
            "project": project,
        }

    def _execute_tool_registry_step(
        self,
        method_names: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        kwargs = self._tool_kwargs(context)

        for method_name in method_names:
            method = getattr(self.tool_registry, method_name, None)

            if callable(method):
                return self._call_flexibly(method, kwargs)

        return {
            "status": "tool_not_available",
            "message": (
                "The required ToolRegistry method was not found. "
                f"Tried: {', '.join(method_names)}"
            ),
            "tried_methods": method_names,
        }

    def _tool_kwargs(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": context.get("project_id"),
            "repo_url": context.get("repo_url"),
            "resource_group": context.get("resource_group"),
            "app_name": context.get("app_name"),
            "app_url": context.get("app_url"),
            "pull_request_url": context.get("pull_request_url"),
            "approval_confirmed": context.get("approval_confirmed", False),
            "overwrite": context.get("overwrite", True),
            "publish_to_github": context.get("publish_to_github", True),
            "session_id": context.get("session_id"),
            "health_path": context.get("health_path"),
            "image": context.get("image"),
        }

    def _call_flexibly(self, method, kwargs: dict[str, Any]) -> dict[str, Any]:
        clean_kwargs = {
            key: value
            for key, value in kwargs.items()
            if value is not None
        }

        try:
            signature = inspect.signature(method)
            parameters = signature.parameters

            if any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            ):
                result = method(**clean_kwargs)
            else:
                supported_kwargs = {
                    key: value
                    for key, value in clean_kwargs.items()
                    if key in parameters
                }

                if supported_kwargs:
                    result = method(**supported_kwargs)
                elif "arguments" in parameters:
                    result = method(arguments=clean_kwargs)
                else:
                    result = method()

            return self._ensure_dict(result)

        except TypeError:
            pass

        try:
            return self._ensure_dict(method(arguments=clean_kwargs))
        except TypeError:
            pass

        try:
            return self._ensure_dict(method(clean_kwargs))
        except TypeError:
            pass

        result = method()
        return self._ensure_dict(result)

    def _ensure_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        if hasattr(value, "model_dump"):
            return value.model_dump()

        if hasattr(value, "dict"):
            return value.dict()

        return {
            "status": "success",
            "result": value,
        }

    def _refresh_plan(self, context: dict[str, Any]) -> dict[str, Any]:
        return self.workflow_engine.build_deployment_plan(
            project_id=context.get("project_id"),
            repo_url=context.get("repo_url"),
        )

    def _hydrate_context_from_project(
        self,
        context: dict[str, Any],
        project: dict[str, Any],
    ) -> None:
        context["project_id"] = context.get("project_id") or project.get("id")
        context["repo_url"] = context.get("repo_url") or project.get("repo_url")
        context["resource_group"] = (
            context.get("resource_group") or project.get("azure_resource_group")
        )
        context["app_name"] = context.get("app_name") or project.get("azure_app_name")
        context["app_url"] = context.get("app_url") or project.get("azure_app_url")
        context["health_path"] = context.get("health_path") or project.get("health_path")
        context["image"] = context.get("image") or project.get("ghcr_image")

    def _hydrate_context_from_output(
        self,
        context: dict[str, Any],
        output: dict[str, Any],
    ) -> None:
        project = output.get("project")

        if isinstance(project, dict):
            context["project_id"] = context.get("project_id") or project.get("id")
            context["repo_url"] = context.get("repo_url") or project.get("repo_url")
            context["health_path"] = context.get("health_path") or project.get("health_path")
            context["image"] = context.get("image") or project.get("ghcr_image")

        analysis = output.get("analysis")

        if not isinstance(analysis, dict):
            for nested_key in ["docker", "kubernetes", "azure", "cicd"]:
                nested_result = output.get(nested_key)

                if isinstance(nested_result, dict) and isinstance(
                    nested_result.get("analysis"),
                    dict,
                ):
                    analysis = nested_result["analysis"]
                    break

        if isinstance(analysis, dict):
            context["repo_url"] = context.get("repo_url") or analysis.get("repo_url")

            primary_component = analysis.get("primary_component")

            if isinstance(primary_component, dict):
                context["health_path"] = (
                    context.get("health_path")
                    or primary_component.get("health_path")
                )

            context["health_path"] = (
                context.get("health_path")
                or analysis.get("health_path")
            )

        context["resource_group"] = (
            output.get("resource_group")
            or output.get("azure_resource_group")
            or context.get("resource_group")
        )
        context["app_name"] = (
            output.get("app_name")
            or output.get("azure_app_name")
            or context.get("app_name")
        )
        context["app_url"] = (
            output.get("app_url")
            or output.get("url")
            or output.get("azure_app_url")
            or context.get("app_url")
        )
        context["health_path"] = (
            output.get("health_path")
            or output.get("detected_health_path")
            or context.get("health_path")
        )
        nested_image = None

        for nested_key in ["cicd", "docker", "kubernetes", "azure"]:
            nested_result = output.get(nested_key)

            if isinstance(nested_result, dict) and nested_result.get("image"):
                nested_image = nested_result.get("image")
                break

        context["image"] = output.get("image") or nested_image or context.get("image")

        pull_request = self._extract_pull_request(output)

        if pull_request:
            context["pull_request_url"] = (
                pull_request.get("url")
                or pull_request.get("html_url")
                or context.get("pull_request_url")
            )

    def _save_execution_result(
        self,
        step: dict[str, Any],
        result: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        project_id = context.get("project_id")
        repo_url = context.get("repo_url")
        output = result.get("output") or {}

        if not project_id and repo_url:
            try:
                project = self.project_memory.create_or_get_project(repo_url=repo_url)
                project_id = project.get("id")
                context["project_id"] = project_id
            except Exception:
                project_id = None

        if not project_id:
            return

        action_type = step.get("tool_intent") or step.get("id") or "pipeline_step"

        try:
            self.project_memory.save_completed_action(
                project_id=project_id,
                session_id=context.get("session_id"),
                action_type=action_type,
                tool_name="pipeline_executor_agent",
                status=result.get("status", "completed"),
                approval_required=bool(step.get("requires_approval")),
                approval_confirmed=bool(context.get("approval_confirmed")),
                input_json={
                    "step": step,
                    "context": {
                        "repo_url": context.get("repo_url"),
                        "resource_group": context.get("resource_group"),
                        "app_name": context.get("app_name"),
                        "health_path": context.get("health_path"),
                    },
                },
                output_json=output,
            )
        except Exception:
            pass

        self._save_pull_request_if_present(project_id=project_id, output=output)
        self._save_generated_files_if_present(project_id=project_id, output=output)
        self._save_deployment_if_present(project_id=project_id, output=output)

    def _save_pull_request_if_present(
        self,
        project_id: str,
        output: dict[str, Any],
    ) -> None:
        pull_request = self._extract_pull_request(output)

        if not pull_request:
            return

        try:
            self.project_memory.save_pull_request_artifact(
                project_id=project_id,
                pull_request=pull_request,
            )
        except Exception:
            pass

    def _save_generated_files_if_present(
        self,
        project_id: str,
        output: dict[str, Any],
    ) -> None:
        generated_files = self._extract_generated_files(output)

        if not generated_files:
            return

        try:
            self.project_memory.save_generated_files(
                project_id=project_id,
                generated_files=generated_files,
            )
        except Exception:
            pass

    def _save_deployment_if_present(
        self,
        project_id: str,
        output: dict[str, Any],
    ) -> None:
        app_url = (
            output.get("app_url")
            or output.get("url")
            or output.get("azure_app_url")
        )

        if not app_url:
            return

        health = output.get("health")

        if isinstance(health, dict):
            health_status = "healthy" if health.get("healthy") else health.get("status") or "unknown"
        else:
            health_status = output.get("health_status") or "unknown"

        try:
            self.project_memory.save_deployment_state(
                project_id=project_id,
                provider="azure",
                resource_group=output.get("resource_group"),
                app_name=output.get("app_name"),
                environment_name=output.get("environment_name"),
                image=output.get("image"),
                url=app_url,
                health_status=health_status,
                metadata=output,
            )
        except TypeError:
            try:
                self.project_memory.save_deployment_state(
                    project_id=project_id,
                    deployment={
                        "provider": "azure",
                        "resource_group": output.get("resource_group"),
                        "app_name": output.get("app_name"),
                        "environment_name": output.get("environment_name"),
                        "image": output.get("image"),
                        "url": app_url,
                        "health_status": health_status,
                        "metadata": output,
                    },
                )
            except Exception:
                pass
        except Exception:
            pass

    def _extract_pull_request(self, output: dict[str, Any]) -> dict[str, Any] | None:
        candidates = [
            output.get("pull_request"),
            output.get("pr"),
            output.get("github_pull_request"),
        ]

        for candidate in candidates:
            if isinstance(candidate, dict):
                return candidate

        git = output.get("git")

        if isinstance(git, dict):
            pull_request = git.get("pull_request")

            if isinstance(pull_request, dict):
                return pull_request

        pr_url = (
            output.get("pull_request_url")
            or output.get("pr_url")
            or output.get("html_url")
        )

        if isinstance(pr_url, str) and pr_url.startswith("http"):
            return {
                "url": pr_url,
                "html_url": pr_url,
                "title": output.get("title") or "Pipeline generated pull request",
            }

        return None

    def _extract_generated_files(self, output: dict[str, Any]) -> list[str]:
        keys = [
            "generated_file_paths",
            "generated_files",
            "files",
            "changed_files",
        ]

        for key in keys:
            value = output.get(key)

            if not isinstance(value, list):
                continue

            result = []

            for item in value:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, dict):
                    result.append(
                        str(
                            item.get("relative_path")
                            or item.get("path")
                            or item.get("name")
                            or item
                        )
                    )
                else:
                    result.append(str(item))

            return result

        return []

    def _normalize_execution_status(self, output: Any) -> str:
        if not isinstance(output, dict):
            return "success"

        raw_status = str(output.get("status", "success")).lower()

        if output.get("error"):
            return "failed"

        if raw_status in {
            "success",
            "completed",
            "published",
            "deployed",
            "deployed_with_warnings",
            "healthy",
            "verified",
            "demo_ready",
            "plan_ready",
            "no_incident",
            "incident_detected",
            "analyzed",
            "preview_ready",
            "no_changes",
        }:
            return raw_status

        if raw_status in {
            "tool_not_available",
            "failed",
            "error",
            "execution_error",
        }:
            return raw_status

        return raw_status or "success"

    def _is_failure_status(self, status: str | None) -> bool:
        return str(status or "").lower() in {
            "failed",
            "error",
            "tool_not_available",
            "execution_error",
            "authentication_required",
            "permission_denied",
            "azure_cli_unavailable",
            "azure_control_plane_error",
            "not_found",
            "unhealthy",
            "warning",
            "verification_failed",
        }

    def _output_has_active_incident(self, output: dict[str, Any]) -> bool:
        incident_detected = output.get("incident_detected")

        if incident_detected is True:
            return True

        status = str(output.get("status", "")).lower()
        severity = str(output.get("severity", "")).lower()

        return status in {"incident_detected", "degraded", "unhealthy"} or severity in {
            "low",
            "medium",
            "high",
            "critical",
        }

    def _gitops_result_needs_manual_review(self, result: dict[str, Any]) -> bool:
        output = result.get("output") or {}

        if self._extract_pull_request(output):
            return True

        status = str(result.get("status", "")).lower()

        return status == "published"

    def _execution_message(
        self,
        step: dict[str, Any],
        output: dict[str, Any],
        status: str,
    ) -> str:
        if isinstance(output, dict) and output.get("message"):
            return str(output["message"])

        if status in {
            "success",
            "completed",
            "published",
            "deployed",
            "deployed_with_warnings",
            "no_changes",
        }:
            return f"Step completed: {step.get('title')}."

        if status == "incident_detected":
            return "Incident analysis completed and detected an active incident."

        if status == "tool_not_available":
            return f"Tool is not available for step: {step.get('title')}."

        if status == "failed":
            return f"Step failed: {step.get('title')}."

        return f"Step finished with status {status}: {step.get('title')}."

    def _response(
        self,
        status: str,
        message: str,
        started: bool,
        completed: bool,
        paused: bool,
        pause_reason: str | None,
        executed_steps: list[dict[str, Any]],
        workflow_status_before: str | None,
        workflow_status_after: str | None,
        plan: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": status,
            "message": message,
            "project_id": context.get("project_id"),
            "repo_url": context.get("repo_url"),
            "started": started,
            "completed": completed,
            "paused": paused,
            "pause_reason": pause_reason,
            "executed_steps": executed_steps,
            "executed_count": len(executed_steps),
            "workflow_status_before": workflow_status_before,
            "workflow_status_after": workflow_status_after,
            "next_step": plan.get("next_step"),
            "workflow_summary": plan.get("summary"),
            "workflow_plan": plan,
            "pipeline_context": {
                "project_id": context.get("project_id"),
                "repo_url": context.get("repo_url"),
                "resource_group": context.get("resource_group"),
                "app_name": context.get("app_name"),
                "app_url": context.get("app_url"),
                "health_path": context.get("health_path"),
                "pull_request_url": context.get("pull_request_url"),
                "image": context.get("image"),
                "merge_commit_sha": context.get("merge_commit_sha"),
                "session_id": context.get("session_id"),
            },
            "safety": self._safety(),
        }

    def _safety(self) -> dict[str, Any]:
        return {
            "backend_pipeline_executor": True,
            "executes_tools": True,
            "approval_required_for_write_steps": True,
            "approval_required_for_azure_deploy": True,
            "pauses_after_gitops_by_default": True,
            "does_not_merge_pull_requests": True,
            "does_not_push_directly_to_main": True,
            "human_review_required_for_prs": True,
            "stops_after_failed_step": True,
            "stops_on_active_incident": True,
            "prevents_duplicate_step_loops": True,
        }
