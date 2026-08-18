from __future__ import annotations

import re
from typing import Any

from app.agents.observability_agent import ObservabilityAgent


class IncidentResponseAgent:
    """
    Phase 20I agent.

    Responsibilities:
    - consume Azure Container Apps status
    - consume Azure Container Apps logs
    - detect real incidents
    - classify severity
    - identify likely causes
    - recommend safe remediation actions
    - mark risky actions as requiring human approval

    Important behavior:
    - A successful public health check is the strongest positive signal.
    - Normal startup logs and "connected" messages are not dependency failures.
    - Dependency failures are detected only from explicit negative patterns.
    - This agent does NOT automatically modify cloud infrastructure.
    """

    def __init__(self) -> None:
        self.observability_agent = ObservabilityAgent()

    def analyze_azure_incident(
        self,
        resource_group: str,
        app_name: str,
        health_path: str = "/health",
        timeout_seconds: int = 60,
        log_tail: int = 100,
    ) -> dict[str, Any]:
        resource_group = resource_group.strip()
        app_name = app_name.strip()

        if not resource_group or not app_name:
            return {
                "status": "failed",
                "message": "resource_group and app_name are required.",
                "incident_detected": False,
                "severity": "unknown",
                "health_path": health_path,
                "recommendations": [
                    "Provide the Azure resource group and Container App name.",
                ],
            }

        status_result = self.observability_agent.check_azure_container_app_status(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
        )

        logs_result = self.observability_agent.get_azure_container_app_logs(
            resource_group=resource_group,
            app_name=app_name,
            tail=log_tail,
        )

        return self.analyze_observability_data(
            status_result=status_result,
            logs_result=logs_result,
            context={
                "platform": "azure_container_apps",
                "resource_group": resource_group,
                "app_name": app_name,
                "health_path": health_path,
            },
        )

    def analyze_observability_data(
        self,
        status_result: dict[str, Any],
        logs_result: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        logs_result = logs_result or {}

        status_findings = self._analyze_status(status_result)
        log_findings = self._analyze_logs(logs_result)

        status_is_healthy = self._status_result_is_healthy(status_result)

        findings = []
        likely_causes = []
        recommended_actions = []
        evidence = []
        risk_notes = []

        findings.extend(status_findings["findings"])
        findings.extend(log_findings["findings"])

        likely_causes.extend(status_findings["likely_causes"])
        likely_causes.extend(log_findings["likely_causes"])

        recommended_actions.extend(status_findings["recommended_actions"])
        recommended_actions.extend(log_findings["recommended_actions"])

        evidence.extend(status_findings["evidence"])
        evidence.extend(log_findings["evidence"])

        risk_notes.extend(status_findings["risk_notes"])
        risk_notes.extend(log_findings["risk_notes"])

        severity = self._calculate_severity(
            status_findings=status_findings,
            log_findings=log_findings,
            status_is_healthy=status_is_healthy,
        )

        incident_detected = severity in ["medium", "high", "critical"]

        if status_is_healthy and log_findings.get("severity_score", 0) < 4:
            incident_detected = False
            severity = "none"

            findings = self._remove_incident_only_findings_when_healthy(findings)

            if not findings:
                findings.append(
                    "No active incident detected. Azure status, public health check, and logs look healthy."
                )

            likely_causes = [
                "No failure cause detected from the available status and logs."
            ]

            recommended_actions = [
                {
                    "title": "Continue monitoring",
                    "description": "No remediation action is required right now.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            ]

        if not incident_detected and not findings:
            findings.append(
                "No active incident detected. Azure status, health check, and logs look healthy."
            )

        if not likely_causes:
            likely_causes.append(
                "No failure cause detected from the available status and logs."
            )

        if not recommended_actions:
            recommended_actions.append(
                {
                    "title": "Continue monitoring",
                    "description": "No remediation action is required right now.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            )

        summary = self._build_summary(
            incident_detected=incident_detected,
            severity=severity,
            findings=findings,
            context=context,
        )

        return {
            "status": "incident_detected" if incident_detected else "healthy",
            "message": summary,
            "incident_detected": incident_detected,
            "severity": severity,
            "context": context,
            "health_path": context.get("health_path"),
            "summary": summary,
            "findings": self._deduplicate_strings(findings),
            "likely_causes": self._deduplicate_strings(likely_causes),
            "recommended_actions": self._deduplicate_actions(recommended_actions),
            "human_approval_required": self._requires_human_approval(recommended_actions),
            "safe_to_auto_fix": False,
            "evidence": self._deduplicate_strings(evidence),
            "risk_notes": self._deduplicate_strings(risk_notes),
            "raw": {
                "status_result": status_result,
                "logs_result": logs_result,
                "status_findings": status_findings,
                "log_findings": log_findings,
            },
        }

    def _analyze_status(
        self,
        status_result: dict[str, Any],
    ) -> dict[str, Any]:
        findings = []
        likely_causes = []
        recommended_actions = []
        evidence = []
        risk_notes = []
        severity_score = 0

        outer_status = status_result.get("status")
        result = status_result.get("result", status_result)

        healthy = self._status_result_is_healthy(status_result)
        azure = result.get("azure", {}) or {}
        health = result.get("health", {}) or {}
        revisions = result.get("revisions", {}) or {}

        provisioning_state = (
            azure.get("provisioning_state")
            or azure.get("provisioningState")
        )
        running_status = (
            azure.get("running_status")
            or azure.get("runningStatus")
        )
        latest_ready_revision_name = (
            azure.get("latest_ready_revision_name")
            or azure.get("latestReadyRevisionName")
        )
        latest_revision_name = (
            azure.get("latest_revision_name")
            or azure.get("latestRevisionName")
        )
        fqdn = azure.get("fqdn")
        target_port = azure.get("target_port")
        min_replicas = azure.get("min_replicas")
        max_replicas = azure.get("max_replicas")

        if result.get("azure_verified") is False:
            endpoint_healthy = result.get("endpoint_healthy") is True
            verification_status = result.get("status") or outer_status or "unknown"

            findings.append(
                "Azure control-plane status could not be verified by CloudMind."
            )
            likely_causes.append(
                result.get("message")
                or "Azure CLI authentication or permissions prevented the status lookup."
            )
            evidence.append(f"azure_verification_status={verification_status}")

            if endpoint_healthy:
                findings.append("The public application health endpoint is healthy.")
                evidence.append(
                    self._format_health_evidence(
                        health=result.get("health") or {},
                        azure=azure,
                    )
                )
                risk_notes.append(
                    "The app is publicly healthy, but Azure metadata and revision state remain unverified."
                )

            recommended_actions.append(
                {
                    "title": "Restore Azure control-plane access",
                    "description": "Refresh Azure CLI authentication or permissions, then retry status and log collection.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            )

            return {
                "severity_score": 0 if endpoint_healthy else 1,
                "findings": findings,
                "likely_causes": likely_causes,
                "recommended_actions": recommended_actions,
                "evidence": evidence,
                "risk_notes": risk_notes,
            }

        if healthy:
            findings.append(
                "Azure Container App public health check is healthy."
            )
            evidence.append(
                self._format_health_evidence(health=health, azure=azure)
            )

            if provisioning_state:
                evidence.append(f"provisioning_state={provisioning_state}")

            if running_status:
                evidence.append(f"running_status={running_status}")

            if latest_ready_revision_name or latest_revision_name:
                evidence.append(
                    f"revision={latest_ready_revision_name or latest_revision_name}"
                )

        if outer_status in ["failed", "not_found"]:
            severity_score = max(severity_score, 4)
            findings.append(
                "CloudMind could not read the Azure Container App status."
            )
            likely_causes.append(
                "The resource group or app name may be wrong, or Azure permissions may be missing."
            )
            evidence.append(
                f"Status endpoint returned status={outer_status}."
            )
            recommended_actions.append(
                {
                    "title": "Verify Azure resource identifiers",
                    "description": "Check that the resource group and Container App name are correct.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            )

        if provisioning_state and provisioning_state != "Succeeded":
            severity_score = max(severity_score, 4)
            findings.append(
                "Azure provisioning state is not Succeeded."
            )
            likely_causes.append(
                "The Azure deployment may have failed or may still be incomplete."
            )
            evidence.append(
                f"provisioning_state={provisioning_state}"
            )
            recommended_actions.append(
                {
                    "title": "Inspect Azure deployment events",
                    "description": "Open the Container App in Azure Portal and inspect deployment/events for the failed provisioning reason.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            )

        if running_status and running_status not in ["Running", "Ready"]:
            severity_score = max(severity_score, 3)
            findings.append(
                "Azure running status is not Running."
            )
            likely_causes.append(
                "The container may not be active, ready, or reachable."
            )
            evidence.append(
                f"running_status={running_status}"
            )
            recommended_actions.append(
                {
                    "title": "Check active revision",
                    "description": "Verify that the latest revision is active and receiving 100% traffic.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            )

        if not healthy and not latest_ready_revision_name:
            severity_score = max(severity_score, 4)
            findings.append(
                "No latest ready revision was detected."
            )
            likely_causes.append(
                "The container may be failing before becoming ready."
            )
            evidence.append(
                "latest_ready_revision_name is missing."
            )
            recommended_actions.append(
                {
                    "title": "Review startup logs",
                    "description": "Check logs for startup failures, missing dependencies, or wrong application command.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            )

        if not healthy and not fqdn:
            severity_score = max(severity_score, 3)
            findings.append(
                "No public FQDN was found for the app."
            )
            likely_causes.append(
                "External ingress may be disabled."
            )
            evidence.append(
                "fqdn is missing."
            )
            recommended_actions.append(
                {
                    "title": "Enable or verify ingress",
                    "description": "Verify that external ingress is enabled and that the target port is correct.",
                    "risk": "medium",
                    "requires_human_approval": True,
                    "safe_to_auto_fix": False,
                }
            )

        if result.get("healthy") is False and not healthy:
            severity_score = max(severity_score, 3)
            findings.append(
                "The public health check is not healthy."
            )
            likely_causes.append(
                "The app may be slow to wake up, listening on the wrong port, or failing to serve the health endpoint."
            )
            evidence.append(
                f"health={health}"
            )

            health_message = str(health.get("message", "")).lower()

            if "timed out" in health_message:
                recommended_actions.append(
                    {
                        "title": "Retry with longer timeout",
                        "description": "Because min_replicas may be 0, the first request after idle can be slow. Retry with timeout_seconds=60.",
                        "risk": "low",
                        "requires_human_approval": False,
                        "safe_to_auto_fix": False,
                    }
                )

                if min_replicas == 0:
                    recommended_actions.append(
                        {
                            "title": "Consider min replicas 1 for production",
                            "description": "Set min_replicas=1 only for production apps that must avoid cold starts. This increases cost.",
                            "risk": "medium",
                            "requires_human_approval": True,
                            "safe_to_auto_fix": False,
                        }
                    )

            recommended_actions.append(
                {
                    "title": "Verify health endpoint",
                    "description": "Open the app URL and the configured health endpoint in the browser and confirm it returns HTTP 200.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            )

        status_code = health.get("status_code")

        if status_code and not (200 <= int(status_code) < 400):
            severity_score = max(severity_score, 3)
            findings.append(
                "The health endpoint returned a non-success HTTP status code."
            )
            likely_causes.append(
                "The application route may be missing, returning an error, or protected by middleware."
            )
            evidence.append(
                f"health_status_code={status_code}"
            )
            recommended_actions.append(
                {
                    "title": "Fix health route",
                    "description": "Ensure the app exposes the expected health path and returns HTTP 200.",
                    "risk": "medium",
                    "requires_human_approval": True,
                    "safe_to_auto_fix": False,
                }
            )

        if revisions and revisions.get("status") != "success":
            if healthy:
                risk_notes.append(
                    "CloudMind could not retrieve revision details, but the public health check passed."
                )
            else:
                severity_score = max(severity_score, 2)
                findings.append(
                    "CloudMind could not retrieve revision details."
                )
                likely_causes.append(
                    "Azure permissions or revision API access may be limited."
                )
                evidence.append(
                    f"revisions={revisions}"
                )

        if min_replicas == 0:
            risk_notes.append(
                "min_replicas=0 is cost-friendly but can cause cold starts after idle periods."
            )

        if max_replicas == 1:
            risk_notes.append(
                "max_replicas=1 is cost-friendly but limits high-availability and scaling."
            )

        if target_port:
            risk_notes.append(
                f"Target port is {target_port}. Verify it matches the application container port."
            )

        return {
            "severity_score": severity_score,
            "findings": findings,
            "likely_causes": likely_causes,
            "recommended_actions": recommended_actions,
            "evidence": evidence,
            "risk_notes": risk_notes,
        }

    def _analyze_logs(
        self,
        logs_result: dict[str, Any],
    ) -> dict[str, Any]:
        findings = []
        likely_causes = []
        recommended_actions = []
        evidence = []
        risk_notes = []
        severity_score = 0

        if not logs_result:
            risk_notes.append(
                "No logs were provided to the incident analyzer."
            )
            recommended_actions.append(
                {
                    "title": "Retrieve logs",
                    "description": "Run the observability logs endpoint before deeper incident diagnosis.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            )

            return {
                "severity_score": 0,
                "findings": findings,
                "likely_causes": likely_causes,
                "recommended_actions": recommended_actions,
                "evidence": evidence,
                "risk_notes": risk_notes,
            }

        result = logs_result.get("result", logs_result)
        logs_status = result.get("status")
        logs = result.get("logs")

        if logs_status == "failed":
            risk_notes.append(
                "CloudMind could not retrieve application logs."
            )
            evidence.append(
                str(result.get("message", "Logs retrieval failed."))
            )
            recommended_actions.append(
                {
                    "title": "Verify Log Analytics",
                    "description": "Open Azure Portal and verify that the Container Apps environment is connected to Log Analytics.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            )

            return {
                "severity_score": 1,
                "findings": findings,
                "likely_causes": likely_causes,
                "recommended_actions": recommended_actions,
                "evidence": evidence,
                "risk_notes": risk_notes,
            }

        normalized_logs = self._normalize_logs(logs)

        if not normalized_logs:
            risk_notes.append(
                "No recent logs were returned. This can be normal if the app has not emitted logs recently or Log Analytics ingestion is delayed."
            )
            recommended_actions.append(
                {
                    "title": "Generate traffic and retry logs",
                    "description": "Open the app URL and the configured health endpoint, wait a few seconds, then retry logs.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            )

            return {
                "severity_score": 0,
                "findings": findings,
                "likely_causes": likely_causes,
                "recommended_actions": recommended_actions,
                "evidence": evidence,
                "risk_notes": risk_notes,
            }

        normal_log_count = 0

        for log_item in normalized_logs:
            log_text = log_item.get("text", "")
            lower = log_text.lower()
            reason = str(log_item.get("reason", "")).lower()
            timestamp = log_item.get("timestamp")
            source_type = log_item.get("type")

            if self._is_benign_log(lower=lower, reason=reason):
                normal_log_count += 1
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )
                continue

            if self._is_image_pull_failure(lower):
                severity_score = max(severity_score, 5)
                findings.append(
                    "Image pull failure detected in logs."
                )
                likely_causes.append(
                    "Azure could not pull the container image from GHCR. The image may be private, missing, or the registry credentials may be wrong."
                )
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )
                recommended_actions.append(
                    {
                        "title": "Fix container registry access",
                        "description": "Verify the GHCR image exists, the tag is correct, and the Azure Container App has valid registry credentials.",
                        "risk": "high",
                        "requires_human_approval": True,
                        "safe_to_auto_fix": False,
                    }
                )
                continue

            if self._is_dependency_failure(lower):
                severity_score = max(severity_score, 3)
                findings.append(
                    "Dependency connection failure detected."
                )
                likely_causes.append(
                    "The app may be unable to reach a database, API, or internal service."
                )
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )
                recommended_actions.append(
                    {
                        "title": "Verify external dependencies",
                        "description": "Check environment variables, network access, database URLs, and service credentials.",
                        "risk": "medium",
                        "requires_human_approval": True,
                        "safe_to_auto_fix": False,
                    }
                )
                continue

            if self._is_missing_dependency_error(lower):
                severity_score = max(severity_score, 4)
                findings.append(
                    "Missing dependency or import failure detected."
                )
                likely_causes.append(
                    "The Docker image may have been built without a needed dependency, or the code imports a package that is not installed."
                )
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )
                recommended_actions.append(
                    {
                        "title": "Update dependencies",
                        "description": "Add the missing dependency to the package manifest, rebuild the Docker image, and redeploy through CI/CD.",
                        "risk": "medium",
                        "requires_human_approval": True,
                        "safe_to_auto_fix": False,
                    }
                )
                continue

            if self._is_application_exception(lower):
                severity_score = max(severity_score, 4)
                findings.append(
                    "Application exception detected in logs."
                )
                likely_causes.append(
                    "The application is throwing runtime errors during startup or request handling."
                )
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )
                recommended_actions.append(
                    {
                        "title": "Inspect stack trace",
                        "description": "Review the stack trace, reproduce locally, fix the code, then redeploy through a pull request.",
                        "risk": "medium",
                        "requires_human_approval": True,
                        "safe_to_auto_fix": False,
                    }
                )
                continue

            if self._is_port_binding_failure(lower):
                severity_score = max(severity_score, 4)
                findings.append(
                    "Port binding issue detected."
                )
                likely_causes.append(
                    "The app may be trying to bind to a wrong or unavailable port."
                )
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )
                recommended_actions.append(
                    {
                        "title": "Verify application port",
                        "description": "Ensure the app listens on 0.0.0.0 and on the same port configured in Azure ingress.",
                        "risk": "medium",
                        "requires_human_approval": True,
                        "safe_to_auto_fix": False,
                    }
                )
                continue

            if self._is_oom_failure(lower):
                severity_score = max(severity_score, 5)
                findings.append(
                    "Out-of-memory failure detected."
                )
                likely_causes.append(
                    "The container may not have enough memory for the application workload."
                )
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )
                recommended_actions.append(
                    {
                        "title": "Increase memory limit",
                        "description": "Increase Container App memory only after confirming the memory requirement. This may increase cost.",
                        "risk": "high",
                        "requires_human_approval": True,
                        "safe_to_auto_fix": False,
                    }
                )
                continue

            if self._is_crash_loop(lower):
                severity_score = max(severity_score, 5)
                findings.append(
                    "Crash loop detected."
                )
                likely_causes.append(
                    "The container repeatedly starts and fails."
                )
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )
                recommended_actions.append(
                    {
                        "title": "Rollback or fix startup failure",
                        "description": "Rollback to the last healthy image or fix the startup error, then redeploy through CI/CD.",
                        "risk": "high",
                        "requires_human_approval": True,
                        "safe_to_auto_fix": False,
                    }
                )
                continue

        if severity_score == 0:
            findings.append(
                "Logs show normal startup/runtime behavior."
            )
            likely_causes.append(
                "No incident cause detected in recent logs."
            )

            if normal_log_count:
                evidence.append(
                    f"Normal log lines inspected: {normal_log_count}"
                )

        return {
            "severity_score": severity_score,
            "findings": findings,
            "likely_causes": likely_causes,
            "recommended_actions": recommended_actions,
            "evidence": evidence,
            "risk_notes": risk_notes,
        }

    def _normalize_logs(
        self,
        logs: Any,
    ) -> list[dict[str, Any]]:
        normalized = []

        if not isinstance(logs, list):
            return normalized

        for item in logs:
            if isinstance(item, str):
                normalized.append(
                    {
                        "timestamp": None,
                        "type": None,
                        "container_app_name": None,
                        "revision_name": None,
                        "text": item,
                        "reason": "",
                    }
                )
                continue

            if not isinstance(item, dict):
                continue

            log_text = (
                item.get("Log")
                or item.get("Message")
                or item.get("message")
                or item.get("log")
                or item.get("text")
                or ""
            )

            normalized.append(
                {
                    "timestamp": (
                        item.get("TimeGenerated")
                        or item.get("TimeStamp")
                        or item.get("time")
                        or item.get("timestamp")
                    ),
                    "type": item.get("Type") or item.get("type"),
                    "container_app_name": item.get("ContainerAppName") or item.get("ContainerAppName_s"),
                    "revision_name": item.get("RevisionName") or item.get("RevisionName_s"),
                    "text": str(log_text),
                    "reason": item.get("Reason") or item.get("Reason_s") or "",
                }
            )

        return normalized

    def _status_result_is_healthy(
        self,
        status_result: dict[str, Any],
    ) -> bool:
        if status_result.get("healthy") is True:
            return True

        status = str(status_result.get("status", "")).lower()

        if status in {"healthy", "success", "completed", "verification_passed"}:
            return True

        result = status_result.get("result")

        if isinstance(result, dict):
            if result.get("healthy") is True:
                return True

            nested_status = str(result.get("status", "")).lower()

            if nested_status in {"healthy", "success", "completed", "verification_passed"}:
                return True

            health = result.get("health")

            if isinstance(health, dict) and self._health_dict_is_healthy(health):
                return True

        health = status_result.get("health")

        if isinstance(health, dict) and self._health_dict_is_healthy(health):
            return True

        return False

    def _health_dict_is_healthy(
        self,
        health: dict[str, Any],
    ) -> bool:
        if health.get("healthy") is True:
            return True

        status = str(health.get("status", "")).lower()

        if status in {"healthy", "success", "completed"}:
            return True

        status_code = health.get("status_code")

        if status_code is not None:
            try:
                return 200 <= int(status_code) < 400
            except (TypeError, ValueError):
                return False

        return False

    def _format_health_evidence(
        self,
        health: dict[str, Any],
        azure: dict[str, Any],
    ) -> str:
        url = health.get("url")
        status_code = health.get("status_code")
        response_preview = (
            health.get("response_preview")
            or health.get("body_preview")
            or ""
        )

        parts = []

        if url:
            parts.append(f"health_url={url}")

        if status_code:
            parts.append(f"status_code={status_code}")

        if response_preview:
            parts.append(f"response_preview={str(response_preview)[:160]}")

        fqdn = azure.get("fqdn")

        if fqdn:
            parts.append(f"fqdn={fqdn}")

        return "; ".join(parts) if parts else "Health check returned a successful result."

    def _is_benign_log(
        self,
        lower: str,
        reason: str,
    ) -> bool:
        benign_phrases = [
            "connecting to the container",
            "successfully connected to container",
            "successfully connected",
            "connected to container",
            "backend is connected",
            "the node.js backend is connected",
            "is running at http://localhost",
            "via-vai-fullstack",
            "npm start",
            "node backend/server.js",
            "application startup complete",
            "server started",
            "listening on",
            "started server",
            "health endpoint responded successfully",
            "get /health",
            "get /api/status",
            "200 ok",
            "successfully pulled image",
            "pulled image",
        ]

        if any(phrase in lower for phrase in benign_phrases):
            return True

        if "containerterminated" in reason and "manuallystopped" in lower:
            return True

        if "kedascaltargetdeactivated" in reason:
            return True

        if "kedascale" in lower:
            return True

        return False

    def _is_image_pull_failure(
        self,
        lower: str,
    ) -> bool:
        patterns = [
            r"\bimagepullbackoff\b",
            r"\berrimagepull\b",
            r"failed\s+to\s+pull\s+image",
            r"\bmanifest\s+unknown\b",
            r"\bunauthorized\b.*\b(ghcr|registry|image|pull)\b",
            r"\bauthentication\s+required\b.*\b(ghcr|registry|image|pull)\b",
            r"\bdenied\b.*\b(ghcr|registry|image|pull)\b",
        ]

        return self._matches_any_regex(lower, patterns)

    def _is_dependency_failure(
        self,
        lower: str,
    ) -> bool:
        if self._is_positive_connection_log(lower):
            return False

        patterns = [
            r"\beconnrefused\b",
            r"\betimedout\b",
            r"\benotfound\b",
            r"\bconnection\s+refused\b",
            r"\bconnection\s+timed\s+out\b",
            r"\bconnect\s+econnrefused\b",
            r"\bconnect\s+etimedout\b",
            r"\bfailed\s+to\s+connect\b",
            r"\bcould\s+not\s+connect\b",
            r"\bunable\s+to\s+connect\b",
            r"\bdatabase\s+unavailable\b",
            r"\bdatabase\s+connection\s+failed\b",
            r"\bdns\s+lookup\s+failed\b",
            r"\bgetaddrinfo\s+enotfound\b",
            r"\bauthentication\s+failed\b",
            r"\blogin\s+failed\b",
        ]

        return self._matches_any_regex(lower, patterns)

    def _is_positive_connection_log(
        self,
        lower: str,
    ) -> bool:
        positive_patterns = [
            "successfully connected",
            "connected to container",
            "backend is connected",
            "node.js backend is connected",
            "database connected",
            "connected successfully",
            "connection established",
        ]

        return any(pattern in lower for pattern in positive_patterns)

    def _is_missing_dependency_error(
        self,
        lower: str,
    ) -> bool:
        patterns = [
            r"\bno\s+module\s+named\b",
            r"\bmodulenotfounderror\b",
            r"\bimporterror\b",
            r"\bcannot\s+import\s+name\b",
            r"\berr_module_not_found\b",
            r"\bcannot\s+find\s+module\b",
            r"\bmodule\s+not\s+found\b",
        ]

        return self._matches_any_regex(lower, patterns)

    def _is_application_exception(
        self,
        lower: str,
    ) -> bool:
        if "no exception" in lower:
            return False

        patterns = [
            r"\btraceback\b",
            r"\bunhandled\s+exception\b",
            r"\bfatal\s+exception\b",
            r"\bruntimeerror\b",
            r"\bvalueerror\b",
            r"\btypeerror\b",
            r"\bsyntaxerror\b",
            r"\breferenceerror\b",
            r"\bunhandledrejection\b",
        ]

        return self._matches_any_regex(lower, patterns)

    def _is_port_binding_failure(
        self,
        lower: str,
    ) -> bool:
        patterns = [
            r"\baddress\s+already\s+in\s+use\b",
            r"\beaddrinuse\b",
            r"\bport\s+already\s+allocated\b",
            r"\bfailed\s+to\s+bind\b",
            r"\bcannot\s+bind\b",
            r"\bbind\s+eacces\b",
        ]

        return self._matches_any_regex(lower, patterns)

    def _is_oom_failure(
        self,
        lower: str,
    ) -> bool:
        patterns = [
            r"\boomkilled\b",
            r"\bout\s+of\s+memory\b",
            r"\bmemory\s+limit\s+exceeded\b",
            r"\bjavascript\s+heap\s+out\s+of\s+memory\b",
        ]

        return self._matches_any_regex(lower, patterns)

    def _is_crash_loop(
        self,
        lower: str,
    ) -> bool:
        patterns = [
            r"\bcrashloopbackoff\b",
            r"\bback-off\s+restarting\s+failed\s+container\b",
            r"\bcontainer\s+restarted\s+repeatedly\b",
        ]

        return self._matches_any_regex(lower, patterns)

    def _matches_any_regex(
        self,
        text: str,
        patterns: list[str],
    ) -> bool:
        return any(re.search(pattern, text) for pattern in patterns)

    def _calculate_severity(
        self,
        status_findings: dict[str, Any],
        log_findings: dict[str, Any],
        status_is_healthy: bool = False,
    ) -> str:
        status_score = status_findings.get("severity_score", 0)
        log_score = log_findings.get("severity_score", 0)

        if status_is_healthy and log_score < 4:
            score = 0
        else:
            score = max(status_score, log_score)

        if score >= 5:
            return "critical"

        if score == 4:
            return "high"

        if score == 3:
            return "medium"

        if score == 2:
            return "low"

        return "none"

    def _remove_incident_only_findings_when_healthy(
        self,
        findings: list[str],
    ) -> list[str]:
        removed_phrases = [
            "Dependency connection failure detected.",
            "The public health check is not healthy.",
            "The health endpoint returned a non-success HTTP status code.",
            "CloudMind could not retrieve revision details.",
        ]

        return [
            finding
            for finding in findings
            if finding not in removed_phrases
        ]

    def _build_summary(
        self,
        incident_detected: bool,
        severity: str,
        findings: list[str],
        context: dict[str, Any],
    ) -> str:
        app_name = context.get("app_name", "application")
        health_path = context.get("health_path")

        if incident_detected:
            return (
                f"Incident detected for {app_name}. "
                f"Severity: {severity}. "
                f"Main finding: {findings[0] if findings else 'Unknown issue.'}"
            )

        if health_path:
            return (
                f"No active incident detected for {app_name}. "
                f"The app appears healthy based on Azure status, logs, and health path {health_path}."
            )

        return (
            f"No active incident detected for {app_name}. "
            "The app appears healthy based on the available Azure status and logs."
        )

    def _requires_human_approval(
        self,
        recommended_actions: list[dict[str, Any]],
    ) -> bool:
        for action in recommended_actions:
            if action.get("requires_human_approval") is True:
                return True

        return False

    def _format_log_evidence(
        self,
        timestamp: Any,
        source_type: Any,
        log_text: str,
    ) -> str:
        timestamp_text = str(timestamp) if timestamp else "unknown time"
        source_text = str(source_type) if source_type else "unknown source"

        return f"[{timestamp_text}] [{source_text}] {log_text}"

    def _deduplicate_strings(
        self,
        items: list[str],
    ) -> list[str]:
        seen = set()
        result = []

        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)

        return result

    def _deduplicate_actions(
        self,
        actions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        seen = set()
        result = []

        for action in actions:
            key = action.get("title", "") + action.get("description", "")

            if key not in seen:
                seen.add(key)
                result.append(action)

        return result
