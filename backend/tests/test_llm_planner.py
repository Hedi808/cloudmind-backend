from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from app.agents.conversation_brain_agent import ConversationBrainAgent
from app.agents.llm_planner_agent import LLMPlannerAgent
from app.agents.llm_planning_context_agent import LLMPlanningContextAgent
from app.agents.llm_provider_agent import (
    GeminiStructuredProvider,
    OllamaStructuredProvider,
    OpenAIResponsesProvider,
    StructuredLLMResult,
)
from app.schemas.llm_planning import LLMPlannedAgentStep, LLMPlannerOutput


class StubContextAgent:
    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context

    def build_context(self, **_: Any) -> dict[str, Any]:
        return self.context


class StubAuditAgent:
    def __init__(self, latest_result: dict[str, Any] | None = None) -> None:
        self.records: list[dict[str, Any]] = []
        self.latest_result = latest_result

    def record(self, **kwargs: Any) -> dict[str, Any]:
        self.records.append(kwargs)
        return {"id": "audit-id"}

    def latest_provider_result(self, **_: Any) -> dict[str, Any] | None:
        return self.latest_result


class MockProvider:
    provider_name = "mock-openai"
    model = "mock-model"
    available = True

    def __init__(self, plan: LLMPlannerOutput) -> None:
        self.plan = plan
        self.calls: list[dict[str, Any]] = []

    def generate_structured(self, **kwargs: Any) -> StructuredLLMResult:
        self.calls.append(kwargs)
        return StructuredLLMResult(
            parsed=self.plan,
            provider=self.provider_name,
            model=self.model,
            response_id="response-id",
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )


class FailingProvider(MockProvider):
    def generate_structured(self, **kwargs: Any) -> StructuredLLMResult:
        raise RuntimeError("simulated provider outage")


class FakeResponsesClient:
    def __init__(self, plan: LLMPlannerOutput) -> None:
        self.plan = plan
        self.kwargs: dict[str, Any] | None = None
        self.responses = self

    def parse(self, **kwargs: Any):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="response-id",
            output_parsed=self.plan,
            usage=SimpleNamespace(
                input_tokens=12,
                output_tokens=8,
                total_tokens=20,
            ),
        )


class FakeGeminiClient:
    def __init__(self, plan: LLMPlannerOutput) -> None:
        self.plan = plan
        self.kwargs: dict[str, Any] | None = None
        self.beta = self
        self.chat = self
        self.completions = self

    def parse(self, **kwargs: Any):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="gemini-response-id",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(parsed=self.plan),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=14,
                completion_tokens=9,
                total_tokens=23,
            ),
        )


class LLMPlannerTests(unittest.TestCase):
    def _context(self) -> dict[str, Any]:
        return {
            "project": {
                "id": "project-id",
                "repo_url": "https://github.com/example/demo.git",
                "framework": "FastAPI",
            },
            "workflow": {
                "status": "next_step_required",
                "summary": {"completed": 1, "required": 2},
                "steps": [
                    {
                        "id": "generate_cicd",
                        "title": "Generate CI/CD workflow",
                        "description": "Generate a workflow through GitOps.",
                        "status": "required",
                        "reason": "CI/CD is required.",
                        "depends_on": [],
                    },
                    {
                        "id": "deploy_to_azure",
                        "title": "Deploy to Azure Container Apps",
                        "description": "Deploy the published image.",
                        "status": "blocked",
                        "reason": "Wait for image publication.",
                        "depends_on": ["generate_cicd"],
                    },
                ],
            },
            "specialist_agents": [],
        }

    def _model_plan(self) -> LLMPlannerOutput:
        return LLMPlannerOutput(
            goal="Deploy this repo and make it production-ready.",
            intent="production_deployment_plan",
            response_type="plan",
            summary="Coordinate the specialist agents.",
            assumptions=[],
            missing_information=[],
            risks=[],
            steps=[
                LLMPlannedAgentStep(
                    id="deploy",
                    title="Deploy to Azure",
                    specialist_agent="CloudMindCoordinatorAgent",
                    tool_name="deploy_azure_runtime",
                    objective="Deploy the image.",
                    action_kind="read",
                    risk="low",
                    requires_approval=False,
                    depends_on=[],
                    success_criteria=["The public endpoint is healthy."],
                )
            ],
            requires_approval=False,
            approval_summary="No approval needed.",
            can_start=True,
            recommended_next_action="Execute now.",
        )

    def test_policy_restores_specialist_ownership_and_write_approval(self) -> None:
        provider = MockProvider(self._model_plan())
        audit = StubAuditAgent()
        planner = LLMPlannerAgent(
            provider=provider,
            context_agent=StubContextAgent(self._context()),
            audit_agent=audit,
            enabled=True,
        )

        result = planner.plan(
            user_goal="Deploy this repo and make it production-ready.",
            session_id="session-id",
            project_id="project-id",
            repo_url="https://github.com/example/demo.git",
            project_context={},
            conversation_state={},
        )
        step = result["plan"]["steps"][0]

        self.assertEqual("AzureRuntimeDeploymentAgent", step["specialist_agent"])
        self.assertEqual("cloud_write", step["action_kind"])
        self.assertEqual("high", step["risk"])
        self.assertTrue(step["requires_approval"])
        self.assertTrue(result["plan"]["requires_approval"])
        self.assertFalse(result["safety"]["planner_executes_tools"])
        self.assertEqual("audit-id", result["audit_id"])
        self.assertEqual(1, len(provider.calls))
        self.assertEqual(1, len(audit.records))

    def test_disabled_llm_uses_multi_agent_deterministic_fallback(self) -> None:
        audit = StubAuditAgent()
        planner = LLMPlannerAgent(
            context_agent=StubContextAgent(self._context()),
            audit_agent=audit,
            enabled=False,
        )

        result = planner.plan(
            user_goal="Deploy this repo and make it production-ready.",
            session_id="session-id",
            project_id="project-id",
            repo_url="https://github.com/example/demo.git",
            project_context={},
            conversation_state={},
        )

        self.assertTrue(result["fallback_used"])
        self.assertEqual("llm_disabled", result["fallback_reason"])
        self.assertEqual("plan_ready", result["status"])
        self.assertEqual(
            ["CICDAgent", "AzureRuntimeDeploymentAgent"],
            [step["specialist_agent"] for step in result["plan"]["steps"]],
        )

    def test_policy_neutralizes_tool_less_write_claims(self) -> None:
        plan = self._model_plan().model_copy(
            update={
                "steps": [
                    LLMPlannedAgentStep(
                        id="direct-write",
                        title="Perform an unspecified write",
                        specialist_agent="AzureRuntimeDeploymentAgent",
                        tool_name=None,
                        objective="Write directly without a registered tool.",
                        action_kind="cloud_write",
                        risk="low",
                        requires_approval=False,
                        depends_on=[],
                        success_criteria=["The write completes."],
                    )
                ]
            }
        )
        planner = LLMPlannerAgent(
            provider=MockProvider(plan),
            context_agent=StubContextAgent(self._context()),
            audit_agent=StubAuditAgent(),
            enabled=True,
        )

        result = planner.plan(
            user_goal="Perform an unspecified cloud write.",
            session_id="session-id",
            project_id="project-id",
            repo_url="https://github.com/example/demo.git",
            project_context={},
            conversation_state={},
        )
        step = result["plan"]["steps"][0]

        self.assertEqual("CloudMindCoordinatorAgent", step["specialist_agent"])
        self.assertEqual("manual_check", step["action_kind"])
        self.assertEqual("high", step["risk"])
        self.assertTrue(step["requires_approval"])
        self.assertIn("tool-less write", result["policy_notes"][0])

    def test_policy_neutralizes_unsupported_tools(self) -> None:
        plan = self._model_plan().model_copy(
            update={
                "steps": [
                    LLMPlannedAgentStep(
                        id="unknown-tool",
                        title="Call an unknown tool",
                        specialist_agent="CloudMindCoordinatorAgent",
                        tool_name="delete_everything",
                        objective="Use a tool outside the CloudMind registry.",
                        action_kind="read",
                        risk="low",
                        requires_approval=False,
                        depends_on=[],
                        success_criteria=["The tool runs."],
                    )
                ]
            }
        )
        planner = LLMPlannerAgent(
            provider=MockProvider(plan),
            context_agent=StubContextAgent(self._context()),
            audit_agent=StubAuditAgent(),
            enabled=True,
        )

        result = planner.plan(
            user_goal="Run an unsupported tool.",
            session_id="session-id",
            project_id="project-id",
            repo_url="https://github.com/example/demo.git",
            project_context={},
            conversation_state={},
        )
        step = result["plan"]["steps"][0]

        self.assertIsNone(step["tool_name"])
        self.assertEqual("manual_check", step["action_kind"])
        self.assertEqual("high", step["risk"])
        self.assertTrue(step["requires_approval"])
        self.assertIn("unsupported tool", result["policy_notes"][0])

    def test_provider_failure_falls_back_and_is_audited(self) -> None:
        provider = FailingProvider(self._model_plan())
        audit = StubAuditAgent()
        planner = LLMPlannerAgent(
            provider=provider,
            context_agent=StubContextAgent(self._context()),
            audit_agent=audit,
            enabled=True,
        )

        result = planner.plan(
            user_goal="Deploy this repo and make it production-ready.",
            session_id="session-id",
            project_id="project-id",
            repo_url="https://github.com/example/demo.git",
            project_context={},
            conversation_state={},
        )

        self.assertTrue(result["fallback_used"])
        self.assertEqual("provider_error", result["fallback_reason"])
        self.assertIn("simulated provider outage", result["provider_error"])
        self.assertEqual("simulated provider outage", audit.records[0]["error"])

    def test_user_goal_is_bounded_before_provider_and_audit(self) -> None:
        provider = MockProvider(self._model_plan())
        audit = StubAuditAgent()
        planner = LLMPlannerAgent(
            provider=provider,
            context_agent=StubContextAgent(self._context()),
            audit_agent=audit,
            enabled=True,
        )

        planner.plan(
            user_goal="x" * 2000,
            session_id="session-id",
            project_id="project-id",
            repo_url="https://github.com/example/demo.git",
            project_context={},
            conversation_state={},
        )

        self.assertEqual(1000, len(audit.records[0]["request"]["user_goal"]))
        self.assertNotIn("x" * 1001, provider.calls[0]["user_prompt"])

    def test_context_agent_redacts_secret_fields(self) -> None:
        context_agent = LLMPlanningContextAgent.__new__(LLMPlanningContextAgent)
        sanitized = context_agent.sanitize(
            {
                "github_token": "secret-token",
                "nested": {
                    "password": "secret-password",
                    "safe": "visible",
                },
            }
        )

        self.assertEqual("[REDACTED]", sanitized["github_token"])
        self.assertEqual("[REDACTED]", sanitized["nested"]["password"])
        self.assertEqual("visible", sanitized["nested"]["safe"])

    def test_openai_provider_uses_responses_structured_output(self) -> None:
        fake_client = FakeResponsesClient(self._model_plan())
        provider = OpenAIResponsesProvider(
            api_key=None,
            model="test-model",
            base_url="https://api.openai.com/v1",
            client=fake_client,
        )

        result = provider.generate_structured(
            system_prompt="system",
            user_prompt="user",
            response_model=LLMPlannerOutput,
        )

        self.assertEqual("response-id", result.response_id)
        self.assertEqual(20, result.usage["total_tokens"])
        self.assertIs(fake_client.kwargs["text_format"], LLMPlannerOutput)
        self.assertFalse(fake_client.kwargs["store"])
        self.assertEqual("medium", fake_client.kwargs["reasoning"]["effort"])

    def test_gemini_provider_uses_compatible_structured_output(self) -> None:
        fake_client = FakeGeminiClient(self._model_plan())
        provider = GeminiStructuredProvider(
            api_key=None,
            model="gemini-3.6-flash",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            client=fake_client,
        )

        result = provider.generate_structured(
            system_prompt="system",
            user_prompt="user",
            response_model=LLMPlannerOutput,
        )

        self.assertEqual("gemini", result.provider)
        self.assertEqual("gemini-response-id", result.response_id)
        self.assertEqual(23, result.usage["total_tokens"])
        self.assertIs(fake_client.kwargs["response_format"], LLMPlannerOutput)
        self.assertEqual("system", fake_client.kwargs["messages"][0]["content"])

    def test_ollama_provider_uses_local_structured_output(self) -> None:
        calls: list[dict[str, Any]] = []

        def requester(payload: dict[str, Any]) -> dict[str, Any]:
            calls.append(payload)
            return {
                "message": {"content": self._model_plan().model_dump_json()},
                "prompt_eval_count": 18,
                "eval_count": 11,
            }

        provider = OllamaStructuredProvider(
            model="llama3.2:3b",
            base_url="http://127.0.0.1:11434",
            requester=requester,
        )
        result = provider.generate_structured(
            system_prompt="system",
            user_prompt="user",
            response_model=LLMPlannerOutput,
        )

        self.assertEqual("ollama", result.provider)
        self.assertEqual("llama3.2:3b", result.model)
        self.assertEqual(29, result.usage["total_tokens"])
        self.assertFalse(calls[0]["stream"])
        self.assertEqual(0, calls[0]["options"]["temperature"])
        self.assertEqual("object", calls[0]["format"]["type"])

    def test_broad_production_goal_routes_to_llm_planner(self) -> None:
        brain = ConversationBrainAgent.__new__(ConversationBrainAgent)

        self.assertEqual(
            "plan_devops_goal",
            brain._detect_intent("Deploy this repo and make it production-ready."),
        )

    def test_llm_health_does_not_claim_an_unverified_key_is_ready(self) -> None:
        planner = LLMPlannerAgent(
            provider=MockProvider(self._model_plan()),
            context_agent=StubContextAgent(self._context()),
            audit_agent=StubAuditAgent(),
            enabled=True,
        )

        health = planner.health()

        self.assertEqual("configured_unverified", health["status"])
        self.assertTrue(health["provider_configured"])
        self.assertIsNone(health["provider_verified"])

    def test_llm_health_reports_the_latest_provider_error(self) -> None:
        planner = LLMPlannerAgent(
            provider=MockProvider(self._model_plan()),
            context_agent=StubContextAgent(self._context()),
            audit_agent=StubAuditAgent(
                latest_result={
                    "status": "provider_error",
                    "fallback_used": True,
                    "error": "Please pass a valid API key",
                    "finished_at": "2026-08-18T19:39:00+00:00",
                }
            ),
            enabled=True,
        )

        health = planner.health()

        self.assertEqual("provider_error", health["status"])
        self.assertFalse(health["provider_verified"])
        self.assertIn("valid API key", health["last_provider_error"])


if __name__ == "__main__":
    unittest.main()
