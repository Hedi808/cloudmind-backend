from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc

from app.db.database import SessionLocal, create_database_tables
from app.db.models import LLMPlanningRun


class LLMPlanningAuditAgent:
    """Persists sanitized LLM planner inputs, outputs, fallbacks, and usage."""

    def record(
        self,
        *,
        project_id: str | None,
        session_id: str | None,
        provider: str,
        model: str | None,
        prompt_version: str,
        status: str,
        fallback_used: bool,
        request: dict[str, Any],
        response: dict[str, Any] | None,
        error: str | None,
        usage: dict[str, int | None] | None,
    ) -> dict[str, Any]:
        create_database_tables()
        usage = usage or {}

        with SessionLocal() as db:
            run = LLMPlanningRun(
                project_id=project_id,
                session_id=session_id,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                status=status,
                fallback_used=fallback_used,
                request_json=request,
                response_json=response,
                error=error,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                total_tokens=usage.get("total_tokens"),
                finished_at=datetime.now(timezone.utc),
            )
            db.add(run)
            db.commit()
            db.refresh(run)

            return {
                "id": run.id,
                "status": run.status,
                "provider": run.provider,
                "model": run.model,
                "fallback_used": run.fallback_used,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }

    def latest_provider_result(
        self,
        *,
        provider: str,
        model: str | None,
    ) -> dict[str, Any] | None:
        create_database_tables()

        with SessionLocal() as db:
            query = db.query(LLMPlanningRun).filter(
                LLMPlanningRun.provider == provider,
            )

            if model:
                query = query.filter(LLMPlanningRun.model == model)

            run = query.order_by(desc(LLMPlanningRun.created_at)).first()

            if run is None:
                return None

            return {
                "status": run.status,
                "fallback_used": run.fallback_used,
                "error": run.error,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }
