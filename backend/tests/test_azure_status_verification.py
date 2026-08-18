from __future__ import annotations

import unittest
from typing import Any

from app.agents.conversation_brain_agent import ConversationBrainAgent
from app.agents.incident_response_agent import IncidentResponseAgent
from app.agents.observability_agent import ObservabilityAgent


class StubObservabilityAgent(ObservabilityAgent):
    def __init__(
        self,
        command_result: dict[str, Any],
        health_result: dict[str, Any] | None = None,
    ) -> None:
        self.command_result = command_result
        self.health_result = health_result

    def _get_azure_account(self) -> dict[str, Any]:
        return {
            "success": True,
            "subscription_id": "subscription-id",
            "account": {"name": "test"},
        }

    def _get_container_app_with_rest(self, **_: Any) -> dict[str, Any]:
        return self.command_result

    def check_http_health(self, **_: Any) -> dict[str, Any]:
        return self.health_result or {
            "status": "unhealthy",
            "healthy": False,
            "status_code": None,
        }


class AzureStatusVerificationTests(unittest.TestCase):
    def test_expired_mfa_is_not_reported_as_missing_app(self) -> None:
        agent = StubObservabilityAgent(
            command_result={
                "success": False,
                "exit_code": 1,
                "stdout": "",
                "stderr": (
                    "invalid_grant AADSTS50078: Presented multi-factor authentication "
                    "has expired. Run az login."
                ),
            },
            health_result={
                "status": "healthy",
                "healthy": True,
                "status_code": 200,
                "url": "https://app.example/api/status",
            },
        )

        result = agent.check_azure_container_app_status(
            resource_group="rg-demo",
            app_name="app-demo",
            app_url="https://app.example",
            health_path="/api/status",
        )

        self.assertEqual("authentication_required", result["status"])
        self.assertFalse(result["azure_verified"])
        self.assertTrue(result["endpoint_healthy"])
        self.assertFalse(result["healthy"])
        self.assertNotEqual("not_found", result["status"])

    def test_real_resource_not_found_remains_not_found(self) -> None:
        agent = StubObservabilityAgent(
            command_result={
                "success": False,
                "exit_code": 1,
                "stdout": "",
                "stderr": "(ResourceNotFound) The Resource could not be found.",
            }
        )

        result = agent.check_azure_container_app_status(
            resource_group="rg-demo",
            app_name="missing-app",
        )

        self.assertEqual("not_found", result["status"])
        self.assertFalse(result["azure_verified"])
        self.assertFalse(result["endpoint_healthy"])

    def test_authentication_gap_does_not_create_false_incident_signal(self) -> None:
        status_result = {
            "status": "authentication_required",
            "message": "Azure CLI authentication expired.",
            "healthy": False,
            "endpoint_healthy": True,
            "azure_verified": False,
            "health": {
                "healthy": True,
                "status_code": 200,
                "url": "https://app.example/api/status",
            },
            "azure": {},
        }

        findings = IncidentResponseAgent()._analyze_status(status_result)

        self.assertEqual(0, findings["severity_score"])
        self.assertTrue(
            any("public application health endpoint is healthy" in item.lower() for item in findings["findings"])
        )
        self.assertFalse(
            any("no latest ready revision" in item.lower() for item in findings["findings"])
        )

    def test_chat_message_separates_endpoint_health_from_azure_verification(self) -> None:
        brain = ConversationBrainAgent.__new__(ConversationBrainAgent)

        message = brain._azure_status_message(
            {
                "status": "authentication_required",
                "message": "Azure CLI authentication expired.",
                "healthy": False,
                "endpoint_healthy": True,
                "azure_verified": False,
                "app_url": "https://app.example",
                "health": {"status_code": 200},
                "health_path": "/api/status",
                "health_path_source": "explicit_argument",
            }
        )

        self.assertIn("public application endpoint is healthy", message.lower())
        self.assertIn("authentication_required", message)
        self.assertNotIn("container app is not healthy", message.lower())


if __name__ == "__main__":
    unittest.main()
