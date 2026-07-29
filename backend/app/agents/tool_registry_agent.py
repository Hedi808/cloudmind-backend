from __future__ import annotations

import inspect
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

    Product rules:
    - Read-only tools run directly.
    - Repo generation tools publish through GitHub pull requests.
    - Runtime deployment tools require approval and deploy to Azure.
    - No direct push to main.
    - No silent fallback to local-only generation.

    Phase 20H hotfix:
    - Runtime health path is resolved automatically from repository analysis.
    - check_azure_status no longer silently falls back to /health when the repo exposes /api/status.
    - analyze_incident uses the detected health path.
    - final_demo_report is blocked if Azure health is not clean or an active incident is detected.
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
                "description": "Analyze a GitHub repository and detect framework, language, components, port, start command, and health path.",
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
                "description": "Check Azure Container App status, revision, URL, and detected health endpoint.",
            },
            {
                "name": "get_azure_logs",
                "description": "Retrieve Azure Container App logs through Log Analytics.",
            },
            {
                "name": "analyze_incident",
                "description": "Analyze Azure health and logs to detect incidents using the detected health endpoint.",
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
                "description": "Generate the final CloudMind mission report only when health and incident checks are clean.",
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
            pull_request_title="Add CloudMind Docker files",
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
            pull_request_title="Add CloudMind Kubernetes manifests",
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
            pull_request_title="Add CloudMind CI/CD workflow",
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
            pull_request_title="Add CloudMind Azure deployment files",
        )

    def _deploy_azure_runtime(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        context = self._runtime_context_from_arguments(arguments)
        repo_url = self._required(context, "repo_url")

        return self.azure_runtime_deployment_agent.deploy_container_app(
            repo_url=repo_url,
            branch=context.get("branch"),
            image=context.get("image"),
            resource_group=context.get("resource_group"),
            app_name=context.get("app_name"),
            environment_name=context.get("environment_name")
            or context.get("container_app_environment"),
            azure_location=context.get("azure_location", "francecentral"),
            target_port=context.get("target_port"),
            health_path=context.get("health_path"),
            min_replicas=context.get("min_replicas", 0),
            max_replicas=context.get("max_replicas", 1),
            cpu=context.get("cpu", 0.25),
            memory=context.get("memory", "0.5Gi"),
            timeout_seconds=context.get("timeout_seconds", 900),
        )

    def _check_azure_status(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        context = self._runtime_context_from_arguments(arguments)

        resource_group = self._required(context, "resource_group")
        app_name = self._required(context, "app_name")
        health_path = context["health_path"]
        timeout_seconds = context.get("timeout_seconds", 60)

        result = self.observability_agent.check_azure_container_app_status(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
        )

        if isinstance(result, dict):
            result["health_path"] = health_path
            result["health_path_source"] = context.get("health_path_source")

        return result

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
        context = self._runtime_context_from_arguments(arguments)

        resource_group = self._required(context, "resource_group")
        app_name = self._required(context, "app_name")
        health_path = context["health_path"]
        timeout_seconds = context.get("timeout_seconds", 60)
        log_tail = context.get("log_tail", 100)

        result = self.incident_response_agent.analyze_azure_incident(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
            log_tail=log_tail,
        )

        if isinstance(result, dict):
            result["health_path"] = health_path
            result["health_path_source"] = context.get("health_path_source")

        return result

    def _plan_remediation(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        context = self._runtime_context_from_arguments(arguments)

        resource_group = self._required(context, "resource_group")
        app_name = self._required(context, "app_name")
        health_path = context["health_path"]
        timeout_seconds = context.get("timeout_seconds", 60)
        log_tail = context.get("log_tail", 100)
        environment = context.get("environment", "development")
        allow_cost_increase = context.get("allow_cost_increase", False)

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
        context = self._runtime_context_from_arguments(arguments)

        resource_group = self._required(context, "resource_group")
        app_name = self._required(context, "app_name")
        health_path = context["health_path"]
        timeout_seconds = context.get("timeout_seconds", 60)
        log_tail = context.get("log_tail", 100)
        require_azure_healthy = context.get("require_azure_healthy", True)

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
        context = self._runtime_context_from_arguments(arguments)

        repo_url = self._required(context, "repo_url")
        resource_group = self._required(context, "resource_group")
        app_name = self._required(context, "app_name")
        health_path = context["health_path"]

        status_result = self._check_azure_status(context)
        incident_result = self._analyze_incident(context)

        azure_healthy = self._status_result_is_healthy(status_result)
        active_incident = self._incident_result_is_active(incident_result)

        if not azure_healthy or active_incident:
            return {
                "status": "demo_blocked",
                "message": (
                    "Final demo report blocked because runtime verification is not clean. "
                    "CloudMind will not mark the demo as ready while Azure health is warning or an active incident is detected."
                ),
                "tool_name": "final_demo_report",
                "demo_ready": False,
                "demo_recommendation": "fix_runtime_verification_before_demo",
                "recommendation": "fix_runtime_verification_before_demo",
                "repo_url": repo_url,
                "resource_group": resource_group,
                "app_name": app_name,
                "health_path": health_path,
                "health_path_source": context.get("health_path_source"),
                "azure_healthy": azure_healthy,
                "incident_detected": active_incident,
                "status_result": status_result,
                "incident_result": incident_result,
                "blockers": self._runtime_blockers(
                    status_result=status_result,
                    incident_result=incident_result,
                ),
            }

        payload = {
            "project_id": context.get("project_id"),
            "repo_url": repo_url,
            "resource_group": resource_group,
            "app_name": app_name,
            "pull_request_url": context.get("pull_request_url"),
            "pull_request_number": context.get("pull_request_number"),
            "health_path": health_path,
            "timeout_seconds": context.get("timeout_seconds", 60),
            "log_tail": context.get("log_tail", 100),
            "environment": context.get("environment", "development"),
            "run_pr_validation": context.get("run_pr_validation", False),
            "run_deployment_verification": context.get("run_deployment_verification", False),
            "run_azure_verification": context.get("run_azure_verification", False),
            "run_remediation_plan": context.get("run_remediation_plan", False),
            "require_ci_success_for_pr_validation": context.get(
                "require_ci_success_for_pr_validation",
                False,
            ),
            "allow_docs_only_without_ci": context.get("allow_docs_only_without_ci", True),
            "require_human_review_for_pr_validation": context.get(
                "require_human_review_for_pr_validation",
                False,
            ),
            "require_pr_merged_for_deployment": context.get(
                "require_pr_merged_for_deployment",
                True,
            ),
            "require_ci_success_for_deployment": context.get(
                "require_ci_success_for_deployment",
                True,
            ),
            "require_azure_healthy": context.get("require_azure_healthy", True),
            "include_raw_outputs": context.get("include_raw_outputs", False),
            "save_to_memory": context.get("save_to_memory", True),
        }

        candidate_methods = [
            "run_final_report",
            "run_final_demo_report",
            "build_final_report",
            "final_report",
            "generate_final_report",
            "generate_report",
            "run",
        ]

        selected_method_name = None
        selected_method = None

        for method_name in candidate_methods:
            if hasattr(self.final_demo_orchestrator_agent, method_name):
                selected_method_name = method_name
                selected_method = getattr(self.final_demo_orchestrator_agent, method_name)
                break

        if selected_method is None:
            available_methods = [
                name
                for name in dir(self.final_demo_orchestrator_agent)
                if not name.startswith("_")
            ]

            return {
                "status": "failed",
                "message": "Final demo report agent has no supported report method.",
                "tool_name": "final_demo_report",
                "available_methods": available_methods,
                "expected_any_of": candidate_methods,
            }

        result = self._call_agent_method_safely(
            method=selected_method,
            payload=payload,
        )

        if isinstance(result, dict):
            result.setdefault("tool_name", "final_demo_report")
            result.setdefault("method_used", selected_method_name)
            result.setdefault("health_path", health_path)
            result.setdefault("health_path_source", context.get("health_path_source"))
            result.setdefault("preflight_status_result", status_result)
            result.setdefault("preflight_incident_result", incident_result)
            return result

        return {
            "status": "success",
            "message": "Final demo report generated.",
            "tool_name": "final_demo_report",
            "method_used": selected_method_name,
            "health_path": health_path,
            "health_path_source": context.get("health_path_source"),
            "preflight_status_result": status_result,
            "preflight_incident_result": incident_result,
            "result": result,
        }

    def _runtime_context_from_arguments(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        context = dict(arguments)

        explicit_health_path = context.get("health_path") or context.get("detected_health_path")

        if explicit_health_path:
            context["health_path"] = self._normalize_health_path(str(explicit_health_path))
            context["health_path_source"] = "explicit_argument"
            return context

        analysis = context.get("analysis")

        health_path = self._extract_health_path_from_analysis(analysis)

        if health_path:
            context["health_path"] = health_path
            context["health_path_source"] = "provided_analysis"
            return context

        repo_url = context.get("repo_url")

        if repo_url:
            try:
                fresh_analysis = self.repository_analyzer.analyze(
                    repo_url=repo_url,
                    branch=context.get("branch"),
                )

                health_path = self._extract_health_path_from_analysis(fresh_analysis)

                if health_path:
                    context["analysis"] = fresh_analysis
                    context["health_path"] = health_path
                    context["health_path_source"] = "fresh_repository_analysis"
                    return context

            except Exception as exc:
                context["health_path_detection_error"] = str(exc)

        context["health_path"] = "/health"
        context["health_path_source"] = "fallback_default"

        return context

    def _extract_health_path_from_analysis(
        self,
        analysis: Any,
    ) -> str | None:
        if not isinstance(analysis, dict):
            return None

        primary_component = analysis.get("primary_component")

        if isinstance(primary_component, dict):
            health_path = primary_component.get("health_path")

            if health_path:
                return self._normalize_health_path(str(health_path))

        health_path = analysis.get("health_path")

        if health_path:
            return self._normalize_health_path(str(health_path))

        components = analysis.get("components")

        if isinstance(components, list):
            for component in components:
                if not isinstance(component, dict):
                    continue

                component_health_path = component.get("health_path")

                if component_health_path:
                    return self._normalize_health_path(str(component_health_path))

        return None

    def _normalize_health_path(
        self,
        value: str,
    ) -> str:
        health_path = value.strip()

        if not health_path:
            return "/health"

        if not health_path.startswith("/"):
            health_path = "/" + health_path

        return health_path

    def _status_result_is_healthy(
        self,
        status_result: dict[str, Any],
    ) -> bool:
        if status_result.get("healthy") is True:
            return True

        status = str(status_result.get("status", "")).lower()

        if status in {"healthy", "success", "completed"}:
            return True

        health = status_result.get("health")

        if isinstance(health, dict):
            if health.get("healthy") is True:
                return True

            health_status = str(health.get("status", "")).lower()

            if health_status in {"healthy", "success", "completed"}:
                return True

        return False

    def _incident_result_is_active(
        self,
        incident_result: dict[str, Any],
    ) -> bool:
        if incident_result.get("incident_detected") is True:
            return True

        status = str(incident_result.get("status", "")).lower()
        severity = str(incident_result.get("severity", "")).lower()

        active_statuses = {
            "incident_detected",
            "degraded",
            "unhealthy",
            "failed",
            "warning",
        }

        active_severities = {
            "low",
            "medium",
            "high",
            "critical",
        }

        return status in active_statuses or severity in active_severities

    def _runtime_blockers(
        self,
        status_result: dict[str, Any],
        incident_result: dict[str, Any],
    ) -> list[str]:
        blockers = []

        if not self._status_result_is_healthy(status_result):
            health = status_result.get("health")

            if isinstance(health, dict):
                url = health.get("url")
                status_code = health.get("status_code")

                if url:
                    blockers.append(
                        f"Azure health check is not clean at {url}. Status code: {status_code}."
                    )
                else:
                    blockers.append("Azure health check is not clean.")
            else:
                blockers.append("Azure status result is not healthy.")

        if self._incident_result_is_active(incident_result):
            summary = incident_result.get("summary") or incident_result.get("message")

            if summary:
                blockers.append(str(summary))
            else:
                blockers.append("Active incident detected.")

        return blockers

    def _call_agent_method_safely(
        self,
        method: Any,
        payload: dict[str, Any],
    ) -> Any:
        signature = inspect.signature(method)
        parameters = signature.parameters

        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )

        if accepts_kwargs:
            return method(**payload)

        filtered_payload = {
            key: value
            for key, value in payload.items()
            if key in parameters
        }

        if filtered_payload:
            return method(**filtered_payload)

        positional_parameters = [
            parameter
            for parameter in parameters.values()
            if parameter.kind
            in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }
        ]

        if len(positional_parameters) == 1:
            return method(payload)

        return method()

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
        pull_request_title: str,
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

        generated_file_records = self._extract_generated_file_records(
            repo_path=repo_path,
            generated_result=generated_result,
        )

        if not generated_file_records:
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

        git_result = self.git_agent.publish_generated_file_contents(
            repo_url=repo_url,
            source_repo_path=str(repo_path),
            generated_files=generated_file_records,
            base_branch=base_branch,
            branch_name=branch_name,
            commit_message="chore: add CloudMind generated files",
            pull_request_title=pull_request_title,
            pull_request_body=(
                "This pull request was generated by CloudMind.\n\n"
                f"Tool result: {nested_key}\n\n"
                "CloudMind generated these files from repository analysis and published them "
                "through Remote GitOps Mode using the GitHub API.\n\n"
                "No direct push to main was performed."
            ),
        )

        if git_result.get("status") in ["failed", "error"]:
            return {
                "status": "failed",
                "message": "Generated files were created, but remote GitHub publishing failed.",
                nested_key: generated_result,
                "git": git_result,
                "pull_request": None,
                "branch": branch_name,
                "generated_files": generated_file_records,
                "generated_file_paths": [item["relative_path"] for item in generated_file_records],
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
            "generated_files": generated_file_records,
            "generated_file_paths": [item["relative_path"] for item in generated_file_records],
            "repo_url": repo_url,
        }

    def _extract_generated_file_records(
        self,
        repo_path: Path,
        generated_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen_paths: set[str] = set()

        for generated_file in generated_result.get("generated_files", []):
            if isinstance(generated_file, str):
                raw_path = generated_file
                relative_path = self._to_repo_relative_path(repo_path, raw_path)
                file_type = None
                component = None

            elif isinstance(generated_file, dict):
                raw_path = generated_file.get("path")
                relative_path = (
                    generated_file.get("relative_path")
                    or generated_file.get("repo_path")
                    or generated_file.get("path_in_repo")
                )

                if not relative_path and raw_path:
                    relative_path = self._to_repo_relative_path(repo_path, raw_path)

                file_type = generated_file.get("type")
                component = generated_file.get("component")

            else:
                continue

            if not raw_path or not relative_path:
                continue

            normalized_relative_path = self._normalize_generated_relative_path(relative_path)

            if not normalized_relative_path or normalized_relative_path in seen_paths:
                continue

            absolute_path = self._resolve_generated_file_path(
                repo_path=repo_path,
                raw_path=raw_path,
            )

            if not absolute_path.exists() or not absolute_path.is_file():
                continue

            records.append(
                {
                    "path": str(absolute_path),
                    "relative_path": normalized_relative_path,
                    "type": file_type,
                    "component": component,
                }
            )
            seen_paths.add(normalized_relative_path)

        return records

    def _resolve_generated_file_path(
        self,
        repo_path: Path,
        raw_path: str,
    ) -> Path:
        file_path = Path(raw_path)

        if file_path.is_absolute():
            return file_path

        repo_text = repo_path.as_posix().rstrip("/")
        file_text = file_path.as_posix()

        if file_text == repo_text or file_text.startswith(repo_text + "/"):
            return file_path

        return repo_path / file_path

    def _to_repo_relative_path(
        self,
        repo_path: Path,
        raw_path: str,
    ) -> str:
        file_path = Path(raw_path)

        try:
            return file_path.relative_to(repo_path).as_posix()
        except ValueError:
            return file_path.as_posix()

    def _normalize_generated_relative_path(
        self,
        path: str,
    ) -> str:
        normalized = path.replace("\\", "/").strip()

        while normalized.startswith("./"):
            normalized = normalized[2:]

        normalized = normalized.strip("/")

        if not normalized:
            return ""

        if ".." in Path(normalized).parts:
            raise ValueError(f"Unsafe generated file path: {path}")

        return normalized

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