from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc

from app.core.auth import get_current_user_id
from app.db.database import SessionLocal, create_database_tables
from app.db.models import ActionRun, DeploymentState, Project, ProjectArtifact


@dataclass
class WorkflowStep:
    id: str
    title: str
    description: str
    category: str
    status: str
    requires_approval: bool
    can_execute_now: bool
    tool_intent: str | None
    user_message: str | None
    depends_on: list[str]
    evidence: list[str]
    reason: str


class WorkflowEngineAgent:
    """
    Phase 20G: strict professional DevOps workflow planner.

    Correct order:
    1. Analyze repository
    2. Generate Docker files
    3. Generate Kubernetes manifests
    4. Generate Azure deployment files
    5. Generate CI/CD workflow
    6. Publish container image
    7. Deploy to Azure Container Apps
    8. Check Azure status
    9. Analyze incident state
    10. Generate final demo report

    Rules:
    - Kubernetes manifests are required before runtime deployment.
    - Azure deployment files are required before runtime deployment.
    - Final report is required, but only after incident analysis is clean.
    - If an active incident is detected, do not loop on analyze_incident.
      Mark incident analysis as completed and block final report.
    """

    REQUIRED_STEP_IDS = {
        "analyze_repository",
        "generate_docker",
        "generate_kubernetes",
        "generate_azure_files",
        "generate_cicd",
        "publish_container_image",
        "deploy_to_azure",
        "check_azure_status",
        "analyze_incident",
        "final_demo_report",
    }

    def build_deployment_plan(
        self,
        project_id: str | None = None,
        repo_url: str | None = None,
    ) -> dict[str, Any]:
        create_database_tables()

        with SessionLocal() as db:
            project = self._load_project(
                db=db,
                project_id=project_id,
                repo_url=repo_url,
            )

            if project is None:
                return {
                    "status": "project_not_found",
                    "message": "No project was found in PostgreSQL memory for the provided identifier.",
                    "project": None,
                    "workflow": self._workflow_definition(),
                    "next_step": {
                        "id": "analyze_repository",
                        "title": "Analyze repository",
                        "reason": "This repository is not tracked yet. Analyze it first so CloudMind can create project memory.",
                        "user_message": "Analyze this repository",
                        "requires_approval": False,
                    },
                    "steps": [],
                    "summary": {
                        "total_steps": 10,
                        "completed": 0,
                        "required": 10,
                        "blocked": 9,
                        "optional": 0,
                        "progress_percent": 0,
                    },
                    "safety": self._safety(),
                }

            actions = (
                db.query(ActionRun)
                .filter(ActionRun.project_id == project.id)
                .order_by(desc(ActionRun.started_at))
                .all()
            )

            artifacts = (
                db.query(ProjectArtifact)
                .filter(ProjectArtifact.project_id == project.id)
                .order_by(desc(ProjectArtifact.created_at))
                .all()
            )

            deployments = (
                db.query(DeploymentState)
                .filter(DeploymentState.project_id == project.id)
                .order_by(desc(DeploymentState.updated_at))
                .all()
            )

            steps = self._build_steps(
                project=project,
                actions=actions,
                artifacts=artifacts,
                deployments=deployments,
            )

            next_step = self._find_next_step(steps)
            summary = self._build_summary(steps)
            workflow_status = self._workflow_status(steps=steps, next_step=next_step)

            return {
                "status": workflow_status,
                "message": self._workflow_message(workflow_status, next_step),
                "project": self._project_to_dict(project),
                "workflow": self._workflow_definition(),
                "next_step": self._step_to_dict(next_step) if next_step else None,
                "steps": [self._step_to_dict(step) for step in steps],
                "summary": summary,
                "safety": self._safety(),
            }

    def _workflow_definition(self) -> dict[str, str]:
        return {
            "id": "full_deployment_pipeline",
            "title": "Full Deployment Pipeline",
            "description": (
                "Analyze repository, generate Docker/Kubernetes/Azure assets through GitOps PRs, "
                "generate CI/CD, publish a container image, deploy to Azure, verify health, "
                "analyze incidents, and generate the final report."
            ),
        }

    def _safety(self) -> dict[str, Any]:
        return {
            "read_only_planner": True,
            "executes_tools": False,
            "creates_pull_requests": False,
            "deploys_to_azure": False,
            "approval_required_for_write_steps": True,
            "kubernetes_required_before_deploy": True,
            "azure_files_required_before_deploy": True,
            "final_report_requires_clean_incident_state": True,
            "does_not_loop_on_active_incidents": True,
        }

    def _load_project(
        self,
        db,
        project_id: str | None,
        repo_url: str | None,
    ) -> Project | None:
        user_id = get_current_user_id()
        tenant_filter = (Project.owner_id == user_id,) if user_id else ()

        if project_id:
            return (
                db.query(Project)
                .filter(Project.id == project_id, *tenant_filter)
                .first()
            )

        if repo_url:
            return (
                db.query(Project)
                .filter(Project.repo_url == repo_url, *tenant_filter)
                .first()
            )

        return None

    def _build_steps(
        self,
        project: Project,
        actions: list[ActionRun],
        artifacts: list[ProjectArtifact],
        deployments: list[DeploymentState],
    ) -> list[WorkflowStep]:
        latest_analysis = self._latest_analysis(project)
        missing_devops_files = self._missing_devops_files(project)
        important_files = self._important_files(project)

        analyzed = self._is_project_analyzed(project)

        docker_ready = self._is_docker_ready(
            missing_devops_files=missing_devops_files,
            important_files=important_files,
            actions=actions,
        )

        kubernetes_ready = self._is_kubernetes_ready(
            missing_devops_files=missing_devops_files,
            important_files=important_files,
            actions=actions,
        )

        azure_files_ready = self._is_azure_files_ready(
            important_files=important_files,
            actions=actions,
        )

        cicd_ready = self._is_cicd_ready(
            project=project,
            actions=actions,
            important_files=important_files,
            deployments=deployments,
        )

        image_ready = self._is_image_ready(
            project=project,
            deployments=deployments,
            actions=actions,
        )

        deployed = self._is_deployed(
            project=project,
            deployments=deployments,
        )

        azure_status_checked = self._is_azure_status_checked(
            project=project,
            deployments=deployments,
            actions=actions,
        )

        incident_checked = self._is_incident_checked(actions=actions)
        incident_clean = self._is_incident_clean(actions=actions)
        active_incident = self._has_active_incident(actions=actions)
        incident_recheck_needed = self._needs_incident_recheck(
            actions=actions,
            deployments=deployments,
        )

        final_report_ready = self._is_final_report_ready(
            actions=actions,
            artifacts=artifacts,
        )

        generate_docker_status = self._dependent_status(
            completed=docker_ready,
            dependencies_done=analyzed,
            required=True,
        )

        generate_kubernetes_status = self._dependent_status(
            completed=kubernetes_ready,
            dependencies_done=docker_ready,
            required=True,
        )

        generate_azure_status = self._dependent_status(
            completed=azure_files_ready,
            dependencies_done=docker_ready and kubernetes_ready,
            required=True,
        )

        generate_cicd_status = self._dependent_status(
            completed=cicd_ready,
            dependencies_done=docker_ready and kubernetes_ready and azure_files_ready,
            required=True,
        )

        publish_image_status = self._dependent_status(
            completed=image_ready,
            dependencies_done=cicd_ready,
            required=True,
        )

        deploy_status = self._dependent_status(
            completed=deployed,
            dependencies_done=image_ready and kubernetes_ready and azure_files_ready,
            required=True,
        )

        check_status_status = self._dependent_status(
            completed=azure_status_checked,
            dependencies_done=deployed,
            required=True,
        )

        if incident_clean:
            incident_status = "completed"
            incident_can_execute = False
            incident_reason = "Latest incident analysis confirms no active incident."

        elif incident_recheck_needed:
            incident_status = "required"
            incident_can_execute = deployed and azure_status_checked
            incident_reason = (
                "Azure status was checked after the last incident finding, so incident analysis should be re-run."
            )

        elif active_incident:
            incident_status = "completed"
            incident_can_execute = False
            incident_reason = (
                "Latest incident analysis detected an active issue. "
                "CloudMind will not repeat this step automatically; final report remains blocked until a clean analysis is recorded."
            )

        else:
            incident_status = self._dependent_status(
                completed=incident_checked,
                dependencies_done=deployed and azure_status_checked,
                required=True,
            )
            incident_can_execute = deployed and azure_status_checked and not incident_checked
            incident_reason = (
                "Incident analysis has already been recorded."
                if incident_checked
                else "Incident analysis is required after status verification."
            )

        final_dependencies_done = deployed and azure_status_checked and incident_clean
        final_status = self._dependent_status(
            completed=final_report_ready,
            dependencies_done=final_dependencies_done,
            required=True,
        )

        steps = [
            WorkflowStep(
                id="analyze_repository",
                title="Analyze repository",
                description="Detect language, framework, port, start command, components, and missing DevOps files.",
                category="analysis",
                status="completed" if analyzed else "required",
                requires_approval=False,
                can_execute_now=not analyzed,
                tool_intent="analyze_repo",
                user_message="Analyze this repository",
                depends_on=[],
                evidence=self._analysis_evidence(project, latest_analysis),
                reason=(
                    "Repository analysis exists in project memory."
                    if analyzed
                    else "CloudMind needs to analyze the repository before planning DevOps work."
                ),
            ),
            WorkflowStep(
                id="generate_docker",
                title="Generate Docker files",
                description="Create Dockerfile, .dockerignore, and compose.yml through a GitHub pull request.",
                category="gitops",
                status=generate_docker_status,
                requires_approval=True,
                can_execute_now=analyzed and not docker_ready,
                tool_intent="generate_docker",
                user_message="Generate Docker files for this repo",
                depends_on=["analyze_repository"],
                evidence=self._docker_evidence(
                    missing_devops_files=missing_devops_files,
                    important_files=important_files,
                    actions=actions,
                ),
                reason=(
                    "Docker assets are present or were generated before."
                    if docker_ready
                    else "Docker files are required before Kubernetes, CI/CD, image build, and deployment."
                ),
            ),
            WorkflowStep(
                id="generate_kubernetes",
                title="Generate Kubernetes manifests",
                description="Create Kubernetes manifests through a GitHub pull request.",
                category="gitops",
                status=generate_kubernetes_status,
                requires_approval=True,
                can_execute_now=docker_ready and not kubernetes_ready,
                tool_intent="generate_kubernetes",
                user_message="Generate Kubernetes manifests for this repo",
                depends_on=["generate_docker"],
                evidence=self._kubernetes_evidence(
                    missing_devops_files=missing_devops_files,
                    important_files=important_files,
                    actions=actions,
                ),
                reason=(
                    "Kubernetes manifests are present or were generated before."
                    if kubernetes_ready
                    else "Kubernetes manifests are required DevOps deliverables before runtime deployment."
                ),
            ),
            WorkflowStep(
                id="generate_azure_files",
                title="Generate Azure deployment files",
                description="Create Azure Container Apps deployment scripts and README through a GitHub pull request.",
                category="gitops",
                status=generate_azure_status,
                requires_approval=True,
                can_execute_now=docker_ready and kubernetes_ready and not azure_files_ready,
                tool_intent="generate_azure",
                user_message="Generate Azure deployment files for this repo",
                depends_on=["generate_docker", "generate_kubernetes"],
                evidence=self._azure_files_evidence(
                    important_files=important_files,
                    actions=actions,
                ),
                reason=(
                    "Azure deployment assets exist or were generated before."
                    if azure_files_ready
                    else "Azure deployment files are required before runtime deployment for reproducibility."
                ),
            ),
            WorkflowStep(
                id="generate_cicd",
                title="Generate CI/CD workflow",
                description="Create GitHub Actions workflow to build and publish the Docker image to GHCR.",
                category="gitops",
                status=generate_cicd_status,
                requires_approval=True,
                can_execute_now=docker_ready and kubernetes_ready and azure_files_ready and not cicd_ready,
                tool_intent="generate_cicd",
                user_message="Generate CI/CD for this repo",
                depends_on=["generate_docker", "generate_kubernetes", "generate_azure_files"],
                evidence=self._cicd_evidence(
                    project=project,
                    important_files=important_files,
                    deployments=deployments,
                    actions=actions,
                ),
                reason=(
                    "CI/CD is already available or was generated before."
                    if cicd_ready
                    else "A CI/CD workflow is required to build and publish the container image."
                ),
            ),
            WorkflowStep(
                id="publish_container_image",
                title="Publish container image",
                description="Confirm that GitHub Actions published a GHCR image.",
                category="image",
                status=publish_image_status,
                requires_approval=False,
                can_execute_now=False,
                tool_intent=None,
                user_message=None,
                depends_on=["generate_cicd"],
                evidence=self._image_evidence(
                    project=project,
                    deployments=deployments,
                    actions=actions,
                ),
                reason=(
                    "A container image exists in memory or was used by deployment."
                    if image_ready
                    else "GitHub Actions must publish the image before Azure runtime deployment."
                ),
            ),
            WorkflowStep(
                id="deploy_to_azure",
                title="Deploy to Azure Container Apps",
                description="Deploy the GHCR image to Azure Container Apps with human approval.",
                category="runtime",
                status=deploy_status,
                requires_approval=True,
                can_execute_now=image_ready and kubernetes_ready and azure_files_ready and not deployed,
                tool_intent="deploy_azure_runtime",
                user_message="Deploy this app to Azure",
                depends_on=["publish_container_image", "generate_kubernetes", "generate_azure_files"],
                evidence=self._deployment_evidence(
                    project=project,
                    deployments=deployments,
                ),
                reason=(
                    "Azure deployment exists in project memory."
                    if deployed
                    else "The app needs to be deployed to Azure after DevOps assets and image publication are ready."
                ),
            ),
            WorkflowStep(
                id="check_azure_status",
                title="Check Azure status",
                description="Verify Azure Container App status, revision, URL, and health.",
                category="observability",
                status=check_status_status,
                requires_approval=False,
                can_execute_now=deployed and not azure_status_checked,
                tool_intent="check_azure_status",
                user_message="Check Azure status",
                depends_on=["deploy_to_azure"],
                evidence=self._status_evidence(
                    project=project,
                    deployments=deployments,
                    actions=actions,
                ),
                reason=(
                    "Azure health/status has been checked."
                    if azure_status_checked
                    else "Runtime status must be checked after deployment."
                ),
            ),
            WorkflowStep(
                id="analyze_incident",
                title="Analyze incident state",
                description="Analyze Azure status and logs to detect active incidents.",
                category="observability",
                status=incident_status,
                requires_approval=False,
                can_execute_now=incident_can_execute,
                tool_intent="analyze_incident",
                user_message="Analyze incident for this Azure app",
                depends_on=["check_azure_status"],
                evidence=self._incident_evidence(actions=actions),
                reason=incident_reason,
            ),
            WorkflowStep(
                id="final_demo_report",
                title="Generate final demo report",
                description="Generate an end-to-end report summarizing repo analysis, GitOps, deployment, health, and incidents.",
                category="reporting",
                status=final_status,
                requires_approval=False,
                can_execute_now=final_dependencies_done and not final_report_ready,
                tool_intent="final_demo_report",
                user_message="Generate the final demo report",
                depends_on=["analyze_incident"],
                evidence=self._final_report_evidence(
                    actions=actions,
                    artifacts=artifacts,
                ),
                reason=(
                    "A final report was already generated."
                    if final_report_ready
                    else (
                        "Final report is required after the deployment is healthy and incident analysis is clean."
                        if not active_incident
                        else "Final report is blocked because the latest incident analysis is not clean."
                    )
                ),
            ),
        ]

        return steps

    def _find_next_step(self, steps: list[WorkflowStep]) -> WorkflowStep | None:
        for step in steps:
            if step.status == "required" and step.can_execute_now:
                return step

        for step in steps:
            if step.status == "blocked":
                return step

        return None

    def _build_summary(self, steps: list[WorkflowStep]) -> dict[str, Any]:
        completed = len([step for step in steps if step.status == "completed"])
        required = len([step for step in steps if step.status == "required"])
        blocked = len([step for step in steps if step.status == "blocked"])
        optional = len([step for step in steps if step.status == "optional"])

        progress_percent = int((completed / len(steps)) * 100) if steps else 0

        return {
            "total_steps": len(steps),
            "completed": completed,
            "required": required,
            "blocked": blocked,
            "optional": optional,
            "progress_percent": progress_percent,
        }

    def _workflow_status(
        self,
        steps: list[WorkflowStep],
        next_step: WorkflowStep | None,
    ) -> str:
        required_unfinished = [
            step
            for step in steps
            if step.id in self.REQUIRED_STEP_IDS
            and step.status in {"required", "blocked"}
        ]

        if not required_unfinished:
            return "workflow_ready"

        if next_step and next_step.status == "blocked":
            return "workflow_blocked"

        return "next_step_required"

    def _workflow_message(
        self,
        workflow_status: str,
        next_step: WorkflowStep | None,
    ) -> str:
        if workflow_status == "workflow_ready":
            return "The full deployment workflow is complete. All required steps are ready."

        if workflow_status == "workflow_blocked":
            if next_step:
                return f"The workflow is blocked at: {next_step.title}."
            return "The workflow is blocked. A dependency must be completed before continuing."

        if next_step:
            return f"Next recommended step: {next_step.title}."

        return "Workflow plan generated."

    def _dependent_status(
        self,
        completed: bool,
        dependencies_done: bool,
        required: bool,
    ) -> str:
        if completed:
            return "completed"

        if not dependencies_done:
            return "blocked"

        return "required" if required else "optional"

    def _is_project_analyzed(self, project: Project) -> bool:
        return bool(
            project.detected_language
            or project.detected_framework
            or project.project_type
            or self._latest_analysis(project)
        )

    def _is_docker_ready(
        self,
        missing_devops_files: list[str],
        important_files: list[str],
        actions: list[ActionRun],
    ) -> bool:
        docker_missing = self._contains_any(
            missing_devops_files,
            ["Dockerfile", ".dockerignore", "Docker Compose file"],
        )

        docker_files_seen = self._contains_any(
            important_files,
            ["Dockerfile", ".dockerignore", "compose.yml", "docker-compose.yml"],
        )

        return (docker_files_seen and not docker_missing) or self._has_successful_action(
            actions=actions,
            action_types=["generate_docker", "prepare_deployment"],
        )

    def _is_kubernetes_ready(
        self,
        missing_devops_files: list[str],
        important_files: list[str],
        actions: list[ActionRun],
    ) -> bool:
        kubernetes_missing = self._contains_any(
            missing_devops_files,
            ["Kubernetes manifests"],
        )

        kubernetes_files_seen = self._contains_any(
            important_files,
            [
                "k8s/deployment.yaml",
                "k8s\\deployment.yaml",
                "kubernetes/deployment.yaml",
                "kubernetes\\deployment.yaml",
                "kustomization.yaml",
                "namespace.yaml",
            ],
        )

        return (
            kubernetes_files_seen and not kubernetes_missing
        ) or self._has_successful_action(
            actions=actions,
            action_types=["generate_kubernetes", "prepare_deployment"],
        )

    def _is_azure_files_ready(
        self,
        important_files: list[str],
        actions: list[ActionRun],
    ) -> bool:
        azure_files_seen = self._contains_any(
            important_files,
            [
                "azure/README.md",
                "azure\\README.md",
                "deploy-container-app.ps1",
                "deploy-container-app.sh",
                "azure/deploy-container-app.ps1",
                "azure/deploy-container-app.sh",
            ],
        )

        return azure_files_seen or self._has_successful_action(
            actions=actions,
            action_types=["generate_azure"],
        )

    def _is_cicd_ready(
        self,
        project: Project,
        actions: list[ActionRun],
        important_files: list[str],
        deployments: list[DeploymentState],
    ) -> bool:
        cicd_files_seen = self._contains_any(
            important_files,
            [
                ".github/workflows",
                "docker-build.yml",
                "ci.yml",
                "deploy.yml",
                "workflow",
            ],
        )

        if cicd_files_seen:
            return True

        if self._has_successful_action(actions=actions, action_types=["generate_cicd"]):
            return True

        if project.ghcr_image:
            return True

        for deployment in deployments:
            if deployment.image and "ghcr.io" in str(deployment.image).lower():
                return True

        return False

    def _is_image_ready(
        self,
        project: Project,
        deployments: list[DeploymentState],
        actions: list[ActionRun],
    ) -> bool:
        if project.ghcr_image:
            return True

        for deployment in deployments:
            if deployment.image and "ghcr.io" in str(deployment.image).lower():
                return True

        if self._has_successful_action(actions=actions, action_types=["deploy_azure_runtime"]):
            return True

        return False

    def _is_deployed(
        self,
        project: Project,
        deployments: list[DeploymentState],
    ) -> bool:
        if project.azure_app_url:
            return True

        return any(deployment.url for deployment in deployments)

    def _is_azure_status_checked(
        self,
        project: Project,
        deployments: list[DeploymentState],
        actions: list[ActionRun],
    ) -> bool:
        for deployment in deployments:
            health_status = str(deployment.health_status or "").lower()

            if health_status in {"healthy", "success", "ok"}:
                return True

        return self._has_successful_action(
            actions=actions,
            action_types=["check_azure_status"],
        )

    def _latest_incident_action(self, actions: list[ActionRun]) -> ActionRun | None:
        for action in actions:
            if action.action_type == "analyze_incident":
                return action

        return None

    def _latest_status_action(self, actions: list[ActionRun]) -> ActionRun | None:
        for action in actions:
            if action.action_type == "check_azure_status":
                return action

        return None

    def _is_incident_checked(self, actions: list[ActionRun]) -> bool:
        return self._latest_incident_action(actions) is not None

    def _is_incident_clean(self, actions: list[ActionRun]) -> bool:
        action = self._latest_incident_action(actions)

        if action is None:
            return False

        output = action.output_json or {}
        incident_detected = output.get("incident_detected")

        if incident_detected is False:
            return True

        if incident_detected is True:
            return False

        output_status = str(output.get("status", "")).lower()
        action_status = str(action.status or "").lower()

        clean_statuses = {
            "success",
            "completed",
            "healthy",
            "no_incident",
            "verified",
        }

        return output_status in clean_statuses or action_status in clean_statuses

    def _has_active_incident(self, actions: list[ActionRun]) -> bool:
        action = self._latest_incident_action(actions)

        if action is None:
            return False

        output = action.output_json or {}
        incident_detected = output.get("incident_detected")

        if incident_detected is True:
            return True

        output_status = str(output.get("status", "")).lower()
        action_status = str(action.status or "").lower()
        severity = str(output.get("severity", "")).lower()

        active_statuses = {
            "incident_detected",
            "degraded",
            "unhealthy",
            "failed",
        }

        active_severities = {
            "low",
            "medium",
            "high",
            "critical",
        }

        return (
            output_status in active_statuses
            or action_status in active_statuses
            or severity in active_severities
        )

    def _needs_incident_recheck(
        self,
        actions: list[ActionRun],
        deployments: list[DeploymentState],
    ) -> bool:
        latest_incident = self._latest_incident_action(actions)

        if latest_incident is None:
            return False

        if not self._has_active_incident(actions):
            return False

        latest_status = self._latest_status_action(actions)

        if latest_status and latest_status.started_at and latest_incident.started_at:
            if latest_status.started_at > latest_incident.started_at:
                output = latest_status.output_json or {}
                output_status = str(output.get("status", "")).lower()
                health = output.get("health")

                if output_status in {"success", "healthy", "completed"}:
                    return True

                if isinstance(health, dict) and health.get("healthy") is True:
                    return True

        for deployment in deployments:
            if not deployment.last_checked_at or not latest_incident.started_at:
                continue

            if deployment.last_checked_at <= latest_incident.started_at:
                continue

            health_status = str(deployment.health_status or "").lower()

            if health_status in {"healthy", "success", "ok"}:
                return True

        return False

    def _is_final_report_ready(
        self,
        actions: list[ActionRun],
        artifacts: list[ProjectArtifact],
    ) -> bool:
        for artifact in artifacts:
            if artifact.artifact_type not in {"final_report", "demo_report"}:
                continue

            metadata = artifact.metadata_json or {}
            status = str(metadata.get("status", "")).lower()
            demo_ready = metadata.get("demo_ready")

            if status == "demo_ready" or demo_ready is True:
                return True

            if not status and artifact.name:
                return True

        return self._has_successful_action(
            actions=actions,
            action_types=["final_demo_report"],
        )

    def _has_successful_action(
        self,
        actions: list[ActionRun],
        action_types: list[str],
    ) -> bool:
        successful_statuses = {
            "success",
            "completed",
            "published",
            "deployed",
            "deployed_with_warnings",
            "healthy",
            "verified",
            "demo_ready",
            "plan_ready",
            "no_incident",
            "analyzed",
        }

        for action in actions:
            if action.action_type not in action_types:
                continue

            action_status = str(action.status or "").lower()

            if action_status in successful_statuses:
                return True

            if action.output_json:
                output_status = str(action.output_json.get("status", "")).lower()

                if output_status in successful_statuses:
                    return True

        return False

    def _latest_analysis(self, project: Project) -> dict[str, Any] | None:
        metadata = project.metadata_json or {}
        latest_analysis = metadata.get("latest_analysis")

        if isinstance(latest_analysis, dict):
            return latest_analysis

        return None

    def _primary_component(self, project: Project) -> dict[str, Any]:
        latest_analysis = self._latest_analysis(project) or {}
        primary_component = latest_analysis.get("primary_component")

        if isinstance(primary_component, dict):
            return primary_component

        components = latest_analysis.get("components")

        if isinstance(components, list):
            for component in components:
                if isinstance(component, dict):
                    return component

        return {}

    def _health_path(self, project: Project) -> str:
        latest_analysis = self._latest_analysis(project) or {}
        primary_component = self._primary_component(project)

        health_path = (
            primary_component.get("health_path")
            or latest_analysis.get("health_path")
            or "/health"
        )

        health_path = str(health_path).strip()

        if not health_path:
            return "/health"

        if not health_path.startswith("/"):
            health_path = "/" + health_path

        return health_path

    def _missing_devops_files(self, project: Project) -> list[str]:
        metadata = project.metadata_json or {}

        if isinstance(metadata.get("missing_devops_files"), list):
            return [str(item) for item in metadata["missing_devops_files"]]

        latest_analysis = self._latest_analysis(project)

        if latest_analysis and isinstance(latest_analysis.get("missing_devops_files"), list):
            return [str(item) for item in latest_analysis["missing_devops_files"]]

        return []

    def _important_files(self, project: Project) -> list[str]:
        latest_analysis = self._latest_analysis(project)

        if latest_analysis and isinstance(latest_analysis.get("important_files"), list):
            return [str(item) for item in latest_analysis["important_files"]]

        return []

    def _analysis_evidence(
        self,
        project: Project,
        latest_analysis: dict[str, Any] | None,
    ) -> list[str]:
        evidence = []

        if project.detected_language:
            evidence.append(f"Language: {project.detected_language}")

        if project.detected_framework:
            evidence.append(f"Framework: {project.detected_framework}")

        if project.port:
            evidence.append(f"Port: {project.port}")

        if project.start_command:
            evidence.append(f"Start command: {project.start_command}")

        health_path = self._health_path(project)

        if health_path:
            evidence.append(f"Health path: {health_path}")

        if latest_analysis:
            evidence.append("Repository analysis saved in project memory")

        return evidence

    def _docker_evidence(
        self,
        missing_devops_files: list[str],
        important_files: list[str],
        actions: list[ActionRun],
    ) -> list[str]:
        evidence = []

        for file_name in ["Dockerfile", ".dockerignore", "compose.yml", "docker-compose.yml"]:
            if self._contains_any(important_files, [file_name]):
                evidence.append(f"Detected file: {file_name}")

        if self._has_successful_action(actions=actions, action_types=["generate_docker"]):
            evidence.append("Docker generation action recorded")

        if self._has_successful_action(actions=actions, action_types=["prepare_deployment"]):
            evidence.append("Deployment preparation action recorded")

        if self._contains_any(missing_devops_files, ["Dockerfile"]):
            evidence.append("Dockerfile reported missing")

        return evidence

    def _kubernetes_evidence(
        self,
        missing_devops_files: list[str],
        important_files: list[str],
        actions: list[ActionRun],
    ) -> list[str]:
        evidence = []

        if self._contains_any(
            important_files,
            ["k8s", "kubernetes", "deployment.yaml", "kustomization.yaml"],
        ):
            evidence.append("Kubernetes files detected")

        if self._has_successful_action(
            actions=actions,
            action_types=["generate_kubernetes"],
        ):
            evidence.append("Kubernetes generation action recorded")

        if self._contains_any(missing_devops_files, ["Kubernetes manifests"]):
            evidence.append("Kubernetes manifests reported missing")

        return evidence

    def _azure_files_evidence(
        self,
        important_files: list[str],
        actions: list[ActionRun],
    ) -> list[str]:
        evidence = []

        if self._contains_any(important_files, ["azure/README.md", "azure\\README.md"]):
            evidence.append("Azure README detected")

        if self._contains_any(important_files, ["deploy-container-app.ps1"]):
            evidence.append("PowerShell Azure deploy script detected")

        if self._contains_any(important_files, ["deploy-container-app.sh"]):
            evidence.append("Shell Azure deploy script detected")

        if self._has_successful_action(
            actions=actions,
            action_types=["generate_azure"],
        ):
            evidence.append("Azure deployment files generation action recorded")

        return evidence

    def _cicd_evidence(
        self,
        project: Project,
        important_files: list[str],
        deployments: list[DeploymentState],
        actions: list[ActionRun],
    ) -> list[str]:
        evidence = []

        if self._contains_any(
            important_files,
            [".github/workflows", "docker-build.yml", "ci.yml", "deploy.yml"],
        ):
            evidence.append("CI/CD workflow file detected")

        if project.ghcr_image:
            evidence.append(f"Project GHCR image: {project.ghcr_image}")

        for deployment in deployments[:3]:
            if deployment.image and "ghcr.io" in str(deployment.image).lower():
                evidence.append(f"Deployment image: {deployment.image}")

        if self._has_successful_action(
            actions=actions,
            action_types=["generate_cicd"],
        ):
            evidence.append("CI/CD generation action recorded")

        return evidence[:8]

    def _image_evidence(
        self,
        project: Project,
        deployments: list[DeploymentState],
        actions: list[ActionRun],
    ) -> list[str]:
        evidence = []

        if project.ghcr_image:
            evidence.append(f"Project GHCR image: {project.ghcr_image}")

        for deployment in deployments[:3]:
            if deployment.image:
                evidence.append(f"Deployment image: {deployment.image}")

            if deployment.url:
                evidence.append("Deployment URL stored in memory")

        if self._has_successful_action(
            actions=actions,
            action_types=["deploy_azure_runtime"],
        ):
            evidence.append("Azure runtime deployment action recorded")

        return evidence[:8]

    def _deployment_evidence(
        self,
        project: Project,
        deployments: list[DeploymentState],
    ) -> list[str]:
        evidence = []

        if project.azure_resource_group:
            evidence.append(f"Resource group: {project.azure_resource_group}")

        if project.azure_app_name:
            evidence.append(f"App name: {project.azure_app_name}")

        if project.azure_app_url:
            evidence.append(f"App URL: {project.azure_app_url}")

        for deployment in deployments[:3]:
            if deployment.url:
                evidence.append("Deployment URL stored in deployment history")

            if deployment.image:
                evidence.append(f"Deployment image: {deployment.image}")

        return evidence

    def _status_evidence(
        self,
        project: Project,
        deployments: list[DeploymentState],
        actions: list[ActionRun],
    ) -> list[str]:
        evidence = []

        for deployment in deployments[:3]:
            if deployment.health_status:
                evidence.append(f"Health: {deployment.health_status}")

            if deployment.last_checked_at:
                evidence.append(f"Last checked: {deployment.last_checked_at.isoformat()}")

        if self._has_successful_action(
            actions=actions,
            action_types=["check_azure_status"],
        ):
            evidence.append("Azure status check action recorded")

        if project.azure_app_url:
            evidence.append("Azure app URL exists")

        evidence.append(f"Expected health path: {self._health_path(project)}")

        return evidence

    def _incident_evidence(
        self,
        actions: list[ActionRun],
    ) -> list[str]:
        action = self._latest_incident_action(actions)

        if not action:
            return []

        output = action.output_json or {}
        incident_detected = output.get("incident_detected")

        if incident_detected is False:
            return ["Latest incident analysis: no active incident detected"]

        if incident_detected is True:
            severity = output.get("severity")
            if severity:
                return [f"Latest incident analysis: incident detected, severity {severity}"]
            return ["Latest incident analysis: incident detected"]

        status = str(output.get("status", "") or action.status or "").lower()

        if status in {"no_incident", "healthy", "success", "completed"}:
            return ["Latest incident analysis: no active incident detected"]

        if status:
            return [f"Latest incident analysis status: {status}"]

        return ["Incident analysis recorded"]

    def _final_report_evidence(
        self,
        actions: list[ActionRun],
        artifacts: list[ProjectArtifact],
    ) -> list[str]:
        evidence = []

        for artifact in artifacts:
            if artifact.artifact_type not in {"final_report", "demo_report"}:
                continue

            metadata = artifact.metadata_json or {}
            status = str(metadata.get("status", "")).lower()
            demo_ready = metadata.get("demo_ready")

            if status == "demo_ready" or demo_ready is True:
                evidence.append(f"Final report artifact saved: {artifact.name or artifact.id}")
                evidence.append("Latest final report status: demo_ready")
                return evidence

            if not status:
                evidence.append(f"Final report artifact saved: {artifact.name or artifact.id}")
                return evidence

        for action in actions:
            if action.action_type != "final_demo_report":
                continue

            output = action.output_json or {}
            output_status = str(output.get("status", "")).lower()
            output_demo_ready = output.get("demo_ready")
            action_status = str(action.status or "").lower()

            if output_status == "demo_ready" or output_demo_ready is True or action_status == "demo_ready":
                return ["Final demo report action recorded: demo_ready"]

        return []

    def _contains_any(
        self,
        values: list[str],
        needles: list[str],
    ) -> bool:
        haystack = " ".join(values).lower()

        return any(needle.lower() in haystack for needle in needles)

    def _project_to_dict(self, project: Project) -> dict[str, Any]:
        return {
            "id": project.id,
            "name": project.name,
            "repo_url": project.repo_url,
            "repo_owner": project.repo_owner,
            "repo_name": project.repo_name,
            "default_branch": project.default_branch,
            "detected_language": project.detected_language,
            "detected_framework": project.detected_framework,
            "project_type": project.project_type,
            "port": project.port,
            "start_command": project.start_command,
            "health_path": self._health_path(project),
            "ghcr_image": project.ghcr_image,
            "azure_resource_group": project.azure_resource_group,
            "azure_app_name": project.azure_app_name,
            "azure_environment_name": project.azure_environment_name,
            "azure_app_url": project.azure_app_url,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        }

    def _step_to_dict(self, step: WorkflowStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "title": step.title,
            "description": step.description,
            "category": step.category,
            "status": step.status,
            "requires_approval": step.requires_approval,
            "can_execute_now": step.can_execute_now,
            "tool_intent": step.tool_intent,
            "user_message": step.user_message,
            "depends_on": step.depends_on,
            "evidence": step.evidence,
            "reason": step.reason,
        }
