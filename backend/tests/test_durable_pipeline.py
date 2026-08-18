from __future__ import annotations

import copy
import unittest
from typing import Any

from app.agents.pipeline_executor_agent import PipelineExecutorAgent
from app.schemas.pipeline import PipelineRunResponse


class InMemoryPipelineRuns:
    def __init__(self, run: dict[str, Any]) -> None:
        self.run = copy.deepcopy(run)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return copy.deepcopy(self.run) if self.run.get("id") == run_id else None

    def update_run(self, run_id: str, **updates: Any) -> dict[str, Any]:
        if run_id != self.run.get("id"):
            raise ValueError("run not found")

        aliases = {
            "context_json": "context",
            "executed_steps_json": "executed_steps",
            "checkpoint_json": "checkpoint",
        }

        for key, value in updates.items():
            self.run[aliases.get(key, key)] = copy.deepcopy(value)

        return copy.deepcopy(self.run)


class StubCheckpoints:
    def __init__(
        self,
        pull_request: dict[str, Any] | None = None,
        ci: dict[str, Any] | None = None,
        image: dict[str, Any] | None = None,
    ) -> None:
        self.pull_request = pull_request or {}
        self.ci = ci or {}
        self.image = image or {}
        self.calls: list[str] = []

    def check_pull_request(self, _: str) -> dict[str, Any]:
        self.calls.append("pull_request")
        return self.pull_request

    def check_ci(self, **_: Any) -> dict[str, Any]:
        self.calls.append("ci")
        return self.ci

    def check_image(self, _: str) -> dict[str, Any]:
        self.calls.append("image")
        return self.image


class DurablePipelineTests(unittest.TestCase):
    def _executor(
        self,
        run: dict[str, Any],
        checkpoints: StubCheckpoints,
    ) -> tuple[PipelineExecutorAgent, InMemoryPipelineRuns]:
        executor = PipelineExecutorAgent.__new__(PipelineExecutorAgent)
        pipeline_runs = InMemoryPipelineRuns(run)
        executor.pipeline_runs = pipeline_runs
        executor.pipeline_checkpoints = checkpoints
        return executor, pipeline_runs

    def _run(
        self,
        checkpoint_status: str,
        checkpoint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": "run-id",
            "project_id": "project-id",
            "session_id": "session-id",
            "status": "waiting",
            "checkpoint_status": checkpoint_status,
            "pause_reason": None,
            "repo_url": "https://github.com/example/demo.git",
            "pull_request_url": "https://github.com/example/demo/pull/7",
            "pull_request_number": 7,
            "merge_commit_sha": None,
            "image": "ghcr.io/example/demo:latest",
            "context": {
                "project_id": "project-id",
                "repo_url": "https://github.com/example/demo.git",
                "pull_request_url": "https://github.com/example/demo/pull/7",
                "image": "ghcr.io/example/demo:latest",
                "health_path": "/api/status",
            },
            "executed_steps": [],
            "checkpoint": checkpoint or {},
            "last_error": None,
        }

    def test_unmerged_pull_request_remains_waiting(self) -> None:
        run = self._run(
            "waiting_for_pr_merge",
            checkpoint={"gitops_step_id": "generate_docker"},
        )
        checkpoints = StubCheckpoints(
            pull_request={
                "status": "not_merged",
                "merged": False,
                "message": "Pull request is not merged yet.",
            }
        )
        executor, pipeline_runs = self._executor(run, checkpoints)

        result = executor._advance_durable_checkpoint(
            pipeline_run=run,
            context=dict(run["context"]),
            approval_confirmed=False,
        )

        self.assertEqual("waiting_for_pr_merge", result["status"])
        self.assertEqual("waiting_for_pr_merge", pipeline_runs.run["checkpoint_status"])
        self.assertEqual(["pull_request"], checkpoints.calls)
        PipelineRunResponse.model_validate(result)

    def test_non_cicd_merge_resumes_normal_execution(self) -> None:
        run = self._run(
            "waiting_for_pr_merge",
            checkpoint={"gitops_step_id": "generate_kubernetes"},
        )
        checkpoints = StubCheckpoints(
            pull_request={
                "status": "merged",
                "merged": True,
                "pull_request": {"number": 7, "merge_commit_sha": "abc123"},
            }
        )
        executor, pipeline_runs = self._executor(run, checkpoints)
        context = dict(run["context"])

        result = executor._advance_durable_checkpoint(
            pipeline_run=run,
            context=context,
            approval_confirmed=False,
        )

        self.assertIsNone(result)
        self.assertEqual("ready", pipeline_runs.run["checkpoint_status"])
        self.assertEqual("abc123", pipeline_runs.run["merge_commit_sha"])
        self.assertFalse(context["approval_confirmed"])

    def test_cicd_merge_with_pending_ci_waits_for_ci(self) -> None:
        run = self._run(
            "waiting_for_pr_merge",
            checkpoint={"gitops_step_id": "generate_cicd"},
        )
        checkpoints = StubCheckpoints(
            pull_request={
                "status": "merged",
                "merged": True,
                "pull_request": {"number": 7, "merge_commit_sha": "abc123"},
            },
            ci={
                "status": "pending",
                "message": "CI checks are still pending.",
                "blocking": True,
            },
        )
        executor, pipeline_runs = self._executor(run, checkpoints)

        result = executor._advance_durable_checkpoint(
            pipeline_run=run,
            context=dict(run["context"]),
            approval_confirmed=False,
        )

        self.assertEqual("waiting_for_ci", result["status"])
        self.assertEqual("waiting_for_ci", pipeline_runs.run["checkpoint_status"])
        self.assertEqual(["pull_request", "ci"], checkpoints.calls)

    def test_passed_ci_and_available_image_wait_for_deployment_approval(self) -> None:
        run = self._run(
            "waiting_for_ci",
            checkpoint={"gitops_step_id": "generate_cicd"},
        )
        run["merge_commit_sha"] = "abc123"
        run["context"]["merge_commit_sha"] = "abc123"
        checkpoints = StubCheckpoints(
            ci={"status": "passed", "message": "CI checks passed."},
            image={
                "checked": True,
                "accessible": True,
                "definitive_missing": False,
                "status_code": 200,
            },
        )
        executor, pipeline_runs = self._executor(run, checkpoints)

        result = executor._advance_durable_checkpoint(
            pipeline_run=run,
            context=dict(run["context"]),
            approval_confirmed=False,
        )

        self.assertEqual("waiting_for_deployment_approval", result["status"])
        self.assertEqual(
            "waiting_for_deployment_approval",
            pipeline_runs.run["checkpoint_status"],
        )
        self.assertEqual(["ci", "image"], checkpoints.calls)

    def test_deployment_approval_releases_checkpoint(self) -> None:
        run = self._run("waiting_for_deployment_approval")
        executor, pipeline_runs = self._executor(run, StubCheckpoints())

        result = executor._advance_durable_checkpoint(
            pipeline_run=run,
            context=dict(run["context"]),
            approval_confirmed=True,
        )

        self.assertIsNone(result)
        self.assertEqual("ready", pipeline_runs.run["checkpoint_status"])
        self.assertEqual("running", pipeline_runs.run["status"])

    def test_gitops_transition_saves_pull_request_checkpoint(self) -> None:
        run = self._run("ready")
        executor, _ = self._executor(run, StubCheckpoints())
        context = {"image": "ghcr.io/example/demo:latest"}

        transition = executor._transition_after_execution(
            execution={
                "status": "manual_review_required",
                "pause_reason": "manual_pr_review_required",
                "executed_steps": [
                    {
                        "step_id": "generate_cicd",
                        "output": {
                            "status": "published",
                            "pull_request": {
                                "number": 7,
                                "html_url": "https://github.com/example/demo/pull/7",
                            },
                        },
                    }
                ],
            },
            context=context,
        )

        self.assertEqual("waiting_for_pr_merge", transition["checkpoint_status"])
        self.assertEqual("generate_cicd", transition["checkpoint"]["gitops_step_id"])
        self.assertEqual(7, transition["pull_request_number"])
        self.assertEqual(
            "https://github.com/example/demo/pull/7",
            context["pull_request_url"],
        )

    def test_run_and_resume_use_the_saved_checkpoint_without_reexecuting(self) -> None:
        run = self._run("ready")
        checkpoints = StubCheckpoints(
            pull_request={
                "status": "not_merged",
                "merged": False,
                "message": "Pull request is not merged yet.",
            }
        )
        executor, pipeline_runs = self._executor(run, checkpoints)
        execution_calls: list[str] = []

        def execute_once(**_: Any) -> dict[str, Any]:
            execution_calls.append("execute")
            return {
                "status": "manual_review_required",
                "message": "Pull request created.",
                "started": True,
                "completed": False,
                "paused": True,
                "pause_reason": "manual_pr_review_required",
                "executed_steps": [
                    {
                        "step_id": "generate_cicd",
                        "title": "Generate CI/CD",
                        "status": "published",
                        "message": "CI/CD pull request created.",
                        "output": {
                            "pull_request": {
                                "number": 7,
                                "html_url": "https://github.com/example/demo/pull/7",
                            }
                        },
                    }
                ],
                "pipeline_context": dict(run["context"]),
            }

        executor.run_pipeline = execute_once
        first = executor.run_or_resume_pipeline(run_id="run-id")

        self.assertEqual("waiting_for_pr_merge", first["checkpoint_status"])
        self.assertEqual(1, len(execution_calls))
        self.assertEqual(
            "https://github.com/example/demo/pull/7",
            pipeline_runs.run["pull_request_url"],
        )

        def fail_if_executed(**_: Any) -> dict[str, Any]:
            raise AssertionError("resume must not execute while the PR is unmerged")

        executor.run_pipeline = fail_if_executed
        resumed = executor.run_or_resume_pipeline(run_id="run-id")

        self.assertEqual("waiting_for_pr_merge", resumed["status"])
        self.assertEqual(["pull_request"], checkpoints.calls)
        self.assertEqual(1, len(execution_calls))

    def test_pr_merge_consumes_old_approval_before_next_write_step(self) -> None:
        run = self._run(
            "waiting_for_pr_merge",
            checkpoint={"gitops_step_id": "generate_kubernetes"},
        )
        checkpoints = StubCheckpoints(
            pull_request={
                "status": "merged",
                "merged": True,
                "pull_request": {"number": 7, "merge_commit_sha": "abc123"},
            }
        )
        executor, _ = self._executor(run, checkpoints)
        received_approval: list[bool] = []

        def capture_execution(**kwargs: Any) -> dict[str, Any]:
            received_approval.append(kwargs["approval_confirmed"])
            return {
                "status": "approval_required",
                "message": "Fresh approval required.",
                "started": True,
                "completed": False,
                "paused": True,
                "pause_reason": "approval_required",
                "executed_steps": [],
                "next_step": {"id": "generate_azure_files"},
                "pipeline_context": dict(run["context"]),
            }

        executor.run_pipeline = capture_execution
        result = executor.run_or_resume_pipeline(
            run_id="run-id",
            approval_confirmed=True,
        )

        self.assertEqual([False], received_approval)
        self.assertEqual("waiting_for_approval", result["checkpoint_status"])


if __name__ == "__main__":
    unittest.main()
