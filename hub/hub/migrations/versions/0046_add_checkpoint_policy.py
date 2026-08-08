"""add checkpoint policy columns

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-09 00:40:00.000000

When a checkpoint is taken, and who decides.

A threshold is one mode plus one value, not two nullable value columns: "50%" and "150 000
tokens" are the same setting in different units, and a column each makes "both set"
representable — a state with no meaning that every reader would have to disambiguate.

`checkpoint_threshold_value` holds canonical units: 0-100 under `percent`, an actual token count
under `tokens`. An operator types thousands; the surface that collects the number converts it.
A column whose meaning depends on another column's units as well as its mode is one indirection
too many.

Projects default to "off". A project should not begin spending tokens on generation, or cutting
conversations over, because it was upgraded.

Guarded, like 0038-0045.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

_PROJECT_COLUMNS = (
    ("checkpoint_mode", sa.String(16), "off"),
    ("checkpoint_threshold_mode", sa.String(8), None),
    ("checkpoint_threshold_value", sa.Integer(), None),
    ("checkpoint_notes_value", sa.Integer(), None),
    ("checkpoint_runner_id", sa.String(64), None),
    ("checkpoint_model", sa.String(256), None),
)

# All nullable: NULL is "inherits", which is what almost every agent will do.
_AGENT_COLUMNS = (
    ("checkpoint_mode", sa.String(16)),
    ("checkpoint_threshold_mode", sa.String(8)),
    ("checkpoint_threshold_value", sa.Integer()),
    ("checkpoint_notes_value", sa.Integer()),
)


def _columns(conn, table: str):
    inspector = sa.inspect(conn)
    if table not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()

    existing = _columns(conn, "projects")
    if existing is not None:
        for name, kind, default in _PROJECT_COLUMNS:
            if name in existing:
                continue
            op.add_column(
                "projects",
                sa.Column(
                    name,
                    kind,
                    nullable=default is None,
                    server_default=default,
                ),
            )

    existing = _columns(conn, "agents")
    if existing is not None:
        for name, kind in _AGENT_COLUMNS:
            if name not in existing:
                op.add_column("agents", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()

    existing = _columns(conn, "agents")
    if existing is not None:
        for name, _kind in _AGENT_COLUMNS:
            if name in existing:
                op.drop_column("agents", name)

    existing = _columns(conn, "projects")
    if existing is not None:
        for name, _kind, _default in _PROJECT_COLUMNS:
            if name in existing:
                op.drop_column("projects", name)
