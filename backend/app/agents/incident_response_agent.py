from typing import Any

from app.agents.observability_agent import ObservabilityAgent


class IncidentResponseAgent:
    """
    Phase 9 agent.

    Responsibilities:
    - consume Azure Container Apps status
    - consume Azure Container Apps logs
    - detect incidents
    - classify severity
    - identify likely causes
    - recommend safe remediation actions
    - mark risky actions as requiring human approval

    This agent does NOT automatically modify cloud infrastructure.
    It only diagnoses and recommends actions.
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

        findings = []
        likely_causes = []
        recommended_actions = []
        evidence = []
        risk_notes = []

        status_findings = self._analyze_status(status_result)
        log_findings = self._analyze_logs(logs_result)

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
        )

        incident_detected = severity in ["medium", "high", "critical"]

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

        healthy = result.get("healthy")
        azure = result.get("azure", {}) or {}
        health = result.get("health", {}) or {}
        revisions = result.get("revisions", {}) or {}

        provisioning_state = azure.get("provisioning_state")
        running_status = azure.get("running_status")
        latest_ready_revision_name = azure.get("latest_ready_revision_name")
        fqdn = azure.get("fqdn")
        target_port = azure.get("target_port")
        min_replicas = azure.get("min_replicas")
        max_replicas = azure.get("max_replicas")

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

        if not latest_ready_revision_name:
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

        if not fqdn:
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

        if healthy is False:
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
                    "description": "Open the app URL and /health endpoint in the browser and confirm they return HTTP 200.",
                    "risk": "low",
                    "requires_human_approval": False,
                    "safe_to_auto_fix": False,
                }
            )

        if health.get("status_code") and not (200 <= int(health["status_code"]) < 400):
            severity_score = max(severity_score, 3)
            findings.append(
                "The health endpoint returned a non-success HTTP status code."
            )
            likely_causes.append(
                "The application route may be missing, returning an error, or protected by middleware."
            )
            evidence.append(
                f"health_status_code={health.get('status_code')}"
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

        if revisions.get("status") != "success":
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

        if target_port and target_port != 8000:
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
            findings.append(
                "No logs were provided to the incident analyzer."
            )
            recommended_actions.append(
                {
                    "title": "Retrieve logs",
                    "description": "Run the observability logs endpoint before incident diagnosis.",
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

        result = logs_result.get("result", logs_result)
        logs_status = result.get("status")
        logs = result.get("logs")

        if logs_status == "failed":
            severity_score = max(severity_score, 2)
            findings.append(
                "CloudMind could not retrieve application logs."
            )
            likely_causes.append(
                "Log Analytics may not be configured, permissions may be missing, or the query may have failed."
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
                "severity_score": severity_score,
                "findings": findings,
                "likely_causes": likely_causes,
                "recommended_actions": recommended_actions,
                "evidence": evidence,
                "risk_notes": risk_notes,
            }

        normalized_logs = self._normalize_logs(logs)

        if not normalized_logs:
            findings.append(
                "No recent logs were returned."
            )
            likely_causes.append(
                "The app may not have produced logs recently or Log Analytics ingestion may be delayed."
            )
            recommended_actions.append(
                {
                    "title": "Generate traffic and retry logs",
                    "description": "Open the app URL and /health endpoint, wait a few seconds, then retry logs.",
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

        for log_item in normalized_logs:
            log_text = log_item.get("text", "")
            lower = log_text.lower()
            reason = str(log_item.get("reason", "")).lower()
            timestamp = log_item.get("timestamp")
            source_type = log_item.get("type")

            if self._contains_any(
                lower,
                [
                    "imagepullbackoff",
                    "errimagepull",
                    "failed to pull image",
                    "unauthorized",
                    "authentication required",
                    "denied",
                    "manifest unknown",
                ],
            ):
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

            if self._contains_any(
                lower,
                [
                    "no module named",
                    "modulenotfounderror",
                    "importerror",
                    "cannot import name",
                ],
            ):
                severity_score = max(severity_score, 4)
                findings.append(
                    "Missing Python dependency or import failure detected."
                )
                likely_causes.append(
                    "requirements.txt may be missing a required dependency, or the Docker image was built without the needed package."
                )
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )
                recommended_actions.append(
                    {
                        "title": "Update dependencies",
                        "description": "Add the missing dependency to requirements.txt, rebuild the Docker image, and redeploy through CI/CD.",
                        "risk": "medium",
                        "requires_human_approval": True,
                        "safe_to_auto_fix": False,
                    }
                )

            if self._contains_any(
                lower,
                [
                    "traceback",
                    "exception",
                    "runtimeerror",
                    "valueerror",
                    "typeerror",
                    "syntaxerror",
                ],
            ):
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
                        "description": "Review the traceback, reproduce locally, fix the code, then redeploy through a pull request.",
                        "risk": "medium",
                        "requires_human_approval": True,
                        "safe_to_auto_fix": False,
                    }
                )

            if self._contains_any(
                lower,
                [
                    "address already in use",
                    "bind",
                    "port already allocated",
                ],
            ):
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

            if self._contains_any(
                lower,
                [
                    "connection refused",
                    "connection timed out",
                    "could not connect",
                    "name or service not known",
                ],
            ):
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

            if self._contains_any(
                lower,
                [
                    "oomkilled",
                    "out of memory",
                    "memory limit exceeded",
                ],
            ):
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

            if self._contains_any(
                lower,
                [
                    "crashloopbackoff",
                    "back-off restarting failed container",
                ],
            ):
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

            if "containerterminated" in reason and "manuallystopped" in lower:
                risk_notes.append(
                    "The logs contain ManuallyStopped termination events. This is usually normal when min_replicas=0 scales the app down."
                )
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )

            if "kedascaltargetdeactivated" in reason or "kedascale" in lower:
                risk_notes.append(
                    "The logs contain KEDA scale-to-zero activity. This is normal for cost-optimized Container Apps with min_replicas=0."
                )
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )

            if "get /health" in lower and "200 ok" in lower:
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )

            if "application startup complete" in lower:
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )

            if "successfully pulled image" in lower:
                evidence.append(
                    self._format_log_evidence(timestamp, source_type, log_text)
                )

        if severity_score == 0:
            findings.append(
                "Logs show normal startup/runtime behavior."
            )
            likely_causes.append(
                "No incident cause detected in recent logs."
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
            if not isinstance(item, dict):
                continue

            log_text = (
                item.get("Log")
                or item.get("Message")
                or item.get("message")
                or item.get("log")
                or ""
            )

            normalized.append(
                {
                    "timestamp": item.get("TimeGenerated") or item.get("time") or item.get("timestamp"),
                    "type": item.get("Type") or item.get("type"),
                    "container_app_name": item.get("ContainerAppName") or item.get("ContainerAppName_s"),
                    "revision_name": item.get("RevisionName") or item.get("RevisionName_s"),
                    "text": str(log_text),
                    "reason": item.get("Reason") or item.get("Reason_s") or "",
                }
            )

        return normalized

    def _calculate_severity(
        self,
        status_findings: dict[str, Any],
        log_findings: dict[str, Any],
    ) -> str:
        score = max(
            status_findings.get("severity_score", 0),
            log_findings.get("severity_score", 0),
        )

        if score >= 5:
            return "critical"

        if score == 4:
            return "high"

        if score == 3:
            return "medium"

        if score == 2:
            return "low"

        return "none"

    def _build_summary(
        self,
        incident_detected: bool,
        severity: str,
        findings: list[str],
        context: dict[str, Any],
    ) -> str:
        app_name = context.get("app_name", "application")

        if incident_detected:
            return (
                f"Incident detected for {app_name}. "
                f"Severity: {severity}. "
                f"Main finding: {findings[0] if findings else 'Unknown issue.'}"
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

    def _contains_any(
        self,
        text: str,
        patterns: list[str],
    ) -> bool:
        return any(pattern in text for pattern in patterns)

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