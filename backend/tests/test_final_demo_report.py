from __future__ import annotations

import unittest

from app.agents.final_demo_orchestrator_agent import FinalDemoOrchestratorAgent


class FinalDemoReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = FinalDemoOrchestratorAgent.__new__(FinalDemoOrchestratorAgent)

    def test_current_report_completes_its_own_workflow_step(self) -> None:
        steps = [
            {
                "id": f"step_{index}",
                "title": f"Step {index}",
                "status": "completed",
                "can_execute_now": False,
            }
            for index in range(1, 10)
        ]
        steps.append(
            {
                "id": "final_demo_report",
                "title": "Generate final demo report",
                "status": "required",
                "can_execute_now": True,
                "evidence": [],
            }
        )

        prepared = self.agent._prepare_report_workflow(
            {
                "status": "next_step_required",
                "next_step": steps[-1],
                "steps": steps,
                "summary": {
                    "total_steps": 10,
                    "completed": 9,
                    "required": 1,
                    "blocked": 0,
                    "optional": 0,
                    "progress_percent": 90,
                },
            }
        )

        self.assertTrue(prepared["report_step_satisfied"])
        self.assertEqual("workflow_ready", prepared["status"])
        self.assertIsNone(prepared["next_step"])
        self.assertEqual(10, prepared["summary"]["completed"])
        self.assertEqual(100, prepared["summary"]["progress_percent"])
        self.assertEqual("completed", prepared["steps"][-1]["status"])

    def test_blocked_final_report_remains_a_real_blocker(self) -> None:
        final_step = {
            "id": "final_demo_report",
            "title": "Generate final demo report",
            "status": "blocked",
            "can_execute_now": False,
            "reason": "Latest incident analysis detected an active issue.",
        }

        prepared = self.agent._prepare_report_workflow(
            {
                "status": "workflow_blocked",
                "next_step": final_step,
                "steps": [final_step],
                "summary": {},
            }
        )
        blockers = self.agent._extract_required_blockers(prepared["steps"])

        self.assertFalse(prepared["report_step_satisfied"])
        self.assertEqual("workflow_blocked", prepared["status"])
        self.assertEqual("blocked", prepared["steps"][0]["status"])
        self.assertEqual("final_demo_report", blockers[0]["id"])

    def test_kubernetes_and_azure_files_are_required_report_dependencies(self) -> None:
        blockers = self.agent._extract_required_blockers(
            [
                {
                    "id": "generate_kubernetes",
                    "title": "Generate Kubernetes manifests",
                    "status": "required",
                },
                {
                    "id": "generate_azure_files",
                    "title": "Generate Azure deployment files",
                    "status": "blocked",
                },
            ]
        )

        self.assertEqual(
            ["generate_kubernetes", "generate_azure_files"],
            [blocker["id"] for blocker in blockers],
        )


if __name__ == "__main__":
    unittest.main()
