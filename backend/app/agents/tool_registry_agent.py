from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.agents.azure_deployment_agent import AzureDeploymentAgent
from app.agents.azure_runtime_deployment_agent import AzureRuntimeDeploymentAgent
from app.agents.cicd_agent import CICDAgent
from app.agents.deployment_prepare_agent import DeploymentPrepareAgent
from app.agents.deployment_verification_agent import DeploymentVerificationAgent
from app.agents.docker_agent import DockerAgent
from app.agents.final_demo_orchestrator_agent import FinalDemoOrchestratorAgent
from app.agents.git_agent import GitAgent
from app.agents.incident_response_agent import IncidentResponseAgent
from app.agents.kubernetes_agent import KubernetesAgent
from app.agents.observability_agent import ObservabilityAgent
from app.agents.remediation_planner_agent import RemediationPlannerAgent
from app.agents.repo_analyzer_agent import RepositoryAnalyzerAgent


class ToolRegistryAgent:
    """
    Tool registry for the conversational brain.

    Product rule:
    - Read-only tools run directly.
    - Repo generation tools publish through GitHub pull requests.
    - Runtime deployment tools require approval and deploy to Azure.
    - No direct push to main.
    - No silent fallback to local-only generation.
    """

    def __init__(self) -> None:
        self.repository_analyzer = RepositoryAnalyzerAgent()
        self.docker_agent = DockerAgent()
        self.kubernetes_agent = KubernetesAgent()
        self.deployment_prepare_agent = DeploymentPrepareAgent()
        self.cicd_agent = CICDAgent()
        self.azure_deployment_agent = AzureDeploymentAgent()
        self.azure_runtime_deployment_agent = AzureRuntimeDeploymentAgent()
        self.git_agent = GitAgent()
        self.observability_agent = ObservabilityAgent()
        self.incident_response_agent = IncidentResponseAgent()
        self.remediation_planner_agent = RemediationPlannerAgent()
        self.deployment_verification_agent = DeploymentVerificationAgent()
        self.final_demo_orchestrator_agent = FinalDemoOrchestratorAgent()

    def run_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            if tool_name == "analyze_repository":
                return self._analyze_repository(arguments)

            if tool_name == "generate_docker":
                return self._generate_docker_and_publish(arguments)

            if tool_name == "generate_kubernetes":
                return self._generate_kubernetes_and_publish(arguments)

            if tool_name == "prepare_deployment":
                return self._prepare_deployment(arguments)

            if tool_name == "generate_cicd":
                return self._generate_cicd_and_publish(arguments)

            if tool_name == "generate_azure":
                return self._generate_azure_and_publish(arguments)

            if tool_name == "deploy_azure_runtime":
                return self._deploy_azure_runtime(arguments)

            if tool_name == "check_azure_status":
                return self._check_azure_status(arguments)

            if tool_name == "get_azure_logs":
                return self._get_azure_logs(arguments)

            if tool_name == "analyze_incident":
                return self._analyze_incident(arguments)

            if tool_name == "plan_remediation":
                return self._plan_remediation(arguments)

            if tool_name == "verify_azure_deployment":
                return self._verify_azure_deployment(arguments)

            if tool_name == "final_demo_report":
                return self._final_demo_report(arguments)

            return {
                "status": "failed",
                "message": f"Unknown tool: {tool_name}",
                "tool_name": tool_name,
            }

        except Exception as exc:
            return {
                "status": "failed",
                "message": f"Tool execution failed for {tool_name}.",
                "tool_name": tool_name,
                "error": str(exc),
            }

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {
                "name": "analyze_repository",
                "description": "Analyze a GitHub repository and detect framework, language, components, and start command.",
            },
            {
                "name": "generate_docker",
                "description": "Generate Docker files and publish them through a GitHub pull request.",
            },
            {
                "name": "generate_kubernetes",
                "description": "Generate Kubernetes manifests and publish them through a GitHub pull request.",
            },
            {
                "name": "prepare_deployment",
                "description": "Generate Docker and Kubernetes assets together and publish them through a GitHub pull request.",
            },
            {
                "name": "generate_cicd",
                "description": "Generate GitHub Actions CI/CD workflow and publish it through a GitHub pull request.",
            },
            {
                "name": "generate_azure",
                "description": "Generate Azure Container Apps deployment scripts and publish them through a GitHub pull request.",
            },
            {
                "name": "deploy_azure_runtime",
                "description": "Deploy the current app image to Azure Container Apps.",
            },
            {
                "name": "check_azure_status",
                "description": "Check Azure Container App status, revision, URL, and health endpoint.",
            },
            {
                "name": "get_azure_logs",
                "description": "Retrieve Azure Container App logs through Log Analytics.",
            },
            {
                "name": "analyze_incident",
                "description": "Analyze Azure health and logs to detect incidents.",
            },
            {
                "name": "plan_remediation",
                "description": "Create a safe remediation plan.",
            },
            {
                "name": "verify_azure_deployment",
                "description": "Verify Azure deployment health, logs, and incident state.",
            },
            {
                "name": "final_demo_report",
                "description": "Generate the final CloudMind mission report.",
            },
        ]

    def _analyze_repository(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        repo_url = self._required(arguments, "repo_url")
        branch = arguments.get("branch")

        return self.repository_analyzer.analyze(
            repo_url=repo_url,
            branch=branch,
        )

    def _generate_docker_and_publish(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        repo_url = self._required(arguments, "repo_url")
        branch = arguments.get("branch")
        overwrite = arguments.get("overwrite", True)
        base_branch = arguments.get("base_branch", "main")

        docker_result = self.docker_agent.generate_for_repo(
            repo_url=repo_url,
            branch=branch,
            overwrite=overwrite,
        )

        return self._publish_generated_result(
            repo_url=repo_url,
            base_branch=base_branch,
            branch_prefix="cloudmind/docker-files",
            generated_result=docker_result,
            nested_key="docker",
            success_message="Docker files generated and published to a GitHub pull request.",
            failure_message="Docker generation failed, so nothing was published.",
            no_changes_message="DockerAgent did not generate any new files to publish.",
        )

    def _generate_kubernetes_and_publish(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        repo_url = self._required(arguments, "repo_url")
        branch = arguments.get("branch")
        overwrite = arguments.get("overwrite", True)
        base_branch = arguments.get("base_branch", "main")

        image_owner = arguments.get("image_owner") or self._github_owner(repo_url)
        repo_name = self._repo_name(repo_url)

        kubernetes_result = self.kubernetes_agent.generate_for_repo(
            repo_url=repo_url,
            branch=branch,
            overwrite=overwrite,
            namespace=arguments.get("namespace", "cloudmind-staging"),
            image_registry=arguments.get("image_registry", "ghcr.io"),
            image_owner=image_owner,
            image_tag=arguments.get("image_tag", "latest"),
            ingress_host=arguments.get("ingress_host", f"{repo_name}.local"),
        )

        return self._publish_generated_result(
            repo_url=repo_url,
            base_branch=base_branch,
            branch_prefix="cloudmind/kubernetes-files",
            generated_result=kubernetes_result,
            nested_key="kubernetes",
            success_message="Kubernetes manifests generated and published to a GitHub pull request.",
            failure_message="Kubernetes generation failed, so nothing was published.",
            no_changes_message="KubernetesAgent did not generate any new files to publish.",
        )

    def _prepare_deployment(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        repo_url = self._required(arguments, "repo_url")
        overwrite = arguments.get("overwrite", True)

        return self.deployment_prepare_agent.prepare(
            repo_url=repo_url,
            publish_to_github=True,
            overwrite=overwrite,
        )

    def _generate_cicd_and_publish(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        repo_url = self._required(arguments, "repo_url")
        branch = arguments.get("branch")
        overwrite = arguments.get("overwrite", True)
        base_branch = arguments.get("base_branch", "main")

        image_owner = arguments.get("image_owner") or self._github_owner(repo_url)

        cicd_result = self.cicd_agent.generate_for_repo(
            repo_url=repo_url,
            branch=branch,
            overwrite=overwrite,
            image_registry=arguments.get("image_registry", "ghcr.io"),
            image_owner=image_owner,
            image_tag=arguments.get("image_tag", "latest"),
            workflow_name=arguments.get("workflow_name", "docker-build.yml"),
        )

        return self._publish_generated_result(
            repo_url=repo_url,
            base_branch=base_branch,
            branch_prefix="cloudmind/cicd-workflow",
            generated_result=cicd_result,
            nested_key="cicd",
            success_message="CI/CD workflow generated and published to a GitHub pull request.",
            failure_message="CI/CD generation failed, so nothing was published.",
            no_changes_message="CICDAgent did not generate any new files to publish.",
        )

    def _generate_azure_and_publish(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        repo_url = self._required(arguments, "repo_url")
        branch = arguments.get("branch")
        overwrite = arguments.get("overwrite", True)
        base_branch = arguments.get("base_branch", "main")

        image_owner = arguments.get("image_owner") or self._github_owner(repo_url)
        repo_name = self._repo_name(repo_url)

        azure_result = self.azure_deployment_agent.generate_for_repo(
            repo_url=repo_url,
            branch=branch,
            overwrite=overwrite,
            azure_location=arguments.get("azure_location", "francecentral"),
            resource_group=arguments.get("resource_group", f"rg-cloudmind-{repo_name}"),
            container_app_environment=arguments.get(
                "container_app_environment",
                f"cae-cloudmind-{repo_name}",
            ),
            image_registry=arguments.get("image_registry", "ghcr.io"),
            image_owner=image_owner,
            image_tag=arguments.get("image_tag", "latest"),
            min_replicas=arguments.get("min_replicas", 0),
            max_replicas=arguments.get("max_replicas", 1),
            cpu=arguments.get("cpu", 0.25),
            memory=arguments.get("memory", "0.5Gi"),
        )

        return self._publish_generated_result(
            repo_url=repo_url,
            base_branch=base_branch,
            branch_prefix="cloudmind/azure-deployment",
            generated_result=azure_result,
            nested_key="azure",
            success_message="Azure deployment files generated and published to a GitHub pull request.",
            failure_message="Azure deployment generation failed, so nothing was published.",
            no_changes_message="AzureDeploymentAgent did not generate any new files to publish.",
        )

    def _deploy_azure_runtime(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        repo_url = self._required(arguments, "repo_url")

        return self.azure_runtime_deployment_agent.deploy_container_app(
            repo_url=repo_url,
            branch=arguments.get("branch"),
            image=arguments.get("image"),
            resource_group=arguments.get("resource_group"),
            app_name=arguments.get("app_name"),
            environment_name=arguments.get("environment_name")
            or arguments.get("container_app_environment"),
            azure_location=arguments.get("azure_location", "francecentral"),
            target_port=arguments.get("target_port"),
            health_path=arguments.get("health_path", "/health"),
            min_replicas=arguments.get("min_replicas", 0),
            max_replicas=arguments.get("max_replicas", 1),
            cpu=arguments.get("cpu", 0.25),
            memory=arguments.get("memory", "0.5Gi"),
            timeout_seconds=arguments.get("timeout_seconds", 900),
        )

    def _check_azure_status(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        resource_group = self._required(arguments, "resource_group")
        app_name = self._required(arguments, "app_name")
        health_path = arguments.get("health_path", "/health")
        timeout_seconds = arguments.get("timeout_seconds", 60)

        return self.observability_agent.check_azure_container_app_status(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
        )

    def _get_azure_logs(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        resource_group = self._required(arguments, "resource_group")
        app_name = self._required(arguments, "app_name")
        tail = arguments.get("tail", 100)

        return self.observability_agent.get_azure_container_app_logs(
            resource_group=resource_group,
            app_name=app_name,
            tail=tail,
        )

    def _analyze_incident(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        resource_group = self._required(arguments, "resource_group")
        app_name = self._required(arguments, "app_name")
        health_path = arguments.get("health_path", "/health")
        timeout_seconds = arguments.get("timeout_seconds", 60)
        log_tail = arguments.get("log_tail", 100)

        return self.incident_response_agent.analyze_azure_incident(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
            log_tail=log_tail,
        )

    def _plan_remediation(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        resource_group = self._required(arguments, "resource_group")
        app_name = self._required(arguments, "app_name")
        health_path = arguments.get("health_path", "/health")
        timeout_seconds = arguments.get("timeout_seconds", 60)
        log_tail = arguments.get("log_tail", 100)
        environment = arguments.get("environment", "development")
        allow_cost_increase = arguments.get("allow_cost_increase", False)

        return self.remediation_planner_agent.plan_from_azure(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
            log_tail=log_tail,
            environment=environment,
            allow_cost_increase=allow_cost_increase,
        )

    def _verify_azure_deployment(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        resource_group = self._required(arguments, "resource_group")
        app_name = self._required(arguments, "app_name")
        health_path = arguments.get("health_path", "/health")
        timeout_seconds = arguments.get("timeout_seconds", 60)
        log_tail = arguments.get("log_tail", 100)
        require_azure_healthy = arguments.get("require_azure_healthy", True)

        return self.deployment_verification_agent.verify_azure_only(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
            log_tail=log_tail,
            require_azure_healthy=require_azure_healthy,
        )

    def _final_demo_report(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        repo_url = self._required(arguments, "repo_url")
        resource_group = self._required(arguments, "resource_group")
        app_name = self._required(arguments, "app_name")
        pull_request_url = arguments.get("pull_request_url")
        pull_request_number = arguments.get("pull_request_number")

        return self.final_demo_orchestrator_agent.run_final_report(
            repo_url=repo_url,
            resource_group=resource_group,
            app_name=app_name,
            pull_request_number=pull_request_number,
            pull_request_url=pull_request_url,
            health_path=arguments.get("health_path", "/health"),
            timeout_seconds=arguments.get("timeout_seconds", 60),
            log_tail=arguments.get("log_tail", 100),
            environment=arguments.get("environment", "development"),
            run_pr_validation=arguments.get("run_pr_validation", False),
            run_azure_verification=arguments.get("run_azure_verification", True),
            run_remediation_plan=arguments.get("run_remediation_plan", True),
            require_ci_success_for_pr_validation=arguments.get("require_ci_success_for_pr_validation", False),
            allow_docs_only_without_ci=arguments.get("allow_docs_only_without_ci", True),
            require_human_review_for_pr_validation=arguments.get("require_human_review_for_pr_validation", False),
            require_pr_merged_for_deployment=arguments.get("require_pr_merged_for_deployment", True),
            require_ci_success_for_deployment=arguments.get("require_ci_success_for_deployment", True),
            require_azure_healthy=arguments.get("require_azure_healthy", True),
            include_raw_outputs=arguments.get("include_raw_outputs", False),
        )

    def _publish_generated_result(
        self,
        repo_url: str,
        base_branch: str,
        branch_prefix: str,
        generated_result: dict[str, Any],
        nested_key: str,
        success_message: str,
        failure_message: str,
        no_changes_message: str,
    ) -> dict[str, Any]:
        if generated_result.get("status") != "success":
            return {
                "status": "failed",
                "message": failure_message,
                nested_key: generated_result,
                "git": None,
                "pull_request": None,
                "generated_files": [],
                "generated_file_paths": [],
                "repo_url": repo_url,
            }

        repo_path = Path(generated_result["analysis"]["metadata"]["local_path"])

        generated_file_paths = self._extract_generated_file_paths(
            repo_path=repo_path,
            generated_result=generated_result,
        )

        if not generated_file_paths:
            return {
                "status": "no_changes",
                "message": no_changes_message,
                nested_key: generated_result,
                "git": None,
                "pull_request": None,
                "generated_files": [],
                "generated_file_paths": [],
                "repo_url": repo_url,
            }

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        branch_name = f"{branch_prefix}-{timestamp}"

        git_result = self.git_agent.publish_deployment_changes(
            local_repo_path=str(repo_path),
            repo_url=repo_url,
            generated_files=generated_file_paths,
            base_branch=base_branch,
            branch_name=branch_name,
        )

        if git_result.get("status") in ["failed", "error"]:
            return {
                "status": "failed",
                "message": "Generated files were created locally, but publishing to GitHub failed.",
                nested_key: generated_result,
                "git": git_result,
                "pull_request": None,
                "branch": branch_name,
                "generated_files": generated_file_paths,
                "generated_file_paths": generated_file_paths,
                "repo_url": repo_url,
            }

        pull_request = self._extract_pull_request_from_git_result(git_result)

        return {
            "status": "published",
            "message": success_message,
            nested_key: generated_result,
            "git": git_result,
            "pull_request": pull_request,
            "branch": git_result.get("branch") or git_result.get("branch_name") or branch_name,
            "generated_files": generated_file_paths,
            "generated_file_paths": generated_file_paths,
            "repo_url": repo_url,
        }

    def _extract_generated_file_paths(
        self,
        repo_path: Path,
        generated_result: dict[str, Any],
    ) -> list[str]:
        generated_file_paths: list[str] = []

        for generated_file in generated_result.get("generated_files", []):
            if isinstance(generated_file, str):
                raw_path = generated_file
            elif isinstance(generated_file, dict):
                raw_path = generated_file.get("path")
            else:
                raw_path = None

            if not raw_path:
                continue

            file_path = Path(raw_path)

            try:
                relative_path = file_path.relative_to(repo_path)
                generated_file_paths.append(relative_path.as_posix())
            except ValueError:
                generated_file_paths.append(file_path.as_posix())

        return generated_file_paths

    def _extract_pull_request_from_git_result(
        self,
        git_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        for key in ["pull_request", "pr", "github_pull_request"]:
            value = git_result.get(key)

            if isinstance(value, dict):
                return value

        pr_url = (
            git_result.get("pull_request_url")
            or git_result.get("pr_url")
            or git_result.get("html_url")
            or git_result.get("url")
        )

        pr_number = (
            git_result.get("pull_request_number")
            or git_result.get("pr_number")
            or git_result.get("number")
        )

        branch = (
            git_result.get("branch")
            or git_result.get("branch_name")
            or git_result.get("head_branch")
            or git_result.get("source_branch")
        )

        if pr_url or pr_number or branch:
            return {
                "url": pr_url,
                "number": pr_number,
                "branch": branch,
            }

        return None

    def _github_owner(
        self,
        repo_url: str,
    ) -> str:
        parsed = urlparse(repo_url)
        parts = [part for part in parsed.path.split("/") if part]

        if parts:
            return parts[0]

        return "your-github-username"

    def _repo_name(
        self,
        repo_url: str,
    ) -> str:
        parsed = urlparse(repo_url)
        parts = [part for part in parsed.path.split("/") if part]

        if len(parts) >= 2:
            return parts[1].removesuffix(".git")

        return "app"

    def _required(
        self,
        arguments: dict[str, Any],
        key: str,
    ) -> Any:
        value = arguments.get(key)

        if value is None or value == "":
            raise ValueError(f"Missing required argument: {key}")

        return value