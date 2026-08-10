"""classify scheduled queue work as autonomous

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-03 02:20:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _replace_constraints(*, include_job: bool) -> None:
    origins = "'operator', 'agent', 'job'" if include_job else "'operator', 'agent'"
    origin_agent = (
        "(origin_type = 'operator' AND origin_agent IS NULL) OR "
        "(origin_type = 'agent' AND origin_agent IS NOT NULL)"
    )
    if include_job:
        origin_agent += " OR (origin_type = 'job' AND origin_agent IS NULL)"
    with op.batch_alter_table("inbound_queue_entries", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_inbound_queue_origin_type", type_="check")
        batch_op.drop_constraint("ck_inbound_queue_origin_agent", type_="check")
        batch_op.create_check_constraint(
            "ck_inbound_queue_origin_type", f"origin_type IN ({origins})"
        )
        batch_op.create_check_constraint("ck_inbound_queue_origin_agent", origin_agent)


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if {"inbound_queue_entries", "projects"} <= tables:
        _replace_constraints(include_job=True)


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if not {"inbound_queue_entries", "projects"} <= tables:
        return
    conn.execute(
        sa.text(
            "UPDATE inbound_queue_entries SET origin_type = 'operator' WHERE origin_type = 'job'"
        )
    )
    _replace_constraints(include_job=False)
