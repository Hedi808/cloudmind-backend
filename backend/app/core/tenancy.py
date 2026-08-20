from __future__ import annotations

from typing import Any

from sqlalchemy import or_

from app.core.auth import hash_password
from app.core.config import settings
from app.db.database import SessionLocal, create_database_tables
from app.db.models import ConversationSession, LLMPlanningRun, PipelineRun, Project, User


def bootstrap_tenancy() -> dict[str, Any]:
    """Create the bootstrap admin and safely claim legacy unowned records."""

    create_database_tables()
    admin_email = settings.admin_email.strip().casefold()

    with SessionLocal() as db:
        admin = db.query(User).filter(User.email == admin_email).first()
        created = admin is None

        if admin is None:
            admin = User(
                email=admin_email,
                display_name=settings.admin_name.strip() or "CloudMind Admin",
                password_hash=hash_password(settings.admin_password),
                email_verified=True,
                is_active=True,
                role="admin",
                must_change_password=True,
            )
            db.add(admin)
            db.flush()
        else:
            admin.role = "admin"
            admin.is_active = True

        projects_assigned = (
            db.query(Project)
            .filter(Project.owner_id.is_(None))
            .update({Project.owner_id: admin.id}, synchronize_session=False)
        )

        legacy_sessions = (
            db.query(ConversationSession)
            .filter(ConversationSession.user_id.is_(None))
            .all()
        )
        for session in legacy_sessions:
            if session.project_id:
                project = db.get(Project, session.project_id)
                session.user_id = project.owner_id if project else admin.id
            else:
                session.user_id = admin.id

        legacy_runs = db.query(PipelineRun).filter(PipelineRun.user_id.is_(None)).all()
        for run in legacy_runs:
            owner_id = None
            if run.project_id:
                project = db.get(Project, run.project_id)
                owner_id = project.owner_id if project else None
            if owner_id is None and run.session_id:
                session = db.get(ConversationSession, run.session_id)
                owner_id = session.user_id if session else None
            run.user_id = owner_id or admin.id

        legacy_planning_runs = (
            db.query(LLMPlanningRun).filter(LLMPlanningRun.user_id.is_(None)).all()
        )
        for run in legacy_planning_runs:
            owner_id = None
            if run.project_id:
                project = db.get(Project, run.project_id)
                owner_id = project.owner_id if project else None
            if owner_id is None and run.session_id:
                session = db.get(ConversationSession, run.session_id)
                owner_id = session.user_id if session else None
            run.user_id = owner_id or admin.id

        # A session can never be attached to a project owned by another user.
        mismatched_sessions = (
            db.query(ConversationSession)
            .join(Project, Project.id == ConversationSession.project_id)
            .filter(
                ConversationSession.project_id.is_not(None),
                or_(
                    ConversationSession.user_id.is_(None),
                    ConversationSession.user_id != Project.owner_id,
                ),
            )
            .all()
        )
        for session in mismatched_sessions:
            session.user_id = session.project.owner_id

        db.commit()

        return {
            "admin_id": admin.id,
            "admin_email": admin.email,
            "admin_created": created,
            "projects_assigned": projects_assigned,
            "sessions_assigned": len(legacy_sessions),
            "pipeline_runs_assigned": len(legacy_runs),
            "planning_runs_assigned": len(legacy_planning_runs),
        }
