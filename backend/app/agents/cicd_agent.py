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

    Phase 20D improvements:
    - uses primary_component/component_path from smart analyzer
    - avoids workspace/repos path assumptions
    - supports root fullstack Node apps
    - generates repository-relative Docker contexts
    - includes relative_path for Remote GitOps publishing
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
        components = self._select_deployable_components(analysis)

        if not components:
            return {
                "status": "failed",
                "message": "No deployable components were detected. CI/CD workflow was not generated.",
                "analysis": analysis,
                "generated_files": [],
                "skipped_files": [],
                "existing_files": [],
                "recommendations": [
                    "Add standard dependency files such as package.json, requirements.txt, or pyproject.toml.",
                    "Make sure repository analysis returns at least one deployable component with component_path or package_file.",
                    "Generate Docker files before generating CI/CD.",
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
                        "relative_path": self._relative_path(repo_path, workflow_path),
                        "reason": "Workflow already exists. Use overwrite=true to replace it.",
                    }
                ],
                "existing_files": [
                    {
                        "path": str(workflow_path),
                        "relative_path": self._relative_path(repo_path, workflow_path),
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
                    "relative_path": self._relative_path(repo_path, workflow_path),
                    "type": "github_actions_workflow",
                }
            ],
            "skipped_files": [],
            "existing_files": [],
            "analysis": analysis,
            "next_step": "After reviewing the workflow, GitAgent can publish it to a CloudMind branch and open a pull request through Remote GitOps Mode.",
        }

    def _select_deployable_components(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        components = analysis.get("components", []) or []
        primary_component = analysis.get("primary_component")

        if primary_component:
            primary_type = primary_component.get("type")
            primary_path = str(primary_component.get("component_path") or ".").strip("/")

            if primary_type in {"fullstack", "backend", "frontend"}:
                if primary_type == "fullstack":
                    return [primary_component]

                if primary_path in {"", "."}:
                    return [primary_component]

        deployable: list[dict[str, Any]] = []
        seen: set[str] = set()

        for component in components:
            component_type = component.get("type")

            if component_type not in {"fullstack", "backend", "frontend"}:
                continue

            if self._is_nested_static_component(component=component, components=components):
                continue

            key = self._component_identity(component)

            if key in seen:
                continue

            seen.add(key)
            deployable.append(component)

        return sorted(
            deployable,
            key=lambda component: (
                self._component_priority(component),
                int(component.get("confidence") or 0),
            ),
            reverse=True,
        )

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
            component_name = self._normalize_name(
                component.get("name") or component.get("type") or "app"
            )
            docker_context = self._component_context(component)
            dockerfile_path = self._dockerfile_path(docker_context)
            image_name = self._image_name(
                image_registry=image_registry,
                image_owner=image_owner,
                repo_name=repo_name,
                component_name=component_name,
                components=components,
            )

            jobs.append(
                self._generate_component_job(
                    component_name=component_name,
                    docker_context=docker_context,
                    dockerfile_path=dockerfile_path,
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
        dockerfile_path: str,
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
          file: {dockerfile_path}
          push: false
          tags: {image_name}:pr-check

      - name: Build and push Docker image
        if: github.event_name != 'pull_request'
        uses: docker/build-push-action@v6
        with:
          context: {docker_context}
          file: {dockerfile_path}
          push: true
          tags: ${{{{ steps.meta.outputs.tags }}}}
          labels: ${{{{ steps.meta.outputs.labels }}}}
"""

    def _component_context(self, component: dict[str, Any]) -> str:
        """
        Returns Docker build context as a GitHub Actions repository-relative path.

        Examples:
        - root app: "."
        - backend/package.json: "./backend"
        - services/api/package.json: "./services/api"
        """
        component_path = component.get("component_path")

        if component_path:
            normalized = self._normalize_repo_path(str(component_path))

            if normalized in {"", "."}:
                return "."

            return f"./{normalized}"

        package_file = component.get("package_file")

        if package_file:
            package_path = self._normalize_repo_path(str(package_file))
            parent = str(Path(package_path).parent).replace("\\", "/")

            if parent in {"", "."}:
                return "."

            return f"./{parent}"

        return "."

    def _dockerfile_path(self, docker_context: str) -> str:
        if docker_context in {"", "."}:
            return "./Dockerfile"

        return f"{docker_context.rstrip('/')}/Dockerfile"

    def _image_name(
        self,
        image_registry: str,
        image_owner: str,
        repo_name: str,
        component_name: str,
        components: list[dict[str, Any]],
    ) -> str:
        clean_repo_name = self._normalize_name(repo_name)

        if len(components) == 1:
            return f"{image_registry}/{image_owner}/{clean_repo_name}"

        return f"{image_registry}/{image_owner}/{clean_repo_name}-{component_name}"

    def _is_nested_static_component(
        self,
        component: dict[str, Any],
        components: list[dict[str, Any]],
    ) -> bool:
        component_type = component.get("type")
        framework = (component.get("framework") or "").lower()

        if component_type != "frontend":
            return False

        if "static" not in framework:
            return False

        if component.get("package_file"):
            return False

        component_path = str(component.get("component_path") or ".").strip("/")

        if component_path in {"", "."}:
            return False

        for parent in components:
            if parent is component:
                continue

            if not parent.get("package_file"):
                continue

            parent_path = str(parent.get("component_path") or ".").strip("/")

            if parent_path in {"", "."}:
                return True

            if component_path.startswith(parent_path + "/"):
                return True

        return False

    def _component_priority(self, component: dict[str, Any]) -> int:
        component_type = component.get("type")

        if component_type == "fullstack":
            return 4

        if component_type == "backend":
            return 3

        if component_type == "frontend":
            return 2

        return 1

    def _component_identity(self, component: dict[str, Any]) -> str:
        return "|".join(
            [
                str(component.get("name") or ""),
                str(component.get("type") or ""),
                str(component.get("component_path") or ""),
                str(component.get("package_file") or ""),
            ]
        )

    def _normalize_repo_path(self, path: str) -> str:
        normalized = path.replace("\\", "/").strip()

        while normalized.startswith("./"):
            normalized = normalized[2:]

        normalized = normalized.strip("/")

        if not normalized:
            return "."

        if ".." in Path(normalized).parts:
            raise ValueError(f"Unsafe repository path: {path}")

        return normalized

    def _relative_path(self, repo_path: Path, path: Path) -> str:
        try:
            relative = path.relative_to(repo_path)
            return relative.as_posix() or "."
        except ValueError:
            return path.as_posix()

    def _normalize_name(self, name: str) -> str:
        name = name.lower().strip()
        name = name.replace("_", "-")
        normalized = "".join(char if char.isalnum() or char == "-" else "-" for char in name)
        normalized = normalized.strip("-")

        return normalized or "app"