from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, create_database_tables
from app.db.models import (
    ActionRun,
    ConversationMessage,
    ConversationSession,
    DeploymentState,
    Project,
    ProjectArtifact,
)


class ProjectMemoryAgent:
    """
    Persistent PostgreSQL memory for CloudMind.

    Responsibilities:
    - Remember projects by repository URL.
    - Store repo analysis.
    - Store conversations.
    - Store action runs.
    - Store generated artifacts, PRs, deployments, and health states.
    """

    def __init__(self) -> None:
        create_database_tables()

    def create_or_get_project(
        self,
        repo_url: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            project = self._get_project_by_repo_url_db(db=db, repo_url=repo_url)

            if project is None:
                repo_owner, repo_name = self._parse_github_repo(repo_url)

                project = Project(
                    name=name or repo_name,
                    repo_url=repo_url,
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    metadata_json={},
                )

                db.add(project)
                db.commit()
                db.refresh(project)

            return self._project_to_dict(project)

    def get_project_by_repo_url(
        self,
        repo_url: str,
    ) -> dict[str, Any] | None:
        with SessionLocal() as db:
            project = self._get_project_by_repo_url_db(db=db, repo_url=repo_url)

            if project is None:
                return None

            return self._project_to_dict(project)

    def get_project_context(
        self,
        project_id: str,
    ) -> dict[str, Any] | None:
        with SessionLocal() as db:
            project = db.get(Project, project_id)

            if project is None:
                return None

            latest_deployment = (
                db.query(DeploymentState)
                .filter(DeploymentState.project_id == project_id)
                .order_by(desc(DeploymentState.updated_at))
                .first()
            )

            latest_actions = (
                db.query(ActionRun)
                .filter(ActionRun.project_id == project_id)
                .order_by(desc(ActionRun.started_at))
                .limit(20)
                .all()
            )

            artifacts = (
                db.query(ProjectArtifact)
                .filter(ProjectArtifact.project_id == project_id)
                .order_by(desc(ProjectArtifact.created_at))
                .limit(20)
                .all()
            )

            return {
                "project": self._project_to_dict(project),
                "latest_deployment": self._deployment_to_dict(latest_deployment) if latest_deployment else None,
                "latest_actions": [self._action_run_to_dict(action) for action in latest_actions],
                "latest_artifacts": [self._artifact_to_dict(artifact) for artifact in artifacts],
            }

    def save_repo_analysis(
        self,
        project_id: str,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            project = db.get(Project, project_id)

            if project is None:
                raise ValueError(f"Project not found: {project_id}")

            detected_languages = analysis.get("detected_languages", [])
            detected_frameworks = analysis.get("detected_frameworks", [])
            components = analysis.get("components", [])

            first_component = components[0] if components else {}

            project.name = analysis.get("repo_name") or project.name
            project.repo_name = analysis.get("repo_name") or project.repo_name
            project.project_type = analysis.get("project_type")
            project.detected_language = detected_languages[0] if detected_languages else None
            project.detected_framework = detected_frameworks[0] if detected_frameworks else None
            project.port = first_component.get("port")
            project.start_command = first_component.get("start_command")
            project.metadata_json = {
                **(project.metadata_json or {}),
                "latest_analysis": analysis,
                "missing_devops_files": analysis.get("missing_devops_files", []),
                "recommendations": analysis.get("recommendations", []),
            }
            project.updated_at = self._now()

            db.commit()
            db.refresh(project)

            return self._project_to_dict(project)

    def create_or_get_session(
        self,
        session_id: str | None = None,
        project_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            session = None

            if session_id:
                session = db.get(ConversationSession, session_id)

            if session is None:
                session = ConversationSession(
                    id=session_id if session_id else None,
                    project_id=project_id,
                    title=title or "CloudMind session",
                    metadata_json={},
                )

                db.add(session)
                db.commit()
                db.refresh(session)

            else:
                if project_id and session.project_id != project_id:
                    session.project_id = project_id

                if title:
                    session.title = title

                session.updated_at = self._now()
                db.commit()
                db.refresh(session)

            return self._session_to_dict(session)

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        intent: str | None = None,
        tool_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            session = db.get(ConversationSession, session_id)

            if session is None:
                session = ConversationSession(
                    id=session_id,
                    title="CloudMind session",
                    metadata_json={},
                )
                db.add(session)
                db.commit()
                db.refresh(session)

            message = ConversationMessage(
                session_id=session.id,
                role=role,
                content=content,
                intent=intent,
                tool_name=tool_name,
                metadata_json=metadata or {},
            )

            session.updated_at = self._now()

            db.add(message)
            db.commit()
            db.refresh(message)

            return self._message_to_dict(message)

    def start_action_run(
        self,
        project_id: str | None,
        session_id: str | None,
        action_type: str,
        tool_name: str | None,
        approval_required: bool,
        approval_confirmed: bool,
        input_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            action = ActionRun(
                project_id=project_id,
                session_id=session_id,
                action_type=action_type,
                tool_name=tool_name,
                status="started",
                approval_required=approval_required,
                approval_confirmed=approval_confirmed,
                input_json=input_json or {},
            )

            db.add(action)
            db.commit()
            db.refresh(action)

            return self._action_run_to_dict(action)

    def finish_action_run(
        self,
        action_run_id: str,
        status: str,
        output_json: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            action = db.get(ActionRun, action_run_id)

            if action is None:
                raise ValueError(f"Action run not found: {action_run_id}")

            action.status = status
            action.output_json = output_json or {}
            action.error = error
            action.finished_at = self._now()

            db.commit()
            db.refresh(action)

            return self._action_run_to_dict(action)

    def save_completed_action(
        self,
        project_id: str | None,
        session_id: str | None,
        action_type: str,
        tool_name: str | None,
        status: str,
        approval_required: bool,
        approval_confirmed: bool,
        input_json: dict[str, Any] | None = None,
        output_json: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        started = self.start_action_run(
            project_id=project_id,
            session_id=session_id,
            action_type=action_type,
            tool_name=tool_name,
            approval_required=approval_required,
            approval_confirmed=approval_confirmed,
            input_json=input_json,
        )

        return self.finish_action_run(
            action_run_id=started["id"],
            status=status,
            output_json=output_json,
            error=error,
        )

    def save_artifact(
        self,
        project_id: str,
        artifact_type: str,
        name: str | None = None,
        path: str | None = None,
        url: str | None = None,
        action_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            artifact = ProjectArtifact(
                project_id=project_id,
                action_run_id=action_run_id,
                artifact_type=artifact_type,
                name=name,
                path=path,
                url=url,
                metadata_json=metadata or {},
            )

            db.add(artifact)
            db.commit()
            db.refresh(artifact)

            return self._artifact_to_dict(artifact)

    def save_pull_request_artifact(
        self,
        project_id: str,
        pull_request: dict[str, Any],
        action_run_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not pull_request:
            return None

        pr_url = (
            pull_request.get("url")
            or pull_request.get("html_url")
            or pull_request.get("pull_request_url")
        )

        pr_number = pull_request.get("number") or pull_request.get("pr_number")

        return self.save_artifact(
            project_id=project_id,
            action_run_id=action_run_id,
            artifact_type="github_pull_request",
            name=f"PR #{pr_number}" if pr_number else "GitHub Pull Request",
            url=pr_url,
            metadata=pull_request,
        )

    def save_generated_files(
        self,
        project_id: str,
        files: list[str],
        action_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        artifacts = []

        for file_path in files:
            artifacts.append(
                self.save_artifact(
                    project_id=project_id,
                    action_run_id=action_run_id,
                    artifact_type="generated_file",
                    name=file_path,
                    path=file_path,
                    metadata=metadata or {},
                )
            )

        return artifacts

    def save_deployment_state(
        self,
        project_id: str,
        provider: str,
        resource_group: str | None,
        app_name: str | None,
        environment_name: str | None,
        image: str | None,
        url: str | None,
        health_status: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            existing = (
                db.query(DeploymentState)
                .filter(
                    DeploymentState.project_id == project_id,
                    DeploymentState.provider == provider,
                    DeploymentState.app_name == app_name,
                )
                .first()
            )

            if existing is None:
                deployment = DeploymentState(
                    project_id=project_id,
                    provider=provider,
                    resource_group=resource_group,
                    app_name=app_name,
                    environment_name=environment_name,
                    image=image,
                    url=url,
                    health_status=health_status,
                    last_checked_at=self._now(),
                    metadata_json=metadata or {},
                )

                db.add(deployment)

            else:
                deployment = existing
                deployment.resource_group = resource_group
                deployment.environment_name = environment_name
                deployment.image = image
                deployment.url = url
                deployment.health_status = health_status
                deployment.last_checked_at = self._now()
                deployment.metadata_json = metadata or {}
                deployment.updated_at = self._now()

            project = db.get(Project, project_id)

            if project:
                project.azure_resource_group = resource_group
                project.azure_app_name = app_name
                project.azure_environment_name = environment_name
                project.azure_app_url = url
                project.ghcr_image = image or project.ghcr_image
                project.updated_at = self._now()

            db.commit()
            db.refresh(deployment)

            return self._deployment_to_dict(deployment)

    def get_project_timeline(
        self,
        project_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with SessionLocal() as db:
            actions = (
                db.query(ActionRun)
                .filter(ActionRun.project_id == project_id)
                .order_by(desc(ActionRun.started_at))
                .limit(limit)
                .all()
            )

            return [self._action_run_to_dict(action) for action in actions]

    def _get_project_by_repo_url_db(
        self,
        db: Session,
        repo_url: str,
    ) -> Project | None:
        return (
            db.query(Project)
            .filter(Project.repo_url == repo_url)
            .first()
        )

    def _parse_github_repo(
        self,
        repo_url: str,
    ) -> tuple[str | None, str | None]:
        parsed = urlparse(repo_url)
        parts = [part for part in parsed.path.split("/") if part]

        if len(parts) >= 2:
            return parts[0], parts[1].removesuffix(".git")

        return None, None

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _project_to_dict(
        self,
        project: Project,
    ) -> dict[str, Any]:
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
            "metadata_json": project.metadata_json,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        }

    def _session_to_dict(
        self,
        session: ConversationSession,
    ) -> dict[str, Any]:
        return {
            "id": session.id,
            "project_id": session.project_id,
            "title": session.title,
            "metadata_json": session.metadata_json,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        }

    def _message_to_dict(
        self,
        message: ConversationMessage,
    ) -> dict[str, Any]:
        return {
            "id": message.id,
            "session_id": message.session_id,
            "role": message.role,
            "content": message.content,
            "intent": message.intent,
            "tool_name": message.tool_name,
            "metadata_json": message.metadata_json,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    def _action_run_to_dict(
        self,
        action: ActionRun,
    ) -> dict[str, Any]:
        return {
            "id": action.id,
            "project_id": action.project_id,
            "session_id": action.session_id,
            "action_type": action.action_type,
            "tool_name": action.tool_name,
            "status": action.status,
            "approval_required": action.approval_required,
            "approval_confirmed": action.approval_confirmed,
            "input_json": action.input_json,
            "output_json": action.output_json,
            "error": action.error,
            "started_at": action.started_at.isoformat() if action.started_at else None,
            "finished_at": action.finished_at.isoformat() if action.finished_at else None,
        }

    def _artifact_to_dict(
        self,
        artifact: ProjectArtifact,
    ) -> dict[str, Any]:
        return {
            "id": artifact.id,
            "project_id": artifact.project_id,
            "action_run_id": artifact.action_run_id,
            "artifact_type": artifact.artifact_type,
            "name": artifact.name,
            "path": artifact.path,
            "url": artifact.url,
            "metadata_json": artifact.metadata_json,
            "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        }

    def _deployment_to_dict(
        self,
        deployment: DeploymentState,
    ) -> dict[str, Any]:
        return {
            "id": deployment.id,
            "project_id": deployment.project_id,
            "provider": deployment.provider,
            "resource_group": deployment.resource_group,
            "app_name": deployment.app_name,
            "environment_name": deployment.environment_name,
            "image": deployment.image,
            "url": deployment.url,
            "health_status": deployment.health_status,
            "last_checked_at": deployment.last_checked_at.isoformat() if deployment.last_checked_at else None,
            "metadata_json": deployment.metadata_json,
            "created_at": deployment.created_at.isoformat() if deployment.created_at else None,
            "updated_at": deployment.updated_at.isoformat() if deployment.updated_at else None,
        }