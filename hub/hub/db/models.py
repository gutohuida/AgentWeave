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
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


PROJECT_DIRECTORY_STATES = (
    "unbound",
    "available",
    "missing",
    "unreadable",
    "not_directory",
    "identity_conflict",
)


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
    charters_seeded: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    working_directory: Mapped[Optional[str]] = mapped_column(String(4096), nullable=True)
    path_key: Mapped[Optional[str]] = mapped_column(String(4096), nullable=True, unique=True)
    directory_state: Mapped[str] = mapped_column(
        String(32), default="unbound", server_default="unbound", nullable=False
    )
    last_opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # "truncate" | "generate". Truncation is the floor and the default: a conversation is named
    # the moment its first message lands, so the rail never shows an identifier and a generation
    # failure changes nothing structural. Generating is an opt-in to spending tokens on titles.
    conversation_title_mode: Mapped[str] = mapped_column(
        String(16), default="truncate", server_default="truncate", nullable=False
    )
    # Which of the project's runners does the titling. Null under "truncate", and null under
    # "generate" means "no runner chosen yet" — which the titling path treats as truncate.
    # Deliberately not a ForeignKey: `runners.project_id` already points here, and closing the
    # loop would make the two tables unsortable for DDL. Validated where it is set instead.
    conversation_title_runner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # --- Integration ---
    # The branch approval merges into. Null means "not chosen", which is not an error: nothing
    # merges, approval is unaffected, and coverage keeps reporting exactly what it reported before.
    #
    # Deliberately not defaulted from `MAIN_BRANCH_NAMES`. Guessing is safe for a read-only report,
    # where a wrong guess costs an `unknown`; it is not safe for an operation that writes commits,
    # where a wrong guess puts work in a branch the operator never chose. The guess survives as a
    # suggestion offered at setup, and takes effect only once someone accepts it.
    main_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # --- Evidence retention ---
    # How long an evidence artifact is kept: "on_acceptance", "daily", "monthly", "manual", or
    # "never". `never` means never delete, and it is a first-class choice rather than a loophole —
    # an operator who wants to manage the tree themselves should not have to fight a cleaner.
    #
    # Whatever the policy, removing an artifact never removes its evidence record: that something
    # was verified, by whom, and against which digest is the record; the artifact is its attachment.
    evidence_retention: Mapped[str] = mapped_column(
        String(16), default="never", server_default="never", nullable=False
    )

    # --- Checkpointing ---
    # "off" | "offered" | "automatic". Off by default: a project should not start spending tokens
    # on generation, or cutting conversations over, because it was upgraded.
    checkpoint_mode: Mapped[str] = mapped_column(
        String(16), default="off", server_default="off", nullable=False
    )
    # One mode plus one value, never two nullable value columns — "150 000 tokens" and "50%" are
    # the same setting expressed differently, and two columns make "both set" representable.
    #
    # `percent` holds 0-100. `tokens` holds a **canonical token count** (150 000), not the
    # thousands an operator types: entry units belong to the surface that collects them, and a
    # column whose meaning depends on another column's *units* as well as its mode is one
    # indirection too many.
    checkpoint_threshold_mode: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    checkpoint_threshold_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Where notes are requested. Same mode as the cutover threshold and necessarily earlier —
    # notes written from an already-degraded context are themselves degraded.
    checkpoint_notes_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Which runner and model generate checkpoints. Not a ForeignKey, for the same reason
    # `conversation_title_runner_id` is not.
    checkpoint_runner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    checkpoint_model: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    # Whether a successor starts working the moment it is handed its checkpoint.
    #
    # Off by default, because a turn nobody asked for costs tokens. But leaving it off and saying
    # nothing else made the successor a dead end: the checkpoint sat in its queue and the only way
    # to start it was to type a message, which is a strange thing to have to invent when the whole
    # point is that the work continues. Off now means an explicit Continue button instead.
    checkpoint_auto_continue: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )

    api_keys: Mapped[List["ApiKey"]] = relationship(back_populates="project")
    messages: Mapped[List["Message"]] = relationship(back_populates="project")
    tasks: Mapped[List["Task"]] = relationship(back_populates="project")
    questions: Mapped[List["Question"]] = relationship(back_populates="project")
    jobs: Mapped[List["AIJob"]] = relationship(back_populates="project")
    agents: Mapped[List["Agent"]] = relationship(back_populates="project")
    queue_entries: Mapped[List["InboundQueueEntry"]] = relationship(back_populates="project")
    conversations: Mapped[List["Conversation"]] = relationship(back_populates="project")
    turn_usages: Mapped[List["TurnUsage"]] = relationship(back_populates="project")
    runners: Mapped[List["Runner"]] = relationship(back_populates="project")
    charters: Mapped[List["Charter"]] = relationship(back_populates="project")

    __table_args__ = (
        CheckConstraint(
            "directory_state IN ('unbound', 'available', 'missing', 'unreadable', "
            "'not_directory', 'identity_conflict')",
            name="ck_projects_directory_state",
        ),
    )


class Agent(Base):
    """Agent configuration and self-registration status."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # What this agent is for, in the operator's own words. Never injected into a turn — the
    # charter is what tells an agent how to behave, and a second field that also shaped behaviour
    # would leave two places to look when an agent acts wrongly. This one is for the human
    # reading a roster of six similarly named agents.
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    contact_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    self_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mcp_endpoint: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    spawn_cmd: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    config: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # Assigned once at registration by arrival order within the project, never derived
    # from the name (a rename must not change it). Persists across restarts because it
    # lives on this row, not in memory. The palette cycles once index >= palette length.
    color_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_by_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    runner_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("runners.id"), nullable=True
    )
    charter_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("charters.id"), nullable=True
    )
    # How long this agent waits on the operator, in seconds. NULL means the built-in default —
    # deliberately not a copy of it, because a row storing today's number would keep saying it
    # after the default moved, pinning every existing agent to a value nobody chose.
    permission_timeout_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    question_timeout_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # What this agent may do when the conversation has not said. One of the postures the model
    # catalog declares, or NULL for the built-in default — the same reasoning as the waiting
    # settings above: a row storing today's default would keep saying it after the default moved.
    # This is the same choice the composer's Permissions pill makes, applied when no run states
    # one, which is why it is not a vocabulary of its own.
    default_permission_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Per-agent overrides of the project's checkpoint policy. All three are NULL for an agent
    # that inherits.
    #
    # An override replaces the **whole** threshold — mode and value together, never one field of
    # it. Resolving field-by-field lets an agent inherit `percent` from the project and supply a
    # value of `150`, which reads as "150%" and never fires. `checkpoint_threshold_mode` being
    # non-NULL is what marks the agent as overriding at all.
    checkpoint_mode: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    checkpoint_threshold_mode: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    checkpoint_threshold_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checkpoint_notes_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Two independent grants, both closed by default.
    #
    # Separate because summary access is not transcript access. A checkpoint is a deliberate,
    # bounded distillation; `recall` returns another agent's raw recorded output verbatim. An
    # agent that may read what a peer concluded need not be able to read everything that peer's
    # tools ever printed, and one flag would make the narrower grant inexpressible.
    #
    # These live on the Agent row and nowhere else. A charter is behaviour text the model reads;
    # if it could widen access, then prose an agent can be persuaded to write would be an
    # authorisation mechanism.
    can_read_checkpoints: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    can_recall: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    # Whether this agent may *accept* evidence for a requirement. Producing evidence is open to
    # anyone; accepting it is the controlled act, because the artifact is a fact and the claim about
    # what it proves is not.
    #
    # Deliberately not a role — the role subsystem was deleted and must not return — and
    # deliberately not conferred by a charter, for the reason above these two flags: a charter says
    # how an agent behaves, and behaviour is not authority. A "Verifier" charter may well describe
    # such an agent; it grants it nothing.
    can_accept_evidence: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    # An agent is archived, never deleted — its conversations, runs and messages keep their
    # attribution, and archival is reversible. Mirrors `Conversation.lifecycle` deliberately:
    # the two are the same act at different scopes, and giving them different vocabularies
    # would make the rail's two "archived" listings read as unrelated features.
    # `server_default` as well as `default`: 0038 adds the column with one, so without it here a
    # freshly created database and an upgraded one would disagree on the schema — and any writer
    # that does not go through the ORM (migration backfills, and the raw inserts the migration
    # tests use to build historical states) would hit a NOT NULL failure.
    lifecycle: Mapped[str] = mapped_column(
        String(16), default="open", server_default="open", nullable=False
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="agents")

    __table_args__ = (
        # Unique: every lookup in the Hub addresses an agent as (project_id, name), so two
        # matching rows make `scalar()` return whichever the database hands back first.
        # Registration already refuses a duplicate with 409, but it SELECTs then INSERTs, and
        # two concurrent registrations interleave through that gap. See migration 0063.
        Index("ix_agents_project_name", "project_id", "name", unique=True),
        CheckConstraint("lifecycle IN ('open', 'archived')", name="ck_agents_lifecycle"),
    )


RUNNER_CLIS = ("claude", "codex")


class Runner(Base):
    """Reusable execution capability an agent is bound to: which CLI, which model.

    Project-scoped. Distinct from `Agent` (roster identity) and `Charter` (behavior) —
    see openspec/changes/runner-agent-charter-separation/design.md for the three-way
    split this replaces the old fixed-role system with. `flags` is a freeform,
    optional escape hatch for future per-runner CLI-flag overrides; nothing populates
    it yet.
    """

    __tablename__ = "runners"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    cli: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    flags: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="runners")

    __table_args__ = (
        CheckConstraint("cli IN ('claude', 'codex')", name="ck_runners_cli"),
        Index("ix_runners_project_name", "project_id", "name"),
    )


class Charter(Base):
    """Authored behavior content an agent is bound to.

    Project-scoped. Replaces the fixed 21-entry role-guide list; seeded once from the
    previously-bundled role guides (see runner-agent-charter-separation design.md) and
    freely editable thereafter through the Hub UI.
    """

    __tablename__ = "charters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="charters")

    __table_args__ = (Index("ix_charters_project_name", "project_id", "name"),)


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


class OperatorCredential(Base):
    """Instance-local operator secret; deliberately carries no project identity."""

    __tablename__ = "operator_credentials"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


CONVERSATION_LIFECYCLES = ("open", "archived")

# Where a conversation came from, recorded at creation and immutable thereafter. `handoff`,
# `spec` and `job` are accepted with no producer yet — deliberately, so that retrofitting a
# producer later does not leave every conversation predating it recorded as something it wasn't.
CONVERSATION_ORIGINS = ("operator", "peer", "handoff", "spec", "job")

# The stored length of a title, and so the ceiling a rename is rejected above.
CONVERSATION_TITLE_MAX_LENGTH = 120

# How a project names its conversations. Truncation is the floor; generation is the opt-in.
CONVERSATION_TITLE_MODES = ("truncate", "generate")


class Conversation(Base):
    """AgentWeave-owned durable conversation, independent of provider session identity."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    lifecycle: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    # Null until the conversation's first message names it. Nothing may present the id as a
    # label, so every surface that lists a titleless conversation labels it as new instead.
    title: Mapped[Optional[str]] = mapped_column(
        String(CONVERSATION_TITLE_MAX_LENGTH), nullable=True
    )
    # An operator-set title is never replaced by a generated one.
    title_set_by_operator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), default="operator", nullable=False)
    # Control id -> value (e.g. {"model": "claude-opus-5", "effort": "high"}), keyed by
    # control identity so a new catalog control needs no migration. Null/empty means "no
    # override" — the conversation inherits its agent's runner and the catalog's control
    # defaults (2026-08-04-hub-model-control-and-provisioning design.md).
    runtime_overrides: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # What a peer message binds to when it arrives here. Exactly one is set on a peer-bound
    # conversation, and both are NULL on every other conversation.
    #
    # A peer send that names no conversation used to land on whatever thread the recipient
    # touched most recently, which scattered one exchange across unrelated threads. Delivery is
    # keyed instead on the *sender's* conversation, so a sender's separate lines of work reach
    # separate recipient threads and a second message on the same line reaches the same one.
    #
    # `bound_sender_agent` is the senderless case — the Hub and the scheduler have no source
    # conversation, so their traffic keys on identity and gets one stable thread per sender.
    # Without it that traffic would have to fall back to recency, which is the behaviour being
    # removed.
    bound_sender_conversation_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    bound_sender_agent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # The task this thread is about, and the durable half of the run→task binding.
    #
    # Without it only the *first* run of a conversation was ever bound: starting work from a board
    # card sent a task id, a follow-up typed into the composer did not, and nothing carried the
    # binding across turns. So a five-turn piece of work was checked once, at the end of turn one —
    # when an agent is most legitimately unfinished — and was invisible for the turn where it
    # actually stopped. The mechanism was noisiest where it mattered least and silent where it
    # mattered most (`2026-08-10-blocked-and-conversation-binding`).
    #
    # A run still records its own `Run.task_id` (design D6). Transitions and divergences are
    # attributed to a run, and an integrity record that had to join through a conversation to say
    # which task it was about would be weaker for it.
    #
    # Released explicitly, or automatically when the bound task reaches a terminal status. Never
    # inferred from what the operator seems to be talking about: a wrong guess silently stops
    # checking a run, and a mechanism that quietly stops enforcing is worse than one that never
    # started (design D7).
    task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Where this conversation stands with its checkpoint threshold: NULL (not warned), `due`
    # (crossed, waiting on the operator), or `dismissed` (the operator chose to keep working).
    #
    # One column, not a `warned` boolean plus a `dismissed` boolean — those two make "dismissed
    # but never warned" representable, and every reader would then have to decide what that
    # meant. A successor is created NULL, so dismissing is final for a conversation and not for
    # a line of work.
    checkpoint_warning: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="conversations")

    __table_args__ = (
        CheckConstraint("lifecycle IN ('open', 'archived')", name="ck_conversations_lifecycle"),
        CheckConstraint(
            "origin IN ('operator', 'peer', 'handoff', 'spec', 'job')",
            name="ck_conversations_origin",
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
    created_by_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

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
    #: The specification document the operator had open when they sent this input, when it came
    #: from the specification workspace. Carried on the entry rather than through the scheduler
    #: call because a busy agent's turn starts from a later call than the one that queued it.
    spec_document: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    #: The task this input is about, when a delegation named one. Carried on the entry for the same
    #: reason `spec_document` is: a busy agent's turn starts from a later scheduler call than the
    #: one that queued this, so anything passed through the call is lost by the time the run exists.
    #: Read at spawn to bind the receiving run (`2026-08-10-run-task-binding`, design D3).
    task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    #: Set when this entry is the Hub's answer to a divergence, naming the run that diverged. The
    #: retry bound lives on the *run*, and a queued response becomes a run in a later call — so
    #: like `task_id` this must survive the queue, or a chain cannot see its own source and cannot
    #: be bounded (design D8).
    divergence_source_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="queue_entries")

    __table_args__ = (
        # `checkpoint` is the Hub handing a successor conversation its predecessor's checkpoint.
        # Deliberately its own value rather than borrowed: under `automatic` no operator asked
        # for it and no agent sent it, so both `operator` and `agent` would misstate where it
        # came from — and a signal that reports something other than what it names is the exact
        # defect this capability exists to remove.
        # `divergence` is the Hub answering a bound run that ended without moving its task —
        # a retry of the same agent, or an escalation to a stronger one. Its own value for the
        # same reason `checkpoint` is: no operator asked for it and no agent sent it, so both
        # would misstate where it came from, in the queue the operator reads.
        CheckConstraint(
            "origin_type IN ('operator', 'agent', 'job', 'checkpoint', 'divergence')",
            name="ck_inbound_queue_origin_type",
        ),
        CheckConstraint(
            "state IN ('queued', 'delivered', 'withdrawn')", name="ck_inbound_queue_state"
        ),
        CheckConstraint("hop_depth >= 0", name="ck_inbound_queue_hop_depth"),
        CheckConstraint(
            "(origin_type = 'operator' AND origin_agent IS NULL) OR "
            "(origin_type = 'agent' AND origin_agent IS NOT NULL) OR "
            "(origin_type = 'job' AND origin_agent IS NULL) OR "
            "(origin_type = 'checkpoint' AND origin_agent IS NULL) OR "
            "(origin_type = 'divergence' AND origin_agent IS NULL)",
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
    created_by_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    updated_by_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # What happens when a run bound to this task ends without the task moving.
    #
    # Per task rather than per project because the operator's stated use — a cheap model doing the
    # work and an expensive one resolving what it could not — is a property of the work, not of the
    # project. One project-wide switch would change behaviour for everything at once.
    #
    # Defaults to `surface`, and that default is load-bearing rather than incidental: it is what
    # every task already on a board acquires, so introducing this capability cannot start runs
    # nobody asked for (`2026-08-10-run-task-binding`, design D7).
    divergence_policy: Mapped[str] = mapped_column(
        String(16), default="surface", server_default="surface", nullable=False
    )
    # Who the work goes to when `divergence_policy` is `escalate`. NULL makes escalation fall back
    # to surfacing — a policy naming nobody cannot route anywhere.
    escalation_agent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # What a `blocked` task is waiting for, in words the operator can act on. Filled from the
    # question text when the runtime parks the task, supplied by the operator when they park it by
    # hand. Cleared on release, so a stale reason cannot outlive the block it described.
    #
    # The whole difference between a card that says "blocked" and one that says "blocked on the API
    # key" (`2026-08-10-blocked-and-conversation-binding`, R5). Since a blocked task stays in the
    # in_progress column rather than moving to one of its own (R3), this text is most of what tells
    # the operator the card is waiting on *them*.
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="tasks")

    # No CHECK on `divergence_policy`, matching `status` and `priority` on this table, which have
    # none. A table-level CHECK naming a column also makes that column undroppable in SQLite, which
    # would make 0056 irreversible. The values are declared in `run_task_binding.py` and validated
    # on the way in.
    __table_args__ = (
        Index("ix_tasks_project_status", "project_id", "status"),
        Index("ix_tasks_project_assignee", "project_id", "assignee"),
    )


class TaskTransition(Base):
    """One accepted move of a task from one status to another. Never updated, never deleted.

    `Task.updated_by_run_id` cannot answer "who approved this?", because it is a single mutable
    column: the approving run overwrites the completing one, and the question the review step
    exists to answer becomes unaskable. Rows here are what author/reviewer separation reads
    (`openspec/changes/2026-08-10-task-transition-machine/`, design D3).

    Append-only is enforced by there being no write path other than the recorder — no update, no
    delete — rather than by a database trigger, which would need a different implementation per
    backend to defend against an actor who already has the database file (D4).

    A task created before this table existed begins its history at its next move. Nothing is
    backfilled: a synthetic "created as pending" row would put a claim in an integrity record that
    nothing observed (D8).
    """

    __tablename__ = "task_transitions"

    # Ordered by an autoincrement key, not by `created_at`, and not by the string id. Several
    # transitions can be staged in one flush and then share a timestamp to the microsecond, at
    # which point a random `ttr-…` id decides what order the history reads in — which for a record
    # whose entire meaning is "this happened, then this" is a corruption rather than an
    # inconvenience. Same shape as `InboundQueueEntry`, which is ordered for the same reason.
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tasks.id"), nullable=False, index=True
    )
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    # "run" or "operator". Explicit rather than inferred from run_id being NULL: the two coincide
    # today, but "no run" and "the operator" are different claims and only one of them is an
    # authorisation (D2).
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Which agent the run belonged to. Denormalised rather than joined through `runs`: this is an
    # integrity record and must answer "who approved this" on its own, without depending on a run
    # row that may be pruned. It is also what author/reviewer separation compares — `run_id` is
    # not, because every turn is a new run and a run-based check is trivially satisfied.
    actor_agent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # "actor" or "runtime" — what caused this transition to be requested.
    #
    # `runtime` means the Hub made the move on the run's behalf, at a moment the run did not
    # choose: today, moving a task to `in_progress` because a run bound to it. The run and agent
    # are still recorded, because the system acts *as* the run rather than instead of it — which
    # is also why there is no third actor kind (design D5).
    #
    # The divergence check is why this column exists. It asks "did this run advance its task?", and
    # the runtime's own auto-transition is a transition by that run on that task — so without a
    # recorded cause it answers yes for every bound run, and the check reports nothing.
    #
    # Rows written before this existed read as `actor`, which is what was true for all of them.
    origin: Mapped[str] = mapped_column(
        String(16), default="actor", server_default="actor", nullable=False
    )
    # A digest of the policy that governed this move: the rigor of each document whose requirements
    # the task serves, and the coverage each of those requirements held.
    #
    # Rigor is operator-editable, which is exactly what makes this necessary rather than
    # theoretical. Without it, a gate that passed last month cannot be explained today — the
    # document now says something else, and nothing records what it said then. Null on a transition
    # that no policy governed.
    policy_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    # No CHECK on `origin`, matching `actor_kind` beside it, which has none either. Two reasons,
    # and the second is not merely pragmatic: a table-level CHECK naming a column makes that column
    # undroppable in SQLite, so the constraint would make 0056 irreversible; and the values are
    # already declared once in `task_transitions.py` and pinned by test, which is where a reader
    # looks for them.
    __table_args__ = (Index("ix_task_transitions_task_sequence", "task_id", "sequence"),)


class RunDivergence(Base):
    """One occurrence of a bound run ending without its task moving.

    A record, not only an event. An SSE broadcast vanishes: the operator needs to see what happened
    while they were not watching, and "how often does this agent drop its work?" is a question worth
    being able to ask (`2026-08-10-run-task-binding`, design D10). B3's evidence model wants the
    same rows.

    Mutable in exactly one respect — `resolved_at` is stamped when a later actor transition lands on
    the task, because a divergence is an open condition rather than a verdict, and long work
    spanning several turns opens one that closes as soon as the work reaches the ledger. Nothing
    else is updated and nothing is deleted; the row survives its own resolution.
    """

    __tablename__ = "run_divergences"

    # Autoincrement, for the reason `TaskTransition` and `InboundQueueEntry` are: rows staged in one
    # flush share `created_at` to the microsecond, and a random id deciding the order of a record
    # whose meaning is "this happened, then this" is a corruption rather than an inconvenience.
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Denormalised for the same reason `TaskTransition.actor_agent` is: this must answer "who
    # dropped this" without depending on a run row that may later be pruned.
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tasks.id"), nullable=False, index=True
    )
    # Where the task stood when the run ended, and how the run ended. The exit status is what makes
    # a crash distinguishable from a run that completed and forgot — both are divergent, and they
    # deserve different reactions from a reader.
    task_status_at_end: Mapped[str] = mapped_column(String(32), nullable=False)
    run_exit_status: Mapped[str] = mapped_column(String(32), nullable=False)
    # The policy the task carried at the moment of divergence, and what was actually done. They
    # differ whenever a policy fell back: `escalate` with no agent named, or a retry that had
    # already spent its one hop.
    policy_applied: Mapped[str] = mapped_column(String(16), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    # The run started in response, when one was.
    response_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Who the task was assigned to before an escalation reassigned it. Escalation moving the
    # assignee is deliberate — leaving it pointing at the agent that just dropped the work would
    # make the board disagree with reality — and this is what makes it reversible (design D9).
    previous_assignee: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_run_divergences_project_task", "project_id", "task_id"),
        Index("ix_run_divergences_project_resolved", "project_id", "resolved_at"),
        CheckConstraint(
            "policy_applied IN ('surface', 'retry', 'escalate')",
            name="ck_run_divergences_policy",
        ),
        CheckConstraint(
            "outcome IN ('surfaced', 'retried', 'escalated')",
            name="ck_run_divergences_outcome",
        ),
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
    # Answers the agent will accept, when it offered a choice rather than an open question.
    # Each entry is {"label", "description"}: the label is what comes back, the description is
    # what lets an operator choose between them without already knowing the trade-off. Empty
    # means open-ended. The operator is never *confined* to these — a typed answer is always
    # allowed — but offering them is what turns a question into one click.
    options: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Short chip shown above the question, e.g. "Database". Optional.
    header: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    multi_select: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    # The chosen labels, structurally. `answer` keeps the human-readable form (a single label,
    # the labels joined, or free text) so everything already reading it still works.
    answer_labels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # One `ask_user` call can carry several questions. They are separate rows sharing a batch id,
    # rather than one row holding a list, so every existing reader of a question keeps working —
    # a question asked on its own is simply a batch of one.
    batch_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Position within the batch, and the batch's total. `batch_size` is denormalized onto every
    # row on purpose: the panel fetches only *unanswered* questions, so this is what lets it say
    # "2 of 3" without a second request for rows it has already finished with.
    batch_index: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    batch_size: Mapped[int] = mapped_column(default=1, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Denormalized from the opening run. Navigation reads the attention state of every
    # conversation on every SSE re-render, and a two-hop join through `Run` per row is the wrong
    # shape for that. Nullable because rows predating the column cannot be attributed.
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # The task this question parked, when it parked one. Answering it releases *this* task.
    #
    # A column rather than a join table because a question blocks at most one task and `ask_user`
    # offers no way to name several — a join table would model a cardinality nothing can produce
    # (`2026-08-10-blocked-and-conversation-binding`, design D4).
    #
    # Recorded rather than re-derived from the asking run's binding: a run may be bound to a task
    # the question was not about, and releasing the wrong task is worse than releasing nothing.
    #
    # No ForeignKey, matching `created_by_run_id` and `conversation_id` above: the block record must
    # outlive a deleted task rather than cascade or refuse.
    blocked_task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # The operator closed this without answering it.
    #
    # Beside `answered` rather than folded into it (`2026-08-11-declining-a-question`, D1). An empty
    # answer claims the operator said nothing in response; declining claims they chose not to
    # respond at all. Collapsing the two would make every reader of `answered` treat a decline as an
    # answer — including `unanswered_blocking_question`, which decides whether a task is parked.
    declined: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    declined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

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
    full agent configuration including runner metadata, yolo flags, and future fields.
    """

    __tablename__ = "project_sessions"

    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), primary_key=True)
    data: Mapped[Any] = mapped_column(JSON, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class ProjectInstructions(Base):
    """Stores per-project instruction content editable via Hub UI.

    One row per project — upserted on PUT. No row = empty instructions.
    Content is prepended to every agent's charter at session start.
    """

    __tablename__ = "project_instructions"

    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


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
    # The one task this run was started for, or NULL.
    #
    # Set by the **runtime** at spawn, from the cause of the run — a delegation naming a task, or
    # the operator starting work from a board card. No agent-facing operation creates, changes or
    # clears it: an agent able to bind itself is an agent able to never bind, and an unbound run is
    # never divergent, so self-binding would reintroduce one level down the forgetting this column
    # exists to remove (`2026-08-10-run-task-binding`, design D2).
    #
    # NULL means unbound, and unbound is legitimate — exploration, conversation, questions and
    # scheduled work are real work with no task. An unbound run is never checked at the boundary.
    task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # The run whose divergence caused this one to be started, or NULL.
    #
    # This is the whole retry bound (D8). A run carrying it never triggers another retry, so
    # `A diverges → B` can only ever be followed by escalation or surfacing. There is no
    # max-attempts field to misconfigure and no loop is expressible. The bound is per chain, not
    # per task lifetime: a response run that does move its task ends the chain.
    divergence_source_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
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
    instance_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # The auto-snapshot commit this turn produced, or NULL when the turn changed no files.
    #
    # `worktrees.snapshot_worktree` has always returned this and both trigger sites discarded it.
    # Without it a checkpoint cannot say what a *conversation* changed: one worktree, and so one
    # branch, is shared by all of an agent's concurrent conversations, every auto-snapshot carries
    # an identical message, and matching commits to turns by timestamp is guesswork. Recorded per
    # run, the union over a conversation's runs is exact.
    snapshot_commit_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint("initiator IN ('operator', 'autonomous')", name="ck_runs_initiator"),
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
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
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
        CheckConstraint("status IN ('measured', 'unavailable')", name="ck_turn_usage_status"),
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
    created_by_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    updated_by_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

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
    requested_by_run_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )

    __table_args__ = (Index("ix_job_runs_job_fired", "job_id", "fired_at"),)

    job: Mapped["AIJob"] = relationship(back_populates="runs")


class AgentJobDeletion(Base):
    """Durable attribution tombstone for an agent-deleted scheduled job."""

    __tablename__ = "agent_job_deletions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class PermissionRequest(Base):
    """One permission decision a run is waiting on an operator to make.

    Created by the approval tool under the operator-answered posture and polled by that same
    tool until `status` leaves "pending". The row outlives the answer so a denial stays visible
    after the fact; `decided_at` distinguishes an answer from a timeout, which also writes a
    terminal status rather than leaving the row pending forever.
    """

    __tablename__ = "permission_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Denormalized from the opening run, for the same reason as `Question.conversation_id`.
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_use_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    tool_input: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # "pending" | "allowed" | "denied" | "expired"
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    # The operator has finished looking at an expired request and cleared it from view.
    #
    # Separate from `status` on purpose. `status` is the run-facing fact — what the agent was told,
    # and the audit record of who authorised what. Whether the operator has since tidied the card
    # away says nothing about that, and folding the two would make "dismissed" look like a decision
    # to every reader of `status`, including the run's own poll.
    dismissed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_permission_requests_project_status", "project_id", "status"),)


class UnaskedQuestion(Base):
    """A question a run ended its turn on without ever routing through `ask_user`.

    Detected rather than reported: no provider protocol lets the Hub require that a turn end
    through a particular tool, so the Hub reads the run's final assistant text instead. The row
    exists because the operator needs something to act on — `status` leaves "pending" when they
    re-prompt the agent ("asked") or decide it was not a real question ("dismissed").

    "asked" means the operator asked the agent to ask properly, not that anyone answered. Whether
    the agent then calls the tool is the agent's business, and its own turn.
    """

    __tablename__ = "unasked_questions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Already recorded since this table was added; indexed now because navigation queries it.
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # "pending" | "asked" | "dismissed"
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_unasked_questions_project_status", "project_id", "status"),)


# The five triggers design.md enumerates. v1 generates uniformly for all of them and records
# which one fired — a deliberate deferral, not a conclusion; see
# `project_checkpoint_trigger_prompts_provisional`.
CHECKPOINT_TRIGGERS = (
    "context_pressure",
    "operator",
    "delegation",
    "run_failure",
    "task_completion",
)

# "ready" means a record exists, carries a written half, and passed its probes — never "the run
# stopped", which is precisely the readiness signal this change exists to remove.
CHECKPOINT_STATUSES = (
    "ready",
    # Envelope computed, written half absent: the worker returned nothing usable. Still a
    # useful record — the computed half is the verifiable half — but nothing to *read*.
    "unwritten",
    # The probes disagreed with the database. Set in section 6; section 5 never produces it.
    "failed",
)

# Effective access is agent capability ∩ checkpoint visibility (design.md, Decision 7).
CHECKPOINT_VISIBILITIES = ("private", "project", "granted")


class Checkpoint(Base):
    """A durable summary of where a conversation got to, generated by the Hub.

    Hybrid by design (exploration task 1.5): a structured envelope the Hub computes and can
    therefore *check*, carrying one markdown body only the model can write. The split is
    verifiability, not style — a model asked for a timestamp it could not obtain invented one,
    and a model asked for pending work reported none from a worktree that is always clean.

    Lineage is stored (`previous_checkpoint_id` for order, `lineage_id` for cheap grouping);
    participation is *not*, because `Task.created_by_run_id -> Run -> (agent, conversation)`
    already answers it as a join. Conflating them gives a `lineage_id` that means two things.
    """

    __tablename__ = "checkpoints"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id"), nullable=False, index=True
    )
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), default="private", nullable=False)

    # Linear, single-agent chain. `lineage_id` is the first checkpoint's id, carried forward, so
    # "show me this thread" is one indexed read rather than a walk.
    previous_checkpoint_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lineage_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Which turns this checkpoint accounts for. The next one anchors on it and reads only what
    # came after, rather than re-reading the transcript from the start.
    covers_from_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    covers_through_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # How it was generated. No foreign key, for the reason `WorkerInvocation.runner_id` has none.
    worker_invocation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    runner: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # --- The computed half. Never solicited from a model. ---
    # [{"path": ..., "commits": [...]}] derived from the conversation's own auto-snapshot commits.
    files_changed: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # `tasks` is project-scoped and carries no conversation, so this is the agent's *whole* list,
    # identical across its concurrent conversations. The payload says so in its `scope` key rather
    # than leaving a reader to assume otherwise — see `checkpoints.TASK_SCOPE_NOTE`.
    tasks: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    open_questions: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    permission_decisions: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    runtime_overrides: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # --- The written half. NULL is a real state: status is then "unwritten". ---
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Stable ids of the recorded observations this checkpoint summarises, each with a short
    # preview. A summary is lossy by construction; citations give it an exact escape hatch, so
    # what the narrative compressed away stays recoverable without re-running a tool and without
    # similarity search. `recall` materialises one by id.
    citations: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # --- The verdict (section 6). NULL until probed. ---
    probe_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    probe_findings: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "trigger IN ('" + "', '".join(CHECKPOINT_TRIGGERS) + "')",
            name="ck_checkpoints_trigger",
        ),
        CheckConstraint(
            "status IN ('" + "', '".join(CHECKPOINT_STATUSES) + "')",
            name="ck_checkpoints_status",
        ),
        CheckConstraint(
            "visibility IN ('" + "', '".join(CHECKPOINT_VISIBILITIES) + "')",
            name="ck_checkpoints_visibility",
        ),
        # "ready" is the one status that promises something to read. Enforced here so a body-less
        # checkpoint cannot be presented as resumable by any code path, present or future.
        CheckConstraint(
            "status <> 'ready' OR body IS NOT NULL",
            name="ck_checkpoints_ready_has_a_body",
        ),
        Index("ix_checkpoints_conversation_created", "conversation_id", "created_at"),
        Index("ix_checkpoints_project_agent", "project_id", "agent"),
    )


class CheckpointNote(Base):
    """What an agent knew that never reached the transcript.

    Hub-side generation cannot recover what was never recorded: what the agent was *about* to do,
    what it suspects but did not verify, what it would warn a successor away from. So the agent is
    asked — through a tool, so that the request, the answer, and the *absence* of an answer are
    all observable, which prompt-and-parse would not be.

    A row, not a column on the conversation, for exactly that reason: "the agent had nothing to
    add" and "the agent was never asked" must not be the same absence.

    Notes are an **input** to generation and never the artifact. `consumed_by_checkpoint_id`
    records which checkpoint took them, so a second checkpoint does not silently reuse notes
    written for the first.
    """

    __tablename__ = "checkpoint_notes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # What the agent was in the middle of doing when it was asked.
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    # Believed but unverified — the things a transcript records as silence.
    suspicions: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # What a successor should be steered away from.
    warnings: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    consumed_by_checkpoint_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        Index("ix_checkpoint_notes_conversation_created", "conversation_id", "created_at"),
    )


# Every way a worker invocation can end. Kept in one place so the check constraint and
# `worker.OUTCOMES` cannot drift; a test asserts they agree.
WORKER_OUTCOMES = (
    "ok",
    "unsupported_cli",
    "unknown_model",
    "spawn_failed",
    "nonzero_exit",
    "timeout",
    "unparseable",
    "schema_invalid",
)


class WorkerInvocation(Base):
    """One out-of-band, single-purpose model call, and what it cost.

    Deliberately not a `Run`: a worker is not a turn, and recording one under an agent's name
    would make that agent look busy to `turn_scheduler` (see `worker.py`). This table is the
    whole accounting surface for such calls.

    `runner_id` carries **no foreign key**, on purpose. This is an audit record, and an audit
    record that a runner deletion could cascade away — or that could block one — is not an audit
    record. It stores which runner was chosen at the time, which stays true afterwards.
    """

    __tablename__ = "worker_invocations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    # What the call was for — "checkpoint", "probe", … — so cost can be attributed per purpose.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # The Hub owns and versions its prompts; a change in output quality must be attributable to
    # the prompt that produced it, which means the version is recorded, not inferred.
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    runner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cli: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # All nullable: a call that never spawned has no usage, and a provider that does not report a
    # dimension leaves it unknown rather than zero.
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cache_read_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cache_write_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_usd_micros: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('" + "', '".join(WORKER_OUTCOMES) + "')",
            name="ck_worker_invocations_outcome",
        ),
        CheckConstraint(
            "error IS NOT NULL OR outcome = 'ok'",
            name="ck_worker_invocations_failure_explained",
        ),
        Index("ix_worker_invocations_project_created", "project_id", "created_at"),
        Index("ix_worker_invocations_project_kind", "project_id", "kind"),
    )


# Phase is the document's state, and it is the Hub's to change. It is stored here rather than in
# the document because the document is a file the operator can edit, and a gate whose value lives
# where the gated party can write it is not a gate. `aw-spec-status` in the rendered markup is a
# copy for a human reading the file, never the authority.
SPEC_PHASES = ("exploring", "proposed", "approved")

SPEC_EVENT_ACTORS = ("operator", "agent", "system")
SPEC_EVENT_ORIGINS = ("control", "submission", "lifecycle")

# What happens to work that ignores this document. **Not phase.** Phase asks "has the operator
# agreed to this?"; rigor asks "what does the system do about work that does not satisfy it?" A
# `gate` document can still be exploring, and an approved document can still be a sketch — treating
# every approved document as enforcing is the barrier-heavy product the direction rules out.
#
# `sketch` is the default and blocks nothing. `contract` reports and blocks nothing — it is a
# statement of intent. `gate` refuses a task's approval while a requirement it serves is unverified.
SPEC_RIGORS = ("sketch", "contract", "gate")
DEFAULT_SPEC_RIGOR = "sketch"


class SpecDocument(Base):
    """One specification document's Hub-owned state.

    The file on disk is the document; this row is what cannot live in a file —
    the phase, the digests that detect an edit made outside the Hub, and the
    identifier bookkeeping that must survive rewording.
    """

    __tablename__ = "spec_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="change-spec")
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="exploring")
    # The digest of the file as the Hub last wrote it. A file whose digest no longer matches was
    # edited by someone else, which the Hub reports and never resolves on the operator's behalf.
    content_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Per-requirement text digests, keyed by minted identifier. Nothing in this change reads them;
    # they exist so a later change can tell that a requirement's *meaning* moved out from under
    # evidence accepted against the old wording. Kept in the database rather than the file for the
    # same reason as `phase`.
    requirement_digests: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # What happens to work that ignores this document. Stated in the file as `aw-spec-rigor` for
    # anyone reading it, and held here because it is a gate and a gate whose value lives where the
    # gated party can write it is not a gate — the same reasoning as `phase`.
    rigor: Mapped[str] = mapped_column(
        String(16), default="sketch", server_default="sketch", nullable=False
    )
    # When the operator declared exploration finished. Null while exploring.
    explore_closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("project_id", "path", name="uq_spec_documents_project_path"),
        CheckConstraint(
            "phase IN ('" + "', '".join(SPEC_PHASES) + "')",
            name="ck_spec_documents_phase",
        ),
        # No CHECK on `rigor`, deliberately, for the reason recorded on `TaskTransition.origin`: a
        # table-level CHECK naming a column makes that column undroppable in SQLite, which would
        # make 0069 irreversible. The values are declared once in `SPEC_RIGORS` and refused on the
        # way in by `spec_rigor.set_rigor`, which is the only writer.
    )


class SpecRigorEvent(Base):
    """Every change of a document's rigor, and who made it. Never updated, never deleted.

    The operator's escape hatch from a gate is to demote the document — which is a legitimate
    decision precisely because it leaves this row. A hidden override would be the same act without
    the record, and the record is the whole difference.

    The digest current at the moment is stored so a change cannot be explained away later: a policy
    that is operator-editable is exactly the kind whose history stops being reconstructible.
    """

    __tablename__ = "spec_rigor_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("spec_documents.id"), nullable=False
    )
    from_rigor: Mapped[str] = mapped_column(String(16), nullable=False)
    to_rigor: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The document's content digest when the change was made. A rigor change is compare-and-swap
    # against this, so it cannot silently land on a document edited underneath it.
    digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "actor_kind IN ('" + "', '".join(SPEC_EVENT_ACTORS) + "')",
            name="ck_spec_rigor_events_actor_kind",
        ),
        Index("ix_spec_rigor_events_document", "document_id", "created_at"),
    )


class SpecDocumentEvent(Base):
    """Append-only history of everything that happened to a document.

    Nothing in this change reads it. It ships now because it **cannot be
    backfilled**: a telemetry query written later would report on the fraction
    of work that happened after the query existed, which is worse than no
    telemetry because it looks complete.
    """

    __tablename__ = "spec_document_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("spec_documents.id"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    # What changed: "created", "content", or "phase".
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # The agent's name, or how the operator identified themselves. Never accepted from a request
    # body — it comes from the credential the run was minted with.
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detail: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "actor_kind IN ('" + "', '".join(SPEC_EVENT_ACTORS) + "')",
            name="ck_spec_document_events_actor_kind",
        ),
        CheckConstraint(
            "origin IN ('" + "', '".join(SPEC_EVENT_ORIGINS) + "')",
            name="ck_spec_document_events_origin",
        ),
        Index("ix_spec_document_events_document", "document_id", "created_at"),
    )


# A requirement removed from its document keeps its row: what it once demanded, and what was built
# for it, is a question that outlives the requirement.
SPEC_REQUIREMENT_STATES = ("active", "retired")

# Where a digest change was observed. `hub` is a submission the Hub itself wrote; `external` is a
# change found by reindexing a file somebody edited directly. Telling them apart is the difference
# between "an agent reworded this" and "the file moved under us".
SPEC_REVISION_SOURCES = ("hub", "external")

# What happened to the requirement, not what it means. Whether a rewording was editorial or
# substantive is a judgement an operator makes later; recording it as a fact here would decide it.
SPEC_REVISION_CLASSIFICATIONS = ("created", "reworded", "retired", "restored")


class SpecRequirement(Base):
    """One requirement, addressable from outside the document that declares it.

    Derived, never authoritative: rebuilt from the document on every save, and reconstructible from
    the files alone. It holds no wording — only the digest of it — so this row cannot come to
    disagree with the document about what a requirement says.

    `identifier` is minted per document (`spec_identity` reads its high-water mark from the
    document's own file), so `FR-1` exists in every document and the uniqueness that can hold is
    per document. Everything that points at a requirement points at `id`, which is unambiguous
    regardless.
    """

    __tablename__ = "spec_requirements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("spec_documents.id"), nullable=False
    )
    # The minted public handle, `FR-n`. Stable across rewordings and never reissued after removal.
    identifier: Mapped[str] = mapped_column(String(32), nullable=False)
    # The agent's document-scoped handle. Kept because it is what re-resolves a requirement after a
    # rewording — the identifier survives precisely by being mapped from this.
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # The semantic digest, from `spec_digest.semantic_digest`. Evidence pins against this value.
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    # Which canonicalization produced `digest`. A digest taken under an older rule is then
    # recognisable as such rather than reading as a rewording.
    digest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Where it sits in the rendered document, as a fragment reference.
    anchor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    # When the index last agreed with the file.
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "document_id",
            "identifier",
            name="uq_spec_requirements_document_identifier",
        ),
        CheckConstraint(
            "state IN ('" + "', '".join(SPEC_REQUIREMENT_STATES) + "')",
            name="ck_spec_requirements_state",
        ),
        Index("ix_spec_requirements_document", "document_id", "identifier"),
        Index("ix_spec_requirements_project_state", "project_id", "state"),
    )


class SpecRequirementRevision(Base):
    """Append-only: every time a requirement's meaning moved, and who moved it.

    This is what makes "the meaning changed under this evidence" a fact rather than an inference.
    It cannot be backfilled — a digest that was never recorded cannot be recovered from the current
    file — so it is written from the first indexed requirement, before anything reads it.
    """

    __tablename__ = "spec_requirement_revisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    requirement_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("spec_requirements.id"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("spec_documents.id"), nullable=False
    )
    # Null on the first revision: a requirement that did not exist has no previous meaning.
    previous_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    digest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # Never accepted from a request body — it comes from the credential the run was minted with.
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "source IN ('" + "', '".join(SPEC_REVISION_SOURCES) + "')",
            name="ck_spec_requirement_revisions_source",
        ),
        CheckConstraint(
            "classification IN ('" + "', '".join(SPEC_REVISION_CLASSIFICATIONS) + "')",
            name="ck_spec_requirement_revisions_classification",
        ),
        CheckConstraint(
            "actor_kind IN ('" + "', '".join(SPEC_EVENT_ACTORS) + "')",
            name="ck_spec_requirement_revisions_actor_kind",
        ),
        Index("ix_spec_requirement_revisions_requirement", "requirement_id", "created_at"),
    )


class TaskRequirementLink(Base):
    """The work a requirement has, as a row rather than a string.

    `Task.requirements` held `"FR-8 — initialize-members"`: something that looks like a reference
    and resolves to nothing. It cannot be joined, cannot be checked, and does not notice when FR-8
    is reworded or retired. Every question this change exists to answer is a join away with rows and
    unanswerable without them.

    **Not removed when a task reaches a terminal state.** "What work served this requirement?" is
    asked mostly about finished work, so deleting on completion would erase the answer exactly when
    it becomes interesting.
    """

    __tablename__ = "task_requirement_links"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("tasks.id"), nullable=False)
    requirement_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("spec_requirements.id"), nullable=False
    )
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("task_id", "requirement_id", name="uq_task_requirement_links_pair"),
        CheckConstraint(
            "actor_kind IN ('" + "', '".join(SPEC_EVENT_ACTORS) + "')",
            name="ck_task_requirement_links_actor_kind",
        ),
        Index("ix_task_requirement_links_requirement", "requirement_id"),
        Index("ix_task_requirement_links_task", "task_id"),
    )


class TaskRequirementReference(Base):
    """A reference naming no requirement this project has, kept verbatim.

    The migration from free text must never discard a value it cannot interpret and must never
    invent a requirement to match one. What is left over lands here with its original string, so a
    mis-parse is re-derivable rather than reconstructed from a backup — and so an operator can see
    that a task used to name something.
    """

    __tablename__ = "task_requirement_references"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("tasks.id"), nullable=False)
    # Exactly what the task carried. Not normalized, not trimmed to the part that parsed.
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    # Why it did not resolve: "unknown", "ambiguous", or "unparsed".
    reason: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (Index("ix_task_requirement_references_task", "task_id"),)


# Open at the edges on purpose. Evidence is whatever demonstrates the work, and constraining it to
# what was imaginable at design time is how a record stops describing what was actually done. Values
# outside this list are accepted; the list is what the surfaces know how to label.
EVIDENCE_KINDS = (
    "test_result",
    "screenshot",
    "artifact_diff",
    "review_record",
    "manual_observation",
    "external_reference",
)

EVIDENCE_REVIEW_STATES = ("awaiting", "accepted", "rejected")
EVIDENCE_DECISIONS = ("accepted", "rejected")

# How long an artifact is kept. `never` means never delete it.
EVIDENCE_RETENTION_POLICIES = ("on_acceptance", "daily", "monthly", "manual", "never")

DRIFT_STATES = ("candidate", "resolved", "superseded")
DRIFT_RESOLUTIONS = ("specification_updated", "implementation_corrected", "no_change_required")


class RequirementEvidence(Base):
    """Something produced to demonstrate a requirement, and what it was produced against.

    **Pinned to the digest, not the requirement.** Evidence accepted against one wording says
    nothing about a different wording, and without the pin that difference is unobservable after the
    fact. It is the whole mechanism behind staleness.

    The artifact lives in the project directory; this row records where. That division is the one
    the product already uses for specification documents, and it means an operator can open, diff,
    move and archive evidence with ordinary tools. A row whose artifact is gone reports that state
    rather than disappearing.
    """

    __tablename__ = "requirement_evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    requirement_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("spec_requirements.id"), nullable=False
    )
    # The requirement digest current when this was produced. Never recomputed.
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    digest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Where the artifact is, relative to the project directory. Empty for a kind that has none.
    locator: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # Never accepted from a request body — it comes from the credential the run was minted with.
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("tasks.id"), nullable=True
    )
    # The current decision, materialised from the append-only reviews so a coverage query is one
    # join rather than a correlated subquery. `evidence_reviews` is what governs.
    review_state: Mapped[str] = mapped_column(
        String(16), default="awaiting", server_default="awaiting", nullable=False
    )
    # Set when retention removed the artifact. The record stays; this is how it says the attachment
    # is gone rather than pretending it is still there.
    artifact_removed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    produced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "review_state IN ('" + "', '".join(EVIDENCE_REVIEW_STATES) + "')",
            name="ck_requirement_evidence_review_state",
        ),
        CheckConstraint(
            "actor_kind IN ('" + "', '".join(SPEC_EVENT_ACTORS) + "')",
            name="ck_requirement_evidence_actor_kind",
        ),
        Index("ix_requirement_evidence_requirement", "requirement_id", "produced_at"),
        Index("ix_requirement_evidence_project", "project_id"),
    )


class EvidenceReview(Base):
    """One decision about one piece of evidence. Never updated, never deleted.

    The same shape as `TaskTransition`, for the same reason: who decided, and on what basis, is the
    record. An update would let the last writer rewrite the history the review exists to create.
    """

    __tablename__ = "evidence_reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    evidence_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("requirement_evidence.id"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "decision IN ('" + "', '".join(EVIDENCE_DECISIONS) + "')",
            name="ck_evidence_reviews_decision",
        ),
        CheckConstraint(
            "actor_kind IN ('" + "', '".join(SPEC_EVENT_ACTORS) + "')",
            name="ck_evidence_reviews_actor_kind",
        ),
        Index("ix_evidence_reviews_evidence", "evidence_id", "created_at"),
    )


class EvidenceFootprint(Base):
    """What the implementation looked like when evidence was produced.

    Two shapes, both first-class. In a git repository: the commit, and the blob ids of the changed
    paths. Without one: the changed paths and a content hash of each. A git-only first cut would
    leave every non-repository project permanently unverifiable, and those are a supported case.

    `reachable_from_main` is what stops `verified` describing code that never ships. Approved work in
    this product currently stays on a per-agent branch that nothing merges, so a footprint routinely
    names a commit the product does not contain.
    """

    __tablename__ = "evidence_footprints"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    evidence_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("requirement_evidence.id"), nullable=False
    )
    # "git" or "paths".
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    commit_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # {path: blob id or content hash}. The fingerprint a later change is compared against.
    entries: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # Whether this footprint is reachable from the project's main line of work, as last observed.
    # Null means not yet determined — distinct from False, which is an answer.
    reachable_from_main: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("evidence_id", name="uq_evidence_footprints_evidence"),
        Index("ix_evidence_footprints_project", "project_id"),
    )


class RequirementDrift(Base):
    """The implementation moved and the requirement did not — as a question, never an edit.

    That an implementation changed is observable. That a requirement *should* change is a judgement,
    and a system inferring it would rewrite an approved specification on the strength of a file diff.
    So this is raised, shown, and resolved by a person.
    """

    __tablename__ = "requirement_drift"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    requirement_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("spec_requirements.id"), nullable=False
    )
    evidence_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("requirement_evidence.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(16), default="candidate", server_default="candidate", nullable=False
    )
    # The fingerprint the evidence was produced against, and what was found later.
    baseline: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    observed: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # The requirement digest at the moment this was raised, so a rewording supersedes it rather than
    # leaving a candidate about a question that has moved on.
    digest: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    resolution: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # The digest and fingerprint current when it was resolved, so the same change does not re-fire.
    resolved_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resolved_fingerprint: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('" + "', '".join(DRIFT_STATES) + "')",
            name="ck_requirement_drift_state",
        ),
        Index("ix_requirement_drift_requirement", "requirement_id", "state"),
        Index("ix_requirement_drift_project_state", "project_id", "state"),
    )


#: What an integration attempt did. `skipped` is a first-class outcome, not a failure: a project
#: that has not chosen a main branch, or an operator mid-edit, is a reason not to merge rather than
#: something going wrong.
INTEGRATION_OUTCOMES = ("merged", "skipped", "failed")

#: How the merge was performed. Only one mechanism exists today; the column exists so that a later
#: mode integrating by a different route is distinguishable in the history rather than conflated
#: with this one after the fact.
INTEGRATION_MECHANISMS = ("local",)


class TaskIntegration(Base):
    """What approving a task did to the repository.

    Append-only, with no update path and no delete path. This is the account of a write the system
    performed on the operator's own history; the thing that wrote it does not get to edit the record
    of what it wrote.

    A row exists for every approval that reached the integration step, including the ones that
    merged nothing. "Nothing happened, and here is why" is the answer an operator needs when work
    they approved is not where they expected it.
    """

    __tablename__ = "task_integrations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("tasks.id"), nullable=False)
    # The commit that was merged, and the branch it came from. Null where nothing was merged.
    commit_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # The project's configured main branch at the time. Null where none was configured, which is
    # itself one of the reasons a merge is skipped.
    target_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    # Why it did not merge, in words an operator can act on. Empty for a successful merge.
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mechanism: Mapped[str] = mapped_column(String(16), nullable=False, default="local")
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('" + "', '".join(INTEGRATION_OUTCOMES) + "')",
            name="ck_task_integrations_outcome",
        ),
        Index("ix_task_integrations_task", "task_id", "created_at"),
        Index("ix_task_integrations_project", "project_id", "created_at"),
    )
