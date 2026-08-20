from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func

from app.core.auth import require_admin_user
from app.db.database import SessionLocal, create_database_tables
from app.db.models import (
    ActionRun,
    ConversationMessage,
    ConversationSession,
    PipelineRun,
    Project,
    User,
    UserSession,
)


router = APIRouter(prefix="/admin", tags=["Phase 23 - Administration"])


@router.get("/overview")
def admin_overview(_: User = Depends(require_admin_user)) -> dict[str, Any]:
    create_database_tables()
    with SessionLocal() as db:
        metrics = {
            "users": db.query(func.count(User.id)).scalar() or 0,
            "active_users": (
                db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar()
                or 0
            ),
            "projects": db.query(func.count(Project.id)).scalar() or 0,
            "conversations": db.query(func.count(ConversationSession.id)).scalar() or 0,
            "messages": db.query(func.count(ConversationMessage.id)).scalar() or 0,
            "agent_actions": db.query(func.count(ActionRun.id)).scalar() or 0,
            "pipeline_runs": db.query(func.count(PipelineRun.id)).scalar() or 0,
            "live_sessions": (
                db.query(func.count(UserSession.id))
                .filter(UserSession.revoked_at.is_(None))
                .scalar()
                or 0
            ),
        }
        users = db.query(User).order_by(User.created_at.desc()).limit(8).all()
        return {
            "status": "success",
            "message": "CloudMind administration overview loaded.",
            "metrics": metrics,
            "recent_users": [_user_summary(db, user) for user in users],
        }


@router.get("/users")
def list_users(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin_user),
) -> dict[str, Any]:
    create_database_tables()
    with SessionLocal() as db:
        total = db.query(func.count(User.id)).scalar() or 0
        users = (
            db.query(User)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "status": "success",
            "total": total,
            "limit": limit,
            "offset": offset,
            "users": [_user_summary(db, user) for user in users],
        }


def _user_summary(db, user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
        "auth_provider": "google" if user.google_sub else "password",
        "project_count": (
            db.query(func.count(Project.id))
            .filter(Project.owner_id == user.id)
            .scalar()
            or 0
        ),
        "conversation_count": (
            db.query(func.count(ConversationSession.id))
            .filter(ConversationSession.user_id == user.id)
            .scalar()
            or 0
        ),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }
