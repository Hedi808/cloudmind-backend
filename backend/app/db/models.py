from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    repo_url: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    repo_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repo_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)

    detected_language: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detected_framework: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_command: Mapped[str | None] = mapped_column(Text, nullable=True)

    ghcr_image: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    azure_resource_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    azure_app_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    azure_environment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    azure_app_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    sessions: Mapped[list["ConversationSession"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )

    action_runs: Mapped[list["ActionRun"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )

    artifacts: Mapped[list["ProjectArtifact"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )

    deployment_states: Mapped[list["DeploymentState"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    project: Mapped[Project | None] = relationship(back_populates="sessions")

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )

    action_runs: Mapped[list["ActionRun"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)

    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    intent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    session: Mapped[ConversationSession] = relationship(back_populates="messages")


class ActionRun(Base):
    __tablename__ = "action_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)

    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    action_type: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(100), nullable=False, default="started")

    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    input_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project | None] = relationship(back_populates="action_runs")
    session: Mapped[ConversationSession | None] = relationship(back_populates="action_runs")

    artifacts: Mapped[list["ProjectArtifact"]] = relationship(
        back_populates="action_run",
        cascade="all, delete-orphan",
    )


class ProjectArtifact(Base):
    __tablename__ = "project_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)

    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("action_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    artifact_type: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    project: Mapped[Project] = relationship(back_populates="artifacts")
    action_run: Mapped[ActionRun | None] = relationship(back_populates="artifacts")


class DeploymentState(Base):
    __tablename__ = "deployment_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)

    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider: Mapped[str] = mapped_column(String(100), nullable=False, default="azure")

    resource_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    app_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    environment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    image: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    health_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    project: Mapped[Project] = relationship(back_populates="deployment_states")