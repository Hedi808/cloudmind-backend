from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from app.agents.tool_registry_agent import ToolRegistryAgent


class StubCICDAgent:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.arguments: dict[str, Any] | None = None

    def generate_for_repo(self, **arguments: Any) -> dict[str, Any]:
        self.arguments = arguments
        return self.result


class StubGitAgent:
    def __init__(
        self,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or {
            "status": "published",
            "branch": "cloudmind/cicd-workflow-test",
            "pull_request": {
                "number": 42,
                "html_url": "https://github.com/example/demo/pull/42",
            },
        }
        self.error = error
        self.arguments: dict[str, Any] | None = None

    def publish_generated_file_contents(self, **arguments: Any) -> dict[str, Any]:
        self.arguments = arguments

        if self.error:
            raise self.error

        return self.result


class ToolRegistryCICDTests(unittest.TestCase):
    def _registry(
        self,
        cicd_result: dict[str, Any],
        git_agent: StubGitAgent | None = None,
    ) -> tuple[ToolRegistryAgent, StubCICDAgent, StubGitAgent]:
        registry = ToolRegistryAgent.__new__(ToolRegistryAgent)
        cicd_agent = StubCICDAgent(cicd_result)
        resolved_git_agent = git_agent or StubGitAgent()
        registry.cicd_agent = cicd_agent
        registry.git_agent = resolved_git_agent
        return registry, cicd_agent, resolved_git_agent

    def test_source_repo_path_is_derived_from_relative_generated_path(self) -> None:
        registry = ToolRegistryAgent.__new__(ToolRegistryAgent)

        repo_path = registry._generated_source_repo_path(
            {
                "generated_files": [
                    {
                        "path": (
                            "workspace/repos/demo-generated/"
                            ".github/workflows/docker-build.yml"
                        ),
                        "relative_path": ".github/workflows/docker-build.yml",
                    }
                ],
                "analysis": {
                    "metadata": {"local_path": "workspace/repos/different-analysis-clone"}
                },
            }
        )

        self.assertEqual(Path("workspace/repos/demo-generated"), repo_path)

    def test_generated_status_is_published_and_arguments_are_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_path = Path(temporary_directory)
            workflow_path = repo_path / ".github" / "workflows" / "docker-build.yml"
            workflow_path.parent.mkdir(parents=True)
            workflow_path.write_text("name: test\n", encoding="utf-8")

            registry, cicd_agent, git_agent = self._registry(
                {
                    "status": "generated",
                    "message": "Workflow generated.",
                    "generated_files": [
                        {
                            "path": str(workflow_path),
                            "relative_path": ".github/workflows/docker-build.yml",
                            "type": "github_actions_workflow",
                        }
                    ],
                    "analysis": {
                        "metadata": {
                            "local_path": str(repo_path / "different-analysis-clone")
                        }
                    },
                }
            )

            result = registry._generate_cicd_and_publish(
                {
                    "repo_url": "https://github.com/ExampleOwner/Demo.git",
                    "base_branch": "develop",
                    "image_owner": "ExplicitOwner",
                    "overwrite": True,
                }
            )

            self.assertEqual("published", result["status"])
            self.assertEqual("develop", cicd_agent.arguments["base_branch"])
            self.assertEqual("ExplicitOwner", cicd_agent.arguments["image_owner"])
            self.assertEqual(str(repo_path), git_agent.arguments["source_repo_path"])
            self.assertEqual("develop", git_agent.arguments["base_branch"])
            self.assertEqual(
                ".github/workflows/docker-build.yml",
                git_agent.arguments["generated_files"][0]["relative_path"],
            )

    def test_generation_failure_exposes_generator_error(self) -> None:
        registry, _, git_agent = self._registry(
            {
                "status": "failed",
                "message": "Repository analysis did not find a deployable component.",
                "generated_files": [],
            }
        )

        result = registry._generate_cicd_and_publish(
            {"repo_url": "https://github.com/example/demo.git"}
        )

        self.assertEqual("failed", result["status"])
        self.assertEqual("generation", result["failure_stage"])
        self.assertIn("deployable component", result["error"])
        self.assertIsNone(git_agent.arguments)

    def test_publish_exception_preserves_generated_file_details(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_path = Path(temporary_directory)
            workflow_path = repo_path / ".github" / "workflows" / "docker-build.yml"
            workflow_path.parent.mkdir(parents=True)
            workflow_path.write_text("name: test\n", encoding="utf-8")

            registry, _, _ = self._registry(
                {
                    "status": "generated",
                    "generated_files": [
                        {
                            "path": str(workflow_path),
                            "relative_path": ".github/workflows/docker-build.yml",
                        }
                    ],
                },
                git_agent=StubGitAgent(
                    error=RuntimeError("GitHub token requires Workflows write permission.")
                ),
            )

            result = registry._generate_cicd_and_publish(
                {"repo_url": "https://github.com/example/demo.git"}
            )

            self.assertEqual("failed", result["status"])
            self.assertEqual("github_publish", result["failure_stage"])
            self.assertIn("Workflows write permission", result["error"])
            self.assertEqual(
                [".github/workflows/docker-build.yml"],
                result["generated_file_paths"],
            )

    def test_publish_failure_result_exposes_github_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_path = Path(temporary_directory)
            workflow_path = repo_path / ".github" / "workflows" / "docker-build.yml"
            workflow_path.parent.mkdir(parents=True)
            workflow_path.write_text("name: test\n", encoding="utf-8")

            registry, _, _ = self._registry(
                {
                    "status": "generated",
                    "generated_files": [
                        {
                            "path": str(workflow_path),
                            "relative_path": ".github/workflows/docker-build.yml",
                        }
                    ],
                },
                git_agent=StubGitAgent(
                    result={
                        "status": "failed",
                        "message": "GitHub rejected workflow modification.",
                        "error": "Resource not accessible by personal access token.",
                    }
                ),
            )

            result = registry._generate_cicd_and_publish(
                {"repo_url": "https://github.com/example/demo.git"}
            )

            self.assertEqual("failed", result["status"])
            self.assertEqual("github_publish", result["failure_stage"])
            self.assertIn("personal access token", result["error"])
            self.assertEqual("failed", result["git"]["status"])


if __name__ == "__main__":
    unittest.main()
