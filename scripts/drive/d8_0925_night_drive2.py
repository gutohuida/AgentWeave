"""0925 night drive part 2: checkpoint handover twice, over real HTTP. Seeds only the prerequisites
(a conversation and two ready checkpoints, through the Hub's own create_checkpoint). No agent turn."""
import asyncio, json, os, sys, uuid
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
DB = os.path.expanduser("~/.agentweave/hub/profiles/drive0925/agentweave.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB}"
os.environ.setdefault("AW_LOG_LEVEL", "WARNING")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hub"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
if ":8000" in os.environ.get("AW_HUB", "") or ":8010" in os.environ.get("AW_HUB", ""):
    sys.exit("refusing")
from hub.checkpoint_generation import CheckpointBody, render_body
from hub.checkpoints import compute_envelope, create_checkpoint
from hub.db.engine import async_session_factory
from hub.db.models import Conversation
from aw import api, P

async def seed():
    cid = "conv-" + uuid.uuid4().hex[:8]
    async with async_session_factory() as db:
        conv = Conversation(id=cid, project_id=P, agent="author", lifecycle="open", origin="operator", title="handover drive", lineage_id=cid)
        db.add(conv); await db.flush()
        ids = []
        for n in (1, 2):
            body = render_body(CheckpointBody(objective=f"obj {n}", state="s", decisions=["d"], dead_ends=["x"], next_actions=["n"], risks=["r"]), notes_incorporated=False)
            cp = await create_checkpoint(db, conv, trigger="context_pressure", envelope=await compute_envelope(db, conv), body=body)
            ids.append(cp.id)
        await db.commit()
    return cid, ids

cid, (c1, c2) = asyncio.run(seed())
print("seeded", cid, c1, c2)
A = f"/projects/{P}"
print("cutover #1", *api("POST", f"{A}/checkpoints/{c1}/cutover", {}))
print("cutover #1 again", *api("POST", f"{A}/checkpoints/{c1}/cutover", {}))
print("cutover #2 (other checkpoint, same conv)", *api("POST", f"{A}/checkpoints/{c2}/cutover", {}))
c, got = api("GET", f"{A}/conversations/{cid}/checkpoints"); print("list", c, json.dumps(got)[:900])
