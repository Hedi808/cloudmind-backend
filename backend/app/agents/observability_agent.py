import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


class ObservabilityAgent:
    """
    Phase 8 agent.

    Responsibilities:
    - check public application health endpoints
    - inspect Azure Container Apps status using Azure CLI + Azure REST
    - retrieve Azure Container Apps logs using Log Analytics REST API
    - avoid broken local Azure CLI extensions by using a clean extension directory
    - return safe diagnostic recommendations
    """

    CONTAINER_APPS_API_VERSION = "2023-05-01"
    LOG_ANALYTICS_API_URL = "https://api.loganalytics.io/v1/workspaces"
    LOG_ANALYTICS_RESOURCE = "https://api.loganalytics.io"
    HTTP_TIMEOUT_SECONDS = 30

    def check_http_health(
        self,
        base_url: str,
        health_path: str = "/health",
        timeout_seconds: int = 10,
    ) -> dict[str, Any]:
        base_url = base_url.strip()

        if not base_url:
            return {
                "status": "failed",
                "message": "Base URL is required.",
                "healthy": False,
                "url": None,
                "recommendations": [
                    "Provide the deployed application URL.",
                ],
            }

        if not base_url.startswith("http://") and not base_url.startswith("https://"):
            base_url = f"https://{base_url}"

        health_path = health_path or "/health"

        if not health_path.startswith("/"):
            health_path = f"/{health_path}"

        url = urljoin(base_url.rstrip("/") + "/", health_path.lstrip("/"))

        try:
            response = requests.get(
                url,
                timeout=timeout_seconds,
                allow_redirects=True,
            )

            healthy = 200 <= response.status_code < 400

            recommendations = []

            if not healthy:
                recommendations.append(
                    "The health endpoint returned a non-success status code. "
                    "Check application logs and container startup configuration."
                )

            return {
                "status": "healthy" if healthy else "unhealthy",
                "message": "Health check completed.",
                "healthy": healthy,
                "url": url,
                "status_code": response.status_code,
                "response_time_seconds": response.elapsed.total_seconds(),
                "response_preview": response.text[:1000],
                "recommendations": recommendations,
            }

        except requests.Timeout:
            return {
                "status": "unhealthy",
                "message": "Health check timed out.",
                "healthy": False,
                "url": url,
                "status_code": None,
                "response_time_seconds": None,
                "response_preview": None,
                "recommendations": [
                    "The app did not respond before the timeout. Check whether the app is running and whether ingress is enabled.",
                    "If the app scales to zero, wait a few seconds and retry because the first request may be slower.",
                ],
            }

        except requests.RequestException as exc:
            return {
                "status": "unhealthy",
                "message": f"Health check failed: {exc}",
                "healthy": False,
                "url": url,
                "status_code": None,
                "response_time_seconds": None,
                "response_preview": None,
                "recommendations": [
                    "Verify that the application URL is correct.",
                    "Verify that Azure Container Apps ingress is enabled.",
                    "Check Azure Container Apps logs for startup errors.",
                ],
            }

    def check_azure_container_app_status(
        self,
        resource_group: str,
        app_name: str,
        health_path: str = "/health",
        timeout_seconds: int = 10,
    ) -> dict[str, Any]:
        resource_group = resource_group.strip()
        app_name = app_name.strip()

        if not resource_group or not app_name:
            return {
                "status": "failed",
                "message": "resource_group and app_name are required.",
                "healthy": False,
                "recommendations": [
                    "Provide the Azure resource group and Container App name.",
                ],
            }

        account_result = self._get_azure_account()

        if not account_result["success"]:
            return {
                "status": "failed",
                "message": "Azure CLI is not logged in or not available.",
                "healthy": False,
                "azure_cli": account_result,
                "recommendations": [
                    "Install Azure CLI if the az command is missing.",
                    "Run az login in PowerShell.",
                    "Run az account show to verify the active subscription.",
                ],
            }

        subscription_id = account_result["subscription_id"]

        app_result = self._get_container_app_with_rest(
            subscription_id=subscription_id,
            resource_group=resource_group,
            app_name=app_name,
        )

        if not app_result["success"]:
            return {
                "status": "not_found",
                "message": "Azure Container App was not found or could not be read.",
                "healthy": False,
                "resource_group": resource_group,
                "app_name": app_name,
                "azure_cli": app_result,
                "recommendations": [
                    "Verify the resource group name.",
                    "Verify the Container App name.",
                    "Run the Azure deployment script again after registering Microsoft.App and Microsoft.OperationalInsights providers.",
                ],
            }

        try:
            app_data = json.loads(app_result["stdout"])
        except json.JSONDecodeError:
            return {
                "status": "failed",
                "message": "Azure REST returned invalid JSON.",
                "healthy": False,
                "resource_group": resource_group,
                "app_name": app_name,
                "raw_output": app_result["stdout"][:2000],
                "recommendations": [
                    "Run the generated az rest command manually and inspect the output.",
                ],
            }

        parsed = self._parse_container_app(app_data)

        health_result = None

        if parsed["fqdn"]:
            health_result = self.check_http_health(
                base_url=f"https://{parsed['fqdn']}",
                health_path=health_path,
                timeout_seconds=timeout_seconds,
            )

        revision_result = self._get_revisions_with_rest(
            subscription_id=subscription_id,
            resource_group=resource_group,
            app_name=app_name,
        )

        recommendations = self._build_status_recommendations(
            parsed=parsed,
            health_result=health_result,
            revision_result=revision_result,
        )

        healthy = (
            parsed["provisioning_state"] == "Succeeded"
            and health_result is not None
            and health_result.get("healthy") is True
        )

        return {
            "status": "healthy" if healthy else "warning",
            "message": "Azure Container App status inspected.",
            "healthy": healthy,
            "resource_group": resource_group,
            "app_name": app_name,
            "app_url": f"https://{parsed['fqdn']}" if parsed["fqdn"] else None,
            "health": health_result,
            "azure": parsed,
            "revisions": revision_result,
            "recommendations": recommendations,
        }

    def get_azure_container_app_logs(
        self,
        resource_group: str,
        app_name: str,
        tail: int = 50,
    ) -> dict[str, Any]:
        resource_group = resource_group.strip()
        app_name = app_name.strip()
        tail = max(10, min(tail, 300))

        if not resource_group or not app_name:
            return {
                "status": "failed",
                "message": "resource_group and app_name are required.",
                "logs": None,
                "recommendations": [
                    "Provide the Azure resource group and Container App name.",
                ],
            }

        return self._get_logs_from_log_analytics_rest(
            resource_group=resource_group,
            app_name=app_name,
            tail=tail,
        )

    def _get_logs_from_log_analytics_rest(
        self,
        resource_group: str,
        app_name: str,
        tail: int,
    ) -> dict[str, Any]:
        account_result = self._get_azure_account()

        if not account_result["success"]:
            return {
                "status": "failed",
                "message": "Could not retrieve logs because Azure CLI is not logged in.",
                "resource_group": resource_group,
                "app_name": app_name,
                "logs": None,
                "azure_cli": account_result,
                "recommendations": [
                    "Run az login.",
                    "Run az account show to verify the active subscription.",
                ],
            }

        subscription_id = account_result["subscription_id"]

        app_result = self._get_container_app_with_rest(
            subscription_id=subscription_id,
            resource_group=resource_group,
            app_name=app_name,
        )

        if not app_result["success"]:
            return {
                "status": "failed",
                "message": "Could not read Container App metadata using Azure REST.",
                "resource_group": resource_group,
                "app_name": app_name,
                "logs": None,
                "azure_rest_error": app_result,
                "recommendations": [
                    "Verify that the Container App exists.",
                    "Verify that the resource group name is correct.",
                ],
            }

        try:
            app_data = json.loads(app_result["stdout"])
            parsed_app = self._parse_container_app(app_data)
            environment_id = parsed_app.get("environment_id")
        except Exception:
            return {
                "status": "failed",
                "message": "Could not parse Container App environment ID.",
                "resource_group": resource_group,
                "app_name": app_name,
                "logs": None,
                "recommendations": [
                    "Inspect the Container App JSON manually and verify environmentId exists.",
                ],
            }

        if not environment_id:
            return {
                "status": "failed",
                "message": "Container App has no environment ID.",
                "resource_group": resource_group,
                "app_name": app_name,
                "logs": None,
                "recommendations": [
                    "Verify the Container App environment exists.",
                ],
            }

        environment_result = self._get_managed_environment_with_rest(
            environment_id=environment_id,
        )

        if not environment_result["success"]:
            return {
                "status": "failed",
                "message": "Could not read Container Apps environment using Azure REST.",
                "resource_group": resource_group,
                "app_name": app_name,
                "logs": None,
                "azure_rest_error": environment_result,
                "recommendations": [
                    "Verify the Container Apps environment exists.",
                    "Verify your Azure account can read Microsoft.App managed environments.",
                ],
            }

        try:
            environment_data = json.loads(environment_result["stdout"])
            workspace_customer_id = self._extract_log_analytics_customer_id(environment_data)
        except Exception:
            workspace_customer_id = None

        if not workspace_customer_id:
            return {
                "status": "failed",
                "message": "Could not find Log Analytics workspace customer ID for this Container Apps environment.",
                "resource_group": resource_group,
                "app_name": app_name,
                "logs": None,
                "recommendations": [
                    "The Container Apps environment may not have Log Analytics configured.",
                    "Open Azure Portal > Container Apps Environment > Monitoring/Logs to verify log configuration.",
                ],
            }

        token_result = self._get_log_analytics_access_token()

        if not token_result["success"]:
            return {
                "status": "failed",
                "message": "Could not get Log Analytics access token.",
                "resource_group": resource_group,
                "app_name": app_name,
                "logs": None,
                "workspace_customer_id": workspace_customer_id,
                "azure_cli": token_result,
                "recommendations": [
                    "Run az login again.",
                    "Run az account get-access-token --resource https://api.loganalytics.io manually.",
                ],
            }

        query = self._build_container_app_logs_query(
            app_name=app_name,
            tail=tail,
        )

        query_result = self._query_log_analytics_rest(
            workspace_customer_id=workspace_customer_id,
            access_token=token_result["access_token"],
            query=query,
        )

        if not query_result["success"]:
            return {
                "status": "failed",
                "message": "Could not retrieve logs from Log Analytics REST API.",
                "resource_group": resource_group,
                "app_name": app_name,
                "logs": None,
                "workspace_customer_id": workspace_customer_id,
                "log_analytics_error": query_result,
                "recommendations": [
                    "Wait a few minutes after deployment because logs may not appear immediately.",
                    "Open Azure Portal > Log Analytics Workspace > Logs and try querying ContainerAppConsoleLogs_CL.",
                    "If this returns 403, your Azure account may need permission to query the workspace.",
                ],
            }

        parsed_logs = self._parse_log_analytics_result(query_result["body"])

        return {
            "status": "success",
            "message": "Logs retrieved successfully using Log Analytics REST API.",
            "resource_group": resource_group,
            "app_name": app_name,
            "method": "Log Analytics REST API",
            "tail": tail,
            "workspace_customer_id": workspace_customer_id,
            "logs": parsed_logs,
            "raw_output": query_result["body"],
            "recommendations": self._analyze_logs(json.dumps(parsed_logs)),
        }

    def _get_azure_account(self) -> dict[str, Any]:
        account_result = self._run_az(
            [
                "account",
                "show",
                "--output",
                "json",
            ],
            timeout_seconds=30,
        )

        if not account_result["success"]:
            return account_result

        try:
            account_data = json.loads(account_result["stdout"])
            subscription_id = account_data["id"]
        except Exception:
            return {
                "success": False,
                "exit_code": None,
                "command": account_result.get("command"),
                "stdout": account_result.get("stdout"),
                "stderr": "Could not parse subscription id from az account show.",
            }

        return {
            "success": True,
            "subscription_id": subscription_id,
            "account": account_data,
            "command": account_result.get("command"),
            "stdout": account_result.get("stdout"),
            "stderr": account_result.get("stderr"),
        }

    def _get_log_analytics_access_token(self) -> dict[str, Any]:
        token_result = self._run_az(
            [
                "account",
                "get-access-token",
                "--resource",
                self.LOG_ANALYTICS_RESOURCE,
                "--output",
                "json",
            ],
            timeout_seconds=30,
        )

        if not token_result["success"]:
            return token_result

        try:
            token_data = json.loads(token_result["stdout"])
            access_token = token_data["accessToken"]
        except Exception:
            return {
                "success": False,
                "exit_code": None,
                "command": token_result.get("command"),
                "stdout": token_result.get("stdout"),
                "stderr": "Could not parse accessToken from az account get-access-token.",
            }

        return {
            "success": True,
            "access_token": access_token,
            "command": token_result.get("command"),
            "stdout": "",
            "stderr": token_result.get("stderr"),
        }

    def _query_log_analytics_rest(
        self,
        workspace_customer_id: str,
        access_token: str,
        query: str,
    ) -> dict[str, Any]:
        url = f"{self.LOG_ANALYTICS_API_URL}/{workspace_customer_id}/query"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "query": query,
            "timespan": "PT24H",
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.HTTP_TIMEOUT_SECONDS,
            )

            success = 200 <= response.status_code < 300

            return {
                "success": success,
                "status_code": response.status_code,
                "url": url,
                "body": response.text,
                "stderr": "" if success else response.text[:2000],
            }

        except requests.Timeout:
            return {
                "success": False,
                "status_code": None,
                "url": url,
                "body": "",
                "stderr": f"Log Analytics REST request timed out after {self.HTTP_TIMEOUT_SECONDS} seconds.",
            }

        except requests.RequestException as exc:
            return {
                "success": False,
                "status_code": None,
                "url": url,
                "body": "",
                "stderr": f"Log Analytics REST request failed: {exc}",
            }

    def _build_container_app_logs_query(
        self,
        app_name: str,
        tail: int,
    ) -> str:
        safe_app_name = app_name.replace('"', "").replace("'", "")

        return (
            "union isfuzzy=true ContainerAppConsoleLogs_CL, ContainerAppSystemLogs_CL "
            "| where TimeGenerated > ago(24h) "
            f"| where tostring(column_ifexists('ContainerAppName_s', column_ifexists('ContainerAppName', ''))) == '{safe_app_name}' "
            "| sort by TimeGenerated desc "
            f"| take {tail} "
            "| project "
            "TimeGenerated, "
            "Type, "
            "ContainerAppName=tostring(column_ifexists('ContainerAppName_s', column_ifexists('ContainerAppName', ''))), "
            "RevisionName=tostring(column_ifexists('RevisionName_s', column_ifexists('RevisionName', ''))), "
            "Log=tostring(column_ifexists('Log_s', column_ifexists('Log', ''))), "
            "Reason=tostring(column_ifexists('Reason_s', column_ifexists('Reason', ''))), "
            "Message=tostring(column_ifexists('Message_s', column_ifexists('Message', '')))"
        )

    def _parse_log_analytics_result(
        self,
        raw_output: str,
    ) -> list[dict[str, Any]]:
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            return [
                {
                    "raw": raw_output[:5000],
                }
            ]

        tables = data.get("tables", [])

        if not tables:
            return []

        table = tables[0]
        columns = table.get("columns", [])
        rows = table.get("rows", [])

        column_names = [column.get("name") for column in columns]

        parsed_rows = []

        for row in rows:
            item = {}

            for index, value in enumerate(row):
                if index < len(column_names):
                    item[column_names[index]] = value
                else:
                    item[f"column_{index}"] = value

            parsed_rows.append(item)

        return parsed_rows

    def _extract_log_analytics_customer_id(
        self,
        environment_data: dict[str, Any],
    ) -> str | None:
        properties = environment_data.get("properties", {})
        app_logs_configuration = properties.get("appLogsConfiguration", {})
        log_analytics_configuration = app_logs_configuration.get("logAnalyticsConfiguration", {})

        customer_id = log_analytics_configuration.get("customerId")

        if customer_id:
            return customer_id

        return None

    def _get_container_app_with_rest(
        self,
        subscription_id: str,
        resource_group: str,
        app_name: str,
    ) -> dict[str, Any]:
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.App/containerApps/{app_name}"
            f"?api-version={self.CONTAINER_APPS_API_VERSION}"
        )

        return self._run_az(
            [
                "rest",
                "--method",
                "get",
                "--url",
                url,
                "--output",
                "json",
            ],
            timeout_seconds=60,
        )

    def _get_managed_environment_with_rest(
        self,
        environment_id: str,
    ) -> dict[str, Any]:
        url = (
            f"https://management.azure.com{environment_id}"
            f"?api-version={self.CONTAINER_APPS_API_VERSION}"
        )

        return self._run_az(
            [
                "rest",
                "--method",
                "get",
                "--url",
                url,
                "--output",
                "json",
            ],
            timeout_seconds=60,
        )

    def _get_revisions_with_rest(
        self,
        subscription_id: str,
        resource_group: str,
        app_name: str,
    ) -> dict[str, Any]:
        url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.App/containerApps/{app_name}/revisions"
            f"?api-version={self.CONTAINER_APPS_API_VERSION}"
        )

        revision_result = self._run_az(
            [
                "rest",
                "--method",
                "get",
                "--url",
                url,
                "--output",
                "json",
            ],
            timeout_seconds=60,
        )

        if not revision_result["success"]:
            return {
                "status": "failed",
                "message": "Could not list revisions using Azure REST.",
                "items": [],
                "azure_cli": revision_result,
            }

        try:
            response_data = json.loads(revision_result["stdout"])
        except json.JSONDecodeError:
            return {
                "status": "failed",
                "message": "Revision list returned invalid JSON.",
                "items": [],
                "raw_output": revision_result["stdout"][:2000],
            }

        revisions = response_data.get("value", [])

        items = []

        for revision in revisions:
            properties = revision.get("properties", {})

            items.append(
                {
                    "name": revision.get("name"),
                    "active": properties.get("active"),
                    "created_time": properties.get("createdTime"),
                    "fqdn": properties.get("fqdn"),
                    "health_state": properties.get("healthState"),
                    "provisioning_state": properties.get("provisioningState"),
                    "replicas": properties.get("replicas"),
                    "traffic_weight": properties.get("trafficWeight"),
                }
            )

        return {
            "status": "success",
            "message": "Revisions listed successfully.",
            "items": items,
        }

    def _parse_container_app(self, app_data: dict[str, Any]) -> dict[str, Any]:
        properties = app_data.get("properties", {})
        configuration = properties.get("configuration", {})
        ingress = configuration.get("ingress") or {}
        template = properties.get("template", {})

        containers = template.get("containers", []) or []

        parsed_containers = []

        for container in containers:
            parsed_containers.append(
                {
                    "name": container.get("name"),
                    "image": container.get("image"),
                    "cpu": container.get("resources", {}).get("cpu"),
                    "memory": container.get("resources", {}).get("memory"),
                }
            )

        scale = template.get("scale") or {}

        return {
            "id": app_data.get("id"),
            "name": app_data.get("name"),
            "location": app_data.get("location"),
            "provisioning_state": properties.get("provisioningState"),
            "running_status": properties.get("runningStatus"),
            "environment_id": properties.get("environmentId"),
            "latest_revision_name": properties.get("latestRevisionName"),
            "latest_ready_revision_name": properties.get("latestReadyRevisionName"),
            "active_revisions_mode": configuration.get("activeRevisionsMode"),
            "fqdn": ingress.get("fqdn"),
            "external": ingress.get("external"),
            "target_port": ingress.get("targetPort"),
            "traffic": ingress.get("traffic"),
            "min_replicas": scale.get("minReplicas"),
            "max_replicas": scale.get("maxReplicas"),
            "containers": parsed_containers,
        }

    def _build_status_recommendations(
        self,
        parsed: dict[str, Any],
        health_result: dict[str, Any] | None,
        revision_result: dict[str, Any],
    ) -> list[str]:
        recommendations = []

        if parsed["provisioning_state"] != "Succeeded":
            recommendations.append(
                "Container App provisioning is not Succeeded. Check Azure deployment events and logs."
            )

        if not parsed["fqdn"]:
            recommendations.append(
                "No public FQDN was found. Verify that ingress is enabled."
            )

        if parsed["external"] is False:
            recommendations.append(
                "Ingress exists but is not external. Enable external ingress for public access."
            )

        if not parsed["latest_ready_revision_name"]:
            recommendations.append(
                "No latest ready revision was detected. The container may be failing to start."
            )

        if health_result and not health_result.get("healthy"):
            recommendations.extend(health_result.get("recommendations", []))

        if revision_result.get("status") != "success":
            recommendations.append(
                "Revision information could not be retrieved. Check Azure CLI permissions."
            )

        if parsed.get("min_replicas") == 0:
            recommendations.append(
                "Min replicas is 0. This is cost-friendly, but first request after idle may be slower."
            )

        return recommendations

    def _analyze_logs(self, logs: str) -> list[str]:
        lower_logs = logs.lower()
        recommendations = []

        if not logs.strip() or logs == "[]":
            recommendations.append(
                "No logs returned. The app may not have produced logs recently, or logs may not be available immediately."
            )

        if "error" in lower_logs or "exception" in lower_logs or "traceback" in lower_logs:
            recommendations.append(
                "Logs contain error-like text. Review the stack trace and verify the application startup command."
            )

        if "address already in use" in lower_logs:
            recommendations.append(
                "The application may be trying to use a port that is already occupied."
            )

        if "connection refused" in lower_logs:
            recommendations.append(
                "A dependency may be unavailable or the app is trying to connect to a wrong host/port."
            )

        if "no module named" in lower_logs:
            recommendations.append(
                "A Python dependency may be missing. Check requirements.txt and rebuild the image."
            )

        if "permission denied" in lower_logs:
            recommendations.append(
                "The container may have a filesystem or user permission issue."
            )

        return recommendations

    def _run_az(
        self,
        args: list[str],
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        az_executable = self._find_azure_cli()

        if not az_executable:
            return {
                "success": False,
                "exit_code": None,
                "command": "az " + " ".join(args),
                "stdout": "",
                "stderr": (
                    "Azure CLI command was not found from the FastAPI process. "
                    "Run Get-Command az in the same PowerShell terminal used to start uvicorn, "
                    "or restart PowerShell/VS Code after installing Azure CLI."
                ),
            }

        environment = self._build_azure_cli_environment()

        return self._run_command(
            command=[az_executable] + args,
            timeout_seconds=timeout_seconds,
            environment=environment,
        )

    def _build_azure_cli_environment(self) -> dict[str, str]:
        environment = os.environ.copy()

        backend_root = Path(__file__).resolve().parents[2]
        clean_extensions_dir = backend_root / ".azure-cli-clean-extensions"
        clean_extensions_dir.mkdir(parents=True, exist_ok=True)

        environment["AZURE_EXTENSION_DIR"] = str(clean_extensions_dir)
        environment["AZURE_CORE_NO_COLOR"] = "true"

        return environment

    def _find_azure_cli(self) -> str | None:
        candidates = [
            shutil.which("az"),
            shutil.which("az.cmd"),
            shutil.which("az.exe"),
            r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
        ]

        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate

        return None

    def _run_command(
        self,
        command: list[str],
        timeout_seconds: int = 60,
        environment: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                shell=False,
                env=environment,
            )

            return {
                "success": completed.returncode == 0,
                "exit_code": completed.returncode,
                "command": " ".join(command),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }

        except FileNotFoundError:
            return {
                "success": False,
                "exit_code": None,
                "command": " ".join(command),
                "stdout": "",
                "stderr": "Azure CLI command was not found. Install Azure CLI and restart PowerShell.",
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": None,
                "command": " ".join(command),
                "stdout": "",
                "stderr": f"Command timed out after {timeout_seconds} seconds.",
            }