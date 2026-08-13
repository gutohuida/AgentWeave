"""add requirement evidence, reviews, footprints and drift

Revision ID: 0068
Revises: 0067
Create Date: 2026-08-13 22:10:00.000000

Evidence is pinned to the requirement digest it was produced against, because evidence accepted
against one wording says nothing about a different wording and that difference is unobservable
afterwards if the pin was never taken.

Two columns outside the new tables: `agents.can_accept_evidence`, an operator-granted capability
alongside `can_recall` and `can_read_checkpoints`, and `projects.evidence_retention`, whose default
is `never` — an operator who wants to manage the artifact tree themselves should not be fighting a
cleaner they never asked for.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None

_ACTORS = ("operator", "agent", "system")
_REVIEW_STATES = ("awaiting", "accepted", "rejected")
_DECISIONS = ("accepted", "rejected")
_DRIFT_STATES = ("candidate", "resolved", "superseded")


def _tables(conn) -> set[str]:
    """An upgrade starting from an early revision reaches this migration with only the tables
    those revisions created; `create_all` builds the rest from the model."""
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "agents" in present and "can_accept_evidence" not in _columns(conn, "agents"):
        op.add_column(
            "agents",
            sa.Column(
                "can_accept_evidence", sa.Boolean, nullable=False, server_default=sa.text("0")
            ),
        )

    if "projects" in present and "evidence_retention" not in _columns(conn, "projects"):
        op.add_column(
            "projects",
            sa.Column("evidence_retention", sa.String(16), nullable=False, server_default="never"),
        )

    if "requirement_evidence" not in present:
        op.create_table(
            "requirement_evidence",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column(
                "requirement_id",
                sa.String(64),
                sa.ForeignKey("spec_requirements.id"),
                nullable=False,
            ),
            sa.Column("digest", sa.String(64), nullable=False),
            sa.Column("digest_version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("locator", sa.Text, nullable=False, server_default=""),
            sa.Column("summary", sa.Text, nullable=False, server_default=""),
            sa.Column("actor_kind", sa.String(16), nullable=False),
            sa.Column("actor", sa.String(128), nullable=False, server_default=""),
            sa.Column("run_id", sa.String(64), nullable=True),
            sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=True),
            sa.Column("review_state", sa.String(16), nullable=False, server_default="awaiting"),
            sa.Column("artifact_removed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("produced_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "review_state IN ('" + "', '".join(_REVIEW_STATES) + "')",
                name="ck_requirement_evidence_review_state",
            ),
            sa.CheckConstraint(
                "actor_kind IN ('" + "', '".join(_ACTORS) + "')",
                name="ck_requirement_evidence_actor_kind",
            ),
        )
        op.create_index(
            "ix_requirement_evidence_requirement",
            "requirement_evidence",
            ["requirement_id", "produced_at"],
        )
        op.create_index("ix_requirement_evidence_project", "requirement_evidence", ["project_id"])

    if "evidence_reviews" not in present:
        op.create_table(
            "evidence_reviews",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column(
                "evidence_id",
                sa.String(64),
                sa.ForeignKey("requirement_evidence.id"),
                nullable=False,
            ),
            sa.Column("decision", sa.String(16), nullable=False),
            sa.Column("actor_kind", sa.String(16), nullable=False),
            sa.Column("actor", sa.String(128), nullable=False, server_default=""),
            sa.Column("run_id", sa.String(64), nullable=True),
            sa.Column("reason", sa.Text, nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "decision IN ('" + "', '".join(_DECISIONS) + "')",
                name="ck_evidence_reviews_decision",
            ),
            sa.CheckConstraint(
                "actor_kind IN ('" + "', '".join(_ACTORS) + "')",
                name="ck_evidence_reviews_actor_kind",
            ),
        )
        op.create_index(
            "ix_evidence_reviews_evidence", "evidence_reviews", ["evidence_id", "created_at"]
        )

    if "evidence_footprints" not in present:
        op.create_table(
            "evidence_footprints",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column(
                "evidence_id",
                sa.String(64),
                sa.ForeignKey("requirement_evidence.id"),
                nullable=False,
            ),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("commit_sha", sa.String(64), nullable=True),
            sa.Column("branch", sa.String(255), nullable=True),
            sa.Column("entries", sa.JSON, nullable=True),
            sa.Column("reachable_from_main", sa.Boolean, nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("evidence_id", name="uq_evidence_footprints_evidence"),
        )
        op.create_index("ix_evidence_footprints_project", "evidence_footprints", ["project_id"])

    if "requirement_drift" not in present:
        op.create_table(
            "requirement_drift",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column(
                "requirement_id",
                sa.String(64),
                sa.ForeignKey("spec_requirements.id"),
                nullable=False,
            ),
            sa.Column(
                "evidence_id",
                sa.String(64),
                sa.ForeignKey("requirement_evidence.id"),
                nullable=False,
            ),
            sa.Column("state", sa.String(16), nullable=False, server_default="candidate"),
            sa.Column("baseline", sa.JSON, nullable=True),
            sa.Column("observed", sa.JSON, nullable=True),
            sa.Column("digest", sa.String(64), nullable=False, server_default=""),
            sa.Column("resolution", sa.String(32), nullable=True),
            sa.Column("resolved_by", sa.String(128), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_digest", sa.String(64), nullable=True),
            sa.Column("resolved_fingerprint", sa.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "state IN ('" + "', '".join(_DRIFT_STATES) + "')",
                name="ck_requirement_drift_state",
            ),
        )
        op.create_index(
            "ix_requirement_drift_requirement", "requirement_drift", ["requirement_id", "state"]
        )
        op.create_index(
            "ix_requirement_drift_project_state", "requirement_drift", ["project_id", "state"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)
    if "requirement_drift" in present:
        op.drop_index("ix_requirement_drift_project_state", table_name="requirement_drift")
        op.drop_index("ix_requirement_drift_requirement", table_name="requirement_drift")
        op.drop_table("requirement_drift")
    if "evidence_footprints" in present:
        op.drop_index("ix_evidence_footprints_project", table_name="evidence_footprints")
        op.drop_table("evidence_footprints")
    if "evidence_reviews" in present:
        op.drop_index("ix_evidence_reviews_evidence", table_name="evidence_reviews")
        op.drop_table("evidence_reviews")
    if "requirement_evidence" in present:
        op.drop_index("ix_requirement_evidence_project", table_name="requirement_evidence")
        op.drop_index("ix_requirement_evidence_requirement", table_name="requirement_evidence")
        op.drop_table("requirement_evidence")
    if "projects" in present and "evidence_retention" in _columns(conn, "projects"):
        op.drop_column("projects", "evidence_retention")
    if "agents" in present and "can_accept_evidence" in _columns(conn, "agents"):
        op.drop_column("agents", "can_accept_evidence")
