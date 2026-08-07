"""questions gain header/multi_select/answer_labels, and options carry descriptions

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-07 15:00:00.000000
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "questions" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("questions")}

    if "header" not in columns:
        op.add_column("questions", sa.Column("header", sa.String(64), nullable=True))
    if "multi_select" not in columns:
        op.add_column(
            "questions",
            sa.Column("multi_select", sa.Boolean(), nullable=False, server_default="0"),
        )
    if "answer_labels" not in columns:
        op.add_column(
            "questions",
            sa.Column("answer_labels", sa.JSON(), nullable=False, server_default="[]"),
        )

    # 0030 stored options as bare strings. Convert them rather than leaving two shapes in one
    # column: a reader tolerant of both never stops being tolerant, and the ambiguity outlives
    # everyone who remembers why it is there.
    rows = conn.execute(sa.text("SELECT id, options FROM questions")).fetchall()
    for row_id, raw in rows:
        if not raw:
            continue
        try:
            options = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        if not isinstance(options, list) or not options:
            continue
        if all(isinstance(entry, dict) for entry in options):
            continue
        converted = [
            {"label": str(entry), "description": ""} if not isinstance(entry, dict) else entry
            for entry in options
        ]
        conn.execute(
            sa.text("UPDATE questions SET options = :options WHERE id = :id"),
            {"options": json.dumps(converted), "id": row_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "questions" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("questions")}
    for name in ("header", "multi_select", "answer_labels"):
        if name in columns:
            op.drop_column("questions", name)
