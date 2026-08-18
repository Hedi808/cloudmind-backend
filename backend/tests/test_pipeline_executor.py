from __future__ import annotations

import unittest
from typing import Any

from app.agents.pipeline_executor_agent import PipelineExecutorAgent


class RepeatingWorkflowEngine:
    def __init__(self, step: dict[str, Any], project: dict[str, Any]) -> None:
        self.step = step
        self.project = project
        self.calls = 0

    def build_deployment_plan(self, **_: Any) -> dict[str, Any]:
        self.calls += 1
        return {
            "status": "next_step_required",
            "project": self.project,
            "next_step": self.step,
            "summary": {"required": 1},
            "steps": [self.step],
        }


class StubProjectMemory:
    def __init__(self) -> None:
        self.saved_actions: list[dict[str, Any]] = []

    def save_completed_action(self, **arguments: Any) -> None:
        self.saved_actions.append(arguments)


class StubToolRegistry:
    def __init__(self, method_name: str, output: dict[str, Any]) -> None:
        self.method_name = method_name
        self.output = output
        self.calls: list[dict[str, Any]] = []

        setattr(self, method_name, self._run)

    def _run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(arguments)
        return self.output


class PipelineExecutorTests(unittest.TestCase):
    def _executor(
        self,
        step: dict[str, Any],
        output: dict[str, Any],
        method_name: str,
    ) -> tuple[PipelineExecutorAgent, RepeatingWorkflowEngine, StubToolRegistry]:
        project = {
            "id": "project-id",
            "repo_url": "https://github.com/example/demo.git",
            "azure_resource_group": "rg-demo",
            "azure_app_name": "demo-app",
            "azure_app_url": "https://demo.example",
            "health_path": "/api/status",
            "ghcr_image": "ghcr.io/example/demo:latest",
        }
        workflow = RepeatingWorkflowEngine(step=step, project=project)
        tool_registry = StubToolRegistry(method_name=method_name, output=output)
        executor = PipelineExecutorAgent.__new__(PipelineExecutorAgent)
        executor.workflow_engine = workflow
        executor.project_memory = StubProjectMemory()
        executor.repo_analyzer = None
        executor.tool_registry = tool_registry
        return executor, workflow, tool_registry

    def test_authentication_required_stops_as_failure_without_looping(self) -> None:
        step = {
            "id": "check_azure_status",
            "title": "Check Azure status",
            "tool_intent": "check_azure_status",
            "status": "required",
            "requires_approval": False,
        }
        executor, workflow, tool_registry = self._executor(
            step=step,
            method_name="_check_azure_status",
            output={
                "status": "authentication_required",
                "message": "Azure CLI authentication expired.",
                "azure_verified": False,
                "endpoint_healthy": True,
            },
        )

        result = executor.run_pipeline(project_id="project-id", max_steps=3)

        self.assertEqual("pipeline_failed", result["status"])
        self.assertEqual("step_failed", result["pause_reason"])
        self.assertEqual(1, result["executed_count"])
        self.assertNotEqual("pipeline_loop_prevented", result["status"])
        self.assertEqual(1, len(tool_registry.calls))
        self.assertEqual(2, workflow.calls)

    def test_health_path_and_app_url_are_passed_to_runtime_tool(self) -> None:
        step = {
            "id": "check_azure_status",
            "title": "Check Azure status",
            "tool_intent": "check_azure_status",
            "status": "required",
            "requires_approval": False,
        }
        executor, _, tool_registry = self._executor(
            step=step,
            method_name="_check_azure_status",
            output={"status": "healthy", "healthy": True},
        )

        executor.run_pipeline(project_id="project-id", max_steps=1)

        self.assertEqual("/api/status", tool_registry.calls[0]["health_path"])
        self.assertEqual("https://demo.example", tool_registry.calls[0]["app_url"])

    def test_active_incident_stops_before_another_step(self) -> None:
        step = {
            "id": "analyze_incident",
            "title": "Analyze incident",
            "tool_intent": "analyze_incident",
            "status": "required",
            "requires_approval": False,
        }
        executor, _, tool_registry = self._executor(
            step=step,
            method_name="_analyze_incident",
            output={
                "status": "incident_detected",
                "incident_detected": True,
                "severity": "high",
            },
        )

        result = executor.run_pipeline(project_id="project-id", max_steps=3)

        self.assertEqual("active_incident_detected", result["status"])
        self.assertEqual("active_incident_detected", result["pause_reason"])
        self.assertEqual(1, len(tool_registry.calls))

    def test_approval_gate_executes_no_write_tool(self) -> None:
        step = {
            "id": "generate_cicd",
            "title": "Generate CI/CD",
            "tool_intent": "generate_cicd",
            "status": "required",
            "requires_approval": True,
        }
        executor, _, tool_registry = self._executor(
            step=step,
            method_name="_generate_cicd_and_publish",
            output={"status": "published"},
        )

        result = executor.run_pipeline(
            project_id="project-id",
            approval_confirmed=False,
            max_steps=3,
        )

        self.assertEqual("approval_required", result["status"])
        self.assertEqual(0, result["executed_count"])
        self.assertEqual([], tool_registry.calls)


if __name__ == "__main__":
    unittest.main()
