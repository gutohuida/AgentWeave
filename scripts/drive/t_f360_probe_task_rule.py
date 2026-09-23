"""F360 live check: Haiku reads a 32-task loop checkpoint under the old and the new probe task rule.

Run from the repository root with DATABASE_URL naming a throwaway file (importing the Hub needs one):
    DATABASE_URL=sqlite+aiosqlite:///<tmp>/f360.db py -3.11 scripts/drive/t_f360_probe_task_rule.py
Measured 2026-09-23: old rule 0/32 on three reads, new rule 32/32 on three reads.
"""

import json
import subprocess
import sys

sys.path.insert(0, "hub")
from hub.checkpoint_generation import _PROBE_PROMPT as NEW  # noqa: E402
from hub.checkpoints import LOOP_TASK_SCOPE_NOTE  # noqa: E402
from hub.pty_runner import resolve_executable  # noqa: E402

OLD = NEW.replace(
    "- List the id of every task listed under the checkpoint's Tasks heading, whatever its status.",
    "- List the id of every task the checkpoint says is assigned to this agent.",
)
assert OLD != NEW

ids = [f"task-{n:012x}" for n in range(0xA1, 0xA1 + 32)]
statuses = (["approved", "in_progress", "pending", "rejected", "completed"] * 7)[:32]
rendered = "\n".join(
    [
        "# Checkpoint",
        "",
        "## Objective",
        "",
        "I am executor. I picked up the next pending task from the queue and tightened the retry budget in the scheduler; the reviewer holds the rest.",
        "",
        "## Files changed",
        "",
        "- hub/hub/scheduler.py",
        "",
        "## Tasks",
        "",
        f"_{LOOP_TASK_SCOPE_NOTE}_",
        "",
        *[f"- {i} — step {n} ({s})" for n, (i, s) in enumerate(zip(ids, statuses), 1)],
        "",
        "## Open questions",
        "",
        "_None._",
    ]
)

for label, template in (("old", OLD), ("new", NEW)):
    got = []
    for _ in range(3):
        out = subprocess.run(
            resolve_executable(["claude", "--model", "claude-haiku-4-5-20251001", "-p", template.format(rendered=rendered)]),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        ).stdout
        text = out[out.find("{") : out.rfind("}") + 1]
        try:
            got.append(len(set(json.loads(text).get("task_ids", [])) & set(ids)))
        except ValueError:
            got.append("unparseable: " + " ".join(out[:160].split()))
    print(label, "task ids recovered of 32, three reads:", got)
