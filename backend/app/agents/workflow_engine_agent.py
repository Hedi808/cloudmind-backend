from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc

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
    Phase 19D: Read-only workflow dependency planner with clean demo evidence.

    This agent does not execute tools.
    It reads PostgreSQL project memory and decides:
    - what is already done
    - what is missing
    - what is blocked
    - what CloudMind should do next

    Phase 19D improvement:
    - Old failed report attempts no longer appear as positive evidence.
    - Incident evidence is displayed in a clean demo-friendly way.
    - Final report evidence prefers saved report artifacts over old action statuses.
    """

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
                    "workflow": None,
                    "next_step": {
                        "id": "analyze_repository",
                        "title": "Analyze repository",
                        "reason": "This repository is not tracked yet. Analyze it first so CloudMind can create project memory.",
                        "user_message": "Analyze this repository",
                        "requires_approval": False,
                    },
                    "steps": [],
                    "summary": {
                        "total_steps": 0,
                        "completed": 0,
                        "required": 1,
                        "blocked": 0,
                        "optional": 0,
                        "progress_percent": 0,
                    },
                    "safety": {
                        "read_only_planner": True,
                        "executes_tools": False,
                        "creates_pull_requests": False,
                        "deploys_to_azure": False,
                        "approval_required_for_write_steps": True,
                    },
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

            workflow_status = self._workflow_status(
                steps=steps,
                next_step=next_step,
            )

            return {
                "status": workflow_status,
                "message": self._workflow_message(workflow_status, next_step),
                "project": self._project_to_dict(project),
                "workflow": {
                    "id": "full_deployment_pipeline",
                    "title": "Full Deployment Pipeline",
                    "description": (
                        "Analyze repository, generate DevOps assets through GitOps PRs, "
                        "build container image, deploy to Azure, verify health, analyze incidents, "
                        "and generate a final report."
                    ),
                },
                "next_step": self._step_to_dict(next_step) if next_step else None,
                "steps": [self._step_to_dict(step) for step in steps],
                "summary": summary,
                "safety": {
                    "read_only_planner": True,
                    "executes_tools": False,
                    "creates_pull_requests": False,
                    "deploys_to_azure": False,
                    "approval_required_for_write_steps": True,
                },
            }

    def _load_project(
        self,
        db,
        project_id: str | None,
        repo_url: str | None,
    ) -> Project | None:
        if project_id:
            return db.get(Project, project_id)

        if repo_url:
            return db.query(Project).filter(Project.repo_url == repo_url).first()

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

        azure_files_ready = self._is_azure_files_ready(
            important_files=important_files,
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

        final_report_ready = self._is_final_report_ready(
            actions=actions,
            artifacts=artifacts,
        )

        steps = [
            WorkflowStep(
                id="analyze_repository",
                title="Analyze repository",
                description="Detect language, framework, port, start command, and missing DevOps files.",
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
                status=self._dependent_status(
                    completed=docker_ready,
                    dependencies_done=analyzed,
                    required=True,
                ),
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
                    else "Docker files are required before reliable image build and deployment."
                ),
            ),
            WorkflowStep(
                id="generate_kubernetes",
                title="Generate Kubernetes manifests",
                description="Create Kubernetes manifests through a GitHub pull request.",
                category="gitops",
                status=self._dependent_status(
                    completed=kubernetes_ready,
                    dependencies_done=analyzed,
                    required=False,
                ),
                requires_approval=True,
                can_execute_now=analyzed and not kubernetes_ready,
                tool_intent="generate_kubernetes",
                user_message="Generate Kubernetes manifests for this repo",
                depends_on=["analyze_repository"],
                evidence=self._kubernetes_evidence(
                    missing_devops_files=missing_devops_files,
                    important_files=important_files,
                    actions=actions,
                ),
                reason=(
                    "Kubernetes manifests are present or were generated before."
                    if kubernetes_ready
                    else "Kubernetes manifests are useful for portability, even if Azure Container Apps is the current target."
                ),
            ),
            WorkflowStep(
                id="generate_cicd",
                title="Generate CI/CD workflow",
                description="Create GitHub Actions workflow to build and publish the Docker image to GHCR.",
                category="gitops",
                status=self._dependent_status(
                    completed=cicd_ready,
                    dependencies_done=docker_ready,
                    required=True,
                ),
                requires_approval=True,
                can_execute_now=docker_ready and not cicd_ready,
                tool_intent="generate_cicd",
                user_message="Generate CI/CD for this repo",
                depends_on=["generate_docker"],
                evidence=self._cicd_evidence(
                    project=project,
                    important_files=important_files,
                    deployments=deployments,
                    actions=actions,
                ),
                reason=(
                    "CI/CD is already available or the project has deployment/image evidence, so it does not block the workflow."
                    if cicd_ready
                    else "A CI/CD workflow is needed to build and publish the container image."
                ),
            ),
            WorkflowStep(
                id="publish_container_image",
                title="Publish container image",
                description="Confirm that GitHub Actions published a GHCR image.",
                category="image",
                status=self._dependent_status(
                    completed=image_ready,
                    dependencies_done=cicd_ready,
                    required=True,
                ),
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
                    "A container image or successful Azure deployment exists in memory."
                    if image_ready
                    else "CloudMind needs a published image before Azure runtime deployment."
                ),
            ),
            WorkflowStep(
                id="generate_azure_files",
                title="Generate Azure deployment files",
                description="Create Azure Container Apps deployment scripts and README through a GitHub pull request.",
                category="gitops",
                status=self._dependent_status(
                    completed=azure_files_ready,
                    dependencies_done=analyzed,
                    required=False,
                ),
                requires_approval=True,
                can_execute_now=analyzed and not azure_files_ready,
                tool_intent="generate_azure",
                user_message="Generate Azure deployment files for this repo",
                depends_on=["analyze_repository"],
                evidence=self._azure_files_evidence(
                    important_files=important_files,
                    actions=actions,
                ),
                reason=(
                    "Azure deployment assets exist or were generated before."
                    if azure_files_ready
                    else "Azure files help document and reproduce deployment."
                ),
            ),
            WorkflowStep(
                id="deploy_to_azure",
                title="Deploy to Azure Container Apps",
                description="Deploy the GHCR image to Azure Container Apps with human approval.",
                category="runtime",
                status=self._dependent_status(
                    completed=deployed,
                    dependencies_done=image_ready,
                    required=True,
                ),
                requires_approval=True,
                can_execute_now=image_ready and not deployed,
                tool_intent="deploy_azure_runtime",
                user_message="Deploy this app to Azure",
                depends_on=["publish_container_image"],
                evidence=self._deployment_evidence(
                    project=project,
                    deployments=deployments,
                ),
                reason=(
                    "Azure deployment exists in project memory."
                    if deployed
                    else "The app needs to be deployed to Azure before runtime verification."
                ),
            ),
            WorkflowStep(
                id="check_azure_status",
                title="Check Azure status",
                description="Verify Azure Container App status, revision, URL, and health.",
                category="observability",
                status=self._dependent_status(
                    completed=azure_status_checked,
                    dependencies_done=deployed,
                    required=True,
                ),
                requires_approval=False,
                can_execute_now=deployed,
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
                    else "Runtime status should be checked after deployment."
                ),
            ),
            WorkflowStep(
                id="analyze_incident",
                title="Analyze incident state",
                description="Analyze Azure status and logs to detect active incidents.",
                category="observability",
                status=self._dependent_status(
                    completed=incident_checked,
                    dependencies_done=deployed,
                    required=True,
                ),
                requires_approval=False,
                can_execute_now=deployed and not incident_checked,
                tool_intent="analyze_incident",
                user_message="Analyze incident for this Azure app",
                depends_on=["deploy_to_azure"],
                evidence=self._incident_evidence(actions=actions),
                reason=(
                    "Incident analysis has already been recorded."
                    if incident_checked
                    else "Incident analysis proves the system can diagnose runtime issues."
                ),
            ),
            WorkflowStep(
                id="final_demo_report",
                title="Generate final demo report",
                description="Generate an end-to-end report summarizing repo analysis, GitOps, deployment, health, and incidents.",
                category="reporting",
                status=self._dependent_status(
                    completed=final_report_ready,
                    dependencies_done=deployed and azure_status_checked,
                    required=False,
                ),
                requires_approval=False,
                can_execute_now=deployed and azure_status_checked and not final_report_ready,
                tool_intent="final_demo_report",
                user_message="Generate the final demo report",
                depends_on=["deploy_to_azure", "check_azure_status"],
                evidence=self._final_report_evidence(
                    actions=actions,
                    artifacts=artifacts,
                ),
                reason=(
                    "A final report was already generated."
                    if final_report_ready
                    else "A final report is useful for the professor/demo."
                ),
            ),
        ]

        return steps

    def _find_next_step(self, steps: list[WorkflowStep]) -> WorkflowStep | None:
        for step in steps:
            if step.status == "required" and step.can_execute_now:
                return step

        final_report_step = next(
            (
                step
                for step in steps
                if step.id == "final_demo_report"
                and step.status == "optional"
                and step.can_execute_now
            ),
            None,
        )

        if final_report_step:
            return final_report_step

        for step in steps:
            if step.status == "optional" and step.can_execute_now:
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
        required_step_ids = {
            "analyze_repository",
            "generate_docker",
            "generate_cicd",
            "publish_container_image",
            "deploy_to_azure",
            "check_azure_status",
            "analyze_incident",
        }

        required_unfinished = [
            step
            for step in steps
            if step.id in required_step_ids and step.status in {"required", "blocked"}
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
            if next_step and next_step.id == "final_demo_report":
                return "The main deployment workflow is ready. Next optional step: generate the final demo report."

            return "The main deployment workflow is ready. Required steps are complete."

        if workflow_status == "workflow_blocked":
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

        if project.ghcr_image:
            return True

        if project.azure_app_url:
            return True

        for deployment in deployments:
            if deployment.image and "ghcr.io" in deployment.image.lower():
                return True

            if deployment.url:
                return True

        return self._has_successful_action(
            actions=actions,
            action_types=["generate_cicd"],
        )

    def _is_image_ready(
        self,
        project: Project,
        deployments: list[DeploymentState],
        actions: list[ActionRun],
    ) -> bool:
        if project.ghcr_image:
            return True

        if project.azure_app_url:
            return True

        for deployment in deployments:
            if deployment.image:
                return True

            if deployment.url:
                return True

        return self._has_successful_action(
            actions=actions,
            action_types=["generate_cicd", "deploy_azure_runtime"],
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
            ],
        )

        return azure_files_seen or self._has_successful_action(
            actions=actions,
            action_types=["generate_azure"],
        )

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
        if any(deployment.health_status for deployment in deployments):
            return True

        if project.azure_app_url and project.azure_resource_group and project.azure_app_name:
            return self._has_successful_action(
                actions=actions,
                action_types=["check_azure_status"],
            )

        return False

    def _is_incident_checked(self, actions: list[ActionRun]) -> bool:
        for action in actions:
            if action.action_type != "analyze_incident":
                continue

            action_status = str(action.status or "").lower()

            if action_status in {
                "success",
                "completed",
                "no_incident",
                "incident_detected",
                "healthy",
            }:
                return True

            if action.output_json:
                output_status = str(action.output_json.get("status", "")).lower()

                if output_status in {
                    "success",
                    "completed",
                    "no_incident",
                    "incident_detected",
                    "healthy",
                }:
                    return True

                if "incident_detected" in action.output_json:
                    return True

        return False

    def _is_final_report_ready(
        self,
        actions: list[ActionRun],
        artifacts: list[ProjectArtifact],
    ) -> bool:
        for artifact in artifacts:
            if artifact.artifact_type in {"final_report", "demo_report"}:
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
            "healthy",
            "verified",
            "demo_ready",
            "plan_ready",
            "no_incident",
            "incident_detected",
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

                if "incident_detected" in action.output_json:
                    return True

        return False

    def _latest_analysis(self, project: Project) -> dict[str, Any] | None:
        metadata = project.metadata_json or {}
        latest_analysis = metadata.get("latest_analysis")

        if isinstance(latest_analysis, dict):
            return latest_analysis

        return None

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

        for file_name in ["Dockerfile", ".dockerignore", "compose.yml"]:
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
            ["k8s", "deployment.yaml", "kustomization.yaml"],
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

        if project.azure_app_url:
            evidence.append("Azure deployment exists, so CI/CD state does not block the demo")

        for deployment in deployments[:3]:
            if deployment.image:
                evidence.append(f"Deployment image: {deployment.image}")

            if deployment.url:
                evidence.append("Deployment URL stored in memory")

        if self._has_successful_action(
            actions=actions,
            action_types=["generate_cicd"],
        ):
            evidence.append("CI/CD generation action recorded")

        return evidence[:8]

    def _action_evidence(
        self,
        actions: list[ActionRun],
        action_types: list[str],
    ) -> list[str]:
        evidence = []
        seen_action_types = set()

        for action in actions:
            if action.action_type not in action_types:
                continue

            if action.action_type in seen_action_types:
                continue

            seen_action_types.add(action.action_type)

            clean_status = self._clean_action_status_label(action)

            evidence.append(f"{self._clean_action_type_label(action.action_type)}: {clean_status}")

        return evidence[:5]

    def _incident_evidence(
        self,
        actions: list[ActionRun],
    ) -> list[str]:
        for action in actions:
            if action.action_type != "analyze_incident":
                continue

            output = action.output_json or {}
            incident_detected = output.get("incident_detected")

            if incident_detected is False:
                return ["Incident analysis recorded: no active incident detected"]

            if incident_detected is True:
                severity = output.get("severity")
                if severity:
                    return [f"Incident analysis recorded: incident detected, severity {severity}"]
                return ["Incident analysis recorded: incident detected"]

            if output:
                status = str(output.get("status", "")).lower()

                if status in {"no_incident", "healthy", "success", "completed"}:
                    return ["Incident analysis recorded: no active incident detected"]

                return ["Incident analysis recorded"]

            return ["Incident analysis recorded"]

        return []

    def _image_evidence(
        self,
        project: Project,
        deployments: list[DeploymentState],
        actions: list[ActionRun],
    ) -> list[str]:
        evidence = []

        if project.ghcr_image:
            evidence.append(f"Project GHCR image: {project.ghcr_image}")

        if project.azure_app_url:
            evidence.append("Azure deployment exists, so a deployable image was already used")

        for deployment in deployments[:3]:
            if deployment.image:
                evidence.append(f"Deployment image: {deployment.image}")

            if deployment.url:
                evidence.append("Deployment URL stored in memory")

        if self._has_successful_action(
            actions=actions,
            action_types=["generate_cicd"],
        ):
            evidence.append("CI/CD generation action recorded")

        if self._has_successful_action(
            actions=actions,
            action_types=["deploy_azure_runtime"],
        ):
            evidence.append("Azure runtime deployment action recorded")

        return evidence[:8]

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

        return evidence

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

    def _clean_action_type_label(self, action_type: str) -> str:
        labels = {
            "analyze_repo": "Repository analysis",
            "generate_docker": "Docker generation",
            "generate_kubernetes": "Kubernetes generation",
            "generate_cicd": "CI/CD generation",
            "generate_azure": "Azure files generation",
            "deploy_azure_runtime": "Azure runtime deployment",
            "check_azure_status": "Azure status check",
            "analyze_incident": "Incident analysis",
            "final_demo_report": "Final demo report",
            "prepare_deployment": "Deployment preparation",
        }

        return labels.get(action_type, action_type.replace("_", " ").title())

    def _clean_action_status_label(self, action: ActionRun) -> str:
        output = action.output_json or {}
        action_status = str(action.status or "").lower()
        output_status = str(output.get("status", "")).lower()

        if action.action_type == "analyze_incident":
            incident_detected = output.get("incident_detected")

            if incident_detected is False:
                return "no active incident detected"

            if incident_detected is True:
                severity = output.get("severity")
                if severity:
                    return f"incident detected, severity {severity}"
                return "incident detected"

            return "analysis recorded"

        if action.action_type == "final_demo_report":
            demo_ready = output.get("demo_ready")

            if output_status == "demo_ready" or demo_ready is True or action_status == "demo_ready":
                return "demo_ready"

            if output_status == "demo_blocked" or action_status == "demo_blocked":
                return "previous report attempt blocked"

            return "report recorded"

        clean_statuses = {
            "success": "success",
            "completed": "completed",
            "published": "published",
            "deployed": "deployed",
            "healthy": "healthy",
            "verified": "verified",
            "demo_ready": "demo_ready",
            "plan_ready": "plan_ready",
            "no_incident": "no active incident",
            "incident_detected": "incident analysis recorded",
            "analyzed": "analyzed",
        }

        if output_status in clean_statuses:
            return clean_statuses[output_status]

        if action_status in clean_statuses:
            return clean_statuses[action_status]

        return action_status or "recorded"

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