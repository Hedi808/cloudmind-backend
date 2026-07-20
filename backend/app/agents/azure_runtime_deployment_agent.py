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


class AzureRuntimeDeploymentAgent:
    """
    Phase 16 agent.

    Smart Azure runtime deployer.

    Behavior:
    - If a reusable Azure Container Apps environment already exists in the target region,
      reuse it and deploy only a new Container App.
    - If no environment exists, create one.
    - If Azure quota blocks creating a new environment, fall back to the existing one.
    - Uses az rest / ARM API to avoid fragile Azure Container Apps CLI extension behavior.
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
        health_path: str = "/health",
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
        )

        preferred_resource_group = derived["resource_group"]
        preferred_app_name = derived["app_name"]
        preferred_environment_name = derived["environment_name"]
        preferred_workspace_name = derived["workspace_name"]
        image = derived["image"]
        target_port = derived["target_port"]

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
            "elapsed_seconds": elapsed_seconds,
            "analysis": {
                "repo_name": analysis.get("repo_name"),
                "project_type": analysis.get("project_type"),
                "detected_languages": analysis.get("detected_languages", []),
                "detected_frameworks": analysis.get("detected_frameworks", []),
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

        body = {
            "location": azure_location,
            "properties": {
                "managedEnvironmentId": environment_id,
                "configuration": {
                    "activeRevisionsMode": "Single",
                    "ingress": {
                        "external": True,
                        "targetPort": target_port,
                        "transport": "auto",
                        "allowInsecure": False,
                    },
                },
                "template": {
                    "containers": [
                        {
                            "name": self._sanitize_container_name(app_name),
                            "image": image,
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
                raise RuntimeError(
                    f"Container App provisioning failed: {provisioning_state}"
                )

            time.sleep(10)

        raise TimeoutError(
            f"Timed out waiting for Container App {app_name}. "
            f"Last result: {last_result}"
        )

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
    ) -> dict[str, Any]:
        owner = self._github_owner(repo_url)
        repo_name = analysis.get("repo_name") or self._repo_name(repo_url)
        repo_slug = self._sanitize_azure_name(repo_name, max_length=24)

        component = self._first_component(analysis)
        component_name = self._normalize_name(
            component.get("name") or component.get("type") or "backend"
        )

        derived_app_name = self._sanitize_azure_name(
            app_name or f"{repo_slug}-{component_name}",
            max_length=32,
        )

        derived_resource_group = self._sanitize_azure_name(
            resource_group or f"rg-cloudmind-{repo_slug}",
            max_length=60,
        )

        derived_environment_name = self._sanitize_azure_name(
            environment_name or f"cae-cloudmind-{repo_slug}",
            max_length=60,
        )

        workspace_name = self._sanitize_azure_name(
            f"log-cloudmind-{repo_slug}",
            max_length=60,
        )

        derived_image = image or (
            f"ghcr.io/{owner.lower()}/{repo_slug}-{component_name}:latest"
        )

        derived_target_port = target_port or int(component.get("port") or 8000)

        return {
            "owner": owner,
            "repo_slug": repo_slug,
            "component_name": component_name,
            "image": derived_image,
            "resource_group": derived_resource_group,
            "app_name": derived_app_name,
            "environment_name": derived_environment_name,
            "workspace_name": workspace_name,
            "target_port": derived_target_port,
        }

    def _first_component(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        components = analysis.get("components", [])

        if components and isinstance(components[0], dict):
            return components[0]

        return {
            "type": "backend",
            "port": 8000,
        }

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
        source: dict[str, Any],
        keys: list[str],
    ) -> Any:
        current: Any = source

        for key in keys:
            if not isinstance(current, dict):
                return None

            current = current.get(key)

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
        return self._sanitize_azure_name(value, max_length=32)