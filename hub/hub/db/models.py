"""SQLAlchemy ORM models — 5 tables, all scoped to project_id."""

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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
    hop_budget: Mapped[int] = mapped_column(Integer, default=6, server_default="6", nullable=False)
    turn_delivery_cap: Mapped[int] = mapped_column(
        Integer, default=10, server_default="10", nullable=False
    )
    agent_budget: Mapped[int] = mapped_column(
        Integer, default=8, server_default="8", nullable=False
    )
    allow_agent_jobs: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    token_budget: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    api_keys: Mapped[List["ApiKey"]] = relationship(back_populates="project")
    messages: Mapped[List["Message"]] = relationship(back_populates="project")
    tasks: Mapped[List["Task"]] = relationship(back_populates="project")
    questions: Mapped[List["Question"]] = relationship(back_populates="project")
    jobs: Mapped[List["AIJob"]] = relationship(back_populates="project")
    agents: Mapped[List["Agent"]] = relationship(back_populates="project")
    queue_entries: Mapped[List["InboundQueueEntry"]] = relationship(back_populates="project")
    conversations: Mapped[List["Conversation"]] = relationship(back_populates="project")
    turn_usages: Mapped[List["TurnUsage"]] = relationship(back_populates="project")


class Agent(Base):
    """Agent configuration and self-registration status."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    contact_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    self_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mcp_endpoint: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    spawn_cmd: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    config: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # Assigned once at registration by arrival order within the project, never derived
    # from the name (a rename must not change it). Persists across restarts because it
    # lives on this row, not in memory. The palette cycles once index >= palette length.
    color_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="agents")

    __table_args__ = (Index("ix_agents_project_name", "project_id", "name"),)


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


CONVERSATION_LIFECYCLES = ("open", "archived")


class Conversation(Base):
    """AgentWeave-owned durable conversation, independent of provider session identity."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    lifecycle: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="conversations")

    __table_args__ = (
        CheckConstraint(
            "lifecycle IN ('open', 'archived')", name="ck_conversations_lifecycle"
        ),
        Index("ix_conversations_project_agent_updated", "project_id", "agent", "updated_at"),
        Index(
            "uq_conversations_project_agent_provider_session",
            "project_id",
            "agent",
            "provider_session_id",
            unique=True,
        ),
    )


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
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("conversations.id"), nullable=True
    )

    project: Mapped["Project"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_messages_project_recipient", "project_id", "recipient"),
        Index("ix_messages_project_read", "project_id", "read"),
        Index("ix_messages_conversation", "conversation_id"),
    )


QUEUE_ENTRY_STATES = ("queued", "delivered", "withdrawn")
QUEUE_ORIGIN_TYPES = ("operator", "agent", "job")


class InboundQueueEntry(Base):
    """One durable item in an agent's ordered inbound queue."""

    __tablename__ = "inbound_queue_entries"

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    origin_type: Mapped[str] = mapped_column(String(16), nullable=False)
    origin_agent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    arrived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    hop_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    delivered_in_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    session_mode: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("conversations.id"), nullable=True
    )
    work_dir: Mapped[Optional[str]] = mapped_column(String(4096), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="queue_entries")

    __table_args__ = (
        CheckConstraint(
            "origin_type IN ('operator', 'agent', 'job')", name="ck_inbound_queue_origin_type"
        ),
        CheckConstraint(
            "state IN ('queued', 'delivered', 'withdrawn')", name="ck_inbound_queue_state"
        ),
        CheckConstraint("hop_depth >= 0", name="ck_inbound_queue_hop_depth"),
        CheckConstraint(
            "(origin_type = 'operator' AND origin_agent IS NULL) OR "
            "(origin_type = 'agent' AND origin_agent IS NOT NULL) OR "
            "(origin_type = 'job' AND origin_agent IS NULL)",
            name="ck_inbound_queue_origin_agent",
        ),
        Index(
            "ix_inbound_queue_project_agent_state_arrival",
            "project_id",
            "agent",
            "state",
            "sequence",
        ),
        Index("ix_inbound_queue_delivered_run", "delivered_in_run_id"),
        Index("ix_inbound_queue_conversation_state", "conversation_id", "state", "sequence"),
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


class ProjectInstructions(Base):
    """Stores per-project instruction content editable via Hub UI.

    One row per project — upserted on PUT. No row = empty instructions.
    Content is prepended to every agent's role guide at session start.
    """

    __tablename__ = "project_instructions"

    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class ProjectSpec(Base):
    """Stores per-project spec HTML files synced from the CLI.

    One row per (project, path) — upserted on POST /project/specs/sync.
    Paths look like ``spec/spec.html`` or ``spec/changes/<slug>/spec.html``.
    """

    __tablename__ = "project_specs"

    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), primary_key=True)
    path: Mapped[str] = mapped_column(String(255), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class ProjectSpecSnapshot(Base):
    """One reconciliation snapshot per (project, source) — the complete
    inventory and manifest state a single CLI workspace last reported.

    Kept separate from ``ProjectSpec`` (the content cache) because a snapshot
    can describe a document that has no content row yet (declared in the
    manifest but never uploaded) and because multiple machines/checkouts of
    the same project each get their own row, letting the Hub detect
    cross-source disagreement instead of trusting whichever polled last.
    """

    __tablename__ = "project_spec_snapshots"

    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    manifest_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # "valid" | "absent" | "unreadable" | "invalid"
    manifest_state: Mapped[str] = mapped_column(String(16), nullable=False)
    inventory: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    diagnostics: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


# Terminal statuses distinguish *why* a run stopped: "stopped" is a deliberate operator
# action (task 3.7), "interrupted" is crash reconciliation finding the process gone
# (task 3.8, Decision 8), "failed"/"completed" are the process's own exit outcome.
RUN_STATUSES = ("running", "completed", "failed", "interrupted", "stopped")
RUN_INITIATORS = ("operator", "autonomous")


class Run(Base):
    """A single agent process execution — the Hub's record of owning a spawned run.

    Central to Decision 2 (direct execution replaces the message-tag protocol: session
    identity lives here as a typed field, never text embedded in a message body) and
    Decision 8 (crash recovery: `pid` + `last_heartbeat_at` are what let the Hub tell, on
    its own restart, whether a run still marked "running" actually still is).
    """

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("conversations.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False, index=True)
    pid: Mapped[Optional[int]] = mapped_column(nullable=True)
    exit_code: Mapped[Optional[int]] = mapped_column(nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    turn_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    initiator: Mapped[str] = mapped_column(
        String(16), default="operator", server_default="operator", nullable=False
    )
    capability_token_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "initiator IN ('operator', 'autonomous')", name="ck_runs_initiator"
        ),
        Index("ix_runs_project_agent", "project_id", "agent"),
        Index("ix_runs_project_status", "project_id", "status"),
        Index("ix_runs_conversation_started", "conversation_id", "started_at"),
    )


TURN_USAGE_STATUSES = ("measured", "unavailable")


class TurnUsage(Base):
    """The immutable accounting outcome for one Hub-owned run."""

    __tablename__ = "turn_usage"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.id"), unique=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), nullable=False
    )
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    runner: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cache_read_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cache_write_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    api_equivalent_usd_micros: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    allowance: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="turn_usages")

    __table_args__ = (
        CheckConstraint(
            "status IN ('measured', 'unavailable')", name="ck_turn_usage_status"
        ),
        CheckConstraint(
            "(status = 'measured' AND total_tokens IS NOT NULL) OR "
            "(status = 'unavailable' AND input_tokens IS NULL AND output_tokens IS NULL "
            "AND total_tokens IS NULL AND cache_read_tokens IS NULL "
            "AND cache_write_tokens IS NULL AND reasoning_tokens IS NULL)",
            name="ck_turn_usage_availability",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0", name="ck_turn_usage_total_nonnegative"
        ),
        Index("ix_turn_usage_project_agent", "project_id", "agent"),
        Index("ix_turn_usage_project_observed", "project_id", "observed_at"),
    )


class AgentOutput(Base):
    __tablename__ = "agent_outputs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("conversations.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # Loose reference to Run.id (no FK constraint — AgentOutput predates the runs table
    # and existing rows may carry ad hoc run_id values from before Run existed).
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sequence: Mapped[Optional[int]] = mapped_column(nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_agent_outputs_project_agent", "project_id", "agent"),
        Index("ix_agent_outputs_project_ts", "project_id", "timestamp"),
        Index("ix_agent_outputs_conversation", "conversation_id", "timestamp"),
        Index(
            "ix_agent_outputs_project_agent_run_sequence",
            "project_id",
            "agent",
            "run_id",
            "sequence",
        ),
    )


class AIJob(Base):
    """Scheduled AI job for recurring agent tasks."""

    __tablename__ = "ai_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    cron: Mapped[str] = mapped_column(String(128), nullable=False)
    session_mode: Mapped[str] = mapped_column(
        String(16), default="new", nullable=False
    )  # "new" or "resume"
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    last_run: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    run_count: Mapped[int] = mapped_column(default=0, nullable=False, server_default="0")
    last_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(
        String(16), default="hub", nullable=False
    )  # "local" or "hub" - tracks origin for sync logic

    project: Mapped["Project"] = relationship(back_populates="jobs")
    runs: Mapped[List["JobRun"]] = relationship(back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_ai_jobs_project_agent", "project_id", "agent"),
        Index("ix_ai_jobs_project_enabled", "project_id", "enabled"),
    )


class JobRun(Base):
    """Execution record for an AI job."""

    __tablename__ = "job_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("ai_jobs.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="fired", nullable=False
    )  # "fired" or "failed"
    trigger: Mapped[str] = mapped_column(
        String(16), default="scheduled", nullable=False
    )  # "scheduled" or "manual"
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_summary: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    __table_args__ = (Index("ix_job_runs_job_fired", "job_id", "fired_at"),)

    job: Mapped["AIJob"] = relationship(back_populates="runs")
