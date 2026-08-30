"""F131 live -- press Continue on a conversation whose input is NOT the input that starts.

F131 was filed from a press on a conversation with *nothing* queued for it, and that path is
unreachable from the shipped UI: the Continue button renders only when an undelivered entry names
the conversation on screen. This drives the path that IS reachable -- both conversations hold a
queued entry and the OTHER one's is older -- which is the case the fix
(openspec/changes/continue-starts-what-it-names) is actually about.

Getting two entries queued at once with the agent idle is the whole trick. Every ordinary route
into the queue schedules the agent immediately, and every run end re-drains it, so an entry cannot
be parked next to another one that way. A **cutover with auto-continue off** is the one operator
act that queues without scheduling: it hands the successor its checkpoint and stops. Two of them,
on two predecessors of the same agent, leaves exactly the state this needs.

Real surface only. No row inserts. Haiku turns. Exact status codes.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aw import api, show  # noqa: E402

WORKDIR = Path(os.environ.get("AW_DRIVE_DIR") or "C:/Users/huida/Documents/drive-f131-0830")
PROJECT_NAME = WORKDIR.name
AGENT = "delta"
HAIKU = "claude-haiku-4-5-20251001"
FORBIDDEN = {"proj-5e960453", "proj-18e5d4e0"}
DB_PATH = os.environ.get("AW_DB") or "C:/Users/huida/AppData/Local/Temp/aw0830/aw0830.db"

VERDICTS = []
STARTED = time.time()


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def step(label):
    print("\n" + "=" * 74)
    print(f"{label}   (+{int(time.time() - STARTED)}s)")
    print("=" * 74)


def summarise():
    print("\n" + "=" * 74)
    bad = [v for v in VERDICTS if not v[1]]
    print(f"{len(VERDICTS) - len(bad)}/{len(VERDICTS)} assertions passed")
    for label, _, detail in bad:
        print(f"  FAILED: {label} -- {detail}")
    print("=" * 74)
    return not bad


def git(*args):
    subprocess.run(["git", "-C", str(WORKDIR), *args], check=True, capture_output=True)


def make_repo():
    WORKDIR.mkdir(parents=True, exist_ok=True)
    if not (WORKDIR / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main", str(WORKDIR)], check=True)
        git("config", "user.email", "drive@example.com")
        git("config", "user.name", "Drive")
        (WORKDIR / "README.md").write_text("f131 drive\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "base")


def ensure_project():
    code, body = api("GET", "/projects")
    for p in body if isinstance(body, list) else body.get("projects") or []:
        if p.get("name") == PROJECT_NAME:
            return p["id"]
    code, body = api("POST", "/projects/open", {"path": str(WORKDIR), "name": PROJECT_NAME})
    if code >= 300:
        show("POST /projects/open", code, body)
        sys.exit("could not register the project")
    return body["id"]


def ensure_runner(project):
    code, body = api("GET", f"/projects/{project}/runners")
    for r in (body.get("runners") if isinstance(body, dict) else body) or []:
        if r.get("name") == "Haiku (cheap)":
            return r["id"]
    code, body = api(
        "POST",
        f"/projects/{project}/runners",
        {"name": "Haiku (cheap)", "cli": "claude", "model": HAIKU},
    )
    if code >= 300:
        show("POST /runners", code, body)
        sys.exit("could not create the runner")
    return body["id"]


def ensure_agent(project, runner):
    code, _ = api("POST", f"/projects/{project}/agents", {"name": AGENT, "runner_id": runner})
    if code >= 300:
        api("PATCH", f"/projects/{project}/agents/{AGENT}", {"runner_id": runner})


def agent_status(project):
    code, body = api("GET", f"/projects/{project}/agents")
    for a in body if isinstance(body, list) else body.get("agents") or []:
        if a.get("name") == AGENT:
            return a.get("status")
    return "?"


def wait_idle(project, limit=420):
    deadline = time.time() + limit
    while time.time() < deadline:
        if agent_status(project) != "running":
            time.sleep(1.5)
            if agent_status(project) != "running":
                return True
        time.sleep(2)
    return False


def queued(project):
    code, body = api("GET", f"/projects/{project}/queue/{AGENT}")
    rows = body.get("entries") if isinstance(body, dict) else body
    return [e for e in (rows or []) if e.get("state") == "queued"]


def runs_for(project, conversation_id):
    """Read-only, straight out of the Hub's own database.

    There is no operator route that lists runs by conversation, and the whole question here is
    *which conversation ran* -- a claim that cannot be settled from the answer under test. Reading
    is not inserting: nothing here writes, and the Hub is the only thing that ever wrote these
    rows.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(
            "SELECT id, status FROM runs WHERE project_id = ? AND conversation_id = ?",
            (project, conversation_id),
        ).fetchall()
    finally:
        conn.close()


def one_turn(project, message):
    """Send a message, wait for the turn to end, and return the conversation it ran in."""
    code, body = api(
        "POST",
        f"/projects/{project}/agent/trigger",
        {"agent": AGENT, "message": message},
        timeout=120,
    )
    if code != 200:
        show("trigger", code, body)
        return None
    conversation = body.get("conversation_id")
    wait_idle(project)
    return conversation


def park_a_queued_entry(project, conversation, label):
    """Checkpoint a conversation and cut it over.

    Auto-continue is off, so the successor's entry is queued and NOTHING is scheduled -- the only
    operator act with that shape.
    """
    code, cp = api(
        "POST", f"/projects/{project}/conversations/{conversation}/checkpoint", {}, timeout=420
    )
    if code != 201:
        show(f"checkpoint {label}", code, cp)
        return None, None
    code, co = api("POST", f"/projects/{project}/checkpoints/{cp['id']}/cutover", {})
    if code != 200:
        show(f"cutover {label}", code, co)
        return None, None
    return co.get("successor_conversation_id"), co.get("queue_entry_id")


def main():
    step("0. the throwaway project, its agent, and a cheap runner")
    make_repo()
    project = ensure_project()
    if project in FORBIDDEN:
        sys.exit(f"REFUSING: {project} is a protected project")
    runner = ensure_runner(project)
    ensure_agent(project, runner)
    # Auto-continue OFF is load-bearing: it is what makes a cutover park an entry instead of
    # starting it, which is the only way to hold two entries queued with the agent idle.
    code, _ = api(
        "PUT",
        f"/projects/{project}/settings",
        {"checkpoint_runner_id": runner, "checkpoint_auto_continue": False},
    )
    print(f"  project {project}, agent {AGENT}, runner {runner}")
    check("auto-continue is off", code < 300, str(code))

    step("1. two real turns, so two conversations have something to checkpoint")
    conv_x = one_turn(project, "Say the single word EX and stop.")
    conv_y = one_turn(project, "Say the single word WHY and stop.")
    check(
        "two distinct conversations ran",
        bool(conv_x and conv_y and conv_x != conv_y),
        f"{conv_x} / {conv_y}",
    )
    if not (conv_x and conv_y and conv_x != conv_y):
        return summarise()

    step("2. park the OLDER entry -- cut over X, auto-continue off")
    succ_x, entry_x = park_a_queued_entry(project, conv_x, "X")
    check(
        "X cut over to a successor holding a queued entry",
        bool(succ_x and entry_x),
        f"{succ_x} / {entry_x}",
    )
    check(
        "nothing started -- the agent is idle with input queued",
        agent_status(project) != "running",
        agent_status(project),
    )

    step("3. park the NEWER entry -- cut over Y, auto-continue off")
    succ_y, entry_y = park_a_queued_entry(project, conv_y, "Y")
    check(
        "Y cut over to a successor holding a queued entry",
        bool(succ_y and entry_y),
        f"{succ_y} / {entry_y}",
    )
    if not (succ_x and succ_y):
        return summarise()

    parked = [(e.get("id"), e.get("conversation_id")) for e in queued(project)]
    check(
        "both entries are queued at once, X's first",
        parked == [(entry_x, succ_x), (entry_y, succ_y)],
        str(parked),
    )

    step("4. press Continue on the NEWER successor -- every UI gate satisfied")
    print(f"  pressing on {succ_y}, whose own entry {entry_y} is queued")
    print(f"  while {succ_x}'s entry {entry_x} arrived first")
    code, b = api("POST", f"/projects/{project}/conversations/{succ_y}/continue", {}, timeout=60)
    show("continue", code, b)
    check("returns exactly 200", code == 200, str(code))
    check(
        "the answer names the conversation the operator pressed",
        b.get("conversation_id") == succ_y,
        repr(b.get("conversation_id")),
    )
    check(
        "F131: it does NOT report started against a conversation that did not start",
        b.get("started") is False,
        repr(b.get("started")),
    )
    check(
        "F131: it names the conversation that actually began",
        b.get("started_conversation_id") == succ_x,
        repr(b.get("started_conversation_id")),
    )
    check(
        "F131: and says this conversation's input is waiting behind other input",
        b.get("waiting_reason") == "this conversation's input is waiting behind other input",
        repr(b.get("waiting_reason")),
    )

    step("5. the waiting answer is only true if the input really is still waiting")
    # Measured at the instant of the press. The queue is *supposed* to keep moving: when the run
    # that did start ends, the Hub re-drains and delivers this entry. Asserting "no run for the
    # pressed conversation" after waiting for idle therefore fails on correct behaviour -- which
    # is what the first version of this drive did, and what step 6 now asserts on purpose.
    left = [(e.get("id"), e.get("conversation_id")) for e in queued(project)]
    check("the pressed conversation's entry is STILL queued", (entry_y, succ_y) in left, str(left))
    check("the older entry was consumed", (entry_x, succ_x) not in left, str(left))
    check(
        "a run exists for the conversation that was NOT pressed",
        bool(runs_for(project, succ_x)),
        str(runs_for(project, succ_x)),
    )
    check(
        "and none yet for the conversation that was pressed",
        not runs_for(project, succ_y),
        str(runs_for(project, succ_y)),
    )

    step("6. and the wait ends -- the re-drain delivers it next, which is why it was true")
    wait_idle(project)
    wait_idle(project)
    check(
        "the input that was waiting behind other input was delivered after it",
        bool(runs_for(project, succ_y)),
        str(runs_for(project, succ_y)),
    )
    still = [(e.get("id"), e.get("conversation_id")) for e in queued(project)]
    check("nothing is left queued", not still, str(still))

    return summarise()


if __name__ == "__main__":
    ok = False
    try:
        ok = main()
    finally:
        print(json.dumps({"drive": "f131", "passed": bool(ok)}))
    sys.exit(0 if ok else 1)
