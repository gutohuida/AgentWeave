"""SQLAlchemy ORM models — 5 tables, all scoped to project_id."""

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    api_keys: Mapped[List["ApiKey"]] = relationship(back_populates="project")
    messages: Mapped[List["Message"]] = relationship(back_populates="project")
    tasks: Mapped[List["Task"]] = relationship(back_populates="project")
    questions: Mapped[List["Question"]] = relationship(back_populates="project")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # aw_live_...
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="api_keys")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    sender: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type: Mapped[str] = mapped_column(String(32), default="message", nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_messages_project_recipient", "project_id", "recipient"),
        Index("ix_messages_project_read", "project_id", "read"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    assignee: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    assigner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
    requirements: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    acceptance_criteria: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    deliverables: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="tasks")

    __table_args__ = (
        Index("ix_tasks_project_status", "project_id", "status"),
        Index("ix_tasks_project_assignee", "project_id", "assignee"),
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    from_agent: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="questions")


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    data: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="info", index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (Index("ix_event_logs_project_ts", "project_id", "timestamp"),)


class AgentHeartbeat(Base):
    __tablename__ = "agent_heartbeats"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (Index("ix_agent_heartbeats_project_agent", "project_id", "agent"),)


class ProjectSession(Base):
    """Stores the synced session.json content pushed from the CLI/watchdog.

    One row per project — upserted every time the local session.json changes.
    This lets the Hub (running in Docker with no filesystem access) know the
    full agent configuration including roles, yolo flags, and future fields.
    """

    __tablename__ = "project_sessions"

    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), primary_key=True)
    data: Mapped[Any] = mapped_column(JSON, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class ProjectRolesConfig(Base):
    """Stores the synced roles.json content pushed from the CLI at init time.

    One row per project — upserted whenever the local roles.json changes.
    Allows the Hub to know each agent's dev role without filesystem access.
    """

    __tablename__ = "project_roles_config"

    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), primary_key=True)
    data: Mapped[Any] = mapped_column(JSON, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class AgentOutput(Base):
    __tablename__ = "agent_outputs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_agent_outputs_project_agent", "project_id", "agent"),
        Index("ix_agent_outputs_project_ts", "project_id", "timestamp"),
    )
