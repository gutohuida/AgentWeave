"""add stable AgentWeave conversations

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-02 20:30:00.000000
"""

import hashlib
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _conversation_id(*parts: object) -> str:
    digest = hashlib.sha256("\x1f".join(str(part) for part in parts).encode()).hexdigest()[:20]
    return f"conv-mig-{digest}"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "conversations" not in tables:
        op.create_table(
            "conversations",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("agent", sa.String(64), nullable=False),
            sa.Column("provider_session_id", sa.String(128), nullable=True),
            sa.Column("lifecycle", sa.String(16), nullable=False, server_default="open"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "lifecycle IN ('open', 'archived')", name="ck_conversations_lifecycle"
            ),
        )
        op.create_index(
            "ix_conversations_project_agent_updated",
            "conversations",
            ["project_id", "agent", "updated_at"],
        )
        op.create_index(
            "uq_conversations_project_agent_provider_session",
            "conversations",
            ["project_id", "agent", "provider_session_id"],
            unique=True,
        )

    for table in ("runs", "inbound_queue_entries", "agent_outputs", "messages"):
        if table not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "conversation_id" not in columns:
            op.add_column(table, sa.Column("conversation_id", sa.String(64), nullable=True))
            # SQLite cannot add a foreign-key constraint after table creation without
            # rebuilding the table. Some historical migration-only test databases do
            # not contain the referenced base tables, so retain SQLite's additive
            # migration shape while enforcing the relation on fresh ORM-created DBs.
            if conn.dialect.name != "sqlite":
                op.create_foreign_key(
                    f"fk_{table}_conversation_id",
                    table,
                    "conversations",
                    ["conversation_id"],
                    ["id"],
                )

    now = datetime.now(timezone.utc)
    conversation_by_binding = {}

    if "runs" in tables:
        runs = conn.execute(
            sa.text(
                "SELECT id, project_id, agent, session_id, started_at FROM runs "
                "ORDER BY started_at, id"
            )
        ).fetchall()
        for run in runs:
            binding = (
                (run.project_id, run.agent, run.session_id) if run.session_id is not None else None
            )
            conversation_id = conversation_by_binding.get(binding) if binding is not None else None
            if conversation_id is None:
                identity = binding if binding is not None else (run.project_id, run.agent, run.id)
                conversation_id = _conversation_id(*identity)
                conn.execute(
                    sa.text(
                        "INSERT INTO conversations "
                        "(id, project_id, agent, provider_session_id, lifecycle, created_at, updated_at) "
                        "VALUES (:id, :project_id, :agent, :session_id, 'open', :created_at, :updated_at)"
                    ),
                    {
                        "id": conversation_id,
                        "project_id": run.project_id,
                        "agent": run.agent,
                        "session_id": run.session_id,
                        "created_at": run.started_at or now,
                        "updated_at": run.started_at or now,
                    },
                )
                if binding is not None:
                    conversation_by_binding[binding] = conversation_id
            conn.execute(
                sa.text("UPDATE runs SET conversation_id = :conversation_id WHERE id = :run_id"),
                {"conversation_id": conversation_id, "run_id": run.id},
            )

    if "agent_outputs" in tables and "runs" in tables:
        conn.execute(
            sa.text(
                "UPDATE agent_outputs SET conversation_id = "
                "(SELECT runs.conversation_id FROM runs WHERE runs.id = agent_outputs.run_id) "
                "WHERE run_id IS NOT NULL"
            )
        )
    if "inbound_queue_entries" in tables and "runs" in tables:
        conn.execute(
            sa.text(
                "UPDATE inbound_queue_entries SET conversation_id = "
                "(SELECT runs.conversation_id FROM runs "
                "WHERE runs.id = inbound_queue_entries.delivered_in_run_id) "
                "WHERE delivered_in_run_id IS NOT NULL"
            )
        )
    if "messages" in tables:
        for binding, conversation_id in conversation_by_binding.items():
            project_id, agent, session_id = binding
            conn.execute(
                sa.text(
                    "UPDATE messages SET conversation_id = :conversation_id "
                    "WHERE project_id = :project_id AND sender = :agent AND session_id = :session_id"
                ),
                {
                    "conversation_id": conversation_id,
                    "project_id": project_id,
                    "agent": agent,
                    "session_id": session_id,
                },
            )

    desired_indexes = {
        "runs": ("ix_runs_conversation_started", ["conversation_id", "started_at"]),
        "inbound_queue_entries": (
            "ix_inbound_queue_conversation_state",
            ["conversation_id", "state", "sequence"],
        ),
        "agent_outputs": ("ix_agent_outputs_conversation", ["conversation_id", "timestamp"]),
        "messages": ("ix_messages_conversation", ["conversation_id"]),
    }
    inspector = sa.inspect(conn)
    for table, (index_name, columns) in desired_indexes.items():
        if table not in tables:
            continue
        existing_indexes = {index["name"] for index in inspector.get_indexes(table)}
        if index_name not in existing_indexes:
            op.create_index(index_name, table, columns)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    indexes = {
        "runs": "ix_runs_conversation_started",
        "inbound_queue_entries": "ix_inbound_queue_conversation_state",
        "agent_outputs": "ix_agent_outputs_conversation",
        "messages": "ix_messages_conversation",
    }
    for table, index in indexes.items():
        if table not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "conversation_id" in columns:
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_index(index)
                batch_op.drop_column("conversation_id")
    if "conversations" in tables:
        op.drop_table("conversations")
