from pathlib import Path
from typing import Any

from app.agents.repo_analyzer_agent import RepositoryAnalyzerAgent


class CICDAgent:
    """
    Phase 6 agent.

    Responsibilities:
    - analyze repository architecture
    - generate GitHub Actions workflow for Docker image build
    - push Docker image to GitHub Container Registry
    - keep workflow cloud-neutral for future Azure / OCI deployment
    """

    def __init__(self):
        self.repo_analyzer = RepositoryAnalyzerAgent()

    def generate_for_repo(
        self,
        repo_url: str,
        branch: str | None = None,
        overwrite: bool = False,
        image_registry: str = "ghcr.io",
        image_owner: str | None = None,
        image_tag: str = "latest",
        workflow_name: str = "docker-build.yml",
    ) -> dict[str, Any]:
        analysis = self.repo_analyzer.analyze(repo_url=repo_url, branch=branch)

        return self.generate_from_analysis(
            analysis=analysis,
            overwrite=overwrite,
            image_registry=image_registry,
            image_owner=image_owner,
            image_tag=image_tag,
            workflow_name=workflow_name,
        )

    def generate_from_analysis(
        self,
        analysis: dict[str, Any],
        overwrite: bool = False,
        image_registry: str = "ghcr.io",
        image_owner: str | None = None,
        image_tag: str = "latest",
        workflow_name: str = "docker-build.yml",
    ) -> dict[str, Any]:
        repo_path = Path(analysis["metadata"]["local_path"])
        components = analysis.get("components", [])

        if not components:
            return {
                "status": "failed",
                "message": "No deployable components were detected. CI/CD workflow was not generated.",
                "analysis": analysis,
                "generated_files": [],
                "skipped_files": [],
                "recommendations": [
                    "Add standard dependency files such as package.json, requirements.txt, or pyproject.toml.",
                    "Run repository analysis again before generating CI/CD workflow.",
                ],
            }

        image_owner = image_owner or "your-github-username"

        workflow_dir = repo_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)

        workflow_path = workflow_dir / workflow_name

        if workflow_path.exists() and not overwrite:
            return {
                "status": "success",
                "message": "CI/CD workflow already exists. Use overwrite=true to replace it.",
                "repo_url": analysis["repo_url"],
                "repo_name": analysis["repo_name"],
                "project_type": analysis["project_type"],
                "components": components,
                "generated_files": [],
                "skipped_files": [
                    {
                        "path": str(workflow_path),
                        "reason": "Workflow already exists. Use overwrite=true to replace it.",
                    }
                ],
                "existing_files": [
                    {
                        "path": str(workflow_path),
                        "type": "github_actions_workflow",
                    }
                ],
                "analysis": analysis,
            }

        workflow_content = self._generate_docker_build_workflow(
            repo_name=analysis["repo_name"],
            components=components,
            image_registry=image_registry,
            image_owner=image_owner,
            image_tag=image_tag,
        )

        workflow_path.write_text(workflow_content, encoding="utf-8")

        return {
            "status": "success",
            "message": "CICDAgent completed successfully.",
            "repo_url": analysis["repo_url"],
            "repo_name": analysis["repo_name"],
            "project_type": analysis["project_type"],
            "components": components,
            "generated_files": [
                {
                    "path": str(workflow_path),
                    "type": "github_actions_workflow",
                }
            ],
            "skipped_files": [],
            "existing_files": [],
            "analysis": analysis,
            "next_step": "After reviewing the workflow, GitAgent can push it to a CloudMind branch and open a pull request.",
        }

    def _generate_docker_build_workflow(
        self,
        repo_name: str,
        components: list[dict[str, Any]],
        image_registry: str,
        image_owner: str,
        image_tag: str,
    ) -> str:
        jobs = []

        for component in components:
            component_name = self._normalize_name(component.get("name") or component.get("type") or "app")
            docker_context = self._component_context(component)
            image_name = f"{image_registry}/{image_owner}/{repo_name}-{component_name}"

            jobs.append(
                self._generate_component_job(
                    component_name=component_name,
                    docker_context=docker_context,
                    image_name=image_name,
                    image_tag=image_tag,
                )
            )

        jobs_content = "\n\n".join(jobs)

        return f"""# Generated by CloudMind
name: Build and Publish Docker Images

on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main
  workflow_dispatch:

permissions:
  contents: read
  packages: write

jobs:
{jobs_content}
"""

    def _generate_component_job(
        self,
        component_name: str,
        docker_context: str,
        image_name: str,
        image_tag: str,
    ) -> str:
        job_name = f"build-{component_name}"

        return f"""  {job_name}:
    name: Build {component_name} image
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GitHub Container Registry
        if: github.event_name != 'pull_request'
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{{{ github.actor }}}}
          password: ${{{{ secrets.GITHUB_TOKEN }}}}

      - name: Extract Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: {image_name}
          tags: |
            type=raw,value={image_tag}
            type=sha,prefix=sha-

      - name: Build Docker image for PR validation
        if: github.event_name == 'pull_request'
        uses: docker/build-push-action@v6
        with:
          context: {docker_context}
          file: {docker_context}/Dockerfile
          push: false
          tags: {image_name}:pr-check

      - name: Build and push Docker image
        if: github.event_name != 'pull_request'
        uses: docker/build-push-action@v6
        with:
          context: {docker_context}
          file: {docker_context}/Dockerfile
          push: true
          tags: ${{{{ steps.meta.outputs.tags }}}}
          labels: ${{{{ steps.meta.outputs.labels }}}}"""

    def _component_context(self, component: dict[str, Any]) -> str:
        package_file = component.get("package_file")

        if not package_file:
            return "."

        component_dir = Path(package_file).parent

        # In generated analysis, package_file is inside workspace/repos/<repo-name>/...
        # For GitHub Actions, paths must be relative to the repository root.
        parts = component_dir.parts

        if "workspace" in parts and "repos" in parts:
            repos_index = parts.index("repos")
            relative_parts = parts[repos_index + 2 :]

            if not relative_parts:
                return "."

            return "./" + "/".join(relative_parts)

        return "."

    def _normalize_name(self, name: str) -> str:
        name = name.lower().strip()
        name = name.replace("_", "-")
        normalized = "".join(char if char.isalnum() or char == "-" else "-" for char in name)
        normalized = normalized.strip("-")

        return normalized or "app"