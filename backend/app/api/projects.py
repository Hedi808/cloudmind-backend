from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, or_

from app.core.auth import get_current_user_id
from app.db.database import SessionLocal, create_database_tables
from app.db.models import ActionRun, DeploymentState, Project, ProjectArtifact


router = APIRouter(
    prefix="/projects",
    tags=["Phase 18A - Project History"],
)


@router.get("")
def list_projects(
    q: str | None = Query(default=None, description="Search by project name, repo name, or repo URL."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    List saved CloudMind projects from PostgreSQL.
    """

    create_database_tables()

    with SessionLocal() as db:
        query = db.query(Project).filter(Project.owner_id == get_current_user_id())

        if q:
            search = f"%{q}%"
            query = query.filter(
                or_(
                    Project.name.ilike(search),
                    Project.repo_name.ilike(search),
                    Project.repo_url.ilike(search),
                )
            )

        total = query.count()

        projects = (
            query.order_by(desc(Project.updated_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "status": "success",
            "message": "Projects loaded successfully.",
            "total": total,
            "limit": limit,
            "offset": offset,
            "projects": [_project_to_dict(project) for project in projects],
        }


@router.get("/by-repo")
def get_project_by_repo(
    repo_url: str = Query(..., description="GitHub repository URL."),
) -> dict[str, Any]:
    """
    Load a project by repository URL.
    """

    create_database_tables()

    with SessionLocal() as db:
        project = (
            db.query(Project)
            .filter(
                Project.repo_url == repo_url,
                Project.owner_id == get_current_user_id(),
            )
            .first()
        )

        if project is None:
            raise HTTPException(
                status_code=404,
                detail=f"No project found for repo_url: {repo_url}",
            )

        return {
            "status": "success",
            "message": "Project loaded successfully.",
            "project": _project_to_dict(project),
            "context": _project_context(db=db, project_id=project.id),
        }


@router.get("/{project_id}")
def get_project(
    project_id: str,
) -> dict[str, Any]:
    """
    Load one project with latest deployment, actions, and artifacts.
    """

    create_database_tables()

    with SessionLocal() as db:
        project = _owned_project(db, project_id)

        if project is None:
            raise HTTPException(
                status_code=404,
                detail=f"Project not found: {project_id}",
            )

        return {
            "status": "success",
            "message": "Project loaded successfully.",
            "project": _project_to_dict(project),
            "context": _project_context(db=db, project_id=project_id),
        }


@router.get("/{project_id}/timeline")
def get_project_timeline(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    Load action history for a project.
    """

    create_database_tables()

    with SessionLocal() as db:
        project = _owned_project(db, project_id)

        if project is None:
            raise HTTPException(
                status_code=404,
                detail=f"Project not found: {project_id}",
            )

        query = db.query(ActionRun).filter(ActionRun.project_id == project_id)

        total = query.count()

        actions = (
            query.order_by(desc(ActionRun.started_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "status": "success",
            "message": "Project timeline loaded successfully.",
            "project": _project_to_dict(project),
            "total": total,
            "limit": limit,
            "offset": offset,
            "timeline": [_action_run_to_dict(action) for action in actions],
        }


@router.get("/{project_id}/artifacts")
def get_project_artifacts(
    project_id: str,
    artifact_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    Load generated files, PRs, reports, incidents, and other artifacts.
    """

    create_database_tables()

    with SessionLocal() as db:
        project = _owned_project(db, project_id)

        if project is None:
            raise HTTPException(
                status_code=404,
                detail=f"Project not found: {project_id}",
            )

        query = db.query(ProjectArtifact).filter(ProjectArtifact.project_id == project_id)

        if artifact_type:
            query = query.filter(ProjectArtifact.artifact_type == artifact_type)

        total = query.count()

        artifacts = (
            query.order_by(desc(ProjectArtifact.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "status": "success",
            "message": "Project artifacts loaded successfully.",
            "project": _project_to_dict(project),
            "total": total,
            "limit": limit,
            "offset": offset,
            "artifacts": [_artifact_to_dict(artifact) for artifact in artifacts],
        }


@router.get("/{project_id}/deployments")
def get_project_deployments(
    project_id: str,
    provider: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    Load deployment history for a project.
    """

    create_database_tables()

    with SessionLocal() as db:
        project = _owned_project(db, project_id)

        if project is None:
            raise HTTPException(
                status_code=404,
                detail=f"Project not found: {project_id}",
            )

        query = db.query(DeploymentState).filter(DeploymentState.project_id == project_id)

        if provider:
            query = query.filter(DeploymentState.provider == provider)

        total = query.count()

        deployments = (
            query.order_by(desc(DeploymentState.updated_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "status": "success",
            "message": "Project deployments loaded successfully.",
            "project": _project_to_dict(project),
            "total": total,
            "limit": limit,
            "offset": offset,
            "deployments": [_deployment_to_dict(deployment) for deployment in deployments],
        }


def _project_context(db, project_id: str) -> dict[str, Any]:
    project = _owned_project(db, project_id)

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

    latest_artifacts = (
        db.query(ProjectArtifact)
        .filter(ProjectArtifact.project_id == project_id)
        .order_by(desc(ProjectArtifact.created_at))
        .limit(20)
        .all()
    )

    return {
        "project": _project_to_dict(project) if project else None,
        "latest_deployment": _deployment_to_dict(latest_deployment) if latest_deployment else None,
        "latest_actions": [_action_run_to_dict(action) for action in latest_actions],
        "latest_artifacts": [_artifact_to_dict(artifact) for artifact in latest_artifacts],
    }


def _owned_project(db, project_id: str) -> Project | None:
    return (
        db.query(Project)
        .filter(
            Project.id == project_id,
            Project.owner_id == get_current_user_id(),
        )
        .first()
    )


def _project_to_dict(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "owner_id": project.owner_id,
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


def _action_run_to_dict(action: ActionRun) -> dict[str, Any]:
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


def _artifact_to_dict(artifact: ProjectArtifact) -> dict[str, Any]:
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


def _deployment_to_dict(deployment: DeploymentState) -> dict[str, Any]:
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
