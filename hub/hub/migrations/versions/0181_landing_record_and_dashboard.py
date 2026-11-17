"""Each landing batch's record, and the landing dashboard for every project --
landing_record_and_dashboard

Revision ID: 0181
Revises: 0180
Create Date: 2026-11-17 16:00:00.000000

`landing-time-and-test-flakiness-are-measured`, FR-7, FR-8. A landing batch records when its
earliest task became ready, when its checks first held a slot, when they ended and how many check
runs it made; every project already here is given the 'Landing time and flaky tests' dashboard (a
project created later is given it by `landing_dashboard.seed`).

Runs on the operator's :8000 data at its next restart. Adds four nullable columns to
`landing_batches`, left NULL on every existing batch (not recorded, never 0), and inserts one
dashboard per project that has none of that name; no existing row is deleted or rewritten. The
panels are this revision's own copy, so a later change to `landing_dashboard` does not change what
this inserted. The downgrade deletes the dashboards this inserted (by name and author `hub`) and
drops the columns, losing only the batches' records.

Guarded for a database without `landing_batches` or `dashboards`, and for the columns already
present (a database built by `create_all`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0181"
down_revision = "0180"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("ready_at", sa.DateTime),
    ("slot_at", sa.DateTime),
    ("checks_ended_at", sa.DateTime),
    ("check_runs", sa.Integer),
)
_NAME = "Landing time and flaky tests"
_AUTHOR = "hub"
_DESCRIPTION = (
    "How long approved work waits and is checked before it lands, and which tests "
    "flake. Wait is from the earliest task ready to land until the batch's checks "
    "held a slot; check time is from then until its last check run ended. A batch "
    "from before these were recorded shows 'not recorded'."
)
_PANELS = [
    {
        "title": "Landing batches, newest first",
        "kind": "table",
        "query": (
            "select id as batch,\n"
            "       created_at as formed_at,\n"
            "       case when ready_at is null or slot_at is null then 'not recorded'\n"
            '            else round((julianday(slot_at) - julianday(ready_at)) * 1440, 1) end as "wait (min)",\n'
            "       case when slot_at is null or checks_ended_at is null then 'not recorded'\n"
            '            else round((julianday(checks_ended_at) - julianday(slot_at)) * 1440, 1) end as "check time (min)",\n'
            "       coalesce(check_runs, 'not recorded') as \"check runs\",\n"
            "       state as outcome\n"
            "from landing_batches\n"
            "order by created_at desc\n"
            "limit 50"
        ),
    },
    {
        "title": "Median landing check time, last 20 batches (min)",
        "kind": "number",
        "query": (
            "with recent as (\n"
            "  select round((julianday(checks_ended_at) - julianday(slot_at)) * 1440, 1) as minutes\n"
            "  from landing_batches\n"
            "  where slot_at is not null and checks_ended_at is not null\n"
            "  order by created_at desc\n"
            "  limit 20\n"
            "), ordered as (\n"
            "  select minutes, row_number() over (order by minutes) as r, count(*) over () as n from recent\n"
            ")\n"
            'select round(avg(minutes), 1) as "median check time (min)"\n'
            "from ordered\n"
            "where r in ((n + 1) / 2, (n + 2) / 2)"
        ),
    },
    {
        "title": "Landing check time over time (min)",
        "kind": "line",
        "query": (
            'select created_at as formed_at, round((julianday(checks_ended_at) - julianday(slot_at)) * 1440, 1) as "check time (min)"\n'
            "from landing_batches\n"
            "where slot_at is not null and checks_ended_at is not null\n"
            "order by created_at asc"
        ),
    },
    {
        "title": "Ten flakiest tests",
        "kind": "table",
        "query": (
            "select check_name, test_id, flake_rate, last_flipped_at from (\n"
            "with ranked as (\n"
            "  select check_name, test_id, outcome, recorded_at,\n"
            "         row_number() over (partition by check_name, test_id order by id desc) as recent,\n"
            "         count(*) over (partition by check_name, test_id) as runs\n"
            "  from test_history\n"
            ")\n"
            "select check_name, test_id,\n"
            "       max(runs) as runs,\n"
            "       sum(outcome = 'flipped') as flips,\n"
            "       sum(recent <= 100) as window_runs,\n"
            "       sum(recent <= 100 and outcome = 'flipped') as window_flips,\n"
            "       case when max(runs) >= 20\n"
            "            then round(1.0 * sum(recent <= 100 and outcome = 'flipped')\n"
            "                       / sum(recent <= 100), 4)\n"
            "       end as flake_rate,\n"
            "       max(case when outcome = 'flipped' then recorded_at end) as last_flipped_at\n"
            "from ranked\n"
            "group by check_name, test_id\n"
            ") where flake_rate > 0 order by flake_rate desc, last_flipped_at desc limit 10"
        ),
    },
]


def _hex() -> str:
    return uuid.uuid4().hex[:12]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if "landing_batches" in tables:
        columns = {column["name"] for column in inspector.get_columns("landing_batches")}
        for name, kind in _COLUMNS:
            if name not in columns:
                op.add_column("landing_batches", sa.Column(name, kind(), nullable=True))
    if "dashboards" not in tables or "projects" not in tables:
        return
    dashboards = sa.table(
        "dashboards",
        sa.column("id", sa.String),
        sa.column("project_id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("panels", sa.JSON),
        sa.column("author", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
        sa.column("version", sa.Integer),
    )
    have = {
        row[0]
        for row in conn.execute(
            sa.text("SELECT project_id FROM dashboards WHERE name = :name"), {"name": _NAME}
        )
    }
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [
        {
            "id": f"dash-{_hex()}",
            "project_id": project_id,
            "name": _NAME,
            "description": _DESCRIPTION,
            "panels": [{"id": f"pnl-{_hex()}", **panel} for panel in _PANELS],
            "author": _AUTHOR,
            "created_at": now,
            "updated_at": now,
            "version": 1,
        }
        for (project_id,) in conn.execute(sa.text("SELECT id FROM projects ORDER BY id"))
        if project_id not in have
    ]
    if rows:
        op.bulk_insert(dashboards, rows)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if "dashboards" in tables:
        seeded = sa.text("SELECT id FROM dashboards WHERE name = :name AND author = :author")
        ids = [row[0] for row in conn.execute(seeded, {"name": _NAME, "author": _AUTHOR})]
        for dashboard_id in ids:
            if "dashboard_versions" in tables:
                conn.execute(
                    sa.text("DELETE FROM dashboard_versions WHERE dashboard_id = :id"),
                    {"id": dashboard_id},
                )
            conn.execute(sa.text("DELETE FROM dashboards WHERE id = :id"), {"id": dashboard_id})
    if "landing_batches" in tables:
        columns = {column["name"] for column in inspector.get_columns("landing_batches")}
        for name, _kind in _COLUMNS:
            if name in columns:
                op.execute(sa.text(f"ALTER TABLE landing_batches DROP COLUMN {name}"))
