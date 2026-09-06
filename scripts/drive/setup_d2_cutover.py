"""Seed the D-2 independent cutover drive (F126's guard, 3142a91).

Only the PREREQUISITES are seeded: a project, an agent, conversations and *ready* checkpoints.
A checkpoint otherwise costs a real Haiku turn and an agent worktree, and none of the probes in
`t_d2_cutover_guard.py` are about generation. The rows are written through the Hub's own
`create_checkpoint`, so they are the rows the product makes.

Everything under test after this is real HTTP against the uvicorn Hub on 8011.

    py -3.11 scripts/drive/setup_d2_cutover.py <db-path> init
    py -3.11 scripts/drive/setup_d2_cutover.py <db-path> ckpt <conversation-id>

`init` does NOT drop tables: the server owns this database and has already migrated it. Seeding
by dropping would take `alembic_version` out of step with the schema.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

DB = sys.argv[1]
CMD = sys.argv[2] if len(sys.argv) > 2 else "init"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB}"
os.environ.setdefault("AW_LOG_LEVEL", "WARNING")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hub"))

from hub.checkpoint_generation import CheckpointBody, render_body  # noqa: E402
from hub.checkpoints import compute_envelope, create_checkpoint  # noqa: E402
from sqlalchemy import select  # noqa: E402

from hub.db.engine import async_session_factory  # noqa: E402
from hub.db.models import Agent, ApiKey, Conversation, OperatorCredential, Project  # noqa: E402

PROJ = "proj-d2drive"
KEY = "aw_live_d2drive0000000000000000000"
AGENT = "delta"

# One conversation per probe, so no probe can be contaminated by another's rows.
CONVS = {
    "conv-d2-unarchive": "Ship the parser",
    "conv-d2-race": "Ship the tokenizer",
    "conv-d2-chain": "Ship the emitter",
}


def body_for(objective):
    return render_body(
        CheckpointBody(
            objective=objective,
            state="The anchor file exists and holds the anchor word.",
            decisions=["Chose the queue entry over a context file."],
            dead_ends=["Tried the per-agent context file; it cannot carry a per-conversation payload."],
            next_actions=["Write the second anchor file."],
            risks=["Do not rewrite the first anchor file."],
        ),
        notes_incorporated=False,
    )


async def add_checkpoint(db, conv, objective):
    return await create_checkpoint(
        db,
        conv,
        trigger="context_pressure",
        envelope=await compute_envelope(db, conv),
        body=body_for(objective),
    )


async def main():
    async with async_session_factory() as db:
        if CMD == "ckpt":
            conv_id = sys.argv[3]
            # `Conversation`'s primary key is `sequence`, not `id` (models.py:418), so
            # `db.get(Conversation, conv_id)` silently returns None.
            conv = await db.scalar(select(Conversation).where(Conversation.id == conv_id))
            cp = await add_checkpoint(db, conv, f"Continue {conv_id}")
            await db.commit()
            print(json.dumps({"conversation": conv_id, "checkpoint": cp.id, "status": cp.status}))
            return

        db.add(
            Project(
                id=PROJ,
                name="d2drive",
                main_branch="master",
                working_directory=str(Path(DB).parent),
            )
        )
        db.add(ApiKey(id=KEY, project_id=PROJ, label="d2"))
        # Operator routes authenticate against OperatorCredential, not ApiKey: the operator
        # secret deliberately carries no project identity (auth.py:88).
        db.add(OperatorCredential(id=KEY, label="d2"))
        db.add(Agent(id="agent-d2drive", project_id=PROJ, name=AGENT))
        out = {"project": PROJ, "key": KEY, "agent": AGENT, "checkpoints": {}}
        for conv_id, title in CONVS.items():
            conv = Conversation(
                id=conv_id,
                project_id=PROJ,
                agent=AGENT,
                lifecycle="open",
                origin="operator",
                title=title,
                lineage_id=conv_id,
            )
            db.add(conv)
            await db.flush()
            cp = await add_checkpoint(db, conv, title)
            out["checkpoints"][conv_id] = {"id": cp.id, "status": cp.status}
        await db.commit()
        print(json.dumps(out, indent=1))


asyncio.run(main())
