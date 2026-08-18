from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc

from app.db.database import SessionLocal, create_database_tables
from app.db.models import PipelineRun


class PipelineRunAgent:
    """PostgreSQL persistence for resumable CloudMind pipeline runs."""

    TERMINAL_STATUSES = {"completed", "failed", "blocked_incident", "cancelled"}

    def __init__(self) -> None:
        create_database_tables()

    def create_run(
        self,
        context: dict[str, Any],
        status: str = "running",
        checkpoint_status: str = "ready",
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            run = PipelineRun(
                project_id=context.get("project_id"),
                session_id=context.get("session_id"),
                status=status,
                checkpoint_status=checkpoint_status,
                repo_url=context.get("repo_url"),
                pull_request_url=context.get("pull_request_url"),
                image=context.get("image"),
                context_json=dict(context),
                executed_steps_json=[],
                checkpoint_json={},
            )
            db.add(run)
            db.commit()
            db.refresh(run)
            return self._to_dict(run)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with SessionLocal() as db:
            run = db.get(PipelineRun, run_id)
            return self._to_dict(run) if run else None

    def list_runs(
        self,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        with SessionLocal() as db:
            query = db.query(PipelineRun)

            if project_id:
                query = query.filter(PipelineRun.project_id == project_id)

            runs = query.order_by(desc(PipelineRun.updated_at)).limit(max(1, min(limit, 100))).all()
            return [self._to_dict(run) for run in runs]

    def update_run(
        self,
        run_id: str,
        **updates: Any,
    ) -> dict[str, Any]:
        allowed_fields = {
            "project_id",
            "session_id",
            "status",
            "checkpoint_status",
            "pause_reason",
            "repo_url",
            "pull_request_url",
            "pull_request_number",
            "merge_commit_sha",
            "image",
            "context_json",
            "executed_steps_json",
            "checkpoint_json",
            "last_error",
        }

        with SessionLocal() as db:
            run = db.get(PipelineRun, run_id)

            if run is None:
                raise ValueError(f"Pipeline run not found: {run_id}")

            for key, value in updates.items():
                if key in allowed_fields:
                    setattr(run, key, value)

            run.updated_at = self._now()

            if run.status in self.TERMINAL_STATUSES:
                run.completed_at = run.completed_at or self._now()
            else:
                run.completed_at = None

            db.commit()
            db.refresh(run)
            return self._to_dict(run)

    def _to_dict(self, run: PipelineRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "project_id": run.project_id,
            "session_id": run.session_id,
            "status": run.status,
            "checkpoint_status": run.checkpoint_status,
            "pause_reason": run.pause_reason,
            "repo_url": run.repo_url,
            "pull_request_url": run.pull_request_url,
            "pull_request_number": run.pull_request_number,
            "merge_commit_sha": run.merge_commit_sha,
            "image": run.image,
            "context": run.context_json or {},
            "executed_steps": run.executed_steps_json or [],
            "checkpoint": run.checkpoint_json or {},
            "last_error": run.last_error,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
