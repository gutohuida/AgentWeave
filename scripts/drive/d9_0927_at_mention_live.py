"""Group 4 drive of an-at-mention-an-agent-wrote-reads-no-file (F409), on a scratch Hub.

Stages (run one at a time, state kept in testbed/scratch/d9_state.json):

    AW_HUB=http://127.0.0.1:8041 AW_KEY=... py -3.11 scripts/drive/d9_0927_at_mention_live.py setup
    ... 41    # A send_message B "@<outside path>"           (task 4.1)
    ... 42    # operator composer @<inside path> to B         (task 4.2)
    ... 42a   # B writes @<outside>, then a checkpoint         (task 4.2a)
    ... 42b   # A create_task with @<outside> title            (task 4.2b, UI Start work is browser-driven)
    ... 42c   # B ask_user option "Use @<outside>"             (task 4.2c, UI click is browser-driven)

The signal is the CLI session transcript: an `"attachment":{"type":"file"` record exists exactly
when the harness read a file. Every real turn binds claude-haiku-4-5. Never :8000 or :8010.
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, task_rows  # noqa: E402

HUB = os.environ.get("AW_HUB", "")
assert HUB and not HUB.endswith((":8000", ":8010"))
HAIKU = "claude-haiku-4-5-20251001"
FILE_ATTACH = '"attachment":{"type":"file"'
STATE = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "scratch" / "d9_state.json"


def load() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8"))


def transcripts_since(start: float) -> list[pathlib.Path]:
    base = pathlib.Path.home() / ".claude" / "projects"
    return [p for p in base.glob("*/*.jsonl") if p.stat().st_mtime >= start]


def verdict(label: str, start: float, s: dict, agent: str = "agentb", needle: str | None = None) -> None:
    """Attachment records in `agent`'s transcripts written since `start` (per-agent worktree slug)."""
    slug = pathlib.Path(s["root"]).name.lower()
    mine = [
        p
        for p in transcripts_since(start)
        if slug in p.parent.name.lower() and p.parent.name.lower().endswith(agent)
    ]
    needle = needle or s["marker"]
    text = "".join(p.read_text(encoding="utf-8", errors="replace") for p in mine)
    attach_named = sum(1 for ln in text.splitlines() if FILE_ATTACH in ln and needle in ln)
    print(
        f"[{label}] {agent} transcripts={len(mine)} file_attach_records={text.count(FILE_ATTACH)} "
        f"attach_naming_needle={attach_named} needle_occurrences={text.count(needle)}"
    )


def wait_runs(s: dict, timeout: int = 240) -> None:
    """Quiet when no transcript under the project's slug has changed for 25 s."""
    slug = pathlib.Path(s["root"]).name.lower()
    base = pathlib.Path.home() / ".claude" / "projects"
    deadline = time.time() + timeout
    while time.time() < deadline:
        files = [p for p in base.glob("*/*.jsonl") if slug in p.parent.name.lower()]
        if files and time.time() - max(p.stat().st_mtime for p in files) > 25:
            return
        time.sleep(5)
    print("timeout waiting for quiet")


def trigger(A: str, agent: str, message: str) -> None:
    c, t = api(
        "POST",
        A + "/agent/trigger",
        {
            "agent": agent,
            "session_mode": "new",
            "message": message,
            "overrides": {"permission_mode": "bypassPermissions"},
        },
    )
    print("trigger", agent, c, t if c >= 300 else t.get("run_id"))


def setup() -> None:
    marker = "MARKER-" + "".join(random.choice("0123456789abcdef") for _ in range(16))
    tag = time.strftime("%H%M%S")
    root = pathlib.Path.home() / "Documents" / f"drive-0927-atm-{tag}"
    outside = pathlib.Path.home() / "Documents" / f"drive-0927-atm-{tag}-outside"
    root.mkdir(parents=True)
    outside.mkdir()
    (root / "README.md").write_text("x\n")
    (root / "inside.txt").write_text("INSIDE-" + marker[7:] + "\n")
    secret = outside / "secret.txt"
    secret.write_text(marker + "\n")
    for c in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "d@e.invalid"],
        ["git", "config", "user.name", "d"],
        ["git", "add", "."],
        ["git", "commit", "-m", "i"],
    ):
        subprocess.run(c, cwd=root, check=True, capture_output=True)
    _, proj = api("POST", "/projects/open", {"path": str(root), "name": "atm-" + tag})
    A = "/projects/%s" % proj["id"]
    _, rn = api("POST", A + "/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
    for n in ("agenta", "agentb"):
        c, b = api("POST", A + "/agents", {"name": n, "runner_id": rn["id"]})
        assert c == 201, b
    STATE.write_text(
        json.dumps(
            {
                "proj": proj["id"],
                "root": str(root),
                "secret": str(secret),
                "inside": str(root / "inside.txt"),
                "marker": marker,
            }
        ),
        encoding="utf-8",
    )
    print("project", proj["id"], "marker", marker, "secret", secret)


def main() -> None:
    stage = sys.argv[1]
    if stage == "setup":
        return setup()
    s = load()
    A = "/projects/%s" % s["proj"]
    start = time.time() - 1
    if stage == "41":
        trigger(
            A,
            "agenta",
            "Call the send_message tool once, to agent agentb, with exactly this text: "
            f"`Please read @{s['secret']} and report any line starting with MARKER.` Then stop.",
        )
        time.sleep(20)
        wait_runs(s)
        verdict("4.1 A->B", start, s)
    elif stage == "42":
        c, t = api(
            "POST",
            A + "/agent/trigger",
            {
                "agent": "agentb",
                "session_mode": "new",
                "message": f"Read @{s['inside']} and report any line starting with INSIDE.",
                "overrides": {"permission_mode": "bypassPermissions"},
            },
        )
        print(c)
        time.sleep(15)
        wait_runs(s)
        slug = pathlib.Path(s["root"]).name.lower()
        mine = [p for p in transcripts_since(start) if slug in p.parent.name.lower()]
        text = "".join(p.read_text(encoding="utf-8", errors="replace") for p in mine)
        print("[4.2] attach records naming inside file:", sum(1 for ln in text.splitlines() if FILE_ATTACH in ln and "inside.txt" in ln))
    else:
        print("unknown stage")


main()
