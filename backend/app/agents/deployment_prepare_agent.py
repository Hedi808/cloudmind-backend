from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.docker_agent import DockerAgent
from app.agents.git_agent import GitAgent
from app.agents.kubernetes_agent import KubernetesAgent
from app.agents.repo_analyzer_agent import RepositoryAnalyzerAgent


class DeploymentPrepareAgent:
    """
    Phase 5 preparation agent.

    It prepares deployment files in one workflow:
    - analyze repository once
    - generate Docker files
    - generate Kubernetes manifests
    - optionally publish everything to one GitHub pull request
    """

    def __init__(self):
        self.repo_analyzer = RepositoryAnalyzerAgent()
        self.docker_agent = DockerAgent()
        self.kubernetes_agent = KubernetesAgent()
        self.git_agent = GitAgent()

    def prepare(
        self,
        repo_url: str,
        branch: str | None = "main",
        base_branch: str = "main",
        overwrite: bool = False,
        publish: bool = True,
        namespace: str = "cloudmind-staging",
        image_registry: str = "ghcr.io",
        image_owner: str | None = None,
        image_tag: str = "latest",
        ingress_host: str | None = None,
        publish_branch_name: str | None = None,
    ) -> dict[str, Any]:
        analysis = self.repo_analyzer.analyze(
            repo_url=repo_url,
            branch=branch,
        )

        repo_path = Path(analysis["metadata"]["local_path"])

        docker_result = self.docker_agent.generate_from_analysis(
            analysis=analysis,
            overwrite=overwrite,
        )

        kubernetes_result = self.kubernetes_agent.generate_from_analysis(
            analysis=analysis,
            overwrite=overwrite,
            namespace=namespace,
            image_registry=image_registry,
            image_owner=image_owner,
            image_tag=image_tag,
            ingress_host=ingress_host,
        )

        generated_file_paths = self._extract_generated_file_paths(
            repo_path=repo_path,
            results=[docker_result, kubernetes_result],
        )

        if not publish:
            return {
                "status": "prepared_locally",
                "message": "Deployment files were generated locally but not published.",
                "repo_url": repo_url,
                "repo_name": analysis["repo_name"],
                "analysis": analysis,
                "docker": docker_result,
                "kubernetes": kubernetes_result,
                "git": None,
                "generated_file_paths": generated_file_paths,
                "next_step": "Set publish=true to create a GitHub branch and pull request.",
            }

        if not generated_file_paths:
            return {
                "status": "no_changes",
                "message": "No new deployment files were generated, so no pull request was created.",
                "repo_url": repo_url,
                "repo_name": analysis["repo_name"],
                "analysis": analysis,
                "docker": docker_result,
                "kubernetes": kubernetes_result,
                "git": None,
                "generated_file_paths": [],
            }

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

        branch_name = (
            publish_branch_name
            or f"cloudmind/prepare-deployment-{timestamp}"
        )

        git_result = self.git_agent.publish_deployment_changes(
            local_repo_path=str(repo_path),
            repo_url=repo_url,
            generated_files=generated_file_paths,
            base_branch=base_branch,
            branch_name=branch_name,
        )

        return {
            "status": "published",
            "message": "Deployment files were generated and published to one GitHub pull request.",
            "repo_url": repo_url,
            "repo_name": analysis["repo_name"],
            "analysis": analysis,
            "docker": docker_result,
            "kubernetes": kubernetes_result,
            "git": git_result,
            "generated_file_paths": generated_file_paths,
        }

    def _extract_generated_file_paths(
        self,
        repo_path: Path,
        results: list[dict[str, Any]],
    ) -> list[str]:
        generated_file_paths: list[str] = []

        for result in results:
            for generated_file in result.get("generated_files", []):
                raw_path = generated_file.get("path")

                if not raw_path:
                    continue

                file_path = Path(raw_path)

                try:
                    relative_path = file_path.relative_to(repo_path)
                    generated_file_paths.append(relative_path.as_posix())
                except ValueError:
                    generated_file_paths.append(file_path.as_posix())

        unique_paths = []
        seen = set()

        for path in generated_file_paths:
            if path in seen:
                continue

            seen.add(path)
            unique_paths.append(path)

        return unique_paths