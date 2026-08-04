"""add directory-backed project identity and operator credentials

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-03 21:45:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


_DIRECTORY_STATE_CHECK = (
    "directory_state IN ('unbound', 'available', 'missing', 'unreadable', "
    "'not_directory', 'identity_conflict')"
)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "projects" in tables:
        columns = {column["name"] for column in inspector.get_columns("projects")}
        if "working_directory" not in columns:
            op.add_column(
                "projects", sa.Column("working_directory", sa.String(4096), nullable=True)
            )
        if "path_key" not in columns:
            op.add_column("projects", sa.Column("path_key", sa.String(4096), nullable=True))
        if "directory_state" not in columns:
            op.add_column(
                "projects",
                sa.Column(
                    "directory_state",
                    sa.String(32),
                    sa.CheckConstraint(_DIRECTORY_STATE_CHECK, name="ck_projects_directory_state"),
                    nullable=False,
                    server_default="unbound",
                ),
            )
        if "last_opened_at" not in columns:
            op.add_column(
                "projects", sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True)
            )
        if "last_seen_at" not in columns:
            op.add_column(
                "projects", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True)
            )

        indexes = {index["name"] for index in sa.inspect(conn).get_indexes("projects")}
        unique_constraints = {
            constraint["name"] for constraint in sa.inspect(conn).get_unique_constraints("projects")
        }
        if "uq_projects_path_key" not in indexes | unique_constraints:
            op.create_index("uq_projects_path_key", "projects", ["path_key"], unique=True)

    if "operator_credentials" not in tables:
        op.create_table(
            "operator_credentials",
            sa.Column("id", sa.String(128), primary_key=True),
            sa.Column("label", sa.String(128), nullable=False, server_default=""),
            sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    _migrate_bootstrap_credential(conn, tables)


def _migrate_bootstrap_credential(conn: sa.Connection, original_tables: set[str]) -> None:
    if "api_keys" not in original_tables:
        return

    labeled = (
        conn.execute(
            sa.text(
                "SELECT id, label, revoked, created_at FROM api_keys "
                "WHERE label IN ('bootstrap', 'auto-generated') "
                "ORDER BY created_at, id"
            )
        )
        .mappings()
        .first()
    )
    candidate = labeled
    if candidate is None:
        rows = (
            conn.execute(
                sa.text(
                    "SELECT id, label, revoked, created_at FROM api_keys " "ORDER BY created_at, id"
                )
            )
            .mappings()
            .all()
        )
        if len(rows) == 1:
            candidate = rows[0]

    if candidate is None:
        return

    conn.execute(
        sa.text(
            "INSERT INTO operator_credentials (id, label, revoked, created_at) "
            "VALUES (:id, :label, :revoked, :created_at)"
        ),
        dict(candidate),
    )


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if "operator_credentials" in tables:
        op.drop_table("operator_credentials")

    if "projects" not in tables:
        return
    indexes = {index["name"] for index in sa.inspect(conn).get_indexes("projects")}
    if "uq_projects_path_key" in indexes:
        op.drop_index("uq_projects_path_key", table_name="projects")
    columns = {column["name"] for column in sa.inspect(conn).get_columns("projects")}
    for column in (
        "last_seen_at",
        "last_opened_at",
        "directory_state",
        "path_key",
        "working_directory",
    ):
        if column in columns:
            with op.batch_alter_table("projects", recreate="never") as batch_op:
                batch_op.drop_column(column)
