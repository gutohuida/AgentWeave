"""SWEEP ROW 13 — CHECKPOINTS. The warning, the dismissal, and the agent plane.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 t_sweep_row13_checkpoints.py
    AW_HUB=... AW_KEY=... py -3.11 t_sweep_row13_checkpoints.py --teardown

**Prior coverage was read first and is deliberately not re-ploughed.** Four harnesses already
drive checkpoints, and between them they own the generate/render/cutover/continue spine:

* `t_row15_cutover.py` — one checkpoint end to end: generate, render, cut over, continue.
* `t_row15_chain.py` — lineage: `previous_checkpoint_id`, `lineage_id`, an empty span (F130).
* `t_continue_branches.py` — `continue`'s refusal and waiting branches.
* `t_f131_start_reported_to_its_own_input.py` — cutover queues without scheduling.

What **none** of them touches, and what this file is about:

* **The warning, and the dismissal.** `POST /conversations/{id}/dismiss-checkpoint-warning` has
  never been called with anything but a nonexistent conversation id (`t_sweep_conversations.py:92`
  probes its 404 and nothing else). The whole `due -> dismissed -> final` state machine
  (`checkpoint_trigger.py:192-220`, `checkpoints.py:215`) is undriven.
* **The agent plane.** `list_checkpoints`, `read_checkpoint` and `recall` are agent-callable MCP
  tools over `agent_actions.py:390-434`, gated by `checkpoint_access.may_read_checkpoint` /
  `may_recall` — capability ∩ visibility. F88 measured that intersection closed on the visibility
  side and it was repaired by defaulting `visibility` to `project`. Nothing has driven it since,
  and no harness anywhere sets `can_read_checkpoints` or `can_recall` (grepped: zero hits under
  `scripts/drive`).
* **`submit_checkpoint_notes`.** The tool promises the notes reach "the next checkpoint of this
  conversation". Nothing has ever checked that they arrive.

One project, three agents (`author`, `peer`, `control`), plus a second project for isolation. Ten
real `claude-haiku-4-5` turns and four checkpoint generations per run — the agent plane is
reachable no other way, because `get_agent_actor` resolves a credential whose plaintext exists
only in the spawned process.

`control` is not decoration. Legs 3-5 measure what a dismissal leaves behind, which on its own
says only that a code path differs; leg 12 runs the identical conversation with no dismissal, so
the claim becomes a measured divergence between two operators rather than a reading of the source.

**Agent tool results are read from the Hub's own record, not from the agent's account of it.**
The first version of this file asked each agent-plane turn to transcribe its tool results into
`submit_checkpoint_notes`; one turn in three wrote the marker and forgot the transcript, which
made an assertion about a refusal pass on an empty string. `agent_outputs.payload` already stores
every call and its verbatim result under a shared `call_id`, so `tool_calls()` reads that instead.
The notes are still submitted, because leg 9 needs them and `submit_checkpoint_notes` is itself
under test.

No job is created, so there is nothing to leave enabled. Both fixture projects are created by this
script — including `git init` and an initial commit, without which no turn can run at all — and
removed by `--teardown`.
"""

import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

HUB = os.environ.get("AW_HUB", "")
if ":8000" in HUB or ":8010" in HUB:
    print("REFUSING TO RUN: 8000 is the operator's real usage and 8010 is the other trial Hub.")
    sys.exit(1)

HAIKU = "claude-haiku-4-5-20251001"
DIR = os.environ.get("AW_DRIVE_DIR", "C:\\Users\\huida\\Documents\\aw-drive-row13")
DIR_OTHER = DIR + "-other"
NAME = os.path.basename(DIR.rstrip("\\/"))
NAME_OTHER = os.path.basename(DIR_OTHER.rstrip("\\/"))
AUTHOR = "author"
PEER = "peer"
CONTROL = "control"
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
DB = os.environ.get("AW_DB", os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db"))

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(
        ("  ok   " if cond else "  FAIL ")
        + label
        + (f"  -- {detail}" if detail and not cond else "")
    )


def note(label, value):
    print(f"  ..   {label}: {value}")


def leg(n, title):
    print(f"\n=== LEG {n}: {title}")


# ---------------------------------------------------------------------------- fixture


def find_project(name):
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return next((p["id"] for p in rows if p.get("name") == name), None)


def project_count():
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return len(rows)


def ensure_repo(path):
    """A fixture directory that is a git repository WITH A COMMIT IN IT.

    Copied from `t_sweep_row12_permissions.py`, and not decoration: a project whose repository has
    no commits cannot run a turn — `git worktree add ... HEAD` fails with "invalid reference: HEAD"
    and `POST /agent/trigger` answers an honest 200 with `run_id: null`.
    """
    os.makedirs(path, exist_ok=True)
    run = lambda *a: subprocess.run(a, cwd=path, capture_output=True, text=True)  # noqa: E731
    if run("git", "rev-parse", "--git-dir").returncode != 0:
        run("git", "init")
    if run("git", "rev-parse", "HEAD").returncode != 0:
        with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("row 13 checkpoints fixture" + chr(10))
        run("git", "add", "README.md")
        run("git", "-c", "user.email=drive@local", "-c", "user.name=drive",
            "commit", "-m", "fixture: initial commit so a worktree can be added")
    head = run("git", "rev-parse", "--short", "HEAD")
    print(f"fixture repo {path} -> HEAD {head.stdout.strip() or head.stderr.strip()}")


def ensure_project(path, name):
    found = find_project(name)
    if found:
        return found
    ensure_repo(path)
    code, body = api("POST", "/projects/open", {"path": path, "name": name})
    if code >= 300:
        sys.exit(f"could not open project {name}: {code} {body}")
    return body["id"]


def ensure_runner(project):
    _, body = api("GET", f"/projects/{project}/runners")
    rows = body if isinstance(body, list) else (body or {}).get("runners") or []
    for r in rows:
        if r.get("name") == "Haiku (cheap)":
            return r["id"]
    code, body = api(
        "POST",
        f"/projects/{project}/runners",
        {"name": "Haiku (cheap)", "cli": "claude", "model": HAIKU},
    )
    if code >= 300:
        sys.exit(f"could not create runner: {code} {body}")
    return body["id"]


def ensure_agent(project, name, runner):
    code, _ = api("POST", f"/projects/{project}/agents", {"name": name, "runner_id": runner})
    if code < 300:
        return name
    _, body = api("GET", f"/projects/{project}/agents")
    rows = body if isinstance(body, list) else (body or {}).get("agents") or []
    if any(a.get("name") == name for a in rows):
        return name
    sys.exit(f"could not create or find agent {name}: {body}")


def teardown():
    for name in (NAME, NAME_OTHER):
        pid = find_project(name)
        if pid:
            code, _ = api("DELETE", f"/projects/{pid}")
            print(f"deleted {name} ({pid}) -> {code}")
    for path in (DIR, DIR_OTHER):
        if os.path.isdir(path):
            # `ignore_errors=True` alone leaves `.git` behind on Windows: git marks loose objects
            # read-only and `os.remove` raises on them. Clear the bit and retry.
            def _force(func, target, _exc):
                os.chmod(target, stat.S_IWRITE)
                func(target)

            shutil.rmtree(path, onerror=_force)
            print(f"removed {path} -> exists={os.path.isdir(path)}")
    print(f"projects now: {project_count()}")


if "--teardown" in sys.argv:
    teardown()
    sys.exit(0)


P = ensure_project(DIR, NAME)
P2 = ensure_project(DIR_OTHER, NAME_OTHER)
RUNNER = ensure_runner(P)
ensure_agent(P, AUTHOR, RUNNER)
ensure_agent(P, PEER, RUNNER)
ensure_agent(P, CONTROL, RUNNER)
A = f"/projects/{P}"
A2 = f"/projects/{P2}"
print(f"fixture: {NAME}={P}  other={NAME_OTHER}={P2}  agents={AUTHOR},{PEER},{CONTROL}  tag={TAG}")


# ---------------------------------------------------------------------------- helpers


def db_rows(sql, args=()):
    """Read the Hub's database read-only. Observation only; the Hub owns this file."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    try:
        cur = con.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        con.close()


def db_run(run_id):
    rows = db_rows("SELECT id, status, exit_code, error FROM runs WHERE id = ?", (run_id,))
    return rows[0] if rows else None


def settings(**fields):
    code, body = api("PUT", f"{A}/settings", fields)
    return code, body


def conversations(agent):
    code, body = api("GET", f"{A}/agent/{agent}/conversations")
    rows = body if isinstance(body, list) else (body or {}).get("conversations") or []
    return code, rows


def newest_conversation(agent):
    _, rows = conversations(agent)
    return rows[0] if rows else None


def conversation(agent, conv_id):
    _, rows = conversations(agent)
    return next((r for r in rows if r.get("id") == conv_id), None)


def warning_of(agent, conv_id):
    row = conversation(agent, conv_id)
    return (row or {}).get("checkpoint_warning", "<no such conversation>")


def checkpoints_of(conv_id):
    code, body = api("GET", f"{A}/conversations/{conv_id}/checkpoints")
    rows = body if isinstance(body, list) else (body or {}).get("checkpoints") or []
    return code, rows


def notes_for(conv_id):
    return db_rows(
        "SELECT id, conversation_id, agent, intent, suspicions, warnings, "
        "consumed_by_checkpoint_id, created_at FROM checkpoint_notes "
        "WHERE conversation_id = ? ORDER BY created_at, id",
        (conv_id,),
    )


def run_turn(agent, message, *, wait=420, conversation_id=None):
    """One real agent turn, waited out on the run row. Returns (run_id, status)."""
    payload = {"agent": agent, "message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    code, body = api("POST", f"{A}/agent/trigger", payload)
    if code not in (200, 201, 202):
        return None, f"trigger {code} {str(body)[:200]}"
    run_id = body.get("run_id") or body.get("id")
    if not run_id:
        return None, f"no run started: {json.dumps(body)[:300]}"
    deadline = time.time() + wait
    row = None
    while time.time() < deadline:
        time.sleep(6)
        row = db_run(run_id)
        if row and row["status"] not in ("running", "queued", "starting"):
            return run_id, row["status"]
    return run_id, f"timeout(last={(row or {}).get('status')})"


def wait_for(label, predicate, timeout=90, interval=3):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    print(f"  ..   TIMED OUT waiting for {label} after {timeout}s")
    return None


def tool_calls(run_id):
    """Every tool this run made, paired with what the Hub recorded coming back.

    THE FIRST VERSION OF THIS HARNESS ASKED THE AGENT TO TRANSCRIBE ITS OWN TOOL RESULTS into
    `submit_checkpoint_notes`, and one turn in three wrote the marker and forgot the transcript —
    which made an assertion about a refusal pass on an empty string. `agent_outputs.payload`
    already holds the verbatim result under the same `call_id` as the call, so this reads the
    Hub's record instead of the model's account of it.
    """
    rows = db_rows(
        "SELECT kind, payload FROM agent_outputs WHERE run_id = ? AND kind IN "
        "('tool_use', 'tool_result') ORDER BY timestamp, id",
        (run_id,),
    )
    calls, results = {}, {}
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except ValueError:
            continue
        if row["kind"] == "tool_use":
            calls[payload.get("call_id")] = payload
        else:
            results[payload.get("call_id")] = payload
    out = []
    for call_id, call in calls.items():
        result = results.get(call_id) or {}
        out.append(
            {
                "tool": (call.get("tool") or "").replace("mcp__agentweave__", ""),
                "input": call.get("input") or "",
                "output": result.get("output") or "",
                "is_error": bool(result.get("is_error")),
            }
        )
    return out


def call_of(calls, tool):
    """The first recorded call to `tool`, or an empty dict."""
    return next((c for c in calls if c["tool"] == tool), {})


def agent_plane_turn(agent, conv_id, instruction, marker):
    """One real turn that calls the agent-plane tools, plus a note so leg 9 has a fixture.

    The note is no longer the evidence — `tool_calls` is. It is still asked for, because the
    notes leg needs one per turn and because `submit_checkpoint_notes` is itself under test.
    """
    message = (
        f"{instruction}" + (chr(10) * 2)
        + f"Then call submit_checkpoint_notes exactly once with intent '{marker}', an empty list "
        f"for suspicions and an empty list for warnings. Do nothing else, and do not read or "
        f"write any file."
    )
    run_id, status = run_turn(agent, message, conversation_id=conv_id)
    return run_id, status, tool_calls(run_id)


# =============================================================================================
leg(1, "The router before anything exists — shapes and refusals")

code, rows = checkpoints_of("conv-nosuchthing")
ok("listing checkpoints of an unknown conversation is a 404", code == 404, str(code))
code, _ = api("GET", f"{A}/checkpoints/cp-nosuchthing/rendered")
ok("rendering an unknown checkpoint is a 404", code == 404, str(code))
code, _ = api("POST", f"{A}/conversations/conv-nosuchthing/dismiss-checkpoint-warning")
ok("dismissing the warning of an unknown conversation is a 404", code == 404, str(code))
code, _ = api("POST", f"{A}/checkpoints/cp-nosuchthing/cutover", {})
ok("cutting over an unknown checkpoint is a 404", code == 404, str(code))

# The dismissal route takes NO body, so a bodyless call is its NORMAL call and is deliberately
# kept out of this probe — iteration 8's lesson. What is probed here is the one mutating route in
# this router that does take a body.
code, _ = api("POST", f"{A}/checkpoints/cp-nosuchthing/cutover")
ok("  ... and cutover with no body at all is still a 404, not a 500", code == 404, str(code))


# =============================================================================================
leg(2, "A conversation crosses its threshold — the warning nobody has driven")

code, body = settings(
    checkpoint_runner_id=RUNNER,
    checkpoint_mode="offered",
    checkpoint_threshold_mode="tokens",
    checkpoint_threshold_value=2000,
    checkpoint_notes_value=None,
)
ok("project configured: offered mode, tokens threshold 2000", code == 200, f"{code} {str(body)[:200]}")
note("checkpoint_mode", (body or {}).get("checkpoint_mode"))

run_id, status = run_turn(
    AUTHOR,
    f"Reply with exactly the words 'row13 author turn one {TAG}' and nothing else. "
    f"Do not use any tool and do not read or write any file.",
)
note("author turn 1", f"{run_id} -> {status}")
ok("the author's first turn completed", status == "completed", str(status))

conv = newest_conversation(AUTHOR)
CONV_A = (conv or {}).get("id")
ok("the turn opened a conversation", bool(CONV_A), str(conv)[:200])
note("author conversation", CONV_A)
note("context reading", (conv or {}).get("context_usage"))

warn = wait_for(
    "checkpoint_warning to become due",
    lambda: warning_of(AUTHOR, CONV_A) if warning_of(AUTHOR, CONV_A) else None,
    timeout=60,
)
ok(
    "crossing the threshold in `offered` mode sets the conversation's warning to `due`",
    warning_of(AUTHOR, CONV_A) == "due",
    repr(warning_of(AUTHOR, CONV_A)),
)
code, rows = checkpoints_of(CONV_A)
ok(
    "  ... and `offered` warns rather than spending a model call: no checkpoint exists yet",
    code == 200 and len(rows) == 0,
    f"{code} {len(rows)}",
)


# =============================================================================================
leg(3, "The dismissal, and what it silences")

code, body = api("POST", f"{A}/conversations/{CONV_A}/dismiss-checkpoint-warning")
ok("dismissing a due warning answers 200", code == 200, f"{code} {str(body)[:200]}")
ok(
    "  ... and reports the state it wrote",
    isinstance(body, dict) and body.get("checkpoint_warning") == "dismissed",
    str(body)[:200],
)
ok(
    "  ... which the conversation surface then reads back",
    warning_of(AUTHOR, CONV_A) == "dismissed",
    repr(warning_of(AUTHOR, CONV_A)),
)

code, body = api("POST", f"{A}/conversations/{CONV_A}/dismiss-checkpoint-warning")
ok("dismissing twice is idempotent rather than a conflict", code == 200, f"{code} {str(body)[:160]}")

run_id, status = run_turn(
    AUTHOR,
    f"Reply with exactly the words 'row13 author turn two {TAG}' and nothing else. "
    f"Do not use any tool and do not read or write any file.",
    conversation_id=CONV_A,
)
note("author turn 2", f"{run_id} -> {status}")
ok(
    "a dismissal is not re-asked on the next turn — the warning stays dismissed",
    warning_of(AUTHOR, CONV_A) == "dismissed",
    repr(warning_of(AUTHOR, CONV_A)),
)
code, rows = checkpoints_of(CONV_A)
ok(
    "  ... and still nothing was generated behind the operator's back",
    code == 200 and len(rows) == 0,
    f"{code} {len(rows)}",
)


# =============================================================================================
leg(4, "The operator takes the checkpoint anyway — and what the dismissal leaves behind")

code, cp = api("POST", f"{A}/conversations/{CONV_A}/checkpoint", {}, timeout=420)
ok("taking a checkpoint by hand answers 201", code == 201, f"{code} {str(cp)[:300]}")
CP_A = (cp or {}).get("id") if isinstance(cp, dict) else None
note("checkpoint", CP_A)
if isinstance(cp, dict):
    note("status/probe", f"{cp.get('status')} / {cp.get('probe_status')}")
    ok(
        "the checkpoint is born `project`-visible — the repair F88 asked for",
        cp.get("visibility") == "project",
        repr(cp.get("visibility")),
    )
    ok(
        "  ... and it says so to the operator, who has no way to change it",
        "visibility" in cp,
        str(list(cp))[:200],
    )
    ok(
        "the body was written",
        cp.get("status") == "ready" and bool(cp.get("body")),
        f"{cp.get('status')} body={len(cp.get('body') or '')}",
    )
    ok(
        "a checkpoint taken with no agent notes says so in its own body",
        "contributed no notes" in (cp.get("body") or ""),
        (cp.get("body") or "")[:200],
    )

after = warning_of(AUTHOR, CONV_A)
note("checkpoint_warning after the operator took the checkpoint", repr(after))
ok(
    "taking the checkpoint answers the warning it was asked about",
    after is None,
    f"still {after!r} -- checkpoints.py:190 clears only `due` and `final`, never `dismissed`",
)

run_id, status = run_turn(
    AUTHOR,
    f"Reply with exactly the words 'row13 author turn three {TAG}' and nothing else. "
    f"Do not use any tool and do not read or write any file.",
    conversation_id=CONV_A,
)
note("author turn 3", f"{run_id} -> {status}")
time.sleep(8)
later = warning_of(AUTHOR, CONV_A)
note("checkpoint_warning one turn after the checkpoint", repr(later))
ok(
    "having taken one checkpoint, the conversation is offered another when it crosses again",
    later == "due",
    f"{later!r} -- a conversation dismissed once is never offered a checkpoint again",
)


# =============================================================================================
leg(5, "A dismissal of a warning that was never shown")

code, _ = settings(checkpoint_threshold_mode="tokens", checkpoint_threshold_value=900000)
ok("threshold raised out of reach so the peer's first turn cannot cross it", code == 200, str(code))

run_id, status = run_turn(
    PEER,
    f"Reply with exactly the words 'row13 peer turn one {TAG}' and nothing else. "
    f"Do not use any tool and do not read or write any file.",
)
note("peer turn 1", f"{run_id} -> {status}")
conv = newest_conversation(PEER)
CONV_P = (conv or {}).get("id")
ok("the peer opened its own conversation", bool(CONV_P), str(conv)[:200])
note("peer conversation", CONV_P)
ok(
    "  ... which has never been warned",
    warning_of(PEER, CONV_P) is None,
    repr(warning_of(PEER, CONV_P)),
)

code, body = api("POST", f"{A}/conversations/{CONV_P}/dismiss-checkpoint-warning")
note("dismissing a warning that was never shown", f"{code} {str(body)[:160]}")
ok(
    "dismissing a warning that does not exist is refused rather than recorded",
    code >= 400,
    f"{code} -- the route writes `dismissed` with no guard (checkpoints.py:244)",
)

code, _ = settings(checkpoint_threshold_mode="tokens", checkpoint_threshold_value=2000)
ok("threshold lowered back so the next peer turn must cross it", code == 200, str(code))
run_id, status = run_turn(
    PEER,
    f"Reply with exactly the words 'row13 peer turn two {TAG}' and nothing else. "
    f"Do not use any tool and do not read or write any file.",
    conversation_id=CONV_P,
)
note("peer turn 2", f"{run_id} -> {status}")
time.sleep(8)
peer_warn = warning_of(PEER, CONV_P)
note("peer checkpoint_warning after crossing the threshold", repr(peer_warn))
ok(
    "the peer is warned when it crosses its threshold for the first time",
    peer_warn == "due",
    f"{peer_warn!r} -- a pre-emptive dismissal silences a warning never shown",
)


# =============================================================================================
leg(6, "The agent plane, ungranted — what a peer may see of its neighbour's checkpoint")

# "Closed by default" is asserted on an agent created RIGHT HERE, not on `peer`.
#
# THIS FILE WAS NOT RE-RUNNABLE UNTIL THIS CHANGE, and the second run on the first's state is what
# caught it: legs 7 and 8 grant `peer` both capabilities and nothing ever took them back, so on the
# next run `peer` arrived already granted and the default-closed assertion failed on the harness's
# own leftovers. Two repairs, and both matter: a throwaway agent whose defaults are genuinely
# fresh every time, and an explicit reset of `peer` so leg 6 tests the ungranted path rather than
# whatever the last run left behind.
PROBE = f"fresh-{TAG}"
ensure_agent(P, PROBE, RUNNER)


def grants_of(name):
    _, rows = api("GET", f"{A}/agents")
    rows = rows if isinstance(rows, list) else (rows or {}).get("agents") or []
    row = next((a for a in rows if a.get("name") == name), {})
    return {k: row.get(k) for k in ("can_read_checkpoints", "can_recall")}


probe_grants = grants_of(PROBE)
note(f"grants on a brand-new agent ({PROBE})", probe_grants)
ok(
    "both reader grants are closed by default on a newly created agent",
    probe_grants.get("can_read_checkpoints") in (False, None)
    and probe_grants.get("can_recall") in (False, None),
    str(probe_grants),
)

before_reset = grants_of(PEER)
note("peer grants as this run found them", before_reset)
for grant in ("can_read_checkpoints", "can_recall"):
    api("PATCH", f"{A}/agents/{PEER}", {grant: False})
after_reset = grants_of(PEER)
ok(
    "peer is put back to ungranted before the ungranted leg is driven",
    after_reset.get("can_read_checkpoints") in (False, None)
    and after_reset.get("can_recall") in (False, None),
    str(after_reset),
)
ok(
    "  ... and a grant can be revoked, not only conferred",
    all(v in (False, None) for v in after_reset.values()),
    f"{before_reset} -> {after_reset}",
)

CITED = None
if isinstance(cp, dict) and cp.get("citations"):
    CITED = (cp["citations"][0] or {}).get("id")
note("an observation the author's checkpoint cites", CITED)

ASK_ALL_THREE = (
    f"Call list_checkpoints() with no arguments. Then call read_checkpoint('{CP_A}'). "
    + (f"Then call recall('{CITED}'). " if CITED else "")
)

run_id, status, calls = agent_plane_turn(PEER, CONV_P, ASK_ALL_THREE, f"UNGRANTED-{TAG}")
note("peer ungranted run", f"{run_id} -> {status}")
note("tools it called", [c["tool"] for c in calls])
listed = call_of(calls, "list_checkpoints")
read = call_of(calls, "read_checkpoint")
print("--- ungranted, as the Hub recorded it ---")
for c in calls:
    print(f"  {c['tool']}({c['input']}) -> {'ERROR ' if c['is_error'] else ''}{c['output'][:300]}")

ok("the ungranted peer did call list_checkpoints", bool(listed), str([c["tool"] for c in calls]))
ok(
    "an ungranted peer's list is empty — the author's checkpoint is not in it",
    bool(listed) and CP_A not in listed["output"],
    listed.get("output", "<no call>")[:300],
)
ok("  ... and it did call read_checkpoint on the id it was given", bool(read), str(read)[:200])
ok(
    "  ... which is refused, indistinguishably from an id that does not exist",
    bool(read) and read["is_error"] and "(404)" in read["output"],
    read.get("output", "<no call>")[:300],
)
if CITED:
    rc = call_of(calls, "recall")
    ok(
        "  ... and recall is refused too",
        bool(rc) and rc["is_error"] and "(404)" in rc["output"],
        rc.get("output", "<no call>")[:300],
    )


# =============================================================================================
leg(7, "The same peer, granted read but not recall — the split the design insists on")

code, body = api("PATCH", f"{A}/agents/{PEER}", {"can_read_checkpoints": True})
ok("the operator can grant checkpoint reading", code == 200, f"{code} {str(body)[:200]}")
note("grants now", {k: (body or {}).get(k) for k in ("can_read_checkpoints", "can_recall")})

run_id, status, calls = agent_plane_turn(PEER, CONV_P, ASK_ALL_THREE, f"READONLY-{TAG}")
note("peer read-granted run", f"{run_id} -> {status}")
listed = call_of(calls, "list_checkpoints")
read = call_of(calls, "read_checkpoint")
print("--- read-granted, as the Hub recorded it ---")
for c in calls:
    print(f"  {c['tool']}({c['input']}) -> {'ERROR ' if c['is_error'] else ''}{c['output'][:400]}")

ok(
    "a granted peer now finds the author's checkpoint by listing",
    bool(listed) and CP_A in listed["output"],
    listed.get("output", "<no call>")[:400],
)
ok(
    "  ... marked as somebody else's, so the peer can tell whose it is",
    '"yours":false' in (listed.get("output") or "").replace(" ", ""),
    listed.get("output", "<no call>")[:400],
)
ok(
    "  ... and reading it by id now succeeds",
    bool(read) and not read["is_error"] and CP_A in read["output"],
    read.get("output", "<no call>")[:400],
)
if CITED:
    rc = call_of(calls, "recall")
    ok(
        "  ... but summary access is not transcript access: recall is still refused",
        bool(rc) and rc["is_error"] and "(404)" in rc["output"],
        rc.get("output", "<no call>")[:300],
    )
    ok(
        "  ... while the checkpoint it just read names the very id it may not open",
        bool(read) and CITED in (read.get("output") or ""),
        read.get("output", "<no call>")[-400:],
    )


# =============================================================================================
leg(8, "Recall granted — the intersection the operator actually opens")

if CITED:
    code, body = api("PATCH", f"{A}/agents/{PEER}", {"can_recall": True})
    ok("the operator can grant recall separately", code == 200, f"{code} {str(body)[:200]}")

    run_id, status, calls = agent_plane_turn(
        PEER, CONV_P, f"Call recall('{CITED}') first. ", f"RECALL-{TAG}"
    )
    note("peer recall-granted run", f"{run_id} -> {status}")
    rc = call_of(calls, "recall")
    print("--- recall-granted, as the Hub recorded it ---")
    for c in calls:
        print(f"  {c['tool']}({c['input']}) -> {'ERROR ' if c['is_error'] else ''}{c['output'][:400]}")
    ok(
        "with both grants, a cited observation comes back",
        bool(rc) and not rc["is_error"],
        rc.get("output", "<no call>")[:300],
    )
    ok(
        "  ... verbatim, carrying the author's own recorded text",
        f"row13 author turn one {TAG}" in (rc.get("output") or ""),
        rc.get("output", "<no call>")[:400],
    )
else:
    note("recall leg skipped", "the checkpoint cited no observations")


# =============================================================================================
leg(9, "The notes the agent left — do they reach the checkpoint they were written for?")

rows = notes_for(CONV_P)
note("notes rows on the peer's conversation", len(rows))
ok("every agent-plane turn left a durable note", len(rows) >= 2, str(len(rows)))
unconsumed = [r for r in rows if not r["consumed_by_checkpoint_id"]]
ok(
    "  ... and none has been consumed yet, because no checkpoint has been taken here",
    len(unconsumed) == len(rows),
    f"{len(unconsumed)}/{len(rows)}",
)

code, cp_p = api("POST", f"{A}/conversations/{CONV_P}/checkpoint", {}, timeout=420)
ok("the peer's conversation checkpoints", code == 201, f"{code} {str(cp_p)[:300]}")
CP_P = (cp_p or {}).get("id") if isinstance(cp_p, dict) else None
note("peer checkpoint", CP_P)

after_rows = notes_for(CONV_P)
consumed = [r for r in after_rows if r["consumed_by_checkpoint_id"] == CP_P]
ok(
    "the checkpoint takes the agent's notes and records that it did",
    len(consumed) == 1,
    f"{[(r['id'], r['consumed_by_checkpoint_id']) for r in after_rows]}",
)
ok(
    "  ... exactly one, so earlier notes are not silently re-read",
    len([r for r in after_rows if r["consumed_by_checkpoint_id"]]) == 1,
    str([(r["id"], r["consumed_by_checkpoint_id"]) for r in after_rows]),
)
still_unread = [r for r in after_rows if not r["consumed_by_checkpoint_id"]]
note("notes left unconsumed after the checkpoint", [r["id"] for r in still_unread])

body_p = (cp_p or {}).get("body") or "" if isinstance(cp_p, dict) else ""
ok(
    "a checkpoint written WITH notes does not claim the agent contributed none",
    "contributed no notes" not in body_p,
    body_p[:300],
)
newest_marker = (after_rows[-1]["intent"] if after_rows else "")[:16]
note("the marker the newest note opens with", newest_marker)
ok(
    "the note it took is the NEWEST one, not the oldest still waiting",
    len(consumed) == 1 and consumed[0]["id"] == after_rows[-1]["id"],
    f"took {[r['id'] for r in consumed]}, newest is {after_rows[-1]['id'] if after_rows else None}",
)

# `pending_notes` takes the most recent UNCONSUMED note. Three were submitted and one was taken,
# so two older ones are still sitting there — and the question this asks is what the NEXT
# checkpoint does with them. If it takes one, a later checkpoint is briefed with notes written
# before the checkpoint that preceded it.
if len(still_unread) >= 1:
    code, cp_p2 = api("POST", f"{A}/conversations/{CONV_P}/checkpoint", {}, timeout=420)
    ok("a second checkpoint on the same conversation is taken", code == 201, f"{code}")
    CP_P2 = (cp_p2 or {}).get("id") if isinstance(cp_p2, dict) else None
    note("second peer checkpoint", CP_P2)
    second_rows = notes_for(CONV_P)
    took = [r for r in second_rows if r["consumed_by_checkpoint_id"] == CP_P2]
    note("what the second checkpoint consumed", [(r["id"], r["intent"][:16]) for r in took])
    body_p2 = (cp_p2 or {}).get("body") or "" if isinstance(cp_p2, dict) else ""
    ok(
        "the second checkpoint is not briefed with notes written before the first",
        len(took) == 0,
        f"it took {[(r['id'], r['intent'][:16]) for r in took]}, all submitted before {CP_P}",
    )
    note(
        "does the second body still claim no notes?",
        "yes" if "contributed no notes" in body_p2 else "no",
    )
    note("notes still unconsumed after two checkpoints",
         [r["id"] for r in second_rows if not r["consumed_by_checkpoint_id"]])


# =============================================================================================
leg(10, "Isolation — the other project cannot reach any of it")

code, _ = api("GET", f"{A2}/conversations/{CONV_A}/checkpoints")
ok("the other project cannot list this conversation's checkpoints", code == 404, str(code))
code, _ = api("GET", f"{A2}/checkpoints/{CP_A}/rendered")
ok("  ... nor render its checkpoint", code == 404, str(code))
code, _ = api("POST", f"{A2}/conversations/{CONV_A}/dismiss-checkpoint-warning")
ok("  ... nor dismiss its warning", code == 404, str(code))
code, _ = api("POST", f"{A2}/conversations/{CONV_A}/checkpoint", {}, timeout=120)
ok("  ... nor take a checkpoint of it", code == 404, str(code))
code, _ = api("POST", f"{A2}/checkpoints/{CP_A}/cutover", {})
ok("  ... nor cut over to its successor", code == 404, str(code))

code, rows = checkpoints_of(CONV_A)
ok(
    "and after all that the author's checkpoint is still the only one on its conversation",
    code == 200 and len(rows) == 1,
    f"{code} {len(rows)}",
)


# =============================================================================================
leg(11, "What the operator's own screens can do with any of this")

import urllib.request  # noqa: E402

def bundle_text():
    url = HUB.rstrip("/") + "/assets/"
    try:
        with urllib.request.urlopen(HUB.rstrip("/") + "/", timeout=20) as r:
            index = r.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return f"<index unreachable: {exc}>"
    out = [index]
    for token in index.split('"'):
        if token.startswith("/assets/") and token.endswith(".js"):
            try:
                with urllib.request.urlopen(HUB.rstrip("/") + token, timeout=40) as r:
                    out.append(r.read().decode("utf-8", "replace"))
            except Exception as exc:  # noqa: BLE001
                out.append(f"<{token} unreachable: {exc}>")
    return "\n".join(out)


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def in_source(needle):
    """How many files under `hub/ui/src` contain `needle` — tests excluded."""
    proc = subprocess.run(
        ["git", "grep", "-l", "-F", needle, "--", "hub/ui/src"],
        cwd=REPO, capture_output=True, text=True,
    )
    return [f for f in proc.stdout.strip().splitlines() if "__tests__" not in f]


SERVED = bundle_text()
note("served bundle size", len(SERVED))

# Matched as a caller writes it, not as a word — D-6's lesson, where measuring the WORD
# `/control` found five comments and would have manufactured a false stale-bundle finding.
for route in ("dismiss-checkpoint-warning", "/checkpoint", "/cutover", "/rendered"):
    files = in_source(route)
    present = route in SERVED
    note(f"`{route}`", f"{len(files)} source file(s), {'in' if present else 'NOT in'} the bundle")
    ok(
        f"the served bundle agrees with the source about `{route}`",
        present == bool(files),
        f"source={files} bundle={present}",
    )

ok(
    "the grant the whole agent plane turns on has an operator control",
    bool(in_source("can_read_checkpoints")),
    "no file under hub/ui/src mentions can_read_checkpoints",
)
note("UI files mentioning can_read_checkpoints", in_source("can_read_checkpoints"))

# THIS ASSERTION USED TO CLAIM A DEFECT AND WAS WRONG. It read that the cut-over banner filters
# on `trigger === 'context_pressure'` while the operator's own button writes `trigger='operator'`,
# and concluded that an operator-taken checkpoint can never be cut over from the app. It can:
# `handleCheckpoint` calls `writeCheckpoint`, which takes the checkpoint AND cuts over in one
# operation (`checkpointOperationStore.ts:70`) without consulting that banner at all. The banner
# is for `automatic` mode, where the Hub generated one unasked and the operator chooses. What is
# asserted now is the fact, not the inference.
note("UI files mentioning context_pressure", in_source("context_pressure"))
ok(
    "the app's own take-a-checkpoint path cuts over directly, without the banner's filter",
    bool(in_source("cutOver")) and "checkpointOperationStore.ts" in " ".join(in_source("cutOver")),
    f"cutOver call sites: {in_source('cutOver')}",
)


# =============================================================================================
leg(12, "The control — the same conversation, never dismissed")

# Legs 3-5 measured what a dismissal leaves behind. On its own that is only half an argument: it
# says a code path differs, not that two operators diverge. This is the other half — an identical
# conversation that reaches `due`, is checkpointed WITHOUT the operator ever pressing Dismiss, and
# then crosses again.

run_id, status = run_turn(
    CONTROL,
    f"Reply with exactly the words 'row13 control turn one {TAG}' and nothing else. "
    f"Do not use any tool and do not read or write any file.",
)
note("control turn 1", f"{run_id} -> {status}")
conv = newest_conversation(CONTROL)
CONV_C = (conv or {}).get("id")
ok("the control opened its own conversation", bool(CONV_C), str(conv)[:200])
note("control conversation", CONV_C)
time.sleep(8)
ok(
    "the control is warned exactly as the author was",
    warning_of(CONTROL, CONV_C) == "due",
    repr(warning_of(CONTROL, CONV_C)),
)

code, cp_c = api("POST", f"{A}/conversations/{CONV_C}/checkpoint", {}, timeout=420)
ok(
    "the control's checkpoint is taken — the same button, no dismissal first",
    code == 201,
    f"{code} {str(cp_c)[:200]}",
)
CP_C = (cp_c or {}).get("id") if isinstance(cp_c, dict) else None
after_c = warning_of(CONTROL, CONV_C)
note("control checkpoint_warning after the checkpoint", repr(after_c))
ok(
    "  ... and taking it clears the warning, which is what checkpoints.py:190 promises",
    after_c is None,
    repr(after_c),
)

run_id, status = run_turn(
    CONTROL,
    f"Reply with exactly the words 'row13 control turn two {TAG}' and nothing else. "
    f"Do not use any tool and do not read or write any file.",
    conversation_id=CONV_C,
)
note("control turn 2", f"{run_id} -> {status}")
time.sleep(10)
later_c = warning_of(CONTROL, CONV_C)
note("control checkpoint_warning one turn later", repr(later_c))
ok(
    "the control IS offered a second checkpoint — the author, who dismissed once, never is",
    later_c == "due",
    repr(later_c),
)
note(
    "the divergence, side by side",
    f"author {CONV_A} -> {warning_of(AUTHOR, CONV_A)!r} (never offered again); "
    f"control {CONV_C} -> {later_c!r}",
)


# =============================================================================================
leg(13, "Cutting over to the checkpoint the operator asked for")

# Leg 11 measured that the only cut-over affordance in the app filters on
# `trigger === 'context_pressure'`, and the operator's own button writes `trigger='operator'`.
# This asks the other half of that question: does the BACKEND mind?

note("the control checkpoint's trigger", (cp_c or {}).get("trigger") if isinstance(cp_c, dict) else None)
ok(
    "the operator's own checkpoint is stamped `operator`, not `context_pressure`",
    isinstance(cp_c, dict) and cp_c.get("trigger") == "operator",
    str((cp_c or {}).get("trigger")),
)
code, cut = api("POST", f"{A}/checkpoints/{CP_C}/cutover", {})
note("cutover of an operator-triggered checkpoint", f"{code} {str(cut)[:300]}")
ok(
    "the Hub cuts over to it happily — nothing in the backend distinguishes the trigger",
    code in (200, 201) and isinstance(cut, dict) and bool(cut.get("successor_conversation_id")),
    f"{code} {str(cut)[:300]}",
)
if isinstance(cut, dict) and cut.get("successor_conversation_id"):
    succ = cut["successor_conversation_id"]
    note("successor conversation", succ)
    # `lifecycle=all`, because the default listing excludes archived rows — and the predecessor
    # being archived is exactly what is being asserted.
    _, rows = api("GET", f"{A}/agent/{CONTROL}/conversations?lifecycle=all")
    rows = rows if isinstance(rows, list) else []
    pred = next((r for r in rows if r.get("id") == CONV_C), None)
    ok(
        "  ... and the predecessor is archived, as a cutover promises",
        bool(pred) and bool(pred.get("archived_at")),
        str(pred)[:250],
    )


# =============================================================================================
print("\n" + "=" * 78)
print(f"PASS {len(PASS)}   FAIL {len(FAIL)}")
for f in FAIL:
    print(f"  FAILED: {f}")
print(f"projects: {project_count()}")
