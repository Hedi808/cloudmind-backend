import json
from typing import Any

from app.agents.incident_response_agent import IncidentResponseAgent


class RemediationPlannerAgent:
    """
    Phase 10 agent.

    Responsibilities:
    - consume IncidentResponseAgent output
    - create safe remediation plans
    - identify files likely needing changes
    - suggest commands for validation
    - mark risky actions as requiring human approval

    This agent does NOT automatically modify source code or cloud infrastructure.
    It only creates a remediation plan.
    """

    def __init__(self) -> None:
        self.incident_response_agent = IncidentResponseAgent()

    def plan_from_azure(
        self,
        resource_group: str,
        app_name: str,
        health_path: str = "/health",
        timeout_seconds: int = 60,
        log_tail: int = 100,
        environment: str = "development",
        allow_cost_increase: bool = False,
    ) -> dict[str, Any]:
        incident_result = self.incident_response_agent.analyze_azure_incident(
            resource_group=resource_group,
            app_name=app_name,
            health_path=health_path,
            timeout_seconds=timeout_seconds,
            log_tail=log_tail,
        )

        return self.plan_from_incident(
            incident_result=incident_result,
            context={
                "platform": "azure_container_apps",
                "resource_group": resource_group,
                "app_name": app_name,
                "health_path": health_path,
            },
            environment=environment,
            allow_cost_increase=allow_cost_increase,
        )

    def plan_from_incident(
        self,
        incident_result: dict[str, Any],
        context: dict[str, Any] | None = None,
        environment: str = "development",
        allow_cost_increase: bool = False,
    ) -> dict[str, Any]:
        normalized_incident = incident_result.get("result", incident_result)
        context = context or normalized_incident.get("context", {}) or {}

        app_name = context.get("app_name", "application")
        incident_detected = bool(normalized_incident.get("incident_detected", False))
        severity = normalized_incident.get("severity", "unknown")

        findings = normalized_incident.get("findings", []) or []
        likely_causes = normalized_incident.get("likely_causes", []) or []
        evidence = normalized_incident.get("evidence", []) or []
        risk_notes = normalized_incident.get("risk_notes", []) or []
        recommended_actions = normalized_incident.get("recommended_actions", []) or []

        signals = self._extract_signals(
            incident_result=normalized_incident,
            findings=findings,
            likely_causes=likely_causes,
            evidence=evidence,
            risk_notes=risk_notes,
        )

        remediation_steps = []

        if signals["status_unreadable"]:
            remediation_steps.append(self._plan_verify_azure_resource_identifiers())

        if signals["image_pull_failure"]:
            remediation_steps.append(self._plan_fix_image_pull())

        if signals["missing_dependency"]:
            remediation_steps.append(self._plan_fix_missing_dependency())

        if signals["app_exception"]:
            remediation_steps.append(self._plan_fix_application_exception())

        if signals["port_issue"]:
            remediation_steps.append(self._plan_fix_port_mismatch())

        if signals["health_timeout"]:
            remediation_steps.append(self._plan_fix_health_timeout())

        if signals["ingress_issue"]:
            remediation_steps.append(self._plan_fix_ingress())

        if signals["no_ready_revision"]:
            remediation_steps.append(self._plan_fix_no_ready_revision())

        if signals["oom"]:
            remediation_steps.append(
                self._plan_fix_out_of_memory(
                    environment=environment,
                    allow_cost_increase=allow_cost_increase,
                )
            )

        if signals["crash_loop"]:
            remediation_steps.append(self._plan_fix_crash_loop())

        if signals["dependency_connection_failure"]:
            remediation_steps.append(self._plan_fix_dependency_connection())

        if signals["logs_unavailable"]:
            remediation_steps.append(self._plan_fix_logs_unavailable())

        if signals["cold_start"]:
            remediation_steps.append(
                self._plan_handle_cold_start(
                    environment=environment,
                    allow_cost_increase=allow_cost_increase,
                )
            )

        if signals["max_replicas_one"] and environment == "production":
            remediation_steps.append(
                self._plan_production_scaling(
                    allow_cost_increase=allow_cost_increase,
                )
            )

        if not remediation_steps:
            remediation_steps.append(
                self._plan_continue_monitoring(
                    environment=environment,
                    allow_cost_increase=allow_cost_increase,
                )
            )

        remediation_required = incident_detected

        approval_required = any(
            step.get("requires_human_approval") is True
            for step in remediation_steps
        )

        safe_to_auto_fix = False

        summary = self._build_summary(
            app_name=app_name,
            incident_detected=incident_detected,
            severity=severity,
            remediation_required=remediation_required,
            remediation_steps=remediation_steps,
        )

        return {
            "status": "plan_ready",
            "message": summary,
            "phase": "phase_10_remediation_planning",
            "app_name": app_name,
            "environment": environment,
            "incident_detected": incident_detected,
            "severity": severity,
            "remediation_required": remediation_required,
            "human_approval_required": approval_required,
            "safe_to_auto_fix": safe_to_auto_fix,
            "execution_mode": "proposal_only",
            "summary": summary,
            "detected_signals": signals,
            "findings": findings,
            "likely_causes": likely_causes,
            "evidence": evidence[:20],
            "risk_notes": risk_notes,
            "original_recommended_actions": recommended_actions,
            "remediation_steps": self._deduplicate_steps(remediation_steps),
            "next_phase_hint": (
                "Phase 11 can convert approved remediation steps into Git branches and pull requests."
            ),
        }

    def simulate_remediation_plan(
        self,
        scenario: str,
        environment: str = "development",
        allow_cost_increase: bool = False,
    ) -> dict[str, Any]:
        synthetic_incident = self._build_synthetic_incident(scenario=scenario)

        return self.plan_from_incident(
            incident_result=synthetic_incident,
            context={
                "platform": "azure_container_apps",
                "resource_group": "rg-cloudmind-test-3s",
                "app_name": "test-3s-backend",
                "health_path": "/health",
                "scenario": scenario,
            },
            environment=environment,
            allow_cost_increase=allow_cost_increase,
        )

    def _extract_signals(
        self,
        incident_result: dict[str, Any],
        findings: list[str],
        likely_causes: list[str],
        evidence: list[str],
        risk_notes: list[str],
    ) -> dict[str, bool]:
        text_blob = self._to_lower_blob(
            {
                "incident_result": incident_result,
                "findings": findings,
                "likely_causes": likely_causes,
                "evidence": evidence,
                "risk_notes": risk_notes,
            }
        )

        raw = incident_result.get("raw", {}) or {}
        status_result = raw.get("status_result", {}) or {}
        status_body = status_result.get("result", status_result)
        azure = status_body.get("azure", {}) or {}

        min_replicas = azure.get("min_replicas")
        max_replicas = azure.get("max_replicas")

        return {
            "status_unreadable": self._contains_any(
                text_blob,
                [
                    "could not read the azure container app status",
                    "not_found",
                    "resource group or app name may be wrong",
                ],
            ),
            "image_pull_failure": self._contains_any(
                text_blob,
                [
                    "image pull failure",
                    "imagepullbackoff",
                    "errimagepull",
                    "failed to pull image",
                    "manifest unknown",
                    "authentication required",
                    "unauthorized",
                ],
            ),
            "missing_dependency": self._contains_any(
                text_blob,
                [
                    "missing python dependency",
                    "no module named",
                    "modulenotfounderror",
                    "importerror",
                    "cannot import name",
                ],
            ),
            "app_exception": self._contains_any(
                text_blob,
                [
                    "application exception",
                    "traceback",
                    "runtimeerror",
                    "valueerror",
                    "typeerror",
                    "syntaxerror",
                ],
            ),
            "port_issue": self._contains_any(
                text_blob,
                [
                    "port binding issue",
                    "wrong port",
                    "target port",
                    "address already in use",
                    "port already allocated",
                    "bind",
                ],
            ),
            "health_timeout": self._contains_any(
                text_blob,
                [
                    "health check timed out",
                    "timed out",
                    "did not respond before the timeout",
                ],
            ),
            "ingress_issue": self._contains_any(
                text_blob,
                [
                    "no public fqdn",
                    "ingress may be disabled",
                    "external ingress",
                    "fqdn is missing",
                ],
            ),
            "no_ready_revision": self._contains_any(
                text_blob,
                [
                    "no latest ready revision",
                    "latest_ready_revision_name is missing",
                ],
            ),
            "oom": self._contains_any(
                text_blob,
                [
                    "out-of-memory",
                    "out of memory",
                    "oomkilled",
                    "memory limit exceeded",
                ],
            ),
            "crash_loop": self._contains_any(
                text_blob,
                [
                    "crash loop",
                    "crashloopbackoff",
                    "back-off restarting failed container",
                ],
            ),
            "dependency_connection_failure": self._contains_any(
                text_blob,
                [
                    "dependency connection failure",
                    "connection refused",
                    "connection timed out",
                    "could not connect",
                    "name or service not known",
                ],
            ),
            "logs_unavailable": self._contains_any(
                text_blob,
                [
                    "could not retrieve application logs",
                    "log analytics may not be configured",
                    "logs retrieval failed",
                    "no recent logs were returned",
                ],
            ),
            "cold_start": min_replicas == 0 or self._contains_any(
                text_blob,
                [
                    "min_replicas=0",
                    "cold starts",
                    "scale-to-zero",
                    "keda scale-to-zero",
                    "manuallystopped",
                ],
            ),
            "max_replicas_one": max_replicas == 1 or "max_replicas=1" in text_blob,
        }

    def _plan_continue_monitoring(
        self,
        environment: str,
        allow_cost_increase: bool,
    ) -> dict[str, Any]:
        proposed_changes = [
            "No code or infrastructure change is required right now.",
            "Keep using /api/observability/azure/status and /api/incidents/analyze-azure after each deployment.",
        ]

        if environment == "production" and allow_cost_increase:
            proposed_changes.append(
                "For production, consider setting min_replicas=1 and max_replicas=2 to reduce cold starts and improve availability."
            )

        return {
            "id": "continue-monitoring",
            "title": "Continue monitoring",
            "problem": "No active incident was detected.",
            "recommended_fix": "No remediation is required. Continue monitoring the app.",
            "target_files": [],
            "proposed_changes": proposed_changes,
            "validation_commands": [
                "POST /api/observability/azure/status",
                "POST /api/observability/azure/logs",
                "POST /api/incidents/analyze-azure",
            ],
            "rollback_plan": "No rollback needed because no change is proposed.",
            "risk": "low",
            "requires_human_approval": False,
            "safe_to_auto_fix": False,
            "cost_impact": "none",
            "availability_impact": "none",
        }

    def _plan_verify_azure_resource_identifiers(self) -> dict[str, Any]:
        return {
            "id": "verify-azure-resource-identifiers",
            "title": "Verify Azure resource identifiers",
            "problem": "CloudMind could not read the Azure Container App.",
            "recommended_fix": "Confirm the resource group name, Container App name, and active Azure subscription.",
            "target_files": [],
            "proposed_changes": [
                "Run az account show and confirm the active subscription.",
                "Run az containerapp list --resource-group <resource-group> --output table.",
                "Retry with the exact app name shown by Azure.",
            ],
            "validation_commands": [
                "az account show",
                "az containerapp list --resource-group rg-cloudmind-test-3s --output table",
            ],
            "rollback_plan": "No rollback needed because this is a verification step.",
            "risk": "low",
            "requires_human_approval": False,
            "safe_to_auto_fix": False,
            "cost_impact": "none",
            "availability_impact": "none",
        }

    def _plan_fix_image_pull(self) -> dict[str, Any]:
        return {
            "id": "fix-image-pull",
            "title": "Fix container image pull",
            "problem": "Azure could not pull the container image.",
            "recommended_fix": "Verify the GHCR image, tag, package visibility, and registry credentials.",
            "target_files": [
                ".github/workflows/docker-build.yml",
                "azure/deploy-container-app.ps1",
                "azure/deploy-container-app.sh",
                "azure/README.md",
            ],
            "proposed_changes": [
                "Confirm the image exists in GHCR with the expected tag.",
                "Confirm the image URL uses lowercase GHCR owner/repo path.",
                "If the image is private, create a GitHub token with read:packages and configure Azure registry credentials.",
                "Rebuild and push the image through the CI/CD workflow.",
            ],
            "validation_commands": [
                "docker pull ghcr.io/hedi808/test-3s-backend:latest",
                "az containerapp show --resource-group rg-cloudmind-test-3s --name test-3s-backend --output table",
            ],
            "rollback_plan": "Rollback to the previous working image tag or redeploy the last successful revision.",
            "risk": "high",
            "requires_human_approval": True,
            "safe_to_auto_fix": False,
            "cost_impact": "none",
            "availability_impact": "high if the image cannot be pulled",
        }

    def _plan_fix_missing_dependency(self) -> dict[str, Any]:
        return {
            "id": "fix-missing-dependency",
            "title": "Fix missing dependency",
            "problem": "The app is failing because a required package or module is missing.",
            "recommended_fix": "Add the missing dependency to the project dependency file, rebuild the image, and redeploy.",
            "target_files": [
                "requirements.txt",
                "pyproject.toml",
                "package.json",
                "Dockerfile",
            ],
            "proposed_changes": [
                "Identify the missing package from logs.",
                "Add it to requirements.txt for Python apps or package.json for Node apps.",
                "Rebuild the Docker image through CI/CD.",
                "Deploy the new image to Azure Container Apps.",
            ],
            "validation_commands": [
                "docker build -t cloudmind-test .",
                "docker run --rm -p 8000:8000 cloudmind-test",
                "curl http://localhost:8000/health",
            ],
            "rollback_plan": "Revert the dependency change and redeploy the previous working image.",
            "risk": "medium",
            "requires_human_approval": True,
            "safe_to_auto_fix": False,
            "cost_impact": "none",
            "availability_impact": "medium",
        }

    def _plan_fix_application_exception(self) -> dict[str, Any]:
        return {
            "id": "fix-application-exception",
            "title": "Fix application exception",
            "problem": "The application logs show runtime errors or stack traces.",
            "recommended_fix": "Reproduce locally, fix the failing code path, test, then redeploy through a pull request.",
            "target_files": [
                "app/",
                "main.py",
                "requirements.txt",
                "Dockerfile",
            ],
            "proposed_changes": [
                "Read the stack trace from logs.",
                "Identify the failing file/function.",
                "Fix the application code.",
                "Add or update tests for the failing path.",
                "Rebuild and redeploy through CI/CD.",
            ],
            "validation_commands": [
                "python -m pytest",
                "docker build -t cloudmind-test .",
                "docker run --rm -p 8000:8000 cloudmind-test",
            ],
            "rollback_plan": "Rollback to the last healthy image or revert the failing commit.",
            "risk": "medium",
            "requires_human_approval": True,
            "safe_to_auto_fix": False,
            "cost_impact": "none",
            "availability_impact": "medium",
        }

    def _plan_fix_port_mismatch(self) -> dict[str, Any]:
        return {
            "id": "fix-port-mismatch",
            "title": "Fix port mismatch",
            "problem": "The app may be listening on a different port than Azure ingress expects.",
            "recommended_fix": "Align Dockerfile, app startup command, and Azure target port.",
            "target_files": [
                "Dockerfile",
                "compose.yml",
                "azure/deploy-container-app.ps1",
                "azure/deploy-container-app.sh",
                "k8s/deployment.yaml",
                "k8s/service.yaml",
            ],
            "proposed_changes": [
                "Ensure the app listens on 0.0.0.0.",
                "Ensure FastAPI uses uvicorn main:app --host 0.0.0.0 --port 8000.",
                "Ensure Dockerfile exposes the same port.",
                "Ensure Azure Container Apps target port matches the app port.",
                "Ensure Kubernetes service targetPort matches the containerPort.",
            ],
            "validation_commands": [
                "docker build -t cloudmind-test .",
                "docker run --rm -p 8000:8000 cloudmind-test",
                "curl http://localhost:8000/health",
            ],
            "rollback_plan": "Revert port changes and redeploy the previous working image.",
            "risk": "medium",
            "requires_human_approval": True,
            "safe_to_auto_fix": False,
            "cost_impact": "none",
            "availability_impact": "high if the app is unreachable",
        }

    def _plan_fix_health_timeout(self) -> dict[str, Any]:
        return {
            "id": "fix-health-timeout",
            "title": "Handle health check timeout",
            "problem": "The health check timed out.",
            "recommended_fix": "Retry with a longer timeout and verify whether this is a cold start caused by min_replicas=0.",
            "target_files": [
                "azure/deploy-container-app.ps1",
                "azure/deploy-container-app.sh",
            ],
            "proposed_changes": [
                "Retry health check with timeout_seconds=60.",
                "If this is development/student-budget mode, keep min_replicas=0.",
                "For production, consider min_replicas=1 to reduce cold starts.",
            ],
            "validation_commands": [
                "POST /api/observability/azure/status with timeout_seconds=60",
                "Open https://<app-url>/health in the browser",
            ],
            "rollback_plan": "Keep min_replicas=0 if cost is more important than cold-start speed.",
            "risk": "low",
            "requires_human_approval": False,
            "safe_to_auto_fix": False,
            "cost_impact": "possible increase if min_replicas is changed to 1",
            "availability_impact": "improves first request latency if min_replicas is increased",
        }

    def _plan_fix_ingress(self) -> dict[str, Any]:
        return {
            "id": "fix-ingress",
            "title": "Fix external ingress",
            "problem": "The app has no public FQDN or external ingress appears disabled.",
            "recommended_fix": "Enable external ingress and verify the target port.",
            "target_files": [
                "azure/deploy-container-app.ps1",
                "azure/deploy-container-app.sh",
                "k8s/ingress.yaml",
                "k8s/service.yaml",
            ],
            "proposed_changes": [
                "Ensure Azure Container Apps ingress is external.",
                "Ensure target port matches the container app port.",
                "For Kubernetes, ensure Service and Ingress point to the correct port.",
            ],
            "validation_commands": [
                "az containerapp show --resource-group rg-cloudmind-test-3s --name test-3s-backend --query properties.configuration.ingress",
                "POST /api/observability/azure/status",
            ],
            "rollback_plan": "Disable external ingress again if the app should remain private.",
            "risk": "medium",
            "requires_human_approval": True,
            "safe_to_auto_fix": False,
            "cost_impact": "none",
            "availability_impact": "high if public traffic is required",
        }

    def _plan_fix_no_ready_revision(self) -> dict[str, Any]:
        return {
            "id": "fix-no-ready-revision",
            "title": "Fix revision readiness",
            "problem": "Azure has no latest ready revision.",
            "recommended_fix": "Inspect startup logs, fix container startup, or rollback to a previous healthy revision.",
            "target_files": [
                "Dockerfile",
                "requirements.txt",
                "azure/deploy-container-app.ps1",
                "azure/deploy-container-app.sh",
            ],
            "proposed_changes": [
                "Check logs for startup failures.",
                "Verify the Docker CMD or ENTRYPOINT.",
                "Verify environment variables required at startup.",
                "Rollback to the last healthy image if needed.",
            ],
            "validation_commands": [
                "POST /api/observability/azure/logs",
                "docker build -t cloudmind-test .",
                "docker run --rm -p 8000:8000 cloudmind-test",
            ],
            "rollback_plan": "Redeploy the last known healthy image tag.",
            "risk": "high",
            "requires_human_approval": True,
            "safe_to_auto_fix": False,
            "cost_impact": "none",
            "availability_impact": "high",
        }

    def _plan_fix_out_of_memory(
        self,
        environment: str,
        allow_cost_increase: bool,
    ) -> dict[str, Any]:
        proposed_changes = [
            "Confirm memory pressure from logs and metrics.",
            "Optimize memory usage in the app if possible.",
        ]

        if allow_cost_increase:
            proposed_changes.append(
                "Increase Azure Container Apps memory from 0.5Gi to a higher value such as 1Gi."
            )
        else:
            proposed_changes.append(
                "Do not increase memory automatically because this can increase cost."
            )

        return {
            "id": "fix-out-of-memory",
            "title": "Fix out-of-memory failure",
            "problem": "The container may be running out of memory.",
            "recommended_fix": "Optimize memory usage or increase memory after human approval.",
            "target_files": [
                "azure/deploy-container-app.ps1",
                "azure/deploy-container-app.sh",
                "k8s/deployment.yaml",
            ],
            "proposed_changes": proposed_changes,
            "validation_commands": [
                "POST /api/observability/azure/logs",
                "Check Azure metrics for memory usage",
            ],
            "rollback_plan": "Return memory settings to the previous value if cost or behavior becomes unacceptable.",
            "risk": "high",
            "requires_human_approval": True,
            "safe_to_auto_fix": False,
            "cost_impact": "possible increase",
            "availability_impact": "high",
        }

    def _plan_fix_crash_loop(self) -> dict[str, Any]:
        return {
            "id": "fix-crash-loop",
            "title": "Fix crash loop",
            "problem": "The container appears to repeatedly start and fail.",
            "recommended_fix": "Rollback immediately if production is affected, then fix the startup failure.",
            "target_files": [
                "Dockerfile",
                "requirements.txt",
                "main.py",
                "app/",
                "azure/deploy-container-app.ps1",
            ],
            "proposed_changes": [
                "Identify the first error before the crash.",
                "Verify startup command.",
                "Verify required environment variables.",
                "Rollback to the previous healthy image if needed.",
                "Fix code and redeploy through CI/CD.",
            ],
            "validation_commands": [
                "POST /api/observability/azure/logs",
                "docker build -t cloudmind-test .",
                "docker run --rm -p 8000:8000 cloudmind-test",
            ],
            "rollback_plan": "Rollback to the previous healthy image tag or revision.",
            "risk": "high",
            "requires_human_approval": True,
            "safe_to_auto_fix": False,
            "cost_impact": "none",
            "availability_impact": "critical",
        }

    def _plan_fix_dependency_connection(self) -> dict[str, Any]:
        return {
            "id": "fix-dependency-connection",
            "title": "Fix dependency connection",
            "problem": "The app cannot connect to a dependency such as a database or external API.",
            "recommended_fix": "Verify environment variables, connection strings, network access, and credentials.",
            "target_files": [
                ".env.example",
                "azure/deploy-container-app.ps1",
                "azure/deploy-container-app.sh",
                "k8s/configmap.yaml",
                "k8s/secret-template.yaml",
            ],
            "proposed_changes": [
                "Check missing environment variables.",
                "Verify database/API URL.",
                "Verify secrets are configured in Azure.",
                "Verify the dependency is reachable from Azure.",
            ],
            "validation_commands": [
                "POST /api/observability/azure/logs",
                "az containerapp show --resource-group rg-cloudmind-test-3s --name test-3s-backend --output json",
            ],
            "rollback_plan": "Revert secret/config changes if they break connectivity.",
            "risk": "medium",
            "requires_human_approval": True,
            "safe_to_auto_fix": False,
            "cost_impact": "none",
            "availability_impact": "medium",
        }

    def _plan_fix_logs_unavailable(self) -> dict[str, Any]:
        return {
            "id": "fix-logs-unavailable",
            "title": "Fix logs availability",
            "problem": "CloudMind could not retrieve logs or no recent logs were returned.",
            "recommended_fix": "Verify Log Analytics configuration and generate traffic to the app.",
            "target_files": [
                "azure/deploy-container-app.ps1",
                "azure/deploy-container-app.sh",
            ],
            "proposed_changes": [
                "Open the app URL and /health endpoint to generate logs.",
                "Wait 1-3 minutes for Log Analytics ingestion.",
                "Verify the Container Apps environment has Log Analytics configured.",
            ],
            "validation_commands": [
                "POST /api/observability/azure/logs",
                "Open https://<app-url>/health",
            ],
            "rollback_plan": "No rollback needed unless Log Analytics configuration is changed.",
            "risk": "low",
            "requires_human_approval": False,
            "safe_to_auto_fix": False,
            "cost_impact": "low possible monitoring cost",
            "availability_impact": "none",
        }

    def _plan_handle_cold_start(
        self,
        environment: str,
        allow_cost_increase: bool,
    ) -> dict[str, Any]:
        proposed_changes = [
            "Keep min_replicas=0 for student-budget or development environments.",
            "Use timeout_seconds=60 for health checks to avoid false alarms after idle periods.",
        ]

        risk = "low"
        requires_human_approval = False
        cost_impact = "none"

        if environment == "production":
            proposed_changes.append(
                "For production, consider changing min_replicas from 0 to 1 to reduce cold starts."
            )
            risk = "medium"
            requires_human_approval = True
            cost_impact = "increase if min_replicas is changed to 1"

        if environment == "production" and allow_cost_increase:
            proposed_changes.append(
                "Approved cost-increase mode is enabled, so a future PR could update Azure deployment files to min_replicas=1."
            )

        return {
            "id": "handle-cold-start",
            "title": "Handle scale-to-zero cold starts",
            "problem": "The app uses min_replicas=0, so the first request after idle can be slower.",
            "recommended_fix": "Keep scale-to-zero for low cost unless production latency matters.",
            "target_files": [
                "azure/deploy-container-app.ps1",
                "azure/deploy-container-app.sh",
            ],
            "proposed_changes": proposed_changes,
            "validation_commands": [
                "POST /api/observability/azure/status with timeout_seconds=60",
                "Open the public /health endpoint after idle time",
            ],
            "rollback_plan": "Set min_replicas back to 0 to reduce cost.",
            "risk": risk,
            "requires_human_approval": requires_human_approval,
            "safe_to_auto_fix": False,
            "cost_impact": cost_impact,
            "availability_impact": "improves cold-start behavior if min_replicas is increased",
        }

    def _plan_production_scaling(
        self,
        allow_cost_increase: bool,
    ) -> dict[str, Any]:
        proposed_changes = [
            "For production, increase max_replicas above 1 to allow scaling during traffic spikes.",
        ]

        if allow_cost_increase:
            proposed_changes.append(
                "A future PR could update Azure deployment files to max_replicas=2 or higher."
            )
        else:
            proposed_changes.append(
                "Do not change replica limits automatically because this may increase cost."
            )

        return {
            "id": "production-scaling-hardening",
            "title": "Improve production scaling",
            "problem": "max_replicas=1 limits high availability and scaling.",
            "recommended_fix": "For production, increase max_replicas after human approval.",
            "target_files": [
                "azure/deploy-container-app.ps1",
                "azure/deploy-container-app.sh",
                "k8s/deployment.yaml",
            ],
            "proposed_changes": proposed_changes,
            "validation_commands": [
                "POST /api/observability/azure/status",
                "Check Azure metrics after load testing",
            ],
            "rollback_plan": "Set max_replicas back to 1 to reduce cost.",
            "risk": "medium",
            "requires_human_approval": True,
            "safe_to_auto_fix": False,
            "cost_impact": "possible increase",
            "availability_impact": "improves production scaling",
        }

    def _build_synthetic_incident(
        self,
        scenario: str,
    ) -> dict[str, Any]:
        scenario = scenario.strip().lower()

        base_context = {
            "platform": "azure_container_apps",
            "resource_group": "rg-cloudmind-test-3s",
            "app_name": "test-3s-backend",
            "health_path": "/health",
        }

        scenarios = {
            "healthy": {
                "status": "healthy",
                "message": "No active incident detected for test-3s-backend.",
                "incident_detected": False,
                "severity": "none",
                "context": base_context,
                "findings": ["Logs show normal startup/runtime behavior."],
                "likely_causes": ["No incident cause detected in recent logs."],
                "evidence": [
                    "[demo] INFO: Application startup complete.",
                    "[demo] INFO: GET /health HTTP/1.1 200 OK",
                ],
                "risk_notes": [
                    "min_replicas=0 is cost-friendly but can cause cold starts after idle periods."
                ],
                "raw": {
                    "status_result": {
                        "healthy": True,
                        "azure": {
                            "min_replicas": 0,
                            "max_replicas": 1,
                        },
                    }
                },
            },
            "cold_start": {
                "status": "incident_detected",
                "message": "Health check timeout detected.",
                "incident_detected": True,
                "severity": "medium",
                "context": base_context,
                "findings": ["The public health check is not healthy."],
                "likely_causes": [
                    "The app may be slow to wake up because min_replicas=0."
                ],
                "evidence": [
                    "Health check timed out after 10 seconds.",
                ],
                "risk_notes": [
                    "min_replicas=0 is cost-friendly but can cause cold starts after idle periods."
                ],
                "raw": {
                    "status_result": {
                        "healthy": False,
                        "health": {
                            "message": "Health check timed out.",
                        },
                        "azure": {
                            "min_replicas": 0,
                            "max_replicas": 1,
                        },
                    }
                },
            },
            "image_pull_failure": {
                "status": "incident_detected",
                "message": "Image pull failure detected.",
                "incident_detected": True,
                "severity": "critical",
                "context": base_context,
                "findings": ["Image pull failure detected in logs."],
                "likely_causes": [
                    "Azure could not pull the image from GHCR."
                ],
                "evidence": [
                    "failed to pull image ghcr.io/hedi808/test-3s-backend:latest unauthorized"
                ],
                "risk_notes": [],
            },
            "missing_dependency": {
                "status": "incident_detected",
                "message": "Missing dependency detected.",
                "incident_detected": True,
                "severity": "high",
                "context": base_context,
                "findings": [
                    "Missing Python dependency or import failure detected."
                ],
                "likely_causes": [
                    "requirements.txt may be missing a required dependency."
                ],
                "evidence": [
                    "ModuleNotFoundError: No module named 'fastapi'"
                ],
                "risk_notes": [],
            },
            "wrong_port": {
                "status": "incident_detected",
                "message": "Port mismatch detected.",
                "incident_detected": True,
                "severity": "medium",
                "context": base_context,
                "findings": [
                    "The public health check is not healthy.",
                    "Port binding issue detected.",
                ],
                "likely_causes": [
                    "The app may be listening on a different port than Azure ingress expects."
                ],
                "evidence": [
                    "target port 8000 but app is listening on 3000"
                ],
                "risk_notes": [],
            },
            "oom": {
                "status": "incident_detected",
                "message": "Out-of-memory failure detected.",
                "incident_detected": True,
                "severity": "critical",
                "context": base_context,
                "findings": [
                    "Out-of-memory failure detected."
                ],
                "likely_causes": [
                    "The container may not have enough memory."
                ],
                "evidence": [
                    "OOMKilled: memory limit exceeded"
                ],
                "risk_notes": [],
            },
            "crash_loop": {
                "status": "incident_detected",
                "message": "Crash loop detected.",
                "incident_detected": True,
                "severity": "critical",
                "context": base_context,
                "findings": [
                    "Crash loop detected."
                ],
                "likely_causes": [
                    "The container repeatedly starts and fails."
                ],
                "evidence": [
                    "CrashLoopBackOff: back-off restarting failed container"
                ],
                "risk_notes": [],
            },
            "dependency_connection_failure": {
                "status": "incident_detected",
                "message": "Dependency connection failure detected.",
                "incident_detected": True,
                "severity": "medium",
                "context": base_context,
                "findings": [
                    "Dependency connection failure detected."
                ],
                "likely_causes": [
                    "The app may be unable to reach a database, API, or internal service."
                ],
                "evidence": [
                    "connection refused while connecting to database"
                ],
                "risk_notes": [],
            },
        }

        return scenarios.get(scenario, scenarios["healthy"])

    def _build_summary(
        self,
        app_name: str,
        incident_detected: bool,
        severity: str,
        remediation_required: bool,
        remediation_steps: list[dict[str, Any]],
    ) -> str:
        if remediation_required:
            return (
                f"Remediation plan created for {app_name}. "
                f"Incident severity is {severity}. "
                f"{len(remediation_steps)} remediation step(s) proposed. "
                "No action has been executed automatically."
            )

        return (
            f"No remediation is required for {app_name}. "
            f"{len(remediation_steps)} monitoring or hardening step(s) proposed. "
            "No action has been executed automatically."
        )

    def _to_lower_blob(
        self,
        data: Any,
    ) -> str:
        try:
            return json.dumps(data, default=str).lower()
        except Exception:
            return str(data).lower()

    def _contains_any(
        self,
        text: str,
        patterns: list[str],
    ) -> bool:
        return any(pattern.lower() in text for pattern in patterns)

    def _deduplicate_steps(
        self,
        steps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        seen = set()
        result = []

        for step in steps:
            key = step.get("id", step.get("title", ""))

            if key not in seen:
                seen.add(key)
                result.append(step)

        return result