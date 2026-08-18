from __future__ import annotations

import unittest
from typing import Any

from app.agents.conversation_brain_agent import ConversationBrainAgent
from app.agents.llm_conversation_agent import LLMConversationAgent
from app.agents.llm_provider_agent import StructuredLLMResult
from app.schemas.llm_conversation import LLMConversationOutput


class StubContextAgent:
    def build_context(self, **_: Any) -> dict[str, Any]:
        return {
            "project": {
                "id": "project-id",
                "name": "Demo Project",
                "repo_url": "https://github.com/example/demo.git",
            },
            "workflow": {
                "status": "workflow_ready",
                "summary": {"completed": 10, "required": 0},
            },
        }

    def sanitize(self, value: Any, key: str | None = None) -> Any:
        return value


class StubAuditAgent:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, **kwargs: Any) -> dict[str, Any]:
        self.records.append(kwargs)
        return {"id": "conversation-audit-id"}


class MockConversationProvider:
    provider_name = "gemini"
    model = "gemini-3.6-flash"
    available = True

    def __init__(self, response: LLMConversationOutput) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def generate_structured(self, **kwargs: Any) -> StructuredLLMResult:
        self.calls.append(kwargs)
        return StructuredLLMResult(
            parsed=self.response,
            provider=self.provider_name,
            model=self.model,
            response_id="gemini-chat-id",
            usage={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
        )


class FailingConversationProvider(MockConversationProvider):
    def generate_structured(self, **kwargs: Any) -> StructuredLLMResult:
        raise RuntimeError("Please pass a valid API key")


class LLMConversationTests(unittest.TestCase):
    def _response(self) -> LLMConversationOutput:
        return LLMConversationOutput(
            response_type="greeting",
            intent_summary="The user greeted CloudMind.",
            message="Hi! I'm CloudMind, your AI multi-agent DevOps assistant.",
            suggested_prompts=["What should I do next?"],
        )

    def test_general_chat_uses_the_llm_conversation_agent(self) -> None:
        provider = MockConversationProvider(self._response())
        audit = StubAuditAgent()
        agent = LLMConversationAgent(
            provider=provider,
            context_agent=StubContextAgent(),
            audit_agent=audit,
            enabled=True,
        )

        result = agent.respond(
            message="HII",
            session_id="session-id",
            project_id="project-id",
            repo_url="https://github.com/example/demo.git",
            project_context={},
            conversation_state={},
            recent_messages=[{"role": "user", "content": "HII"}],
        )

        self.assertEqual("response_ready", result["status"])
        self.assertEqual("gemini", result["provider"])
        self.assertFalse(result["fallback_used"])
        self.assertIn("multi-agent", result["message"])
        self.assertFalse(result["safety"]["conversation_agent_executes_tools"])
        self.assertEqual("conversation-audit-id", result["audit_id"])
        self.assertIs(
            provider.calls[0]["response_model"],
            LLMConversationOutput,
        )
        self.assertEqual(1, len(audit.records))

        prompt = provider.calls[0]["user_prompt"]
        self.assertNotIn("workflow_ready", prompt)
        self.assertTrue(prompt.endswith("CURRENT USER MESSAGE:\nHII"))

    def test_project_question_includes_relevant_project_context(self) -> None:
        provider = MockConversationProvider(self._response())
        agent = LLMConversationAgent(
            provider=provider,
            context_agent=StubContextAgent(),
            audit_agent=StubAuditAgent(),
            enabled=True,
        )

        agent.respond(
            message="What is the project deployment status?",
            session_id="session-id",
            project_id="project-id",
            repo_url="https://github.com/example/demo.git",
            project_context={},
            conversation_state={},
            recent_messages=[
                {"role": "assistant", "content": "An earlier answer."},
                {"role": "user", "content": "What is the project deployment status?"},
            ],
        )

        prompt = provider.calls[0]["user_prompt"]
        self.assertIn("workflow_ready", prompt)
        self.assertIn("An earlier answer.", prompt)
        self.assertEqual(1, prompt.count("What is the project deployment status?"))

    def test_general_chat_has_a_safe_fallback(self) -> None:
        agent = LLMConversationAgent(
            provider=None,
            context_agent=StubContextAgent(),
            audit_agent=StubAuditAgent(),
            enabled=False,
        )

        result = agent.respond(
            message="HII",
            session_id="session-id",
            project_id="project-id",
            repo_url="https://github.com/example/demo.git",
            project_context={},
            conversation_state={},
        )

        self.assertTrue(result["fallback_used"])
        self.assertEqual("llm_disabled", result["fallback_reason"])
        self.assertIn("Demo Project", result["message"])

    def test_provider_error_is_not_presented_as_an_ai_answer(self) -> None:
        agent = LLMConversationAgent(
            provider=FailingConversationProvider(self._response()),
            context_agent=StubContextAgent(),
            audit_agent=StubAuditAgent(),
            enabled=True,
        )

        result = agent.respond(
            message="Explain the project",
            session_id="session-id",
            project_id="project-id",
            repo_url="https://github.com/example/demo.git",
            project_context={},
            conversation_state={},
        )

        self.assertEqual("provider_error", result["status"])
        self.assertTrue(result["fallback_used"])
        self.assertFalse(result["provider_verified"])
        self.assertIn("rejected the configured API key", result["message"])
        self.assertNotIn("workflow status", result["message"])

    def test_general_chat_routes_to_conversation_agent(self) -> None:
        brain = ConversationBrainAgent.__new__(ConversationBrainAgent)
        action_plan = brain._build_action_plan(
            intent="general_chat",
            state={},
            approval_confirmed=False,
        )

        self.assertTrue(action_plan["can_execute"])
        self.assertEqual("llm_conversation", action_plan["tool_name"])
        self.assertFalse(action_plan["requires_approval"])

    def test_conversation_message_is_rendered_directly(self) -> None:
        brain = ConversationBrainAgent.__new__(ConversationBrainAgent)
        message = brain._build_assistant_message(
            intent="general_chat",
            action_plan={
                "can_execute": True,
                "tool_name": "llm_conversation",
                "requires_approval": False,
                "missing_fields": [],
            },
            tool_result={
                "status": "response_ready",
                "response": {"message": "A real Gemini response."},
            },
            state={},
        )

        self.assertEqual("A real Gemini response.", message)


if __name__ == "__main__":
    unittest.main()
