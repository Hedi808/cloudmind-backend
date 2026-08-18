from __future__ import annotations

import unittest
from typing import Any

from app.agents.azure_runtime_deployment_agent import AzureRuntimeDeploymentAgent


class AzureRuntimeNamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = AzureRuntimeDeploymentAgent()

    def test_numeric_repo_app_name_gets_required_letter_prefix(self) -> None:
        self.assertEqual(
            "app-3s-test-demo",
            self.agent._sanitize_container_app_name("3s-test-demo-app"),
        )

    def test_numeric_multicomponent_name_keeps_component_suffix(self) -> None:
        self.assertEqual(
            "app-3s-test-demo-backend",
            self.agent._sanitize_container_app_name("3s-test-demo-backend"),
        )

    def test_existing_valid_app_name_is_unchanged(self) -> None:
        self.assertEqual(
            "via-vai-app",
            self.agent._sanitize_container_app_name("via-vai-app"),
        )

    def test_container_app_name_obeys_all_azure_constraints(self) -> None:
        sanitized = self.agent._sanitize_container_app_name(
            "99__Very LONG..Repository!!Name---With---Extra---Characters-app"
        )

        self.assertLessEqual(len(sanitized), 32)
        self.assertTrue(sanitized[0].isalpha())
        self.assertTrue(sanitized[-1].isalnum())
        self.assertNotIn("--", sanitized)
        self.assertRegex(sanitized, r"^[a-z][a-z0-9-]*[a-z0-9]$")

    def test_default_derivation_uses_valid_name_for_3s_repository(self) -> None:
        def fake_image_resolution(**_: Any) -> dict[str, Any]:
            return {
                "selected_image": "ghcr.io/hedi808/3s-test-demo:latest",
                "source": "test",
                "candidates": ["ghcr.io/hedi808/3s-test-demo:latest"],
                "checks": [],
                "definitive_missing": False,
            }

        self.agent._resolve_container_image = fake_image_resolution

        analysis = {
            "repo_name": "3s-test-demo",
            "health_path": "/api/status",
            "primary_component": {
                "name": "app",
                "type": "fullstack",
                "port": 3000,
                "health_path": "/api/status",
            },
            "components": [],
        }

        derived = self.agent._derive_defaults_from_analysis(
            repo_url="https://github.com/Hedi808/3s-test-demo.git",
            analysis=analysis,
            image=None,
            resource_group=None,
            app_name=None,
            environment_name=None,
            target_port=None,
            health_path=None,
        )

        self.assertEqual("app-3s-test-demo", derived["app_name"])
        self.assertEqual(3000, derived["target_port"])
        self.assertEqual("/api/status", derived["health_path"])


if __name__ == "__main__":
    unittest.main()
