from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.agents.repo_analyzer_agent import RepositoryAnalyzerAgent
from app.tools.git_tools import clone_repository


class CICDAgent:
    """
    CloudMind CI/CD generator.

    Generates GitHub Actions workflows for Docker image build/publish.

    Phase 20J fix:
    - Always lowercases GHCR image owner/repository.
    - PR validation builds the Docker image without pushing.
    - Main branch builds and pushes latest + sha tags.
    - Adds a simple smoke test for PR validation using the detected port and health path.
    - Keeps generated files repository-relative for Remote GitOps publishing.
    """

    def __init__(self) -> None:
        self.repo_analyzer = RepositoryAnalyzerAgent()

    def generate_for_repo(
        self,
        repo_url: str,
        branch: str | None = None,
        base_branch: str = "main",
        overwrite: bool = True,
        image_owner: str | None = None,
        workflow_name: str = "docker-build.yml",
        **_: Any,
    ) -> dict[str, Any]:
        if not repo_url:
            return {
                "status": "failed",
                "message": "repo_url is required.",
                "generated_files": [],
            }

        analysis = self.repo_analyzer.analyze(
            repo_url=repo_url,
            branch=branch,
        )

        repo_path = self._repo_path_from_analysis(
            analysis=analysis,
            repo_url=repo_url,
            branch=branch,
        )

        return self.generate_from_analysis(
            analysis=analysis,
            repo_path=str(repo_path),
            base_branch=base_branch,
            overwrite=overwrite,
            image_owner=image_owner,
            workflow_name=workflow_name,
        )

    def generate_from_analysis(
        self,
        analysis: dict[str, Any],
        repo_path: str | None = None,
        base_branch: str = "main",
        overwrite: bool = True,
        image_owner: str | None = None,
        workflow_name: str = "docker-build.yml",
        **_: Any,
    ) -> dict[str, Any]:
        if not analysis:
            return {
                "status": "failed",
                "message": "Repository analysis is required.",
                "generated_files": [],
            }

        repo_url = analysis.get("repo_url") or analysis.get("remote_url") or ""
        owner, repo_name = self._owner_and_repo_from_analysis(
            analysis=analysis,
            repo_url=repo_url,
        )

        if image_owner:
            owner = image_owner

        owner = self._sanitize_oci_segment(owner)
        repo_slug = self._sanitize_oci_segment(repo_name)

        if not owner or not repo_slug:
            return {
                "status": "failed",
                "message": "Could not derive a valid lowercase GHCR image name.",
                "generated_files": [],
                "analysis": analysis,
            }

        primary_component = self._primary_component(analysis)
        component_path = self._component_path(primary_component)
        docker_context = self._docker_context(component_path)
        dockerfile_path = self._dockerfile_path(component_path)

        app_port = self._detected_port(primary_component, analysis)
        health_path = self._detected_health_path(primary_component, analysis)

        image_name = self._image_name(
            owner=owner,
            repo_slug=repo_slug,
            analysis=analysis,
            primary_component=primary_component,
        )

        repo_root = Path(repo_path or analysis.get("local_path") or analysis.get("repo_path") or ".")
        workflow_relative_path = Path(".github") / "workflows" / workflow_name
        workflow_path = repo_root / workflow_relative_path

        if workflow_path.exists() and not overwrite:
            return {
                "status": "skipped",
                "message": "CI/CD workflow already exists and overwrite is disabled.",
                "generated_files": [
                    {
                        "path": str(workflow_path),
                        "relative_path": workflow_relative_path.as_posix(),
                        "type": "github_actions_workflow",
                    }
                ],
                "image": image_name,
                "analysis": analysis,
            }

        workflow_path.parent.mkdir(parents=True, exist_ok=True)

        workflow_content = self._build_workflow_yaml(
            image_name=image_name,
            docker_context=docker_context,
            dockerfile_path=dockerfile_path,
            app_port=app_port,
            health_path=health_path,
            base_branch=base_branch,
        )

        workflow_path.write_text(workflow_content, encoding="utf-8")

        return {
            "status": "generated",
            "message": "CI/CD workflow generated successfully with lowercase GHCR image naming.",
            "repo_url": repo_url,
            "repo_name": repo_name,
            "image": image_name,
            "image_owner": owner,
            "docker_context": docker_context,
            "dockerfile_path": dockerfile_path,
            "app_port": app_port,
            "health_path": health_path,
            "generated_files": [
                {
                    "path": str(workflow_path),
                    "relative_path": workflow_relative_path.as_posix(),
                    "type": "github_actions_workflow",
                    "component": primary_component.get("name") if isinstance(primary_component, dict) else "app",
                }
            ],
            "workflow_path": str(workflow_path),
            "relative_path": workflow_relative_path.as_posix(),
            "analysis": analysis,
            "next_steps": [
                "Publish this generated workflow through a GitHub pull request.",
                "Open the PR and confirm the PR validation build is green.",
                "Merge the PR to main.",
                "Confirm the main workflow publishes the GHCR image with latest and sha tags.",
            ],
        }

    def _build_workflow_yaml(
        self,
        image_name: str,
        docker_context: str,
        dockerfile_path: str,
        app_port: int,
        health_path: str,
        base_branch: str,
    ) -> str:
        return f"""name: Build and Publish Docker Images

on:
  push:
    branches:
      - {base_branch}
  pull_request:
    branches:
      - {base_branch}
  workflow_dispatch:

permissions:
  contents: read
  packages: write

env:
  IMAGE_NAME: {image_name}
  APP_PORT: "{app_port}"
  HEALTH_PATH: "{health_path}"

jobs:
  build-app-image:
    name: Build app image
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

      - name: Build Docker image for PR validation
        if: github.event_name == 'pull_request'
        uses: docker/build-push-action@v6
        with:
          context: {docker_context}
          file: {dockerfile_path}
          push: false
          load: true
          tags: ${{{{ env.IMAGE_NAME }}}}:pr-check

      - name: Smoke test PR image
        if: github.event_name == 'pull_request'
        shell: bash
        run: |
          set -e

          docker rm -f cloudmind-pr-smoke >/dev/null 2>&1 || true

          docker run -d \\
            --name cloudmind-pr-smoke \\
            -p "${{{{ env.APP_PORT }}}}:${{{{ env.APP_PORT }}}}" \\
            "${{{{ env.IMAGE_NAME }}}}:pr-check"

          cleanup() {{
            docker logs cloudmind-pr-smoke || true
            docker rm -f cloudmind-pr-smoke >/dev/null 2>&1 || true
          }}

          trap cleanup EXIT

          for attempt in {{1..20}}; do
            if curl -fsS "http://localhost:${{{{ env.APP_PORT }}}}${{{{ env.HEALTH_PATH }}}}"; then
              echo "Smoke test passed."
              exit 0
            fi

            echo "Waiting for app to become healthy... attempt $attempt"
            sleep 3
          done

          echo "Smoke test failed."
          exit 1

      - name: Build and push Docker image
        if: github.event_name != 'pull_request'
        uses: docker/build-push-action@v6
        with:
          context: {docker_context}
          file: {dockerfile_path}
          push: true
          tags: |
            ${{{{ env.IMAGE_NAME }}}}:latest
            ${{{{ env.IMAGE_NAME }}}}:sha-${{{{ github.sha }}}}
"""

    def _repo_path_from_analysis(
        self,
        analysis: dict[str, Any],
        repo_url: str,
        branch: str | None,
    ) -> Path:
        possible_paths = [
            analysis.get("local_path"),
            analysis.get("repo_path"),
            analysis.get("path"),
            analysis.get("repository_path"),
        ]

        for possible_path in possible_paths:
            if possible_path and Path(str(possible_path)).exists():
                return Path(str(possible_path))

        return Path(clone_repository(repo_url=repo_url, branch=branch))

    def _owner_and_repo_from_analysis(
        self,
        analysis: dict[str, Any],
        repo_url: str,
    ) -> tuple[str, str]:
        owner = (
            analysis.get("repo_owner")
            or analysis.get("owner")
            or analysis.get("github_owner")
        )

        repo_name = (
            analysis.get("repo_name")
            or analysis.get("name")
            or analysis.get("repository_name")
        )

        if owner and repo_name:
            return str(owner), str(repo_name).replace(".git", "")

        if repo_url:
            parsed = urlparse(repo_url)
            parts = [part for part in parsed.path.split("/") if part]

            if len(parts) >= 2:
                parsed_owner = parts[0]
                parsed_repo = parts[1].replace(".git", "")
                return parsed_owner, parsed_repo

        return "owner", str(repo_name or "app").replace(".git", "")

    def _primary_component(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        primary_component = analysis.get("primary_component")

        if isinstance(primary_component, dict):
            return primary_component

        components = analysis.get("components")

        if isinstance(components, list):
            for component in components:
                if isinstance(component, dict):
                    return component

        return {
            "name": "app",
            "component_path": ".",
            "port": analysis.get("port") or 8000,
            "health_path": analysis.get("health_path") or "/health",
        }

    def _component_path(
        self,
        component: dict[str, Any],
    ) -> str:
        component_path = component.get("component_path")

        if component_path:
            return self._normalize_repo_relative_path(str(component_path))

        package_file = component.get("package_file")

        if package_file:
            parent = Path(str(package_file)).parent.as_posix()
            return "." if parent in ["", "."] else parent

        dockerfile = component.get("dockerfile")

        if dockerfile:
            parent = Path(str(dockerfile)).parent.as_posix()
            return "." if parent in ["", "."] else parent

        return "."

    def _docker_context(
        self,
        component_path: str,
    ) -> str:
        normalized = self._normalize_repo_relative_path(component_path)

        if normalized in ["", "."]:
            return "."

        return normalized

    def _dockerfile_path(
        self,
        component_path: str,
    ) -> str:
        normalized = self._normalize_repo_relative_path(component_path)

        if normalized in ["", "."]:
            return "./Dockerfile"

        return f"./{normalized}/Dockerfile"

    def _detected_port(
        self,
        component: dict[str, Any],
        analysis: dict[str, Any],
    ) -> int:
        candidates = [
            component.get("port"),
            analysis.get("port"),
            8000,
        ]

        for candidate in candidates:
            try:
                port = int(candidate)

                if 1 <= port <= 65535:
                    return port
            except (TypeError, ValueError):
                continue

        return 8000

    def _detected_health_path(
        self,
        component: dict[str, Any],
        analysis: dict[str, Any],
    ) -> str:
        candidates = [
            component.get("health_path"),
            analysis.get("health_path"),
            "/health",
        ]

        for candidate in candidates:
            if not candidate:
                continue

            health_path = str(candidate).strip()

            if not health_path:
                continue

            if not health_path.startswith("/"):
                health_path = "/" + health_path

            return health_path

        return "/health"

    def _image_name(
        self,
        owner: str,
        repo_slug: str,
        analysis: dict[str, Any],
        primary_component: dict[str, Any],
    ) -> str:
        components = analysis.get("components")

        deployable_components = []

        if isinstance(components, list):
            for component in components:
                if not isinstance(component, dict):
                    continue

                component_type = str(component.get("type", "")).lower()

                if component_type in ["backend", "frontend", "fullstack", "app", "service", "api"]:
                    deployable_components.append(component)

        if len(deployable_components) <= 1:
            image_repo = repo_slug
        else:
            component_name = self._sanitize_oci_segment(
                str(primary_component.get("name") or primary_component.get("type") or "app")
            )
            image_repo = f"{repo_slug}-{component_name}"

        image_repo = self._sanitize_oci_segment(image_repo)

        return f"ghcr.io/{owner}/{image_repo}"

    def _sanitize_oci_segment(
        self,
        value: str,
    ) -> str:
        sanitized = str(value or "").strip().lower()
        sanitized = sanitized.replace(".git", "")
        sanitized = re.sub(r"[^a-z0-9._-]+", "-", sanitized)
        sanitized = re.sub(r"-{2,}", "-", sanitized)
        sanitized = re.sub(r"\.{2,}", ".", sanitized)
        sanitized = sanitized.strip("-._")

        return sanitized

    def _normalize_repo_relative_path(
        self,
        value: str,
    ) -> str:
        path = str(value or ".").strip().replace("\\", "/")
        path = re.sub(r"/+", "/", path)
        path = path.strip("/")

        if path in ["", "."]:
            return "."

        safe_parts = []

        for part in path.split("/"):
            if part in ["", "."]:
                continue

            if part == "..":
                continue

            safe_parts.append(part)

        return "/".join(safe_parts) if safe_parts else "."