import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from app.agents.repo_analyzer_agent import RepositoryAnalyzerAgent
from app.core.config import settings


class AzureRuntimeDeploymentAgent:
    """
    Phase 16 / Phase 20D agent.

    Smart Azure runtime deployer.

    Behavior:
    - Analyzes the repository.
    - Derives app name, image name, target port, and health path automatically.
    - Uses the same image naming convention as CICDAgent.
    - Reuses an existing Azure Container Apps environment when Azure quota requires it.
    - Uses az rest / ARM API to avoid fragile Azure Container Apps CLI extension behavior.
    - Deletes/recreates failed Container Apps automatically when retrying.
    """

    def __init__(self) -> None:
        self.repo_analyzer = RepositoryAnalyzerAgent()

    def deploy_container_app(
        self,
        repo_url: str,
        branch: str | None = None,
        image: str | None = None,
        resource_group: str | None = None,
        app_name: str | None = None,
        environment_name: str | None = None,
        azure_location: str = "francecentral",
        target_port: int | None = None,
        health_path: str | None = "/health",
        min_replicas: int = 0,
        max_replicas: int = 1,
        cpu: float = 0.25,
        memory: str = "0.5Gi",
        timeout_seconds: int = 900,
    ) -> dict[str, Any]:
        started_at = time.time()

        account = self._get_azure_account()
        subscription_id = account["id"]

        analysis = self.repo_analyzer.analyze(repo_url=repo_url, branch=branch)

        derived = self._derive_defaults_from_analysis(
            repo_url=repo_url,
            analysis=analysis,
            image=image,
            resource_group=resource_group,
            app_name=app_name,
            environment_name=environment_name,
            target_port=target_port,
            health_path=health_path,
        )

        preferred_resource_group = derived["resource_group"]
        preferred_app_name = derived["app_name"]
        preferred_environment_name = derived["environment_name"]
        preferred_workspace_name = derived["workspace_name"]

        image = derived["image"]
        target_port = derived["target_port"]
        health_path = derived["health_path"]

        image_resolution = derived["image_resolution"]

        if image_resolution.get("definitive_missing"):
            raise RuntimeError(
                "CloudMind could not deploy because the expected container image "
                "does not exist in the registry yet. "
                f"Selected image: {image}. "
                f"Checked candidates: {image_resolution.get('candidates')}. "
                "Merge the Docker and CI/CD pull requests first, then wait for GitHub Actions "
                "to publish the image to GHCR."
            )

        self._register_provider("Microsoft.App")
        self._register_provider("Microsoft.OperationalInsights")

        environment_reused = False
        environment_decision = "not_decided"
        workspace_name = preferred_workspace_name

        reusable_environment = self._find_reusable_managed_environment(
            subscription_id=subscription_id,
            azure_location=azure_location,
            preferred_environment_name=environment_name,
        )

        if reusable_environment:
            environment_reused = True
            environment_decision = "reused_existing_environment_before_create"
            managed_environment = reusable_environment["resource"]
            managed_environment_id = reusable_environment["id"]
            environment_name = reusable_environment["name"]
            resource_group = reusable_environment["resource_group"]
            workspace_name = None

        else:
            resource_group = preferred_resource_group
            environment_name = preferred_environment_name

            self._create_resource_group(
                resource_group=resource_group,
                azure_location=azure_location,
            )

            workspace = self._create_or_update_log_analytics_workspace(
                subscription_id=subscription_id,
                resource_group=resource_group,
                workspace_name=workspace_name,
                azure_location=azure_location,
            )

            workspace_shared_key = self._get_log_analytics_shared_key(
                subscription_id=subscription_id,
                resource_group=resource_group,
                workspace_name=workspace_name,
            )

            try:
                managed_environment = self._create_or_update_managed_environment(
                    subscription_id=subscription_id,
                    resource_group=resource_group,
                    environment_name=environment_name,
                    azure_location=azure_location,
                    workspace_customer_id=workspace["customer_id"],
                    workspace_shared_key=workspace_shared_key,
                )

                managed_environment_id = managed_environment["id"]
                environment_decision = "created_new_environment"

            except Exception as exc:
                if not self._is_environment_quota_error(exc):
                    raise

                fallback_environment = self._find_reusable_managed_environment(
                    subscription_id=subscription_id,
                    azure_location=azure_location,
                    preferred_environment_name=None,
                )

                if not fallback_environment:
                    raise RuntimeError(
                        "Azure blocked creating a new Container Apps environment because of quota, "
                        "but CloudMind could not find an existing environment to reuse."
                    ) from exc

                environment_reused = True
                environment_decision = "reused_existing_environment_after_quota_error"
                managed_environment = fallback_environment["resource"]
                managed_environment_id = fallback_environment["id"]
                environment_name = fallback_environment["name"]
                resource_group = fallback_environment["resource_group"]

        app_name = preferred_app_name

        predeployment_cleanup = self._delete_failed_container_app_if_needed(
            subscription_id=subscription_id,
            resource_group=resource_group,
            app_name=app_name,
        )

        container_app = self._create_or_update_container_app(
            subscription_id=subscription_id,
            resource_group=resource_group,
            app_name=app_name,
            environment_id=managed_environment_id,
            azure_location=azure_location,
            image=image,
            target_port=target_port,
            min_replicas=min_replicas,
            max_replicas=max_replicas,
            cpu=cpu,
            memory=memory,
        )

        final_container_app = self._wait_for_container_app(
            subscription_id=subscription_id,
            resource_group=resource_group,
            app_name=app_name,
            timeout_seconds=timeout_seconds,
        )

        fqdn = self._extract_fqdn(final_container_app) or self._extract_fqdn(container_app)
        app_url = f"https://{fqdn}" if fqdn else None

        health_result = self._check_health(
            app_url=app_url,
            health_path=health_path,
            timeout_seconds=min(timeout_seconds, 180),
        )

        elapsed_seconds = round(time.time() - started_at, 2)

        if health_result["healthy"]:
            status = "deployed"
            message = "Azure Container App deployed successfully and health check passed."
        else:
            status = "deployed_with_warnings"
            message = "Azure Container App was deployed, but the health endpoint did not pass yet."

        return {
            "status": status,
            "message": message,
            "repo_url": repo_url,
            "repo_name": analysis.get("repo_name"),
            "image": image,
            "image_resolution": image_resolution,
            "resource_group": resource_group,
            "app_name": app_name,
            "environment_name": environment_name,
            "environment_reused": environment_reused,
            "environment_decision": environment_decision,
            "workspace_name": workspace_name,
            "azure_location": azure_location,
            "target_port": target_port,
            "health_path": health_path,
            "app_url": app_url,
            "health": health_result,
            "predeployment_cleanup": predeployment_cleanup,
            "elapsed_seconds": elapsed_seconds,
            "analysis": {
                "repo_name": analysis.get("repo_name"),
                "project_type": analysis.get("project_type"),
                "detected_language": analysis.get("detected_language"),
                "detected_framework": analysis.get("detected_framework"),
                "detected_languages": analysis.get("detected_languages", []),
                "detected_frameworks": analysis.get("detected_frameworks", []),
                "primary_component": analysis.get("primary_component"),
                "components": analysis.get("components", []),
            },
            "azure": {
                "subscription_id": subscription_id,
                "managed_environment_id": managed_environment_id,
                "container_app_id": final_container_app.get("id") or container_app.get("id"),
                "provisioning_state": self._nested_get(
                    final_container_app,
                    ["properties", "provisioningState"],
                ),
                "running_status": self._nested_get(
                    final_container_app,
                    ["properties", "runningStatus"],
                ),
            },
            "next_steps": [
                "Use Check Azure status to verify runtime state.",
                "Use Analyze incident to inspect status and logs.",
                "Use Generate final demo report after the deployment is healthy.",
            ],
        }

    def _get_azure_account(self) -> dict[str, Any]:
        return self._run_az_json(["account", "show"])

    def _register_provider(
        self,
        namespace: str,
    ) -> None:
        self._run_az(
            [
                "provider",
                "register",
                "--namespace",
                namespace,
                "--wait",
            ],
            timeout_seconds=300,
        )

    def _create_resource_group(
        self,
        resource_group: str,
        azure_location: str,
    ) -> dict[str, Any]:
        return self._run_az_json(
            [
                "group",
                "create",
                "--name",
                resource_group,
                "--location",
                azure_location,
            ],
            timeout_seconds=180,
        )

    def _find_reusable_managed_environment(
        self,
        subscription_id: str,
        azure_location: str,
        preferred_environment_name: str | None = None,
    ) -> dict[str, Any] | None:
        environments = self._list_managed_environments()

        matching_environments = []

        for environment in environments:
            location = environment.get("location")

            if self._normalize_location(location) != self._normalize_location(azure_location):
                continue

            environment_id = environment.get("id")
            name = environment.get("name")

            if not environment_id or not name:
                continue

            resource_group = self._extract_resource_group_from_id(environment_id)

            if not resource_group:
                continue

            if preferred_environment_name and name == preferred_environment_name:
                full_environment = self._get_managed_environment_by_id(
                    environment_id=environment_id,
                )

                return {
                    "id": environment_id,
                    "name": name,
                    "resource_group": resource_group,
                    "resource": full_environment,
                }

            matching_environments.append(
                {
                    "id": environment_id,
                    "name": name,
                    "resource_group": resource_group,
                    "raw": environment,
                    "score": self._environment_reuse_score(environment),
                }
            )

        if not matching_environments:
            return None

        matching_environments.sort(key=lambda item: item["score"], reverse=True)
        selected = matching_environments[0]

        full_environment = self._get_managed_environment_by_id(
            environment_id=selected["id"],
        )

        return {
            "id": selected["id"],
            "name": selected["name"],
            "resource_group": selected["resource_group"],
            "resource": full_environment,
        }

    def _list_managed_environments(self) -> list[dict[str, Any]]:
        result = self._run_az_json(
            [
                "resource",
                "list",
                "--resource-type",
                "Microsoft.App/managedEnvironments",
            ],
            timeout_seconds=120,
        )

        if isinstance(result, list):
            return result

        return []

    def _get_managed_environment_by_id(
        self,
        environment_id: str,
    ) -> dict[str, Any]:
        url = (
            f"https://management.azure.com{environment_id}"
            f"?api-version=2025-01-01"
        )

        return self._az_rest(
            method="get",
            url=url,
            body=None,
            timeout_seconds=120,
        )

    def _environment_reuse_score(
        self,
        environment: dict[str, Any],
    ) -> int:
        score = 0
        name = str(environment.get("name", "")).lower()

        if name.startswith("cae-cloudmind"):
            score += 100

        if environment.get("status") == "Succeeded":
            score += 20

        if environment.get("provisioningState") == "Succeeded":
            score += 20

        return score

    def _create_or_update_log_analytics_workspace(
        self,
        subscription_id: str,
        resource_group: str,
        workspace_name: str,
        azure_location: str,
    ) -> dict[str, Any]:
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.OperationalInsights/workspaces/{workspace_name}"
            f"?api-version=2023-09-01"
        )

        body = {
            "location": azure_location,
            "properties": {
                "sku": {
                    "name": "PerGB2018",
                },
                "retentionInDays": 30,
            },
        }

        result = self._az_rest(
            method="put",
            url=url,
            body=body,
            timeout_seconds=300,
        )

        customer_id = self._nested_get(result, ["properties", "customerId"])

        if not customer_id:
            result = self._az_rest(
                method="get",
                url=url,
                body=None,
                timeout_seconds=120,
            )
            customer_id = self._nested_get(result, ["properties", "customerId"])

        if not customer_id:
            raise RuntimeError("Could not retrieve Log Analytics workspace customerId.")

        return {
            "id": result.get("id"),
            "name": workspace_name,
            "customer_id": customer_id,
        }

    def _get_log_analytics_shared_key(
        self,
        subscription_id: str,
        resource_group: str,
        workspace_name: str,
    ) -> str:
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.OperationalInsights/workspaces/{workspace_name}"
            f"/sharedKeys?api-version=2023-09-01"
        )

        result = self._az_rest(
            method="post",
            url=url,
            body={},
            timeout_seconds=120,
        )

        shared_key = result.get("primarySharedKey")

        if not shared_key:
            raise RuntimeError("Could not retrieve Log Analytics workspace shared key.")

        return shared_key

    def _create_or_update_managed_environment(
        self,
        subscription_id: str,
        resource_group: str,
        environment_name: str,
        azure_location: str,
        workspace_customer_id: str,
        workspace_shared_key: str,
    ) -> dict[str, Any]:
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.App/managedEnvironments/{environment_name}"
            f"?api-version=2025-01-01"
        )

        body = {
            "location": azure_location,
            "properties": {
                "appLogsConfiguration": {
                    "destination": "log-analytics",
                    "logAnalyticsConfiguration": {
                        "customerId": workspace_customer_id,
                        "sharedKey": workspace_shared_key,
                    },
                },
            },
        }

        self._az_rest(
            method="put",
            url=url,
            body=body,
            timeout_seconds=300,
        )

        return self._wait_for_managed_environment(
            subscription_id=subscription_id,
            resource_group=resource_group,
            environment_name=environment_name,
            timeout_seconds=900,
        )

    def _wait_for_managed_environment(
        self,
        subscription_id: str,
        resource_group: str,
        environment_name: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.App/managedEnvironments/{environment_name}"
            f"?api-version=2025-01-01"
        )

        deadline = time.time() + timeout_seconds
        last_result: dict[str, Any] = {}

        while time.time() < deadline:
            last_result = self._az_rest(
                method="get",
                url=url,
                body=None,
                timeout_seconds=120,
            )

            provisioning_state = self._nested_get(
                last_result,
                ["properties", "provisioningState"],
            )

            if provisioning_state == "Succeeded":
                return last_result

            if provisioning_state in ["Failed", "Canceled"]:
                raise RuntimeError(
                    f"Managed environment provisioning failed: {provisioning_state}"
                )

            time.sleep(15)

        raise TimeoutError(
            f"Timed out waiting for managed environment {environment_name}. "
            f"Last result: {last_result}"
        )

    def _delete_failed_container_app_if_needed(
        self,
        subscription_id: str,
        resource_group: str,
        app_name: str,
    ) -> dict[str, Any]:
        existing_app = self._get_container_app_or_none(
            subscription_id=subscription_id,
            resource_group=resource_group,
            app_name=app_name,
        )

        if not existing_app:
            return {
                "deleted_failed_app": False,
                "reason": "No existing Container App with the same name.",
            }

        provisioning_state = self._nested_get(
            existing_app,
            ["properties", "provisioningState"],
        )

        if provisioning_state not in ["Failed", "Canceled"]:
            return {
                "deleted_failed_app": False,
                "reason": f"Existing Container App state is {provisioning_state}.",
            }

        self._delete_container_app(
            subscription_id=subscription_id,
            resource_group=resource_group,
            app_name=app_name,
        )

        self._wait_for_container_app_deleted(
            subscription_id=subscription_id,
            resource_group=resource_group,
            app_name=app_name,
            timeout_seconds=300,
        )

        return {
            "deleted_failed_app": True,
            "reason": f"Existing Container App was {provisioning_state}, so CloudMind deleted it before retrying.",
        }

    def _get_container_app_or_none(
        self,
        subscription_id: str,
        resource_group: str,
        app_name: str,
    ) -> dict[str, Any] | None:
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.App/containerApps/{app_name}"
            f"?api-version=2025-01-01"
        )

        try:
            return self._az_rest(
                method="get",
                url=url,
                body=None,
                timeout_seconds=120,
            )
        except RuntimeError as exc:
            message = str(exc).lower()

            if "404" in message or "notfound" in message or "not found" in message:
                return None

            raise

    def _delete_container_app(
        self,
        subscription_id: str,
        resource_group: str,
        app_name: str,
    ) -> None:
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.App/containerApps/{app_name}"
            f"?api-version=2025-01-01"
        )

        self._az_rest(
            method="delete",
            url=url,
            body=None,
            timeout_seconds=180,
        )

    def _wait_for_container_app_deleted(
        self,
        subscription_id: str,
        resource_group: str,
        app_name: str,
        timeout_seconds: int,
    ) -> None:
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            existing = self._get_container_app_or_none(
                subscription_id=subscription_id,
                resource_group=resource_group,
                app_name=app_name,
            )

            if not existing:
                return

            time.sleep(10)

        raise TimeoutError(
            f"Timed out waiting for failed Container App {app_name} to be deleted."
        )

    def _create_or_update_container_app(
        self,
        subscription_id: str,
        resource_group: str,
        app_name: str,
        environment_id: str,
        azure_location: str,
        image: str,
        target_port: int,
        min_replicas: int,
        max_replicas: int,
        cpu: float,
        memory: str,
    ) -> dict[str, Any]:
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.App/containerApps/{app_name}"
            f"?api-version=2025-01-01"
        )

        configuration: dict[str, Any] = {
            "activeRevisionsMode": "Single",
            "ingress": {
                "external": True,
                "targetPort": target_port,
                "transport": "auto",
                "allowInsecure": False,
            },
        }

        registry_configuration = self._registry_configuration_for_image(image)

        if registry_configuration.get("secrets"):
            configuration["secrets"] = registry_configuration["secrets"]

        if registry_configuration.get("registries"):
            configuration["registries"] = registry_configuration["registries"]

        body = {
            "location": azure_location,
            "properties": {
                "managedEnvironmentId": environment_id,
                "configuration": configuration,
                "template": {
                    "containers": [
                        {
                            "name": self._sanitize_container_name(app_name),
                            "image": image,
                            "env": [
                                {
                                    "name": "PORT",
                                    "value": str(target_port),
                                }
                            ],
                            "resources": {
                                "cpu": cpu,
                                "memory": memory,
                            },
                        }
                    ],
                    "scale": {
                        "minReplicas": min_replicas,
                        "maxReplicas": max_replicas,
                    },
                },
            },
        }

        return self._az_rest(
            method="put",
            url=url,
            body=body,
            timeout_seconds=300,
        )

    def _registry_configuration_for_image(
        self,
        image: str,
    ) -> dict[str, Any]:
        parsed = self._parse_container_image(image)

        if parsed.get("registry") != "ghcr.io":
            return {
                "secrets": [],
                "registries": [],
                "reason": "No registry credentials configured for non-GHCR image.",
            }

        github_token = getattr(settings, "github_token", None)
        github_username = getattr(settings, "github_username", None)

        if not github_token:
            return {
                "secrets": [],
                "registries": [],
                "reason": "No GitHub token configured. Assuming GHCR image is public.",
            }

        username = github_username or parsed.get("owner") or "cloudmind"

        return {
            "secrets": [
                {
                    "name": "ghcr-token",
                    "value": github_token,
                }
            ],
            "registries": [
                {
                    "server": "ghcr.io",
                    "username": username,
                    "passwordSecretRef": "ghcr-token",
                }
            ],
            "reason": "GHCR registry credentials configured from backend GitHub token.",
        }

    def _wait_for_container_app(
        self,
        subscription_id: str,
        resource_group: str,
        app_name: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.App/containerApps/{app_name}"
            f"?api-version=2025-01-01"
        )

        deadline = time.time() + timeout_seconds
        last_result: dict[str, Any] = {}

        while time.time() < deadline:
            last_result = self._az_rest(
                method="get",
                url=url,
                body=None,
                timeout_seconds=120,
            )

            provisioning_state = self._nested_get(
                last_result,
                ["properties", "provisioningState"],
            )

            fqdn = self._extract_fqdn(last_result)

            if provisioning_state == "Succeeded" and fqdn:
                return last_result

            if provisioning_state in ["Failed", "Canceled"]:
                failure_summary = self._summarize_container_app_failure(last_result)

                raise RuntimeError(
                    f"Container App provisioning failed: {provisioning_state}. "
                    f"Details: {json.dumps(failure_summary, ensure_ascii=False)}"
                )

            time.sleep(10)

        raise TimeoutError(
            f"Timed out waiting for Container App {app_name}. "
            f"Last result: {last_result}"
        )

    def _summarize_container_app_failure(
        self,
        container_app: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": container_app.get("id"),
            "name": container_app.get("name"),
            "provisioning_state": self._nested_get(
                container_app,
                ["properties", "provisioningState"],
            ),
            "running_status": self._nested_get(
                container_app,
                ["properties", "runningStatus"],
            ),
            "latest_revision": self._nested_get(
                container_app,
                ["properties", "latestRevisionName"],
            ),
            "latest_ready_revision": self._nested_get(
                container_app,
                ["properties", "latestReadyRevisionName"],
            ),
            "image": self._nested_get(
                container_app,
                ["properties", "template", "containers", 0, "image"],
            ),
            "target_port": self._nested_get(
                container_app,
                ["properties", "configuration", "ingress", "targetPort"],
            ),
            "fqdn": self._extract_fqdn(container_app),
        }

    def _check_health(
        self,
        app_url: str | None,
        health_path: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        if not app_url:
            return {
                "healthy": False,
                "status_code": None,
                "url": None,
                "message": "No app URL was available.",
            }

        url = app_url.rstrip("/") + "/" + health_path.lstrip("/")
        deadline = time.time() + timeout_seconds
        last_error = None
        last_status_code = None
        last_text = ""

        while time.time() < deadline:
            try:
                response = requests.get(url, timeout=15)
                last_status_code = response.status_code
                last_text = response.text[:500]

                if 200 <= response.status_code < 400:
                    return {
                        "healthy": True,
                        "status_code": response.status_code,
                        "url": url,
                        "message": "Health endpoint responded successfully.",
                        "body_preview": last_text,
                    }

            except Exception as exc:
                last_error = str(exc)

            time.sleep(10)

        return {
            "healthy": False,
            "status_code": last_status_code,
            "url": url,
            "message": "Health endpoint did not become healthy before timeout.",
            "last_error": last_error,
            "body_preview": last_text,
        }

    def _derive_defaults_from_analysis(
        self,
        repo_url: str,
        analysis: dict[str, Any],
        image: str | None,
        resource_group: str | None,
        app_name: str | None,
        environment_name: str | None,
        target_port: int | None,
        health_path: str | None,
    ) -> dict[str, Any]:
        owner = self._github_owner(repo_url)
        repo_name = analysis.get("repo_name") or self._repo_name(repo_url)
        repo_slug = self._normalize_name(repo_name)

        azure_repo_slug = self._sanitize_azure_name(repo_slug, max_length=24)

        deployable_components = self._select_deployable_components(analysis)
        component = self._first_component(analysis, deployable_components)

        component_name = self._normalize_name(
            component.get("name") or component.get("type") or "backend"
        )

        derived_app_name = self._sanitize_container_app_name(
            app_name or f"{azure_repo_slug}-{component_name}",
        )

        derived_resource_group = self._sanitize_azure_name(
            resource_group or f"rg-cloudmind-{azure_repo_slug}",
            max_length=60,
        )

        derived_environment_name = self._sanitize_azure_name(
            environment_name or f"cae-cloudmind-{azure_repo_slug}",
            max_length=60,
        )

        workspace_name = self._sanitize_azure_name(
            f"log-cloudmind-{azure_repo_slug}",
            max_length=60,
        )

        image_resolution = self._resolve_container_image(
            explicit_image=image,
            owner=owner,
            repo_slug=repo_slug,
            component=component,
            components=deployable_components,
        )

        derived_image = image_resolution["selected_image"]
        derived_target_port = int(target_port or component.get("port") or 8000)
        derived_health_path = self._derive_health_path(
            requested_health_path=health_path,
            component=component,
            analysis=analysis,
        )

        return {
            "owner": owner,
            "repo_slug": repo_slug,
            "component_name": component_name,
            "image": derived_image,
            "image_resolution": image_resolution,
            "resource_group": derived_resource_group,
            "app_name": derived_app_name,
            "environment_name": derived_environment_name,
            "workspace_name": workspace_name,
            "target_port": derived_target_port,
            "health_path": derived_health_path,
        }

    def _select_deployable_components(
        self,
        analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        components = analysis.get("components", []) or []
        primary_component = analysis.get("primary_component")

        if primary_component and isinstance(primary_component, dict):
            primary_type = primary_component.get("type")

            if primary_type in {"fullstack", "backend", "frontend"}:
                if primary_type == "fullstack":
                    return [primary_component]

        deployable: list[dict[str, Any]] = []
        seen: set[str] = set()

        for component in components:
            if not isinstance(component, dict):
                continue

            component_type = component.get("type")

            if component_type not in {"fullstack", "backend", "frontend"}:
                continue

            if self._is_nested_static_component(component, components):
                continue

            key = self._component_identity(component)

            if key in seen:
                continue

            seen.add(key)
            deployable.append(component)

        if primary_component and isinstance(primary_component, dict):
            key = self._component_identity(primary_component)

            if key not in seen and primary_component.get("type") in {"fullstack", "backend", "frontend"}:
                deployable.insert(0, primary_component)

        return sorted(
            deployable,
            key=lambda item: (
                self._component_priority(item),
                int(item.get("confidence") or 0),
            ),
            reverse=True,
        )

    def _first_component(
        self,
        analysis: dict[str, Any],
        deployable_components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        primary_component = analysis.get("primary_component")

        if isinstance(primary_component, dict) and primary_component:
            return primary_component

        if deployable_components:
            return deployable_components[0]

        components = analysis.get("components", [])

        if components and isinstance(components[0], dict):
            return components[0]

        return {
            "name": "app",
            "type": "backend",
            "port": analysis.get("port") or 8000,
            "health_path": analysis.get("health_path") or "/health",
        }

    def _resolve_container_image(
        self,
        explicit_image: str | None,
        owner: str,
        repo_slug: str,
        component: dict[str, Any],
        components: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if explicit_image:
            check = self._check_container_image_access(explicit_image)

            return {
                "selected_image": explicit_image,
                "source": "explicit_user_or_context_image",
                "candidates": [explicit_image],
                "checks": [check],
                "definitive_missing": check.get("definitive_missing", False),
            }

        candidates = self._build_image_candidates(
            owner=owner,
            repo_slug=repo_slug,
            component=component,
            components=components,
        )

        checks = []

        for candidate in candidates:
            check = self._check_container_image_access(candidate)
            checks.append(check)

            if check.get("accessible"):
                return {
                    "selected_image": candidate,
                    "source": "registry_accessible_candidate",
                    "candidates": candidates,
                    "checks": checks,
                    "definitive_missing": False,
                }

        all_definitely_missing = bool(checks) and all(
            check.get("definitive_missing") for check in checks
        )

        return {
            "selected_image": candidates[0],
            "source": "first_candidate_fallback",
            "candidates": candidates,
            "checks": checks,
            "definitive_missing": all_definitely_missing,
        }

    def _build_image_candidates(
        self,
        owner: str,
        repo_slug: str,
        component: dict[str, Any],
        components: list[dict[str, Any]],
    ) -> list[str]:
        owner = owner.lower()
        repo_slug = self._normalize_name(repo_slug)
        component_name = self._normalize_name(
            component.get("name") or component.get("type") or "app"
        )
        component_type = self._normalize_name(component.get("type") or "app")

        candidates: list[str] = []

        if len(components) <= 1:
            candidates.append(f"ghcr.io/{owner}/{repo_slug}:latest")
            candidates.append(f"ghcr.io/{owner}/{repo_slug}-{component_name}:latest")

            if component_type != component_name:
                candidates.append(f"ghcr.io/{owner}/{repo_slug}-{component_type}:latest")

            candidates.append(f"ghcr.io/{owner}/{repo_slug}-backend:latest")
            candidates.append(f"ghcr.io/{owner}/{repo_slug}-app:latest")
        else:
            candidates.append(f"ghcr.io/{owner}/{repo_slug}-{component_name}:latest")
            candidates.append(f"ghcr.io/{owner}/{repo_slug}-{component_type}:latest")
            candidates.append(f"ghcr.io/{owner}/{repo_slug}:latest")

        return list(dict.fromkeys(candidates))

    def _check_container_image_access(
        self,
        image: str,
    ) -> dict[str, Any]:
        parsed = self._parse_container_image(image)

        if parsed.get("registry") != "ghcr.io":
            return {
                "image": image,
                "checked": False,
                "accessible": False,
                "definitive_missing": False,
                "reason": "Only GHCR images are checked automatically for now.",
            }

        repository = parsed["repository"]
        reference = parsed["reference"]

        manifest_url = f"https://ghcr.io/v2/{repository}/manifests/{reference}"

        headers = {
            "Accept": (
                "application/vnd.oci.image.index.v1+json,"
                "application/vnd.oci.image.manifest.v1+json,"
                "application/vnd.docker.distribution.manifest.v2+json"
            )
        }

        try:
            response = requests.head(manifest_url, headers=headers, timeout=15)

            if response.status_code == 405:
                response = requests.get(manifest_url, headers=headers, timeout=15)

            if response.status_code == 200:
                return {
                    "image": image,
                    "checked": True,
                    "accessible": True,
                    "definitive_missing": False,
                    "status_code": response.status_code,
                    "reason": "Registry manifest is accessible.",
                }

            if response.status_code == 401:
                token = self._get_ghcr_bearer_token(
                    www_authenticate=response.headers.get("WWW-Authenticate", ""),
                    repository=repository,
                )

                if token:
                    auth_headers = dict(headers)
                    auth_headers["Authorization"] = f"Bearer {token}"

                    retry = requests.head(
                        manifest_url,
                        headers=auth_headers,
                        timeout=15,
                    )

                    if retry.status_code == 405:
                        retry = requests.get(
                            manifest_url,
                            headers=auth_headers,
                            timeout=15,
                        )

                    if retry.status_code == 200:
                        return {
                            "image": image,
                            "checked": True,
                            "accessible": True,
                            "definitive_missing": False,
                            "status_code": retry.status_code,
                            "reason": "Registry manifest is accessible after token request.",
                        }

                    if retry.status_code == 404:
                        return {
                            "image": image,
                            "checked": True,
                            "accessible": False,
                            "definitive_missing": True,
                            "status_code": retry.status_code,
                            "reason": "Registry manifest was not found.",
                        }

                    return {
                        "image": image,
                        "checked": True,
                        "accessible": False,
                        "definitive_missing": False,
                        "status_code": retry.status_code,
                        "reason": retry.text[:300],
                    }

            if response.status_code == 404:
                return {
                    "image": image,
                    "checked": True,
                    "accessible": False,
                    "definitive_missing": True,
                    "status_code": response.status_code,
                    "reason": "Registry manifest was not found.",
                }

            return {
                "image": image,
                "checked": True,
                "accessible": False,
                "definitive_missing": False,
                "status_code": response.status_code,
                "reason": response.text[:300],
            }

        except Exception as exc:
            return {
                "image": image,
                "checked": False,
                "accessible": False,
                "definitive_missing": False,
                "reason": f"Registry check failed but deployment can still continue: {exc}",
            }

    def _get_ghcr_bearer_token(
        self,
        www_authenticate: str,
        repository: str,
    ) -> str | None:
        attributes = dict(re.findall(r'(\w+)="([^"]+)"', www_authenticate))

        realm = attributes.get("realm") or "https://ghcr.io/token"
        service = attributes.get("service") or "ghcr.io"
        scope = attributes.get("scope") or f"repository:{repository}:pull"

        params = {
            "service": service,
            "scope": scope,
        }

        headers = {}

        github_token = getattr(settings, "github_token", None)

        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        try:
            response = requests.get(
                realm,
                params=params,
                headers=headers,
                timeout=15,
            )

            if response.status_code != 200 and github_token:
                username = getattr(settings, "github_username", None) or "x-access-token"

                response = requests.get(
                    realm,
                    params=params,
                    auth=(username, github_token),
                    timeout=15,
                )

            if response.status_code != 200:
                return None

            data = response.json()

            return data.get("token")

        except Exception:
            return None

    def _parse_container_image(
        self,
        image: str,
    ) -> dict[str, Any]:
        clean = image.strip()
        registry = ""
        remainder = clean
        reference = "latest"

        if "/" in clean and "." in clean.split("/")[0]:
            registry, remainder = clean.split("/", 1)

        if ":" in remainder:
            repository, reference = remainder.rsplit(":", 1)
        else:
            repository = remainder

        parts = repository.split("/")

        return {
            "image": image,
            "registry": registry,
            "repository": repository,
            "reference": reference,
            "owner": parts[0] if parts else None,
            "name": parts[-1] if parts else repository,
        }

    def _derive_health_path(
        self,
        requested_health_path: str | None,
        component: dict[str, Any],
        analysis: dict[str, Any],
    ) -> str:
        component_health_path = component.get("health_path")
        analysis_health_path = analysis.get("health_path")

        if requested_health_path and requested_health_path not in {"/health", "health"}:
            return self._normalize_health_path(requested_health_path)

        if component_health_path:
            return self._normalize_health_path(str(component_health_path))

        if analysis_health_path:
            return self._normalize_health_path(str(analysis_health_path))

        return self._normalize_health_path(requested_health_path or "/health")

    def _normalize_health_path(
        self,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            return "/health"

        if not value.startswith("/"):
            value = "/" + value

        return value

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

            if not isinstance(parent, dict):
                continue

            if not parent.get("package_file"):
                continue

            parent_path = str(parent.get("component_path") or ".").strip("/")

            if parent_path in {"", "."}:
                return True

            if component_path.startswith(parent_path + "/"):
                return True

        return False

    def _component_priority(
        self,
        component: dict[str, Any],
    ) -> int:
        component_type = component.get("type")

        if component_type == "fullstack":
            return 4

        if component_type == "backend":
            return 3

        if component_type == "frontend":
            return 2

        return 1

    def _component_identity(
        self,
        component: dict[str, Any],
    ) -> str:
        return "|".join(
            [
                str(component.get("name") or ""),
                str(component.get("type") or ""),
                str(component.get("component_path") or ""),
                str(component.get("package_file") or ""),
            ]
        )

    def _extract_fqdn(
        self,
        container_app: dict[str, Any],
    ) -> str | None:
        return self._nested_get(
            container_app,
            ["properties", "configuration", "ingress", "fqdn"],
        )

    def _az_rest(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        command = [
            "rest",
            "--method",
            method,
            "--url",
            url,
        ]

        temp_path: Path | None = None

        if body is not None:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".json",
                delete=False,
                encoding="utf-8",
            ) as temp_file:
                json.dump(body, temp_file)
                temp_path = Path(temp_file.name)

            command.extend(["--body", f"@{temp_path}"])

        try:
            return self._run_az_json(command, timeout_seconds=timeout_seconds)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _run_az_json(
        self,
        args: list[str],
        timeout_seconds: int = 120,
    ) -> Any:
        output = self._run_az(
            args=[*args, "--output", "json"],
            timeout_seconds=timeout_seconds,
        )

        if not output.strip():
            return {}

        return json.loads(output)

    def _resolve_az_executable(self) -> str:
        candidates = [
            "az.cmd",
            "az.CMD",
            "az.exe",
            "az",
        ]

        for candidate in candidates:
            resolved = shutil.which(candidate)

            if resolved:
                return resolved

        common_paths = [
            Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"),
            Path(r"C:\Program Files (x86)\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"),
        ]

        for path in common_paths:
            if path.exists():
                return str(path)

        raise RuntimeError(
            "Azure CLI was not found from the backend process. "
            "Install Azure CLI or restart the terminal/backend so az.cmd is available in PATH."
        )

    def _run_az(
        self,
        args: list[str],
        timeout_seconds: int = 120,
    ) -> str:
        az_executable = self._resolve_az_executable()
        command = [az_executable, *args]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()

            raise RuntimeError(
                "Azure CLI command failed.\n"
                f"Command: {' '.join(command)}\n"
                f"STDOUT: {stdout}\n"
                f"STDERR: {stderr}"
            )

        return completed.stdout

    def _is_environment_quota_error(
        self,
        exc: Exception,
    ) -> bool:
        message = str(exc)

        quota_error_markers = [
            "MaxNumberOfRegionalEnvironmentsInSubExceeded",
            "cannot have more than",
            "Managed Environment Count",
            "quota",
        ]

        return any(marker.lower() in message.lower() for marker in quota_error_markers)

    def _extract_resource_group_from_id(
        self,
        resource_id: str,
    ) -> str | None:
        parts = [part for part in resource_id.split("/") if part]

        for index, part in enumerate(parts):
            if part.lower() == "resourcegroups" and index + 1 < len(parts):
                return parts[index + 1]

        return None

    def _normalize_location(
        self,
        value: str | None,
    ) -> str:
        if not value:
            return ""

        return value.lower().replace(" ", "")

    def _nested_get(
        self,
        source: Any,
        keys: list[Any],
    ) -> Any:
        current: Any = source

        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
                continue

            if isinstance(current, list) and isinstance(key, int):
                if 0 <= key < len(current):
                    current = current[key]
                    continue

                return None

            return None

        return current

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

    def _normalize_name(
        self,
        value: str,
    ) -> str:
        value = value.lower().strip()
        value = value.replace("_", "-")
        value = re.sub(r"[^a-z0-9-]+", "-", value)
        value = re.sub(r"-+", "-", value)
        value = value.strip("-")

        return value or "app"

    def _sanitize_azure_name(
        self,
        value: str,
        max_length: int,
    ) -> str:
        value = self._normalize_name(value)
        value = value[:max_length].strip("-")

        if not value:
            value = "cloudmind-app"

        if not value[0].isalnum():
            value = "a" + value

        if not value[-1].isalnum():
            value = value + "0"

        return value

    def _sanitize_container_name(
        self,
        value: str,
    ) -> str:
        return self._sanitize_container_app_name(value)

    def _sanitize_container_app_name(
        self,
        value: str,
    ) -> str:
        value = self._normalize_name(value)

        if not value[0].isalpha():
            if value.endswith("-app"):
                value = value[:-4].rstrip("-")

            value = f"app-{value}"

        value = self._sanitize_azure_name(value, max_length=32)

        if not value[0].isalpha():
            value = self._sanitize_azure_name(f"app-{value}", max_length=32)

        return value
